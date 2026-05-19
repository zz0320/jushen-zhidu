from __future__ import annotations

import threading
import urllib.parse
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Generator, Optional

from fastapi import Depends, FastAPI, Form, Request
import httpx
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from .arxiv import FetchResult, fetch_papers_for_date
from .app_settings import qwen_settings_view, resolve_runtime_settings, save_qwen_form
from .config import Settings, get_settings
from .database import build_engine, create_db_and_tables
from .dates import parse_day
from .defaults import init_default_config
from .models import (
    Category,
    DailyReport,
    Keyword,
    KeywordGroup,
    Paper,
    PaperAbstractTranslation,
    PaperFullTextSummary,
    PaperSummary,
)
from .pdf_text import download_paper_pdf, extract_paper_pdf_text
from .reports import export_daily_markdown, render_daily_markdown
from .summaries import (
    generate_abstract_translation,
    generate_daily_report,
    generate_paper_full_text_summary,
    generate_paper_summary,
)
from .text import (
    clean_latex_text,
    clean_translation_title,
    clean_translation_text,
    format_datetime,
    markdown_to_html,
    strip_first_markdown_heading,
    summary_to_html,
)

PACKAGE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
templates.env.filters["clean_latex"] = clean_latex_text
templates.env.filters["translation_title"] = clean_translation_title
templates.env.filters["translation_text"] = clean_translation_text
templates.env.filters["summary_html"] = summary_to_html
templates.env.filters["markdown_html"] = markdown_to_html
templates.env.filters["format_dt"] = format_datetime
templates.env.filters["strip_first_heading"] = strip_first_markdown_heading


def _model_display_name(value: object) -> str:
    raw = str(value or "").strip()
    if not raw or "qwen" in raw.lower():
        return "智能模型"
    return raw


templates.env.filters["model_label"] = _model_display_name


def _latest_day_with_papers(session: Session) -> str:
    latest_paper = session.exec(
        select(Paper).order_by(Paper.fetched_for_date.desc(), Paper.published_at.desc())
    ).first()
    return latest_paper.fetched_for_date if latest_paper else ""


def _day_nav_context(target_day: date, session: Session) -> Dict[str, str]:
    return {
        "previous_day": (target_day - timedelta(days=1)).isoformat(),
        "next_day": (target_day + timedelta(days=1)).isoformat(),
        "latest_day": _latest_day_with_papers(session),
    }


def _redirect(path: str, **query: object) -> RedirectResponse:
    filtered = {key: value for key, value in query.items() if value not in (None, "")}
    suffix = f"?{urllib.parse.urlencode(filtered)}" if filtered else ""
    return RedirectResponse(f"{path}{suffix}", status_code=303)


def _message_from_fetch(result: FetchResult) -> str:
    return (
        f"Fetched {result.fetched}; saved {result.saved}; "
        f"skipped no keyword {result.skipped_no_keyword}; skipped excluded {result.skipped_excluded}."
    )


def _fetch_stage_label(stage: str) -> str:
    labels = {
        "queued": "等待开始",
        "preparing": "准备检索",
        "waiting": "等待 arXiv",
        "requesting": "请求 arXiv",
        "processing": "解析与评分",
        "saving": "写入数据库",
        "complete": "抓取完成",
        "failed": "抓取失败",
    }
    return labels.get(stage, "正在抓取")


def _fetch_stage_message(payload: Dict[str, object]) -> str:
    stage = str(payload.get("stage", "running"))
    page = int(payload.get("page") or 0)
    total_pages = int(payload.get("total_pages") or 0)
    fetched = int(payload.get("fetched") or 0)
    saved = int(payload.get("saved") or 0)
    if stage == "requesting":
        return f"正在请求 arXiv 第 {page}/{total_pages} 页。"
    if stage == "waiting":
        seconds = payload.get("wait_seconds")
        if payload.get("retry"):
            attempt = payload.get("retry_attempt")
            retry_count = payload.get("retry_count")
            return f"arXiv 正在限流，等待 {seconds} 秒后重试（{attempt}/{retry_count}）。"
        return f"按 arXiv API 规范等待 {seconds} 秒后继续下一页。"
    if stage == "processing":
        return f"正在解析论文并计算关键词相关性，已读取 {fetched} 篇。"
    if stage == "saving":
        return f"已保存 {saved} 篇命中论文。"
    if stage == "complete":
        return "抓取完成，正在刷新列表。"
    return "正在准备检索条件。"


def _fetch_error_message(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        if status_code == 429:
            return "arXiv 仍在限流（429），系统已自动等待重试但仍未成功，请稍后再抓取。"
        return f"arXiv 返回 HTTP {status_code}，本次抓取未完成。"
    if isinstance(exc, httpx.TimeoutException):
        return "连接 arXiv 超时，本次抓取未完成。"
    if isinstance(exc, httpx.RequestError):
        return "无法连接 arXiv，请检查网络后重试。"
    return str(exc)


def _summary_stage_label(stage: str) -> str:
    labels = {
        "queued": "等待开始",
        "preparing": "整理材料",
        "downloading": "下载 PDF",
        "extracting": "提取全文",
        "calling_model": "调用智能模型",
        "saving": "保存结果",
        "complete": "生成完成",
        "failed": "生成失败",
    }
    return labels.get(stage, "正在生成")


def _summary_error_message(exc: Exception) -> str:
    message = str(exc)
    if "DASHSCOPE_API_KEY" in message:
        return "尚未配置智能模型 API Key，请先到“智能设置”页面配置。"
    if isinstance(exc, httpx.TimeoutException):
        return "调用智能模型超时，本次生成未完成。"
    if isinstance(exc, httpx.RequestError):
        return "无法连接智能模型 API，请检查网络或 Base URL。"
    return message


def create_app(settings: Optional[Settings] = None, engine: Optional[Engine] = None) -> FastAPI:
    settings = settings or get_settings()
    engine = engine or build_engine(settings)
    create_db_and_tables(engine)
    with Session(engine) as session:
        init_default_config(session)

    app = FastAPI(title="具身智读")
    app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")
    fetch_jobs: Dict[str, Dict[str, object]] = {}
    fetch_jobs_lock = threading.Lock()
    arxiv_fetch_lock = threading.Lock()
    summary_jobs: Dict[str, Dict[str, object]] = {}
    summary_jobs_lock = threading.Lock()

    def get_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    @app.get("/")
    def index(
        request: Request,
        day: Optional[str] = None,
        message: str = "",
        error: str = "",
        session: Session = Depends(get_session),
    ) -> Response:
        target_day = parse_day(day, settings.timezone)
        papers = session.exec(
            select(Paper)
            .where(Paper.fetched_for_date == target_day.isoformat())
            .order_by(Paper.relevance_score.desc(), Paper.published_at.desc())
        ).all()
        paper_ids = [paper.arxiv_id for paper in papers]
        translations = (
            session.exec(select(PaperAbstractTranslation).where(PaperAbstractTranslation.arxiv_id.in_(paper_ids))).all()
            if paper_ids
            else []
        )
        translations_by_paper = {translation.arxiv_id: translation for translation in translations}
        report = session.exec(select(DailyReport).where(DailyReport.report_date == target_day.isoformat())).first()
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "day": target_day.isoformat(),
                "papers": papers,
                "translations_by_paper": translations_by_paper,
                "report": report,
                "message": message,
                "error": error,
                **_day_nav_context(target_day, session),
            },
        )

    @app.post("/fetch")
    def fetch(day: str = Form(...), session: Session = Depends(get_session)) -> RedirectResponse:
        target_day = date.fromisoformat(day)
        try:
            with arxiv_fetch_lock:
                result = fetch_papers_for_date(session, target_day, settings)
        except Exception as exc:  # pragma: no cover - exercised through manual runtime
            return _redirect("/", day=day, error=str(exc))
        return _redirect("/", day=day, message=_message_from_fetch(result))

    @app.post("/fetch-jobs")
    def start_fetch_job(day: str = Form(...)) -> Dict[str, object]:
        job_id = uuid.uuid4().hex
        target_day = date.fromisoformat(day)
        with fetch_jobs_lock:
            fetch_jobs[job_id] = {
                "id": job_id,
                "day": day,
                "redirect_url": f"/?day={urllib.parse.quote(day)}",
                "status": "queued",
                "stage": "queued",
                "stage_label": "等待开始",
                "percent": 1,
                "fetched": 0,
                "saved": 0,
                "skipped_no_keyword": 0,
                "skipped_excluded": 0,
                "page": 0,
                "total_pages": max(1, (settings.arxiv_max_results + settings.arxiv_page_size - 1) // settings.arxiv_page_size),
                "message": "任务已创建，正在排队。",
                "error": "",
            }

        def update_job(**values: object) -> None:
            with fetch_jobs_lock:
                fetch_jobs[job_id].update(values)

        def progress(payload: Dict[str, object]) -> None:
            stage = str(payload.get("stage", "running"))
            progress_values = dict(payload)
            progress_values.update(
                {
                    "status": "running",
                    "stage": stage,
                    "stage_label": _fetch_stage_label(stage),
                    "message": _fetch_stage_message(payload),
                }
            )
            update_job(**progress_values)

        def worker() -> None:
            update_job(status="running", stage="preparing", stage_label="准备检索", message="正在读取分类和关键词配置。", percent=3)
            with Session(engine) as worker_session:
                try:
                    with arxiv_fetch_lock:
                        result = fetch_papers_for_date(
                            worker_session,
                            target_day,
                            settings,
                            progress_callback=progress,
                        )
                    current_count = len(
                        worker_session.exec(
                            select(Paper.arxiv_id).where(Paper.fetched_for_date == target_day.isoformat())
                        ).all()
                    )
                except Exception as exc:  # pragma: no cover - runtime network path
                    error_message = _fetch_error_message(exc)
                    update_job(
                        status="failed",
                        stage="failed",
                        stage_label="抓取失败",
                        percent=100,
                        error=error_message,
                        message=error_message,
                    )
                    return
                update_job(
                    status="completed",
                    stage="complete",
                    stage_label="抓取完成",
                    percent=100,
                    fetched=result.fetched,
                    saved=result.saved,
                    skipped_no_keyword=result.skipped_no_keyword,
                    skipped_excluded=result.skipped_excluded,
                    query=result.query,
                    current_count=current_count,
                    message=_message_from_fetch(result),
                )

        thread = threading.Thread(target=worker, name=f"fetch-arxiv-{job_id}", daemon=True)
        thread.start()
        return {"job_id": job_id}

    @app.get("/fetch-jobs/{job_id}")
    def fetch_job_status(job_id: str) -> Dict[str, object]:
        with fetch_jobs_lock:
            job = fetch_jobs.get(job_id)
            if job is None:
                return {"id": job_id, "status": "not_found", "stage_label": "任务不存在", "percent": 100}
            return dict(job)

    def create_summary_job(kind: str, label: str, redirect_url: str) -> str:
        job_id = uuid.uuid4().hex
        with summary_jobs_lock:
            summary_jobs[job_id] = {
                "id": job_id,
                "kind": kind,
                "status": "queued",
                "stage": "queued",
                "stage_label": "等待开始",
                "percent": 1,
                "label": label,
                "message": "任务已创建，正在排队。",
                "error": "",
                "redirect_url": redirect_url,
            }
        return job_id

    def update_summary_job(job_id: str, **values: object) -> None:
        with summary_jobs_lock:
            summary_jobs[job_id].update(values)

    @app.post("/summary-jobs/papers/{arxiv_id:path}")
    def start_paper_summary_job(arxiv_id: str, force: bool = Form(False)) -> Dict[str, object]:
        redirect_url = f"/papers/{arxiv_id}"
        job_id = create_summary_job("paper", "单篇研究摘要", redirect_url)

        def worker() -> None:
            with Session(engine) as worker_session:
                reused_existing = False
                try:
                    paper = worker_session.get(Paper, arxiv_id)
                    if paper is None:
                        raise ValueError(f"Paper not found: {arxiv_id}")
                    update_summary_job(
                        job_id,
                        status="running",
                        stage="preparing",
                        stage_label=_summary_stage_label("preparing"),
                        percent=12,
                        message="正在整理标题、作者、摘要和关键词命中信息。",
                    )
                    existing = worker_session.exec(select(PaperSummary).where(PaperSummary.arxiv_id == arxiv_id)).first()
                    if existing is not None and not force:
                        summary = existing
                        reused_existing = True
                        update_summary_job(
                            job_id,
                            stage="saving",
                            stage_label=_summary_stage_label("saving"),
                            percent=88,
                            message="已找到现有摘要总结，正在刷新页面。",
                            model=_model_display_name(summary.model),
                        )
                    else:
                        runtime_settings = resolve_runtime_settings(worker_session, settings)
                        update_summary_job(
                            job_id,
                            stage="calling_model",
                            stage_label=_summary_stage_label("calling_model"),
                            percent=38,
                            message="正在调用智能模型生成单篇总结。",
                            model=_model_display_name(runtime_settings.qwen_model),
                        )
                        summary = generate_paper_summary(worker_session, arxiv_id, runtime_settings, force=force)
                    update_summary_job(
                        job_id,
                        stage="saving",
                        stage_label=_summary_stage_label("saving"),
                        percent=88,
                        message="正在保存总结结果。" if force or existing is None else "正在读取已有总结结果。",
                    )
                except Exception as exc:  # pragma: no cover - runtime model path
                    error_message = _summary_error_message(exc)
                    update_summary_job(
                        job_id,
                        status="failed",
                        stage="failed",
                        stage_label=_summary_stage_label("failed"),
                        percent=100,
                        error=error_message,
                        message=error_message,
                    )
                    return
                update_summary_job(
                    job_id,
                    status="completed",
                    stage="complete",
                    stage_label=_summary_stage_label("complete"),
                    percent=100,
                    model=_model_display_name(summary.model),
                    message="已使用现有单篇总结，正在刷新页面。" if reused_existing else "单篇总结已生成，正在刷新页面。",
                )

        threading.Thread(target=worker, name=f"summary-paper-{job_id}", daemon=True).start()
        return {"job_id": job_id}

    @app.post("/summary-jobs/paper-abstract-translation")
    def start_paper_abstract_translation_job(
        arxiv_id: str = Form(...),
        force: bool = Form(False),
    ) -> Dict[str, object]:
        redirect_url = f"/papers/{arxiv_id}"
        job_id = create_summary_job("paper_abstract_translation", "题目与摘要中文翻译", redirect_url)

        def worker() -> None:
            with Session(engine) as worker_session:
                reused_existing = False
                try:
                    paper = worker_session.get(Paper, arxiv_id)
                    if paper is None:
                        raise ValueError(f"Paper not found: {arxiv_id}")
                    update_summary_job(
                        job_id,
                        status="running",
                        stage="preparing",
                        stage_label=_summary_stage_label("preparing"),
                        percent=15,
                        message="正在整理标题和英文摘要。",
                    )
                    existing = worker_session.exec(
                        select(PaperAbstractTranslation).where(PaperAbstractTranslation.arxiv_id == arxiv_id)
                    ).first()
                    if existing is not None and not force and existing.title_content:
                        translation = existing
                        reused_existing = True
                        update_summary_job(
                            job_id,
                            stage="saving",
                            stage_label=_summary_stage_label("saving"),
                            percent=88,
                            message="已找到现有题目与摘要译文，正在刷新页面。",
                            model=_model_display_name(translation.model),
                        )
                    else:
                        runtime_settings = resolve_runtime_settings(worker_session, settings)
                        update_summary_job(
                            job_id,
                            stage="calling_model",
                            stage_label=_summary_stage_label("calling_model"),
                            percent=42,
                            message="正在调用智能模型翻译题目和摘要。",
                            model=_model_display_name(runtime_settings.qwen_model),
                        )
                        translation = generate_abstract_translation(
                            worker_session,
                            arxiv_id,
                            runtime_settings,
                            force=force,
                        )
                    update_summary_job(
                        job_id,
                        stage="saving",
                        stage_label=_summary_stage_label("saving"),
                        percent=88,
                        message="正在保存中文翻译。" if force or not reused_existing else "正在读取已有中文翻译。",
                    )
                except Exception as exc:  # pragma: no cover - runtime model path
                    error_message = _summary_error_message(exc)
                    update_summary_job(
                        job_id,
                        status="failed",
                        stage="failed",
                        stage_label=_summary_stage_label("failed"),
                        percent=100,
                        error=error_message,
                        message=error_message,
                    )
                    return
                update_summary_job(
                    job_id,
                    status="completed",
                    stage="complete",
                    stage_label=_summary_stage_label("complete"),
                    percent=100,
                    model=_model_display_name(translation.model),
                    message="已使用现有题目与摘要译文，正在刷新页面。" if reused_existing else "题目与摘要翻译已生成，正在刷新页面。",
                )

        threading.Thread(target=worker, name=f"translate-abstract-{job_id}", daemon=True).start()
        return {"job_id": job_id}

    @app.post("/summary-jobs/paper-full-text")
    def start_paper_full_text_summary_job(
        arxiv_id: str = Form(...),
        force: bool = Form(False),
    ) -> Dict[str, object]:
        redirect_url = f"/papers/{arxiv_id}"
        job_id = create_summary_job("paper_full_text", "单篇全文总结", redirect_url)

        def worker() -> None:
            with Session(engine) as worker_session:
                reused_existing = False
                try:
                    paper = worker_session.get(Paper, arxiv_id)
                    if paper is None:
                        raise ValueError(f"Paper not found: {arxiv_id}")
                    runtime_settings = resolve_runtime_settings(worker_session, settings)
                    existing = worker_session.exec(
                        select(PaperFullTextSummary).where(PaperFullTextSummary.arxiv_id == arxiv_id)
                    ).first()
                    extraction = None
                    if existing is None or force:
                        if not runtime_settings.qwen_api_key:
                            raise RuntimeError("DASHSCOPE_API_KEY is not set. Configure it before generating summaries.")
                        update_summary_job(
                            job_id,
                            status="running",
                            stage="downloading",
                            stage_label=_summary_stage_label("downloading"),
                            percent=10,
                            message="正在下载 arXiv PDF。",
                            model=_model_display_name(runtime_settings.qwen_model),
                        )
                        source_url, pdf_bytes = download_paper_pdf(paper)
                        update_summary_job(
                            job_id,
                            stage="extracting",
                            stage_label=_summary_stage_label("extracting"),
                            percent=28,
                            message="正在从 PDF 提取正文文本。",
                        )
                        extraction = extract_paper_pdf_text(
                            paper,
                            pdf_bytes,
                            source_url=source_url,
                            max_chars=runtime_settings.full_text_max_chars,
                        )
                    else:
                        reused_existing = True
                        update_summary_job(
                            job_id,
                            status="running",
                            stage="preparing",
                            stage_label=_summary_stage_label("preparing"),
                            percent=20,
                            message="已找到现有全文总结，正在准备返回。",
                            model=_model_display_name(existing.model),
                        )
                    update_summary_job(
                        job_id,
                        stage="calling_model" if extraction is not None else "saving",
                        stage_label=_summary_stage_label("calling_model" if extraction is not None else "saving"),
                        percent=48 if extraction is not None else 88,
                        message=(
                            "正在调用智能模型生成全文总结。"
                            if extraction is not None
                            else "正在读取已有全文总结。"
                        ),
                        model=_model_display_name(
                            runtime_settings.qwen_model if extraction is not None else existing.model if existing else ""
                        ),
                    )
                    summary = generate_paper_full_text_summary(
                        worker_session,
                        arxiv_id,
                        runtime_settings,
                        force=force,
                        extraction=extraction,
                    )
                    update_summary_job(
                        job_id,
                        stage="saving",
                        stage_label=_summary_stage_label("saving"),
                        percent=88,
                        message="正在保存全文总结结果。",
                    )
                except Exception as exc:  # pragma: no cover - runtime model/PDF path
                    error_message = _summary_error_message(exc)
                    update_summary_job(
                        job_id,
                        status="failed",
                        stage="failed",
                        stage_label=_summary_stage_label("failed"),
                        percent=100,
                        error=error_message,
                        message=error_message,
                    )
                    return
                update_summary_job(
                    job_id,
                    status="completed",
                    stage="complete",
                    stage_label=_summary_stage_label("complete"),
                    percent=100,
                    model=_model_display_name(summary.model),
                    message="已使用现有全文总结，正在刷新页面。" if reused_existing else "全文总结已生成，正在刷新页面。",
                )

        threading.Thread(target=worker, name=f"summary-paper-full-text-{job_id}", daemon=True).start()
        return {"job_id": job_id}

    @app.post("/summary-jobs/daily/{day}")
    def start_daily_summary_job(day: str, force: bool = Form(False)) -> Dict[str, object]:
        target_day = date.fromisoformat(day)
        redirect_url = f"/daily/{day}"
        job_id = create_summary_job("daily", "当日日报", redirect_url)

        def worker() -> None:
            with Session(engine) as worker_session:
                try:
                    update_summary_job(
                        job_id,
                        status="running",
                        stage="preparing",
                        stage_label=_summary_stage_label("preparing"),
                        percent=10,
                        message="正在读取当天论文并组装日报上下文。",
                    )
                    runtime_settings = resolve_runtime_settings(worker_session, settings)
                    paper_count = len(
                        worker_session.exec(select(Paper).where(Paper.fetched_for_date == day)).all()
                    )
                    if paper_count:
                        progress_stage = "calling_model"
                        progress_message = "正在调用智能模型生成当日日报。"
                        progress_model = _model_display_name(runtime_settings.qwen_model)
                    else:
                        progress_stage = "saving"
                        progress_message = "当天没有候选论文，正在生成空日报。"
                        progress_model = "local"
                    update_summary_job(
                        job_id,
                        stage=progress_stage,
                        stage_label=_summary_stage_label(progress_stage),
                        percent=36,
                        message=progress_message,
                        model=progress_model,
                    )
                    report = generate_daily_report(worker_session, target_day, runtime_settings, force=force)
                    update_summary_job(
                        job_id,
                        stage="saving",
                        stage_label=_summary_stage_label("saving"),
                        percent=88,
                        message="正在保存日报内容。",
                    )
                except Exception as exc:  # pragma: no cover - runtime model path
                    error_message = _summary_error_message(exc)
                    update_summary_job(
                        job_id,
                        status="failed",
                        stage="failed",
                        stage_label=_summary_stage_label("failed"),
                        percent=100,
                        error=error_message,
                        message=error_message,
                    )
                    return
                update_summary_job(
                    job_id,
                    status="completed",
                    stage="complete",
                    stage_label=_summary_stage_label("complete"),
                    percent=100,
                    model=_model_display_name(report.model),
                    message="日报已生成，正在刷新页面。",
                )

        threading.Thread(target=worker, name=f"summary-daily-{job_id}", daemon=True).start()
        return {"job_id": job_id}

    @app.get("/summary-jobs/{job_id}")
    def summary_job_status(job_id: str) -> Dict[str, object]:
        with summary_jobs_lock:
            job = summary_jobs.get(job_id)
            if job is None:
                return {"id": job_id, "status": "not_found", "stage_label": "任务不存在", "percent": 100}
            return dict(job)

    @app.get("/keywords")
    def keywords(
        request: Request,
        message: str = "",
        error: str = "",
        session: Session = Depends(get_session),
    ) -> Response:
        categories = session.exec(select(Category).order_by(Category.code)).all()
        groups = session.exec(select(KeywordGroup).order_by(KeywordGroup.name)).all()
        keywords_by_group = {}
        keyword_stats = {
            "enabled_categories": sum(1 for category in categories if category.enabled),
            "enabled_groups": sum(1 for group in groups if group.enabled),
            "include_keywords": 0,
            "exclude_keywords": 0,
        }
        for group in groups:
            group_keywords = session.exec(
                select(Keyword).where(Keyword.group_id == group.id).order_by(Keyword.kind, Keyword.value)
            ).all()
            keywords_by_group[group.id] = group_keywords
            keyword_stats["include_keywords"] += sum(
                1 for keyword in group_keywords if keyword.kind == "include" and keyword.enabled
            )
            keyword_stats["exclude_keywords"] += sum(
                1 for keyword in group_keywords if keyword.kind == "exclude" and keyword.enabled
            )
        return templates.TemplateResponse(
            "keywords.html",
            {
                "request": request,
                "categories": categories,
                "groups": groups,
                "keywords_by_group": keywords_by_group,
                "keyword_stats": keyword_stats,
                "message": message,
                "error": error,
            },
        )

    @app.get("/settings")
    def settings_page(
        request: Request,
        message: str = "",
        error: str = "",
        session: Session = Depends(get_session),
    ) -> Response:
        return templates.TemplateResponse(
            "settings.html",
            {
                "request": request,
                "settings_view": qwen_settings_view(session, settings),
                "message": message,
                "error": error,
            },
        )

    @app.post("/settings/qwen")
    def save_qwen_settings(
        api_key: str = Form(""),
        base_url: str = Form(...),
        model: str = Form(...),
        temperature: float = Form(...),
        max_tokens_single: int = Form(...),
        max_tokens_full_text: int = Form(...),
        max_tokens_daily: int = Form(...),
        daily_top_n: int = Form(...),
        daily_abstract_chars: int = Form(...),
        full_text_max_chars: int = Form(...),
        clear_api_key: bool = Form(False),
        session: Session = Depends(get_session),
    ) -> RedirectResponse:
        if not base_url.strip():
            return _redirect("/settings", error="Base URL is required.")
        save_qwen_form(
            session=session,
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=temperature,
            max_tokens_single=max_tokens_single,
            max_tokens_full_text=max_tokens_full_text,
            max_tokens_daily=max_tokens_daily,
            daily_top_n=daily_top_n,
            daily_abstract_chars=daily_abstract_chars,
            full_text_max_chars=full_text_max_chars,
            clear_api_key=clear_api_key,
        )
        return _redirect("/settings", message="智能模型 API 设置已保存。")

    @app.post("/keywords/categories")
    def add_category(code: str = Form(...), session: Session = Depends(get_session)) -> RedirectResponse:
        code = code.strip()
        if not code:
            return _redirect("/keywords", error="Category code is required.")
        existing = session.exec(select(Category).where(Category.code == code)).first()
        if existing is None:
            session.add(Category(code=code, enabled=True))
        else:
            existing.enabled = True
            session.add(existing)
        session.commit()
        return _redirect("/keywords", message=f"Category {code} saved.")

    @app.post("/keywords/categories/{category_id}/toggle")
    def toggle_category(category_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
        category = session.get(Category, category_id)
        if category:
            category.enabled = not category.enabled
            session.add(category)
            session.commit()
        return _redirect("/keywords")

    @app.post("/keywords/categories/{category_id}/delete")
    def delete_category(category_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
        category = session.get(Category, category_id)
        if category:
            session.delete(category)
            session.commit()
        return _redirect("/keywords")

    @app.post("/keywords/groups")
    def add_group(
        name: str = Form(...),
        weight: float = Form(1.0),
        session: Session = Depends(get_session),
    ) -> RedirectResponse:
        name = name.strip()
        if not name:
            return _redirect("/keywords", error="Group name is required.")
        existing = session.exec(select(KeywordGroup).where(KeywordGroup.name == name)).first()
        if existing is None:
            session.add(KeywordGroup(name=name, weight=weight, enabled=True))
        else:
            existing.weight = weight
            existing.enabled = True
            session.add(existing)
        session.commit()
        return _redirect("/keywords", message=f"Group {name} saved.")

    @app.post("/keywords/groups/{group_id}/weight")
    def update_group_weight(
        group_id: int,
        weight: float = Form(...),
        session: Session = Depends(get_session),
    ) -> RedirectResponse:
        group = session.get(KeywordGroup, group_id)
        if group:
            group.weight = weight
            session.add(group)
            session.commit()
        return _redirect("/keywords")

    @app.post("/keywords/groups/{group_id}/toggle")
    def toggle_group(group_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
        group = session.get(KeywordGroup, group_id)
        if group:
            group.enabled = not group.enabled
            session.add(group)
            session.commit()
        return _redirect("/keywords")

    @app.post("/keywords/groups/{group_id}/delete")
    def delete_group(group_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
        group = session.get(KeywordGroup, group_id)
        if group:
            for keyword in session.exec(select(Keyword).where(Keyword.group_id == group_id)).all():
                session.delete(keyword)
            session.delete(group)
            session.commit()
        return _redirect("/keywords")

    @app.post("/keywords/groups/{group_id}/keywords")
    def add_keyword(
        group_id: int,
        value: str = Form(...),
        kind: str = Form("include"),
        session: Session = Depends(get_session),
    ) -> RedirectResponse:
        value = value.strip()
        kind = kind if kind in ("include", "exclude") else "include"
        if not value:
            return _redirect("/keywords", error="Keyword value is required.")
        session.add(Keyword(group_id=group_id, value=value, kind=kind, enabled=True))
        session.commit()
        return _redirect("/keywords", message=f"Keyword {value} added.")

    @app.post("/keywords/keywords/{keyword_id}/toggle")
    def toggle_keyword(keyword_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
        keyword = session.get(Keyword, keyword_id)
        if keyword:
            keyword.enabled = not keyword.enabled
            session.add(keyword)
            session.commit()
        return _redirect("/keywords")

    @app.post("/keywords/keywords/{keyword_id}/delete")
    def delete_keyword(keyword_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
        keyword = session.get(Keyword, keyword_id)
        if keyword:
            session.delete(keyword)
            session.commit()
        return _redirect("/keywords")

    @app.get("/papers/{arxiv_id:path}")
    def paper_detail(
        request: Request,
        arxiv_id: str,
        message: str = "",
        error: str = "",
        session: Session = Depends(get_session),
    ) -> Response:
        paper = session.get(Paper, arxiv_id)
        if paper is None:
            return templates.TemplateResponse(
                "not_found.html",
                {"request": request, "title": "Paper not found", "message": arxiv_id},
                status_code=404,
            )
        summary = session.exec(select(PaperSummary).where(PaperSummary.arxiv_id == arxiv_id)).first()
        abstract_translation = session.exec(
            select(PaperAbstractTranslation).where(PaperAbstractTranslation.arxiv_id == arxiv_id)
        ).first()
        full_text_summary = session.exec(
            select(PaperFullTextSummary).where(PaperFullTextSummary.arxiv_id == arxiv_id)
        ).first()
        day_papers = session.exec(
            select(Paper)
            .where(Paper.fetched_for_date == paper.fetched_for_date)
            .order_by(Paper.relevance_score.desc(), Paper.published_at.desc())
        ).all()
        paper_position = next(
            (index for index, day_paper in enumerate(day_papers) if day_paper.arxiv_id == paper.arxiv_id),
            None,
        )
        previous_paper = day_papers[paper_position - 1] if paper_position not in (None, 0) else None
        next_paper = (
            day_papers[paper_position + 1]
            if paper_position is not None and paper_position + 1 < len(day_papers)
            else None
        )
        return templates.TemplateResponse(
            "paper.html",
            {
                "request": request,
                "paper": paper,
                "paper_position": paper_position + 1 if paper_position is not None else None,
                "paper_count": len(day_papers),
                "previous_paper": previous_paper,
                "next_paper": next_paper,
                "summary": summary,
                "abstract_translation": abstract_translation,
                "full_text_summary": full_text_summary,
                "message": message,
                "error": error,
            },
        )

    @app.post("/papers/{arxiv_id:path}/summarize")
    def summarize_paper(
        arxiv_id: str,
        force: bool = Form(False),
        session: Session = Depends(get_session),
    ) -> RedirectResponse:
        try:
            generate_paper_summary(session, arxiv_id, resolve_runtime_settings(session, settings), force=force)
        except Exception as exc:  # pragma: no cover - model runtime path
            return _redirect(f"/papers/{arxiv_id}", error=_summary_error_message(exc))
        return _redirect(f"/papers/{arxiv_id}", message="Paper summary generated.")

    @app.post("/paper-abstract/translate")
    def translate_paper_abstract(
        arxiv_id: str = Form(...),
        force: bool = Form(False),
        session: Session = Depends(get_session),
    ) -> RedirectResponse:
        try:
            generate_abstract_translation(session, arxiv_id, resolve_runtime_settings(session, settings), force=force)
        except Exception as exc:  # pragma: no cover - model runtime path
            return _redirect(f"/papers/{arxiv_id}", error=_summary_error_message(exc))
        return _redirect(f"/papers/{arxiv_id}", message="Abstract translation generated.")

    @app.post("/paper-full-text/summarize")
    def summarize_paper_full_text(
        arxiv_id: str = Form(...),
        force: bool = Form(False),
        session: Session = Depends(get_session),
    ) -> RedirectResponse:
        try:
            generate_paper_full_text_summary(session, arxiv_id, resolve_runtime_settings(session, settings), force=force)
        except Exception as exc:  # pragma: no cover - model/PDF runtime path
            return _redirect(f"/papers/{arxiv_id}", error=_summary_error_message(exc))
        return _redirect(f"/papers/{arxiv_id}", message="Full-text paper summary generated.")

    @app.get("/daily/{day}")
    def daily_report_page(
        request: Request,
        day: str,
        message: str = "",
        error: str = "",
        session: Session = Depends(get_session),
    ) -> Response:
        target_day = date.fromisoformat(day)
        report = session.exec(select(DailyReport).where(DailyReport.report_date == day)).first()
        papers = session.exec(
            select(Paper)
            .where(Paper.fetched_for_date == day)
            .order_by(Paper.relevance_score.desc(), Paper.published_at.desc())
        ).all()
        markdown_preview = render_daily_markdown(session, target_day)
        return templates.TemplateResponse(
            "daily.html",
            {
                "request": request,
                "day": day,
                "report": report,
                "papers": papers,
                "markdown_preview": markdown_preview,
                "message": message,
                "error": error,
                **_day_nav_context(target_day, session),
            },
        )

    @app.post("/daily/{day}/summarize")
    def summarize_day(
        day: str,
        force: bool = Form(False),
        session: Session = Depends(get_session),
    ) -> RedirectResponse:
        target_day = date.fromisoformat(day)
        try:
            generate_daily_report(session, target_day, resolve_runtime_settings(session, settings), force=force)
        except Exception as exc:  # pragma: no cover - model runtime path
            return _redirect(f"/daily/{day}", error=_summary_error_message(exc))
        return _redirect(f"/daily/{day}", message="Daily report generated.")

    @app.post("/daily/{day}/export")
    def export_day(day: str, session: Session = Depends(get_session)) -> RedirectResponse:
        path = export_daily_markdown(session, date.fromisoformat(day), settings)
        return _redirect(f"/daily/{day}", message=f"Exported to {path}")

    return app


app = create_app()
