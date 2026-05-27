from __future__ import annotations

import threading
import time
import urllib.parse
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Generator, Optional

from fastapi import Depends, FastAPI, Form, Query, Request
import httpx
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from .arxiv import FetchQuotaExceeded, FetchResult, fetch_papers_for_date, fetch_quota_status
from .app_settings import qwen_settings_view, resolve_runtime_settings, save_qwen_form
from .config import Settings, get_settings
from .database import build_engine, create_db_and_tables
from .dates import arxiv_date_range, arxiv_date_ranges, parse_day
from .defaults import init_default_config
from .forest import (
    build_forest_tiles,
    filter_tile,
    forest_client_tiles,
    forest_counts,
    forest_filters,
    forest_groves,
    forest_scene_context,
    forest_status_filters,
    forest_topic_filters,
)
from .models import (
    ArxivFetchRun,
    Category,
    Keyword,
    KeywordGroup,
    Paper,
    PaperAbstractTranslation,
    ArxivPageCache,
    PaperFullTextSummary,
    PaperSummary,
    utc_now,
)
from .pdf_text import DEFAULT_FIGURE_OUTPUT_DIR, download_paper_pdf, extract_paper_pdf_text
from .summaries import (
    generate_abstract_translation,
    generate_paper_full_text_summary,
    generate_paper_summary,
)
from .text import (
    clean_latex_text,
    clean_translation_title,
    clean_translation_text,
    format_datetime,
    summary_excerpt,
    summary_to_html,
)

PACKAGE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
templates.env.filters["clean_latex"] = clean_latex_text
templates.env.filters["translation_title"] = clean_translation_title
templates.env.filters["translation_text"] = clean_translation_text
templates.env.filters["summary_html"] = summary_to_html
templates.env.filters["summary_excerpt"] = summary_excerpt
templates.env.filters["format_dt"] = format_datetime


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


def _parse_optional_day(value: Optional[str], settings: Settings) -> tuple[date, str]:
    if not value:
        return parse_day(None, settings.timezone), ""
    try:
        return parse_day(value, settings.timezone), ""
    except ValueError:
        return parse_day(None, settings.timezone), f"日期 {value} 无法识别，已展示今天的论文森林。"


def _redirect(path: str, **query: object) -> RedirectResponse:
    filtered = {key: value for key, value in query.items() if value not in (None, "")}
    suffix = f"?{urllib.parse.urlencode(filtered)}" if filtered else ""
    return RedirectResponse(f"{path}{suffix}", status_code=303)


def _arxiv_policy_view(settings: Settings) -> Dict[str, object]:
    official_base_url = "https://export.arxiv.org/api/query"
    return {
        "base_url": settings.arxiv_base_url,
        "official_base_url": official_base_url,
        "uses_official_api": settings.arxiv_base_url.rstrip("/") == official_base_url,
        "request_delay_seconds": settings.effective_arxiv_request_delay_seconds,
        "page_size": settings.arxiv_page_size,
        "max_results": settings.arxiv_max_results,
        "user_agent": settings.arxiv_user_agent,
    }


def _message_from_fetch(result: FetchResult) -> str:
    source_note = f"联网请求 {result.network_requests} 次，缓存页 {result.cached_pages} 页。"
    quota_note = ""
    if result.daily_network_fetch_limit > 0:
        quota_note = f" 今日有效拉取额度 {result.daily_network_fetch_used}/{result.daily_network_fetch_limit}。"
    return (
        f"读取 {result.fetched} 篇；命中 {result.matched} 篇；"
        f"新增 {result.saved} 篇；刷新已有 {result.updated} 篇；"
        f"无关键词跳过 {result.skipped_no_keyword} 篇；排除词跳过 {result.skipped_excluded} 篇。"
        f" {source_note}{quota_note}"
    )


def _message_from_clear_day_cache(day_text: str, counts: Dict[str, int]) -> str:
    smart_count = counts["translations"] + counts["paper_summaries"] + counts["full_text_summaries"]
    return (
        f"已清理 {day_text}：论文 {counts['papers']} 篇，智能结果 {smart_count} 条，"
        f"arXiv 页面缓存 {counts['arxiv_pages']} 页。限流记录已保留。"
    )


def _message_from_clear_all_cache(counts: Dict[str, int]) -> str:
    smart_count = counts["translations"] + counts["paper_summaries"] + counts["full_text_summaries"]
    return (
        f"已清理全部缓存：论文 {counts['papers']} 篇，智能结果 {smart_count} 条，"
        f"arXiv 页面缓存 {counts['arxiv_pages']} 页，全文图片缓存 {counts['figure_files']} 个。"
        "关键词、模型设置和限流记录已保留。"
    )


def _fetch_quota_view(target_day: date, session: Session, settings: Settings) -> Dict[str, object]:
    status = fetch_quota_status(session, target_day, settings)
    return {
        "target_date": status.target_date,
        "run_date": status.run_date,
        "limit": status.limit,
        "used": status.used,
        "remaining": status.remaining,
        "unlimited": status.unlimited,
        "exhausted": (not status.unlimited and status.remaining == 0),
    }


def _delete_rows(session: Session, rows: list[object]) -> int:
    for row in rows:
        session.delete(row)
    return len(rows)


def _clear_day_paper_cache(session: Session, target_day: date, settings: Settings) -> Dict[str, int]:
    day_text = target_day.isoformat()
    paper_ids = session.exec(select(Paper.arxiv_id).where(Paper.fetched_for_date == day_text)).all()
    counts = {
        "papers": 0,
        "translations": 0,
        "paper_summaries": 0,
        "full_text_summaries": 0,
        "arxiv_pages": 0,
    }

    if paper_ids:
        counts["translations"] = _delete_rows(
            session,
            session.exec(select(PaperAbstractTranslation).where(PaperAbstractTranslation.arxiv_id.in_(paper_ids))).all(),
        )
        counts["paper_summaries"] = _delete_rows(
            session,
            session.exec(select(PaperSummary).where(PaperSummary.arxiv_id.in_(paper_ids))).all(),
        )
        counts["full_text_summaries"] = _delete_rows(
            session,
            session.exec(select(PaperFullTextSummary).where(PaperFullTextSummary.arxiv_id.in_(paper_ids))).all(),
        )

    cache_markers = {f"submittedDate:{arxiv_date_range(target_day, settings.timezone)}"}
    cache_markers.update(f"submittedDate:{date_range}" for date_range in arxiv_date_ranges(target_day, settings.timezone))
    cache_rows_by_key = {}
    for cache_marker in cache_markers:
        for row in session.exec(select(ArxivPageCache).where(ArxivPageCache.query.contains(cache_marker))).all():
            cache_rows_by_key[row.cache_key] = row
    counts["arxiv_pages"] = _delete_rows(session, list(cache_rows_by_key.values()))
    counts["papers"] = _delete_rows(
        session,
        session.exec(select(Paper).where(Paper.fetched_for_date == day_text)).all(),
    )
    session.commit()
    return counts


def _clear_generated_figure_cache(output_dir: Optional[Path] = None) -> int:
    output_dir = output_dir or DEFAULT_FIGURE_OUTPUT_DIR
    if not output_dir.exists():
        return 0
    count = 0
    for path in output_dir.iterdir():
        if not path.is_file():
            continue
        path.unlink(missing_ok=True)
        count += 1
    return count


def _clear_all_paper_cache(session: Session) -> Dict[str, int]:
    counts = {
        "papers": 0,
        "translations": _delete_rows(session, session.exec(select(PaperAbstractTranslation)).all()),
        "paper_summaries": _delete_rows(session, session.exec(select(PaperSummary)).all()),
        "full_text_summaries": _delete_rows(session, session.exec(select(PaperFullTextSummary)).all()),
        "arxiv_pages": _delete_rows(session, session.exec(select(ArxivPageCache)).all()),
        "figure_files": _clear_generated_figure_cache(),
    }
    counts["papers"] = _delete_rows(session, session.exec(select(Paper)).all())
    session.commit()
    return counts


def _fetch_stage_label(stage: str) -> str:
    labels = {
        "queued": "等待开始",
        "preparing": "准备检索",
        "locked": "等待抓取",
        "waiting": "等待 arXiv",
        "requesting": "请求 arXiv",
        "cached": "读取缓存",
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
    matched = int(payload.get("matched") or 0)
    updated = int(payload.get("updated") or 0)
    if stage == "locked":
        seconds = int(payload.get("wait_seconds") or 0)
        return f"上一个抓取任务仍在运行，已等待 {seconds} 秒。"
    if stage == "requesting":
        return f"正在请求 arXiv 第 {page}/{total_pages} 页。"
    if stage == "cached":
        return f"正在使用本地缓存解析第 {page}/{total_pages} 页。"
    if stage == "waiting":
        seconds = payload.get("wait_seconds")
        if payload.get("retry"):
            attempt = payload.get("retry_attempt")
            retry_count = payload.get("retry_count")
            reason = str(payload.get("retry_reason") or "")
            if reason == "server_busy":
                status = payload.get("http_status")
                return f"arXiv 官方 API 繁忙（HTTP {status}），等待 {seconds} 秒后重试（{attempt}/{retry_count}）。"
            if reason == "timeout":
                return f"连接 arXiv 官方 API 超时，等待 {seconds} 秒后重试（{attempt}/{retry_count}）。"
            if reason == "network":
                return f"暂时无法连接 arXiv 官方 API，等待 {seconds} 秒后重试（{attempt}/{retry_count}）。"
            return f"arXiv 官方 API 正在限流，等待 {seconds} 秒后重试（{attempt}/{retry_count}）。"
        return f"按 arXiv API 规范等待 {seconds} 秒后继续下一页。"
    if stage == "processing":
        return f"正在解析论文并计算关键词相关性，已读取 {fetched} 篇。"
    if stage == "saving":
        return f"已命中 {matched} 篇，新增 {saved} 篇，刷新已有 {updated} 篇。"
    if stage == "complete":
        return "抓取完成，正在刷新列表。"
    return "正在准备检索条件。"


def _fetch_error_message(exc: Exception) -> str:
    if isinstance(exc, FetchQuotaExceeded):
        return str(exc)
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        if status_code == 429:
            return "arXiv 官方 API 仍在限流（HTTP 429），系统已自动等待重试但仍未成功，请稍后再抓取。"
        if status_code in {502, 503, 504}:
            return f"arXiv 官方 API 暂时繁忙（HTTP {status_code}），本次抓取未完成，请稍后再试。"
        return f"arXiv 官方 API 返回 HTTP {status_code}，本次抓取未完成。"
    if isinstance(exc, httpx.TimeoutException):
        return "连接 arXiv 官方 API 超时，本次抓取未完成。"
    if isinstance(exc, httpx.RequestError):
        return "暂时无法连接 arXiv 官方 API，请检查网络或稍后重试。"
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


def _forest_data(session: Session, target_day: date) -> Dict[str, object]:
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
    paper_summaries = (
        session.exec(select(PaperSummary).where(PaperSummary.arxiv_id.in_(paper_ids))).all()
        if paper_ids
        else []
    )
    full_text_summaries = (
        session.exec(select(PaperFullTextSummary).where(PaperFullTextSummary.arxiv_id.in_(paper_ids))).all()
        if paper_ids
        else []
    )
    tiles = build_forest_tiles(papers, target_day, translations, paper_summaries, full_text_summaries)
    return {
        "papers": papers,
        "tiles": tiles,
        "client_tiles": forest_client_tiles(tiles),
        "counts": forest_counts(tiles),
        "filters": forest_filters(tiles),
        "topic_filters": forest_topic_filters(tiles),
        "status_filters": forest_status_filters(tiles),
        "groves": forest_groves(tiles),
        "scene": forest_scene_context(target_day),
    }


def _mark_stale_fetch_runs_failed(session: Session) -> int:
    rows = session.exec(select(ArxivFetchRun).where(ArxivFetchRun.status == "running")).all()
    for row in rows:
        row.status = "failed"
        row.finished_at = utc_now()
        row.message = "服务重启后任务已中止，请重新抓取。"
        session.add(row)
    if rows:
        session.commit()
    return len(rows)


def create_app(settings: Optional[Settings] = None, engine: Optional[Engine] = None) -> FastAPI:
    settings = settings or get_settings()
    engine = engine or build_engine(settings)
    create_db_and_tables(engine)
    with Session(engine) as session:
        init_default_config(session)
        _mark_stale_fetch_runs_failed(session)

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

    def active_fetch_job_for_day(day_text: str) -> Optional[Dict[str, object]]:
        with fetch_jobs_lock:
            active_jobs = [
                dict(job)
                for job in fetch_jobs.values()
                if job.get("day") == day_text and job.get("status") in {"queued", "running"}
            ]
        if not active_jobs:
            return None
        active_jobs.sort(key=lambda job: float(job.get("created_at") or 0.0))
        return active_jobs[-1]

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
        paper_summaries = (
            session.exec(select(PaperSummary).where(PaperSummary.arxiv_id.in_(paper_ids))).all()
            if paper_ids
            else []
        )
        summaries_by_paper = {summary.arxiv_id: summary for summary in paper_summaries}
        full_text_summaries = (
            session.exec(select(PaperFullTextSummary).where(PaperFullTextSummary.arxiv_id.in_(paper_ids))).all()
            if paper_ids
            else []
        )
        full_text_summaries_by_paper = {summary.arxiv_id: summary for summary in full_text_summaries}
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "day": target_day.isoformat(),
                "papers": papers,
                "translations_by_paper": translations_by_paper,
                "summaries_by_paper": summaries_by_paper,
                "full_text_summaries_by_paper": full_text_summaries_by_paper,
                "fetch_quota": _fetch_quota_view(target_day, session, settings),
                "arxiv_policy": _arxiv_policy_view(settings),
                "active_fetch_job": active_fetch_job_for_day(target_day.isoformat()),
                "message": message,
                "error": error,
                **_day_nav_context(target_day, session),
            },
        )

    @app.post("/fetch")
    def fetch(
        day: str = Form(...),
        force_refresh: bool = Form(False),
        session: Session = Depends(get_session),
    ) -> RedirectResponse:
        target_day = date.fromisoformat(day)
        try:
            with arxiv_fetch_lock:
                result = fetch_papers_for_date(session, target_day, settings, force_refresh=force_refresh)
        except Exception as exc:  # pragma: no cover - exercised through manual runtime
            return _redirect("/", day=day, error=_fetch_error_message(exc))
        return _redirect("/", day=day, message=_message_from_fetch(result))

    @app.post("/day-cache/{day}/clear")
    def clear_day_cache(day: str, session: Session = Depends(get_session)) -> RedirectResponse:
        target_day = date.fromisoformat(day)
        with arxiv_fetch_lock:
            counts = _clear_day_paper_cache(session, target_day, settings)
        return _redirect("/", day=day, message=_message_from_clear_day_cache(day, counts))

    @app.post("/cache/clear")
    def clear_all_cache(day: str = Form(""), session: Session = Depends(get_session)) -> RedirectResponse:
        target_day = parse_day(day or None, settings.timezone)
        with arxiv_fetch_lock:
            counts = _clear_all_paper_cache(session)
        return _redirect("/", day=target_day.isoformat(), message=_message_from_clear_all_cache(counts))

    @app.post("/fetch-jobs")
    def start_fetch_job(day: str = Form(...), force_refresh: bool = Form(False)) -> Dict[str, object]:
        job_id = uuid.uuid4().hex
        target_day = date.fromisoformat(day)
        with Session(engine) as quota_session:
            quota_view = _fetch_quota_view(target_day, quota_session, settings)
        now = time.time()
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
                "matched": 0,
                "updated": 0,
                "skipped_no_keyword": 0,
                "skipped_excluded": 0,
                "network_requests": 0,
                "cached_pages": 0,
                "daily_network_fetch_limit": quota_view["limit"],
                "daily_network_fetch_used": quota_view["used"],
                "daily_network_fetch_remaining": quota_view["remaining"],
                "page": 0,
                "total_pages": max(1, (settings.arxiv_max_results + settings.arxiv_page_size - 1) // settings.arxiv_page_size),
                "message": "任务已创建，正在排队。",
                "error": "",
                "created_at": now,
                "updated_at": now,
            }

        def update_job(**values: object) -> None:
            with fetch_jobs_lock:
                values["updated_at"] = time.time()
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
            if stage != "waiting":
                progress_values["error"] = ""
            update_job(**progress_values)

        def worker() -> None:
            update_job(status="running", stage="preparing", stage_label="准备检索", message="正在读取分类和关键词配置。", percent=3)
            with Session(engine) as worker_session:
                try:
                    lock_started_at = time.monotonic()
                    while not arxiv_fetch_lock.acquire(timeout=1.0):
                        waited = int(time.monotonic() - lock_started_at)
                        update_job(
                            status="running",
                            stage="locked",
                            stage_label=_fetch_stage_label("locked"),
                            percent=2,
                            wait_seconds=waited,
                            message=f"上一个抓取任务仍在运行，已等待 {waited} 秒。",
                        )
                        if waited >= max(30, settings.request_timeout_seconds * 2):
                            raise RuntimeError("上一个抓取任务长时间未结束。请刷新页面后重新抓取。")
                    try:
                        result = fetch_papers_for_date(
                            worker_session,
                            target_day,
                            settings,
                            progress_callback=progress,
                            force_refresh=force_refresh,
                        )
                    finally:
                        arxiv_fetch_lock.release()
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
                    matched=result.matched,
                    updated=result.updated,
                    skipped_no_keyword=result.skipped_no_keyword,
                    skipped_excluded=result.skipped_excluded,
                    network_requests=result.network_requests,
                    cached_pages=result.cached_pages,
                    daily_network_fetch_limit=result.daily_network_fetch_limit,
                    daily_network_fetch_used=result.daily_network_fetch_used,
                    daily_network_fetch_remaining=(
                        max(0, result.daily_network_fetch_limit - result.daily_network_fetch_used)
                        if result.daily_network_fetch_limit > 0
                        else None
                    ),
                    query=result.query,
                    current_count=current_count,
                    message=_message_from_fetch(result),
                    error="",
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
            stale_after = max(90.0, settings.request_timeout_seconds * 3)
            if (
                job.get("status") in {"queued", "running"}
                and time.time() - float(job.get("updated_at") or 0.0) > stale_after
            ):
                job.update(
                    status="failed",
                    stage="failed",
                    stage_label="抓取失败",
                    percent=100,
                    error="抓取任务长时间没有进展，请重新抓取。",
                    message="抓取任务长时间没有进展，请重新抓取。",
                    updated_at=time.time(),
                )
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

    @app.post("/summary-jobs/papers/{arxiv_id:path}/all")
    def start_paper_all_insights_job(arxiv_id: str, force: bool = Form(False)) -> Dict[str, object]:
        redirect_url = f"/papers/{urllib.parse.quote(arxiv_id, safe='')}#paper-abstract"
        job_id = create_summary_job("paper_all", "翻译、摘要与全文总结", redirect_url)

        def worker() -> None:
            with Session(engine) as worker_session:
                try:
                    paper = worker_session.get(Paper, arxiv_id)
                    if paper is None:
                        raise ValueError(f"Paper not found: {arxiv_id}")
                    runtime_settings = resolve_runtime_settings(worker_session, settings)
                    update_summary_job(
                        job_id,
                        status="running",
                        stage="preparing",
                        stage_label=_summary_stage_label("preparing"),
                        percent=8,
                        message="正在整理单篇论文上下文。",
                        model=_model_display_name(runtime_settings.qwen_model),
                    )
                    update_summary_job(
                        job_id,
                        stage="calling_model",
                        stage_label="生成译文",
                        percent=22,
                        message="正在生成题目与摘要中文翻译。",
                    )
                    translation = generate_abstract_translation(
                        worker_session,
                        arxiv_id,
                        runtime_settings,
                        force=force,
                    )
                    update_summary_job(
                        job_id,
                        stage="calling_model",
                        stage_label="生成摘要",
                        percent=48,
                        message="正在生成摘要版研究总结。",
                        model=_model_display_name(translation.model),
                    )
                    summary = generate_paper_summary(
                        worker_session,
                        arxiv_id,
                        runtime_settings,
                        force=force,
                    )
                    update_summary_job(
                        job_id,
                        stage="calling_model",
                        stage_label="生成全文",
                        percent=72,
                            message=(
                                "正在提取 PDF 正文生成文字总结；随后上传 PDF 给 Qwen 文档模型生成关键图片总结。"
                                if runtime_settings.full_text_pdf_upload_enabled
                                else "正在提取 PDF 正文和图片；有论文图时会调用 Qwen 多模态模型生成全文总结。"
                            ),
                        model=_model_display_name(summary.model),
                    )
                    full_text_summary = generate_paper_full_text_summary(
                        worker_session,
                        arxiv_id,
                        runtime_settings,
                        force=force,
                    )
                    update_summary_job(
                        job_id,
                        stage="saving",
                        stage_label=_summary_stage_label("saving"),
                        percent=92,
                        message="正在保存三类智能结果。",
                        model=_model_display_name(full_text_summary.model),
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
                    model=_model_display_name(full_text_summary.model),
                    message="三类智能结果已生成，可手动查看结果。",
                )

        threading.Thread(target=worker, name=f"summary-paper-all-{job_id}", daemon=True).start()
        return {"job_id": job_id}

    @app.post("/summary-jobs/papers/{arxiv_id:path}")
    def start_paper_summary_job(arxiv_id: str, force: bool = Form(False)) -> Dict[str, object]:
        redirect_url = f"/papers/{urllib.parse.quote(arxiv_id, safe='')}#abstract-summary"
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
                            message="已找到现有摘要总结，可手动查看结果。",
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
                    message="已使用现有单篇总结，可手动查看结果。" if reused_existing else "单篇总结已生成，可手动查看结果。",
                )

        threading.Thread(target=worker, name=f"summary-paper-{job_id}", daemon=True).start()
        return {"job_id": job_id}

    @app.post("/summary-jobs/paper-abstract-translation")
    def start_paper_abstract_translation_job(
        arxiv_id: str = Form(...),
        force: bool = Form(False),
    ) -> Dict[str, object]:
        redirect_url = f"/papers/{urllib.parse.quote(arxiv_id, safe='')}#abstract-translation"
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
                            message="已找到现有题目与摘要译文，可手动查看结果。",
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
                    message="已使用现有题目与摘要译文，可手动查看结果。" if reused_existing else "题目与摘要翻译已生成，可手动查看结果。",
                )

        threading.Thread(target=worker, name=f"translate-abstract-{job_id}", daemon=True).start()
        return {"job_id": job_id}

    @app.post("/summary-jobs/paper-full-text")
    def start_paper_full_text_summary_job(
        arxiv_id: str = Form(...),
        force: bool = Form(False),
    ) -> Dict[str, object]:
        redirect_url = f"/papers/{urllib.parse.quote(arxiv_id, safe='')}#full-text-summary"
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
                    pdf_bytes = None
                    source_url = ""
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
                            model=_model_display_name(
                                runtime_settings.qwen_pdf_model
                                if runtime_settings.full_text_pdf_upload_enabled
                                else runtime_settings.qwen_model
                            ),
                        )
                        source_url, pdf_bytes = download_paper_pdf(paper)
                        update_summary_job(
                            job_id,
                            stage="extracting",
                            stage_label=_summary_stage_label("extracting"),
                            percent=28,
                            message="正在从 PDF 提取正文文本和图片。",
                        )
                        extraction = extract_paper_pdf_text(
                            paper,
                            pdf_bytes,
                            source_url=source_url,
                            max_chars=runtime_settings.full_text_max_chars,
                            figure_limit=runtime_settings.full_text_figure_limit,
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
                            "正在生成文字总结，并上传 PDF 给 Qwen 文档模型生成关键图片总结。"
                            if extraction is not None and runtime_settings.full_text_pdf_upload_enabled
                            else "正在调用 Qwen 多模态模型生成图文全文总结。"
                            if extraction is not None and extraction.figures
                            else "正在调用智能模型生成全文总结。"
                            if extraction is not None
                            else "正在读取已有全文总结。"
                        ),
                        model=_model_display_name(
                            runtime_settings.qwen_pdf_model
                            if extraction is not None and runtime_settings.full_text_pdf_upload_enabled
                            else runtime_settings.qwen_vision_model
                            if extraction is not None and extraction.figures
                            else runtime_settings.qwen_model
                            if extraction is not None
                            else existing.model
                            if existing
                            else ""
                        ),
                    )
                    summary = generate_paper_full_text_summary(
                        worker_session,
                        arxiv_id,
                        runtime_settings,
                        force=force,
                        extraction=extraction,
                        pdf_bytes=pdf_bytes,
                        source_url=source_url,
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
                    message="已使用现有全文总结，可手动查看结果。" if reused_existing else "全文总结已生成，可手动查看结果。",
                )

        threading.Thread(target=worker, name=f"summary-paper-full-text-{job_id}", daemon=True).start()
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
        model: str = Form(""),
        vision_model: str = Form(""),
        qwen_pdf_model: str = Form(""),
        temperature: float = Form(...),
        max_tokens_single: int = Form(...),
        max_tokens_full_text: int = Form(...),
        full_text_max_chars: int = Form(...),
        full_text_figure_limit: int = Form(6),
        full_text_pdf_upload_enabled: bool = Form(True),
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
            vision_model=vision_model,
            qwen_pdf_model=qwen_pdf_model,
            temperature=temperature,
            max_tokens_single=max_tokens_single,
            max_tokens_full_text=max_tokens_full_text,
            full_text_max_chars=full_text_max_chars,
            full_text_figure_limit=full_text_figure_limit,
            full_text_pdf_upload_enabled=full_text_pdf_upload_enabled,
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

    @app.get("/forest")
    def forest_page(
        request: Request,
        forest_date: Optional[str] = Query(None, alias="date"),
        message: str = "",
        error: str = "",
        session: Session = Depends(get_session),
    ) -> Response:
        target_day, date_error = _parse_optional_day(forest_date, settings)
        data = _forest_data(session, target_day)
        return templates.TemplateResponse(
            "forest.html",
            {
                "request": request,
                "day": target_day.isoformat(),
                "message": message,
                "error": error or date_error,
                **data,
                **_day_nav_context(target_day, session),
            },
        )

    @app.get("/api/forest")
    def forest_api(
        forest_date: Optional[str] = Query(None, alias="date"),
        filter_key: Optional[str] = Query(None, alias="filter"),
        session: Session = Depends(get_session),
    ) -> Dict[str, object]:
        target_day, date_error = _parse_optional_day(forest_date, settings)
        data = _forest_data(session, target_day)
        tiles = data["tiles"]
        if filter_key:
            tiles = [tile for tile in tiles if filter_tile(tile, filter_key)]
        return {
            "date": target_day.isoformat(),
            "error": date_error,
            "filter": filter_key or "all",
            "counts": data["counts"],
            "filters": data["filters"],
            "scene": data["scene"],
            "tiles": tiles,
        }

    @app.get("/papers")
    @app.get("/papers/")
    def papers_index(
        request: Request,
        day: Optional[str] = None,
        session: Session = Depends(get_session),
    ) -> Response:
        latest_day = _latest_day_with_papers(session)
        target_day = parse_day(day or latest_day or None, settings.timezone)
        papers = session.exec(
            select(Paper)
            .where(Paper.fetched_for_date == target_day.isoformat())
            .order_by(Paper.relevance_score.desc(), Paper.published_at.desc())
        ).all()
        paper_ids = [paper.arxiv_id for paper in papers]
        paper_summaries = (
            session.exec(select(PaperSummary).where(PaperSummary.arxiv_id.in_(paper_ids))).all()
            if paper_ids
            else []
        )
        full_text_summaries = (
            session.exec(select(PaperFullTextSummary).where(PaperFullTextSummary.arxiv_id.in_(paper_ids))).all()
            if paper_ids
            else []
        )
        return templates.TemplateResponse(
            "papers.html",
            {
                "request": request,
                "day": target_day.isoformat(),
                "papers": papers,
                "summaries_by_paper": {summary.arxiv_id: summary for summary in paper_summaries},
                "full_text_summaries_by_paper": {summary.arxiv_id: summary for summary in full_text_summaries},
                **_day_nav_context(target_day, session),
            },
        )

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

    @app.post("/papers/{arxiv_id:path}/summarize-all")
    def summarize_paper_all(
        arxiv_id: str,
        force: bool = Form(False),
        session: Session = Depends(get_session),
    ) -> RedirectResponse:
        try:
            runtime_settings = resolve_runtime_settings(session, settings)
            generate_abstract_translation(session, arxiv_id, runtime_settings, force=force)
            generate_paper_summary(session, arxiv_id, runtime_settings, force=force)
            generate_paper_full_text_summary(session, arxiv_id, runtime_settings, force=force)
        except Exception as exc:  # pragma: no cover - model/PDF runtime path
            return _redirect(f"/papers/{arxiv_id}", error=_summary_error_message(exc))
        return _redirect(f"/papers/{arxiv_id}", message="三类智能结果已生成。")

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

    return app


app = create_app()
