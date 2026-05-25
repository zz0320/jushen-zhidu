from __future__ import annotations

import json
import hashlib
import os
import re
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

import httpx
from sqlmodel import Session, select

from .config import Settings, get_settings
from .dates import arxiv_submitted_date_query
from .models import ArxivFetchRun, ArxivPageCache, Category, Paper, utc_now
from .scoring import KeywordRule, load_keyword_rules, score_text

ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"
OPENSEARCH_NS = "{http://a9.com/-/spec/opensearch/1.1/}"


@dataclass(frozen=True)
class ArxivEntry:
    arxiv_id: str
    title: str
    abstract: str
    authors: List[str]
    affiliations: List[str]
    primary_category: str
    categories: List[str]
    published_at: Optional[datetime]
    updated_at: Optional[datetime]
    abs_url: str
    pdf_url: str
    doi: str = ""
    comment: str = ""


@dataclass(frozen=True)
class ArxivFeedPage:
    entries: List[ArxivEntry]
    total_results: Optional[int] = None
    start_index: Optional[int] = None
    items_per_page: Optional[int] = None


@dataclass(frozen=True)
class FetchResult:
    fetched: int
    saved: int
    skipped_no_keyword: int
    skipped_excluded: int
    query: str
    network_requests: int = 0
    cached_pages: int = 0
    daily_network_fetch_limit: int = 0
    daily_network_fetch_used: int = 0
    matched: int = 0
    updated: int = 0


@dataclass(frozen=True)
class FetchQuotaStatus:
    target_date: str
    run_date: str
    limit: int
    used: int

    @property
    def unlimited(self) -> bool:
        return self.limit <= 0

    @property
    def remaining(self) -> Optional[int]:
        if self.unlimited:
            return None
        return max(0, self.limit - self.used)


class FetchQuotaExceeded(RuntimeError):
    def __init__(self, status: FetchQuotaStatus) -> None:
        self.status = status
        super().__init__(
            f"{status.target_date} 今日实时抓取次数已用完（{status.used}/{status.limit}）。"
            "请使用本地缓存重算，或明天再实时刷新。"
        )


ProgressCallback = Callable[[Dict[str, object]], None]
SleepFn = Callable[[float], None]


def normalize_arxiv_id(raw_id: str) -> str:
    raw_id = (raw_id or "").strip()
    raw_id = raw_id.rstrip("/")
    if "/abs/" in raw_id:
        raw_id = raw_id.rsplit("/abs/", 1)[1]
    return raw_id


def _text(parent: ET.Element, path: str, default: str = "") -> str:
    value = parent.findtext(path)
    return re.sub(r"\s+", " ", value or default).strip()


def _parse_dt(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_int(value: str) -> Optional[int]:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _unique_strings(values: Iterable[str]) -> List[str]:
    unique: List[str] = []
    seen = set()
    for value in values:
        text = re.sub(r"\s+", " ", value or "").strip()
        if text and text not in seen:
            seen.add(text)
            unique.append(text)
    return unique


def parse_atom_page(xml_text: str) -> ArxivFeedPage:
    root = ET.fromstring(xml_text)
    entries: List[ArxivEntry] = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        raw_id = _text(entry, f"{ATOM_NS}id")
        arxiv_id = normalize_arxiv_id(raw_id)
        links: Dict[str, str] = {"abs": raw_id, "pdf": ""}
        for link in entry.findall(f"{ATOM_NS}link"):
            href = link.attrib.get("href", "")
            rel = link.attrib.get("rel", "")
            title = link.attrib.get("title", "")
            content_type = link.attrib.get("type", "")
            if rel == "alternate" and href:
                links["abs"] = href
            if title == "pdf" or content_type == "application/pdf":
                links["pdf"] = href

        categories = [node.attrib.get("term", "") for node in entry.findall(f"{ATOM_NS}category")]
        categories = [category for category in categories if category]
        primary_category_node = entry.find(f"{ARXIV_NS}primary_category")
        primary_category = ""
        if primary_category_node is not None:
            primary_category = primary_category_node.attrib.get("term", "")
        if not primary_category and categories:
            primary_category = categories[0]

        authors: List[str] = []
        affiliations: List[str] = []
        for author in entry.findall(f"{ATOM_NS}author"):
            author_name = _text(author, f"{ATOM_NS}name")
            if author_name:
                authors.append(author_name)
            for affiliation in author.findall(f"{ARXIV_NS}affiliation"):
                affiliation_text = _text(affiliation, ".")
                if affiliation_text:
                    affiliations.append(affiliation_text)
        affiliations = _unique_strings(affiliations)

        entries.append(
            ArxivEntry(
                arxiv_id=arxiv_id,
                title=_text(entry, f"{ATOM_NS}title"),
                abstract=_text(entry, f"{ATOM_NS}summary"),
                authors=authors,
                affiliations=affiliations,
                primary_category=primary_category,
                categories=categories,
                published_at=_parse_dt(_text(entry, f"{ATOM_NS}published")),
                updated_at=_parse_dt(_text(entry, f"{ATOM_NS}updated")),
                abs_url=links["abs"],
                pdf_url=links["pdf"],
                doi=_text(entry, f"{ARXIV_NS}doi"),
                comment=_text(entry, f"{ARXIV_NS}comment"),
            )
        )
    return ArxivFeedPage(
        entries=entries,
        total_results=_parse_int(_text(root, f"{OPENSEARCH_NS}totalResults")),
        start_index=_parse_int(_text(root, f"{OPENSEARCH_NS}startIndex")),
        items_per_page=_parse_int(_text(root, f"{OPENSEARCH_NS}itemsPerPage")),
    )


def parse_atom_feed(xml_text: str) -> List[ArxivEntry]:
    return parse_atom_page(xml_text).entries


def enabled_categories(session: Session) -> List[str]:
    rows = session.exec(select(Category).where(Category.enabled == True)).all()  # noqa: E712
    return [row.code for row in rows]


def build_search_query(categories: Iterable[str], day: date, timezone_name: str = "Asia/Shanghai") -> str:
    category_terms = [f"cat:{category}" for category in categories]
    if not category_terms:
        raise ValueError("At least one arXiv category must be enabled.")
    category_query = "(" + " OR ".join(category_terms) + ")"
    return f"{category_query} AND {arxiv_submitted_date_query(day, timezone_name)}"


def _upsert_paper(
    session: Session,
    entry: ArxivEntry,
    target_day: date,
    score: float,
    matched_keywords: List[Dict[str, object]],
) -> bool:
    existing = session.get(Paper, entry.arxiv_id)
    payload = {
        "title": entry.title,
        "abstract": entry.abstract,
        "authors_json": json.dumps(entry.authors, ensure_ascii=False),
        "affiliations_json": json.dumps(entry.affiliations, ensure_ascii=False),
        "primary_category": entry.primary_category,
        "categories_json": json.dumps(entry.categories, ensure_ascii=False),
        "published_at": entry.published_at,
        "updated_at": entry.updated_at,
        "abs_url": entry.abs_url,
        "pdf_url": entry.pdf_url,
        "doi": entry.doi,
        "comment": entry.comment,
        "fetched_for_date": target_day.isoformat(),
        "relevance_score": score,
        "matched_keywords_json": json.dumps(matched_keywords, ensure_ascii=False),
        "refreshed_at": utc_now(),
    }
    if existing is None:
        session.add(Paper(arxiv_id=entry.arxiv_id, **payload))
        return True

    for key, value in payload.items():
        setattr(existing, key, value)
    session.add(existing)
    return False


def _retry_after_seconds(response: httpx.Response, attempt: int, settings: Settings) -> float:
    raw_retry_after = response.headers.get("Retry-After", "")
    if raw_retry_after:
        try:
            return max(settings.effective_arxiv_request_delay_seconds, float(raw_retry_after))
        except ValueError:
            try:
                retry_after = parsedate_to_datetime(raw_retry_after)
            except (TypeError, ValueError):
                pass
            else:
                if retry_after.tzinfo is None:
                    retry_after = retry_after.replace(tzinfo=timezone.utc)
                delay = (retry_after - datetime.now(timezone.utc)).total_seconds()
                return max(settings.effective_arxiv_request_delay_seconds, delay)
    return _retry_backoff_seconds(attempt, settings)


def _has_reached_feed_end(start: int, entries_count: int, page_size: int, total_results: Optional[int], max_results: int) -> bool:
    if entries_count < page_size:
        return True
    if total_results is None:
        return False
    result_limit = min(total_results, max_results)
    return start + entries_count >= result_limit


def _retry_backoff_seconds(attempt: int, settings: Settings) -> float:
    return min(300.0, max(settings.arxiv_retry_base_delay_seconds, settings.effective_arxiv_request_delay_seconds) * (2**attempt))


def _current_run_date(settings: Settings) -> str:
    return datetime.now(ZoneInfo(settings.timezone)).date().isoformat()


def _count_network_fetches(session: Session, target_date: str, run_date: str) -> int:
    rows = session.exec(
        select(ArxivFetchRun).where(
            ArxivFetchRun.target_date == target_date,
            ArxivFetchRun.run_date == run_date,
            ArxivFetchRun.status.in_(["running", "completed", "failed"]),
        )
    ).all()
    return sum(1 for row in rows if row.status == "completed" and row.saved_papers > 0)


def fetch_quota_status(
    session: Session,
    target_day: date,
    settings: Optional[Settings] = None,
) -> FetchQuotaStatus:
    settings = settings or get_settings()
    target_date = target_day.isoformat()
    run_date = _current_run_date(settings)
    limit = max(0, settings.arxiv_daily_network_fetch_limit)
    used = _count_network_fetches(session, target_date, run_date)
    return FetchQuotaStatus(target_date=target_date, run_date=run_date, limit=limit, used=used)


def _start_network_fetch(
    session: Session,
    target_day: date,
    settings: Settings,
    force_refresh: bool,
) -> int:
    status = fetch_quota_status(session, target_day, settings)
    if not status.unlimited and status.used >= status.limit:
        raise FetchQuotaExceeded(status)
    run = ArxivFetchRun(
        target_date=status.target_date,
        run_date=status.run_date,
        status="running",
        force_refresh=force_refresh,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    if run.id is None:
        raise RuntimeError("无法记录 arXiv 抓取次数。")
    return int(run.id)


def _finish_network_fetch(
    session: Session,
    run_id: Optional[int],
    status: str,
    network_requests: int,
    cached_pages: int,
    saved_papers: int = 0,
    message: str = "",
) -> None:
    if run_id is None:
        return
    run = session.get(ArxivFetchRun, run_id)
    if run is None:
        return
    run.status = status
    run.network_requests = network_requests
    run.cached_pages = cached_pages
    run.saved_papers = saved_papers
    run.message = message
    run.finished_at = utc_now()
    session.add(run)
    session.commit()


def _page_cache_key(settings: Settings, query: str, start: int, page_size: int) -> str:
    payload = {
        "base_url": settings.arxiv_base_url,
        "query": query,
        "start": start,
        "max_results": page_size,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _age_seconds(value: datetime) -> float:
    timestamp = value
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - timestamp).total_seconds())


def _is_empty_feed(xml_text: str) -> bool:
    try:
        page = parse_atom_page(xml_text)
    except ET.ParseError:
        return False
    if page.total_results == 0:
        return True
    return page.total_results is None and not page.entries


def _empty_cache_ttl_seconds(target_day: date, settings: Settings) -> Optional[float]:
    ttl = settings.arxiv_empty_cache_ttl_seconds
    if ttl <= 0:
        return None
    current_day = date.fromisoformat(_current_run_date(settings))
    if target_day >= current_day - timedelta(days=1):
        return ttl
    return None


def _cached_page_text(
    session: Session,
    cache_key: str,
    force_refresh: bool,
    empty_cache_ttl_seconds: Optional[float] = None,
) -> Optional[str]:
    if force_refresh:
        return None
    cached = session.get(ArxivPageCache, cache_key)
    if cached is None:
        return None
    if (
        empty_cache_ttl_seconds is not None
        and _age_seconds(cached.fetched_at) > empty_cache_ttl_seconds
        and _is_empty_feed(cached.response_text)
    ):
        return None
    return cached.response_text


def _store_page_cache(
    session: Session,
    cache_key: str,
    query: str,
    start: int,
    page_size: int,
    response_text: str,
) -> None:
    cached = session.get(ArxivPageCache, cache_key)
    if cached is None:
        cached = ArxivPageCache(
            cache_key=cache_key,
            query=query,
            start=start,
            page_size=page_size,
            response_text=response_text,
        )
    else:
        cached.query = query
        cached.start = start
        cached.page_size = page_size
        cached.response_text = response_text
        cached.fetched_at = utc_now()
    session.add(cached)
    session.commit()


def _request_with_shared_rate_limit(
    settings: Settings,
    request_fn: Callable[[], httpx.Response],
    sleep: SleepFn,
    wait_callback: Callable[[float], None],
    before_request: Optional[Callable[[], None]] = None,
) -> httpx.Response:
    lock_path = settings.effective_arxiv_rate_limit_path
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import fcntl
    except ImportError:  # pragma: no cover - non-POSIX fallback
        if before_request is not None:
            before_request()
        return request_fn()

    with lock_path.open("a+", encoding="utf-8") as state_file:
        fcntl.flock(state_file.fileno(), fcntl.LOCK_EX)
        try:
            state_file.seek(0)
            raw_last_request = state_file.read().strip()
            try:
                last_request_at = float(raw_last_request) if raw_last_request else 0.0
            except ValueError:
                last_request_at = 0.0

            delay = max(0.0, settings.effective_arxiv_request_delay_seconds - (time.time() - last_request_at))
            if delay > 0:
                wait_callback(delay)
                sleep(delay)

            if before_request is not None:
                before_request()

            try:
                return request_fn()
            finally:
                state_file.seek(0)
                state_file.truncate()
                state_file.write(str(time.time()))
                state_file.flush()
                os.fsync(state_file.fileno())
        finally:
            fcntl.flock(state_file.fileno(), fcntl.LOCK_UN)


def fetch_papers_for_date(
    session: Session,
    target_day: date,
    settings: Optional[Settings] = None,
    http_get: Optional[Callable[..., httpx.Response]] = None,
    rules: Optional[List[KeywordRule]] = None,
    progress_callback: Optional[ProgressCallback] = None,
    sleep_fn: Optional[SleepFn] = None,
    force_refresh: bool = False,
) -> FetchResult:
    settings = settings or get_settings()
    categories = enabled_categories(session)
    rules = rules if rules is not None else load_keyword_rules(session)
    query = build_search_query(categories, target_day, settings.timezone)
    fetched = 0
    saved = 0
    matched = 0
    updated = 0
    skipped_no_keyword = 0
    skipped_excluded = 0
    network_requests = 0
    cached_pages = 0
    network_fetch_run_id: Optional[int] = None
    external_http_get = http_get is not None
    http_get = http_get or httpx.get
    sleep = sleep_fn or time.sleep
    should_rate_limit = sleep_fn is not None or not external_http_get
    should_use_shared_rate_limit = should_rate_limit and not external_http_get
    last_request_at: Optional[float] = None
    total_pages = max(1, (settings.arxiv_max_results + settings.arxiv_page_size - 1) // settings.arxiv_page_size)

    def report(stage: str, start: int = 0, page: int = 0, percent: int = 0, **extra: object) -> None:
        if progress_callback is None:
            return
        payload = {
            "stage": stage,
            "percent": max(0, min(100, percent)),
            "page": page,
            "total_pages": total_pages,
            "fetched": fetched,
            "saved": saved,
            "matched": matched,
            "updated": updated,
            "skipped_no_keyword": skipped_no_keyword,
            "skipped_excluded": skipped_excluded,
            "query": query,
            "start": start,
            "max_results": settings.arxiv_max_results,
        }
        payload.update(extra)
        progress_callback(payload)

    def wait_for_rate_limit(start: int, page: int, percent: int) -> None:
        nonlocal last_request_at
        if not should_rate_limit or last_request_at is None:
            return
        elapsed = time.monotonic() - last_request_at
        delay = max(0.0, settings.effective_arxiv_request_delay_seconds - elapsed)
        if delay <= 0:
            return
        report("waiting", start=start, page=page, percent=percent, wait_seconds=round(delay, 1), retry=False)
        sleep(delay)

    def request_page(start: int, page: int, page_size: int, percent: int) -> str:
        nonlocal last_request_at, network_requests, cached_pages, network_fetch_run_id
        cache_key = _page_cache_key(settings, query, start, page_size)
        if settings.arxiv_cache_enabled:
            cached_text = _cached_page_text(
                session,
                cache_key,
                force_refresh,
                empty_cache_ttl_seconds=_empty_cache_ttl_seconds(target_day, settings),
            )
            if cached_text is not None:
                cached_pages += 1
                report("cached", start=start, page=page, percent=percent, cached_pages=cached_pages)
                return cached_text

        def ensure_network_fetch_started() -> None:
            nonlocal network_fetch_run_id
            if network_fetch_run_id is None:
                network_fetch_run_id = _start_network_fetch(session, target_day, settings, force_refresh)

        attempt = 0
        transient_status_codes = {429, 502, 503, 504}
        while True:
            def do_request() -> httpx.Response:
                return http_get(
                    settings.arxiv_base_url,
                    params={
                        "search_query": query,
                        "start": start,
                        "max_results": page_size,
                        "sortBy": "submittedDate",
                        "sortOrder": "descending",
                    },
                    headers={"User-Agent": settings.arxiv_user_agent},
                    timeout=settings.request_timeout_seconds,
                )

            try:
                if should_use_shared_rate_limit:
                    response = _request_with_shared_rate_limit(
                        settings,
                        do_request,
                        sleep,
                        lambda delay: report(
                            "waiting",
                            start=start,
                            page=page,
                            percent=percent,
                            wait_seconds=round(delay, 1),
                            retry=False,
                            shared=True,
                        ),
                        before_request=ensure_network_fetch_started,
                    )
                else:
                    ensure_network_fetch_started()
                    wait_for_rate_limit(start, page, percent)
                    response = do_request()
                    last_request_at = time.monotonic()
            except httpx.RequestError as exc:
                if attempt >= settings.arxiv_retry_count:
                    raise
                wait_seconds = _retry_backoff_seconds(attempt, settings)
                report(
                    "waiting",
                    start=start,
                    page=page,
                    percent=percent,
                    wait_seconds=round(wait_seconds, 1),
                    retry=True,
                    retry_reason="timeout" if isinstance(exc, httpx.TimeoutException) else "network",
                    retry_attempt=attempt + 1,
                    retry_count=settings.arxiv_retry_count,
                    error=str(exc),
                )
                sleep(wait_seconds)
                last_request_at = None
                attempt += 1
                continue

            network_requests += 1
            if response.status_code not in transient_status_codes:
                response.raise_for_status()
                if settings.arxiv_cache_enabled:
                    _store_page_cache(session, cache_key, query, start, page_size, response.text)
                return response.text
            if attempt >= settings.arxiv_retry_count:
                response.raise_for_status()
            wait_seconds = _retry_after_seconds(response, attempt, settings)
            report(
                "waiting",
                start=start,
                page=page,
                percent=percent,
                wait_seconds=round(wait_seconds, 1),
                retry=True,
                retry_reason="rate_limit" if response.status_code == 429 else "server_busy",
                http_status=response.status_code,
                retry_attempt=attempt + 1,
                retry_count=settings.arxiv_retry_count,
            )
            sleep(wait_seconds)
            last_request_at = None
            attempt += 1

    try:
        report("preparing", percent=4)

        for start in range(0, settings.arxiv_max_results, settings.arxiv_page_size):
            page_size = min(settings.arxiv_page_size, settings.arxiv_max_results - start)
            page = start // settings.arxiv_page_size + 1
            request_percent = min(90, int(start / settings.arxiv_max_results * 80) + 8)
            report("requesting", start=start, page=page, percent=request_percent)
            response_text = request_page(start, page, page_size, request_percent)
            feed_page = parse_atom_page(response_text)
            entries = feed_page.entries
            if not entries:
                report("complete", start=start, page=page, percent=100)
                break

            report("processing", start=start, page=page, percent=min(92, int((start + len(entries)) / settings.arxiv_max_results * 80) + 12))
            fetched += len(entries)
            for entry in entries:
                score = score_text(entry.title, entry.abstract, rules)
                if score.excluded_keywords:
                    skipped_excluded += 1
                    continue
                if not score.matched_keywords:
                    skipped_no_keyword += 1
                    continue
                matched += 1
                created = _upsert_paper(
                    session=session,
                    entry=entry,
                    target_day=target_day,
                    score=score.score,
                    matched_keywords=score.matched_keywords,
                )
                if created:
                    saved += 1
                else:
                    updated += 1

            session.commit()
            report("saving", start=start, page=page, percent=min(95, int((start + len(entries)) / settings.arxiv_max_results * 85) + 10))
            if _has_reached_feed_end(start, len(entries), page_size, feed_page.total_results, settings.arxiv_max_results):
                break
    except Exception as exc:
        _finish_network_fetch(
            session,
            network_fetch_run_id,
            "failed",
            network_requests,
            cached_pages,
            0,
            str(exc),
        )
        raise

    report("complete", percent=100, page=min(total_pages, (fetched // settings.arxiv_page_size) + 1))
    _finish_network_fetch(session, network_fetch_run_id, "completed", network_requests, cached_pages, saved)
    quota = fetch_quota_status(session, target_day, settings)
    return FetchResult(
        fetched=fetched,
        saved=saved,
        matched=matched,
        updated=updated,
        skipped_no_keyword=skipped_no_keyword,
        skipped_excluded=skipped_excluded,
        query=query,
        network_requests=network_requests,
        cached_pages=cached_pages,
        daily_network_fetch_limit=quota.limit,
        daily_network_fetch_used=quota.used,
    )
