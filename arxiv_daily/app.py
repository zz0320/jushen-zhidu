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
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from .arxiv import FetchQuotaExceeded, FetchResult, fetch_papers_for_date, fetch_quota_status
from .auth import (
    ROLE_LABELS,
    active_admin_count,
    clear_login_cookie,
    create_user,
    create_user_session,
    find_user_by_username,
    hash_password,
    normalize_role,
    normalize_username,
    read_current_user,
    request_next_url,
    revoke_session,
    revoke_user_sessions,
    role_allows,
    role_label,
    safe_next_url,
    set_login_cookie,
    user_count,
    validate_password,
    validate_username,
    verify_password,
)
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
    User,
    UserPaperFavorite,
    UserSession,
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
    inline_text_to_html,
    summary_excerpt,
    summary_to_html,
)

PACKAGE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
templates.env.filters["clean_latex"] = clean_latex_text
templates.env.filters["translation_title"] = clean_translation_title
templates.env.filters["translation_text"] = clean_translation_text
templates.env.filters["inline_text"] = inline_text_to_html
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


def _request_path_with_query(request: Request) -> str:
    path = request.url.path
    return f"{path}?{request.url.query}" if request.url.query else path


def _current_user_id(request: Request) -> int:
    current_user = getattr(request.state, "current_user", None)
    return int(current_user.id or 0) if current_user is not None and current_user.id is not None else 0


def _favorite_ids(session: Session, user_id: int, paper_ids: list[str]) -> set[str]:
    if not user_id or not paper_ids:
        return set()
    return set(
        session.exec(
            select(UserPaperFavorite.arxiv_id).where(
                UserPaperFavorite.user_id == user_id,
                UserPaperFavorite.arxiv_id.in_(paper_ids),
            )
        ).all()
    )


def _favorite_count(session: Session, user_id: int) -> int:
    if not user_id:
        return 0
    return len(session.exec(select(UserPaperFavorite.id).where(UserPaperFavorite.user_id == user_id)).all())


def _mark_favorite_tiles(tiles: list[Dict[str, object]], favorite_ids: set[str]) -> None:
    for tile in tiles:
        tile["favorite"] = str(tile.get("arxiv_id") or "") in favorite_ids


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


def _redirect_to_safe_url(next_url: str, **query: object) -> RedirectResponse:
    target = safe_next_url(next_url)
    parts = urllib.parse.urlsplit(target)
    merged_query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    merged_query.update({key: str(value) for key, value in query.items() if value not in (None, "")})
    rebuilt = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(merged_query), parts.fragment))
    return RedirectResponse(rebuilt, status_code=303)


def _is_public_path(path: str) -> bool:
    return path in {"/login", "/setup-admin", "/favicon.ico"} or path.startswith("/static/")


def _is_json_request(path: str, request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return (
        path.startswith("/api/")
        or path.startswith("/fetch-jobs")
        or path.startswith("/summary-jobs")
        or "application/json" in accept
    )


def _required_role_for_request(request: Request) -> str:
    path = request.url.path
    method = request.method.upper()
    if path.startswith("/users") or path.startswith("/settings") or path.startswith("/keywords"):
        return "admin"
    if method == "POST" and (
        path.startswith("/cache")
        or path.startswith("/day-cache")
        or path == "/fetch"
        or path == "/fetch-jobs"
        or path.startswith("/summary-jobs")
        or path.startswith("/paper-abstract")
        or path.startswith("/paper-full-text")
        or (path.startswith("/papers/") and "summarize" in path)
    ):
        return "editor"
    if path.startswith("/fetch-jobs") or path.startswith("/summary-jobs"):
        return "editor"
    return "viewer"


def _auth_redirect_to_login(request: Request) -> RedirectResponse:
    next_url = request_next_url(request) if request.method.upper() == "GET" else "/"
    return _redirect("/login", next=next_url)


def _auth_forbidden_response(request: Request) -> Response:
    if _is_json_request(request.url.path, request):
        return JSONResponse({"error": "权限不足。"}, status_code=403)
    return _redirect("/", error="权限不足。请使用具备对应权限的账号。")


def _is_same_origin_write(request: Request) -> bool:
    if request.method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
        return True
    expected_origin = f"{request.url.scheme}://{request.url.netloc}"
    origin = request.headers.get("origin")
    if origin:
        return origin == expected_origin
    referer = request.headers.get("referer")
    if not referer:
        return True
    parsed = urllib.parse.urlsplit(referer)
    return f"{parsed.scheme}://{parsed.netloc}" == expected_origin


def _csrf_forbidden_response(request: Request) -> Response:
    if _is_json_request(request.url.path, request):
        return JSONResponse({"error": "请求来源不可信。"}, status_code=403)
    return _redirect("/", error="请求来源不可信，请从系统页面重新提交。")


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


def _empty_fetch_message(target_day: Optional[date] = None) -> str:
    if target_day is not None and target_day.weekday() >= 5:
        return (
            f"arXiv 没有返回 {target_day.isoformat()} 的论文。该日期是周末；"
            "arXiv 通常不在周末发布新的公开公告批次，周末提交会进入后续工作日批次。"
        )
    if target_day is not None:
        return (
            f"arXiv 没有返回 {target_day.isoformat()} 的论文；通常是该日期尚未发布新批次、"
            "节假日暂停，或本地日期与 arXiv 公告批次存在时差。"
        )
    return "arXiv 没有返回这一天的论文；通常是该日期尚未发布新批次，或周末/节假日没有新提交。"


def _message_from_fetch(result: FetchResult, target_day: Optional[date] = None) -> str:
    source_note = f"联网请求 {result.network_requests} 次，缓存页 {result.cached_pages} 页。"
    quota_note = ""
    if result.daily_network_fetch_limit > 0:
        quota_note = f" 今日有效拉取额度 {result.daily_network_fetch_used}/{result.daily_network_fetch_limit}。"
    if result.fetched == 0:
        return f"{_empty_fetch_message(target_day)} {source_note}{quota_note}"
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
        _delete_rows(
            session,
            session.exec(select(UserPaperFavorite).where(UserPaperFavorite.arxiv_id.in_(paper_ids))).all(),
        )
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
        "favorites": _delete_rows(session, session.exec(select(UserPaperFavorite)).all()),
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


def _fetch_job_stale_after(job: Dict[str, object], settings: Settings) -> float:
    stale_after = max(90.0, settings.request_timeout_seconds * 3)
    stage = str(job.get("stage") or "")
    if stage in {"waiting", "locked"}:
        try:
            wait_seconds = float(job.get("wait_seconds") or 0.0)
        except (TypeError, ValueError):
            wait_seconds = 0.0
        stale_after = max(stale_after, wait_seconds + settings.request_timeout_seconds + 30.0)
    return stale_after


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


def _forest_data(session: Session, target_day: date, user_id: int = 0) -> Dict[str, object]:
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
    _mark_favorite_tiles(tiles, _favorite_ids(session, user_id, paper_ids))
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

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        path = request.url.path
        request.state.current_user = None
        request.state.auth_session = None
        request.state.auth_session_token_hash = ""
        request.state.role_labels = ROLE_LABELS
        request.state.has_users = False

        if path.startswith("/static/") or path == "/favicon.ico":
            return await call_next(request)
        if not _is_same_origin_write(request):
            return _csrf_forbidden_response(request)

        with Session(engine) as auth_session:
            has_users = user_count(auth_session) > 0
            request.state.has_users = has_users
            if not has_users:
                if path == "/setup-admin":
                    return await call_next(request)
                if _is_json_request(path, request):
                    return JSONResponse({"error": "需要先创建管理员账号。"}, status_code=503)
                return _redirect("/setup-admin", next=request_next_url(request))

            token = request.cookies.get(settings.auth_cookie_name, "")
            current_user, current_session = read_current_user(auth_session, token)
            request.state.current_user = current_user
            request.state.auth_session = current_session
            request.state.auth_session_token_hash = current_session.token_hash if current_session is not None else ""

            if _is_public_path(path):
                return await call_next(request)

            if current_user is None:
                if _is_json_request(path, request):
                    return JSONResponse({"error": "请先登录。"}, status_code=401)
                return _auth_redirect_to_login(request)

            if current_user.must_change_password and path not in {"/account/password", "/logout"}:
                if _is_json_request(path, request):
                    return JSONResponse({"error": "需要先更新密码。"}, status_code=403)
                return _redirect("/account/password", message="首次登录或密码重置后，请先更新密码。")

            required_role = _required_role_for_request(request)
            if not role_allows(current_user.role, required_role):
                return _auth_forbidden_response(request)

        return await call_next(request)

    def get_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    def expire_fetch_job_if_stale(job: Dict[str, object]) -> bool:
        if job.get("status") not in {"queued", "running"}:
            return False
        updated_at = float(job.get("updated_at") or 0.0)
        if time.time() - updated_at <= _fetch_job_stale_after(job, settings):
            return False
        job.update(
            status="failed",
            stage="failed",
            stage_label="抓取失败",
            percent=100,
            error="抓取任务长时间没有进展，请重新抓取。",
            message="抓取任务长时间没有进展，请重新抓取。",
            updated_at=time.time(),
        )
        return True

    def active_fetch_job_for_day_locked(day_text: str) -> Optional[Dict[str, object]]:
        active_jobs = []
        for job in fetch_jobs.values():
            expire_fetch_job_if_stale(job)
            if job.get("day") == day_text and job.get("status") in {"queued", "running"}:
                active_jobs.append(dict(job))
        if not active_jobs:
            return None
        active_jobs.sort(key=lambda job: float(job.get("created_at") or 0.0))
        return active_jobs[-1]

    def active_fetch_job_for_day(day_text: str) -> Optional[Dict[str, object]]:
        with fetch_jobs_lock:
            active_job = active_fetch_job_for_day_locked(day_text)
            if active_job is None:
                return None
            return dict(active_job)

    @app.get("/setup-admin")
    def setup_admin_page(
        request: Request,
        next: str = "/",
        message: str = "",
        error: str = "",
        session: Session = Depends(get_session),
    ) -> Response:
        if user_count(session) > 0:
            return _redirect("/login", next=safe_next_url(next))
        return templates.TemplateResponse(
            "setup_admin.html",
            {
                "request": request,
                "next": safe_next_url(next),
                "message": message,
                "error": error,
            },
        )

    @app.post("/setup-admin")
    def setup_admin(
        request: Request,
        username: str = Form(...),
        display_name: str = Form(""),
        password: str = Form(...),
        password_confirm: str = Form(...),
        next: str = Form("/"),
        session: Session = Depends(get_session),
    ) -> RedirectResponse:
        if user_count(session) > 0:
            return _redirect("/login", next=safe_next_url(next))
        username = normalize_username(username)
        username_error = validate_username(username)
        password_error = validate_password(password, username)
        if username_error:
            return _redirect("/setup-admin", next=safe_next_url(next), error=username_error)
        if password != password_confirm:
            return _redirect("/setup-admin", next=safe_next_url(next), error="两次输入的密码不一致。")
        if password_error:
            return _redirect("/setup-admin", next=safe_next_url(next), error=password_error)
        user = create_user(
            session,
            username=username,
            display_name=display_name,
            password=password,
            role="admin",
            must_change_password=False,
        )
        token = create_user_session(session, user, settings, request.headers.get("user-agent", ""))
        response = _redirect_to_safe_url(next, message="管理员账号已创建。")
        set_login_cookie(response, token, settings)
        return response

    @app.get("/login")
    def login_page(
        request: Request,
        next: str = "/",
        message: str = "",
        error: str = "",
        session: Session = Depends(get_session),
    ) -> Response:
        if user_count(session) == 0:
            return _redirect("/setup-admin", next=safe_next_url(next))
        if request.state.current_user is not None:
            return _redirect(safe_next_url(next))
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "next": safe_next_url(next),
                "message": message,
                "error": error,
            },
        )

    @app.post("/login")
    def login(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        next: str = Form("/"),
        session: Session = Depends(get_session),
    ) -> RedirectResponse:
        user = find_user_by_username(session, username)
        if user is None or not user.enabled or not verify_password(password, user.password_hash):
            return _redirect("/login", next=safe_next_url(next), error="用户名或密码不正确。")
        token = create_user_session(session, user, settings, request.headers.get("user-agent", ""))
        target = "/account/password" if user.must_change_password else safe_next_url(next)
        response = _redirect_to_safe_url(target, message="已登录。")
        set_login_cookie(response, token, settings)
        return response

    @app.post("/logout")
    def logout(request: Request, session: Session = Depends(get_session)) -> RedirectResponse:
        token = request.cookies.get(settings.auth_cookie_name, "")
        revoke_session(session, token)
        response = _redirect("/login", message="已退出登录。")
        clear_login_cookie(response, settings)
        return response

    @app.get("/account/password")
    def account_password_page(request: Request, message: str = "", error: str = "") -> Response:
        return templates.TemplateResponse(
            "account_password.html",
            {"request": request, "message": message, "error": error},
        )

    @app.post("/account/password")
    def update_account_password(
        request: Request,
        current_password: str = Form(...),
        new_password: str = Form(...),
        new_password_confirm: str = Form(...),
        session: Session = Depends(get_session),
    ) -> RedirectResponse:
        current_user = request.state.current_user
        if current_user is None:
            return _redirect("/login")
        user = session.get(User, current_user.id)
        if user is None:
            return _redirect("/login", error="账号不存在，请重新登录。")
        if not verify_password(current_password, user.password_hash):
            return _redirect("/account/password", error="当前密码不正确。")
        if new_password != new_password_confirm:
            return _redirect("/account/password", error="两次输入的新密码不一致。")
        password_error = validate_password(new_password, user.username)
        if password_error:
            return _redirect("/account/password", error=password_error)
        user.password_hash = hash_password(new_password)
        user.must_change_password = False
        user.updated_at = utc_now()
        session.add(user)
        session.commit()
        revoke_user_sessions(
            session,
            user.id or 0,
            keep_token_hash=getattr(request.state, "auth_session_token_hash", ""),
        )
        return _redirect("/account/password", message="密码已更新。")

    @app.get("/users")
    def users_page(request: Request, message: str = "", error: str = "", session: Session = Depends(get_session)) -> Response:
        users = session.exec(select(User).order_by(User.role, User.username)).all()
        active_sessions = session.exec(
            select(UserSession).where(UserSession.revoked_at == None, UserSession.expires_at > utc_now())  # noqa: E711
        ).all()
        active_session_counts: Dict[int, int] = {}
        for auth_session in active_sessions:
            active_session_counts[auth_session.user_id] = active_session_counts.get(auth_session.user_id, 0) + 1
        user_stats = {
            "total": len(users),
            "enabled": sum(1 for user in users if user.enabled),
            "admin": sum(1 for user in users if user.role == "admin"),
            "editor": sum(1 for user in users if user.role == "editor"),
            "viewer": sum(1 for user in users if user.role == "viewer"),
            "must_change_password": sum(1 for user in users if user.must_change_password),
        }
        return templates.TemplateResponse(
            "users.html",
            {
                "request": request,
                "users": users,
                "user_stats": user_stats,
                "role_labels": ROLE_LABELS,
                "active_session_counts": active_session_counts,
                "message": message,
                "error": error,
            },
        )

    @app.post("/users")
    def add_user(
        username: str = Form(...),
        display_name: str = Form(""),
        role: str = Form("viewer"),
        password: str = Form(...),
        password_confirm: str = Form(...),
        session: Session = Depends(get_session),
    ) -> RedirectResponse:
        username = normalize_username(username)
        username_error = validate_username(username)
        password_error = validate_password(password, username)
        if username_error:
            return _redirect("/users", error=username_error)
        if find_user_by_username(session, username) is not None:
            return _redirect("/users", error="该用户名已存在。")
        if password != password_confirm:
            return _redirect("/users", error="两次输入的密码不一致。")
        if password_error:
            return _redirect("/users", error=password_error)
        user = create_user(
            session,
            username=username,
            display_name=display_name,
            password=password,
            role=normalize_role(role),
            must_change_password=True,
        )
        return _redirect("/users", message=f"账号 {user.username} 已创建。")

    @app.post("/users/{user_id}/role")
    def update_user_role(
        request: Request,
        user_id: int,
        role: str = Form(...),
        session: Session = Depends(get_session),
    ) -> RedirectResponse:
        user = session.get(User, user_id)
        if user is None:
            return _redirect("/users", error="账号不存在。")
        if request.state.current_user is not None and request.state.current_user.id == user_id:
            return _redirect("/users", error="不能修改自己的角色。")
        new_role = normalize_role(role)
        if user.role == "admin" and new_role != "admin" and user.enabled and active_admin_count(session) <= 1:
            return _redirect("/users", error="至少需要保留一个启用中的管理员。")
        user.role = new_role
        user.updated_at = utc_now()
        session.add(user)
        session.commit()
        if new_role != "admin":
            revoke_user_sessions(session, user.id or 0)
        return _redirect("/users", message=f"{user.username} 的角色已更新为 {role_label(user.role)}。")

    @app.post("/users/{user_id}/status")
    def toggle_user_status(
        request: Request,
        user_id: int,
        session: Session = Depends(get_session),
    ) -> RedirectResponse:
        user = session.get(User, user_id)
        if user is None:
            return _redirect("/users", error="账号不存在。")
        if request.state.current_user is not None and request.state.current_user.id == user_id:
            return _redirect("/users", error="不能停用自己的账号。")
        if user.role == "admin" and user.enabled and active_admin_count(session) <= 1:
            return _redirect("/users", error="至少需要保留一个启用中的管理员。")
        user.enabled = not user.enabled
        user.updated_at = utc_now()
        session.add(user)
        session.commit()
        if not user.enabled:
            revoke_user_sessions(session, user.id or 0)
        return _redirect("/users", message=f"{user.username} 已{'启用' if user.enabled else '停用'}。")

    @app.post("/users/{user_id}/password")
    def reset_user_password(
        user_id: int,
        password: str = Form(...),
        password_confirm: str = Form(...),
        session: Session = Depends(get_session),
    ) -> RedirectResponse:
        user = session.get(User, user_id)
        if user is None:
            return _redirect("/users", error="账号不存在。")
        if password != password_confirm:
            return _redirect("/users", error="两次输入的密码不一致。")
        password_error = validate_password(password, user.username)
        if password_error:
            return _redirect("/users", error=password_error)
        user.password_hash = hash_password(password)
        user.must_change_password = True
        user.updated_at = utc_now()
        session.add(user)
        session.commit()
        revoke_user_sessions(session, user.id or 0)
        return _redirect("/users", message=f"{user.username} 的密码已重置，下次登录需要改密。")

    @app.post("/users/{user_id}/delete")
    def delete_user(request: Request, user_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
        user = session.get(User, user_id)
        if user is None:
            return _redirect("/users", error="账号不存在。")
        if request.state.current_user is not None and request.state.current_user.id == user_id:
            return _redirect("/users", error="不能删除自己的账号。")
        if user.role == "admin" and user.enabled and active_admin_count(session) <= 1:
            return _redirect("/users", error="至少需要保留一个启用中的管理员。")
        for auth_session in session.exec(select(UserSession).where(UserSession.user_id == user_id)).all():
            session.delete(auth_session)
        for favorite in session.exec(select(UserPaperFavorite).where(UserPaperFavorite.user_id == user_id)).all():
            session.delete(favorite)
        session.delete(user)
        session.commit()
        return _redirect("/users", message=f"账号 {user.username} 已删除。")

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
        user_id = _current_user_id(request)
        favorite_ids = _favorite_ids(session, user_id, paper_ids)
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "current_url": _request_path_with_query(request),
                "day": target_day.isoformat(),
                "papers": papers,
                "favorite_ids": favorite_ids,
                "favorite_count": _favorite_count(session, user_id),
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
        return _redirect("/", day=day, message=_message_from_fetch(result, target_day))

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
            active_job = active_fetch_job_for_day_locked(day)
            if active_job is not None:
                return {"job_id": active_job["id"], "reused": True}
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
                    total_pages = max(1, (settings.arxiv_max_results + settings.arxiv_page_size - 1) // settings.arxiv_page_size)
                    lock_wait_limit = max(
                        900.0,
                        settings.request_timeout_seconds * (settings.arxiv_retry_count + 2),
                        settings.effective_arxiv_request_delay_seconds * total_pages + 120.0,
                    )
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
                        if waited >= lock_wait_limit:
                            raise RuntimeError("另一个抓取任务长时间未释放，请稍后刷新状态或重启服务。")
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
                    latest_day = _latest_day_with_papers(worker_session)
                    redirect_url = f"/?day={urllib.parse.quote(day)}"
                    completion_message = _message_from_fetch(result, target_day)
                    if current_count == 0 and latest_day and latest_day != target_day.isoformat():
                        completion_message = f"{completion_message} 本地最近有论文的日期是 {latest_day}，可手动切换查看。"
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
                    latest_day=latest_day,
                    redirect_url=redirect_url,
                    message=completion_message,
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
            expire_fetch_job_if_stale(job)
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
        data = _forest_data(session, target_day, _current_user_id(request))
        return templates.TemplateResponse(
            "forest.html",
            {
                "request": request,
                "current_url": _request_path_with_query(request),
                "day": target_day.isoformat(),
                "message": message,
                "error": error or date_error,
                **data,
                **_day_nav_context(target_day, session),
            },
        )

    @app.get("/api/forest")
    def forest_api(
        request: Request,
        forest_date: Optional[str] = Query(None, alias="date"),
        filter_key: Optional[str] = Query(None, alias="filter"),
        session: Session = Depends(get_session),
    ) -> Dict[str, object]:
        target_day, date_error = _parse_optional_day(forest_date, settings)
        data = _forest_data(session, target_day, _current_user_id(request))
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
        favorites: bool = Query(False),
        message: str = "",
        error: str = "",
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
        user_id = _current_user_id(request)
        favorite_ids = _favorite_ids(session, user_id, paper_ids)
        if favorites:
            papers = [paper for paper in papers if paper.arxiv_id in favorite_ids]
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
                "current_url": _request_path_with_query(request),
                "day": target_day.isoformat(),
                "papers": papers,
                "favorite_ids": favorite_ids,
                "favorite_count": _favorite_count(session, user_id),
                "favorites_only": favorites,
                "favorites_page": False,
                "message": message,
                "error": error,
                "summaries_by_paper": {summary.arxiv_id: summary for summary in paper_summaries},
                "full_text_summaries_by_paper": {summary.arxiv_id: summary for summary in full_text_summaries},
                **_day_nav_context(target_day, session),
            },
        )

    @app.get("/favorites")
    def favorites_page(
        request: Request,
        message: str = "",
        error: str = "",
        session: Session = Depends(get_session),
    ) -> Response:
        user_id = _current_user_id(request)
        favorite_rows = session.exec(
            select(UserPaperFavorite)
            .where(UserPaperFavorite.user_id == user_id)
            .order_by(UserPaperFavorite.created_at.desc())
        ).all()
        favorite_order = [favorite.arxiv_id for favorite in favorite_rows]
        papers_by_id = {}
        if favorite_order:
            papers = session.exec(select(Paper).where(Paper.arxiv_id.in_(favorite_order))).all()
            papers_by_id = {paper.arxiv_id: paper for paper in papers}
        papers = [papers_by_id[arxiv_id] for arxiv_id in favorite_order if arxiv_id in papers_by_id]
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
        today = parse_day(None, settings.timezone)
        return templates.TemplateResponse(
            "papers.html",
            {
                "request": request,
                "current_url": _request_path_with_query(request),
                "day": today.isoformat(),
                "papers": papers,
                "favorite_ids": set(paper_ids),
                "favorite_count": len(favorite_order),
                "favorites_only": True,
                "favorites_page": True,
                "message": message,
                "error": error,
                "summaries_by_paper": {summary.arxiv_id: summary for summary in paper_summaries},
                "full_text_summaries_by_paper": {summary.arxiv_id: summary for summary in full_text_summaries},
                **_day_nav_context(today, session),
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
        user_id = _current_user_id(request)
        return templates.TemplateResponse(
            "paper.html",
            {
                "request": request,
                "current_url": _request_path_with_query(request),
                "paper": paper,
                "is_favorite": paper.arxiv_id in _favorite_ids(session, user_id, [paper.arxiv_id]),
                "favorite_count": _favorite_count(session, user_id),
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

    @app.post("/papers/{arxiv_id:path}/favorite")
    def toggle_paper_favorite(
        request: Request,
        arxiv_id: str,
        next: str = Form(""),
        session: Session = Depends(get_session),
    ) -> Response:
        current_user = request.state.current_user
        if current_user is None or current_user.id is None:
            return _redirect("/login", next=safe_next_url(next or "/"))
        paper = session.get(Paper, arxiv_id)
        if paper is None:
            if "application/json" in request.headers.get("accept", ""):
                return JSONResponse({"error": "论文不存在。"}, status_code=404)
            return _redirect_to_safe_url(next or "/papers", error="论文不存在。")
        existing = session.exec(
            select(UserPaperFavorite).where(
                UserPaperFavorite.user_id == current_user.id,
                UserPaperFavorite.arxiv_id == arxiv_id,
            )
        ).first()
        if existing is None:
            session.add(UserPaperFavorite(user_id=current_user.id, arxiv_id=arxiv_id))
            favorite = True
            message = "已加入收藏。"
        else:
            session.delete(existing)
            favorite = False
            message = "已取消收藏。"
        session.commit()
        if "application/json" in request.headers.get("accept", ""):
            return JSONResponse(
                {
                    "arxiv_id": arxiv_id,
                    "favorite": favorite,
                    "favorite_count": _favorite_count(session, current_user.id),
                    "message": message,
                }
            )
        return _redirect_to_safe_url(next or f"/papers/{arxiv_id}", message=message)

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
