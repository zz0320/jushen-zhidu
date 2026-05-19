from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Dict, Iterable, List, Optional

import httpx
from sqlmodel import Session, select

from .config import Settings, get_settings
from .dates import arxiv_date_range
from .models import Category, Paper
from .scoring import KeywordRule, load_keyword_rules, score_text

ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"


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
class FetchResult:
    fetched: int
    saved: int
    skipped_no_keyword: int
    skipped_excluded: int
    query: str


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


def _unique_strings(values: Iterable[str]) -> List[str]:
    unique: List[str] = []
    seen = set()
    for value in values:
        text = re.sub(r"\s+", " ", value or "").strip()
        if text and text not in seen:
            seen.add(text)
            unique.append(text)
    return unique


def parse_atom_feed(xml_text: str) -> List[ArxivEntry]:
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
    return entries


def enabled_categories(session: Session) -> List[str]:
    rows = session.exec(select(Category).where(Category.enabled == True)).all()  # noqa: E712
    return [row.code for row in rows]


def build_search_query(categories: Iterable[str], day: date, timezone_name: str = "Asia/Shanghai") -> str:
    category_terms = [f"cat:{category}" for category in categories]
    if not category_terms:
        raise ValueError("At least one arXiv category must be enabled.")
    category_query = "(" + " OR ".join(category_terms) + ")"
    return f"{category_query} AND submittedDate:{arxiv_date_range(day, timezone_name)}"


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
            return max(settings.arxiv_request_delay_seconds, float(raw_retry_after))
        except ValueError:
            pass
    return min(60.0, settings.arxiv_request_delay_seconds * (2**attempt))


def fetch_papers_for_date(
    session: Session,
    target_day: date,
    settings: Optional[Settings] = None,
    http_get: Optional[Callable[..., httpx.Response]] = None,
    rules: Optional[List[KeywordRule]] = None,
    progress_callback: Optional[ProgressCallback] = None,
    sleep_fn: Optional[SleepFn] = None,
) -> FetchResult:
    settings = settings or get_settings()
    categories = enabled_categories(session)
    rules = rules if rules is not None else load_keyword_rules(session)
    query = build_search_query(categories, target_day, settings.timezone)
    fetched = 0
    saved = 0
    skipped_no_keyword = 0
    skipped_excluded = 0
    external_http_get = http_get is not None
    http_get = http_get or httpx.get
    sleep = sleep_fn or time.sleep
    should_rate_limit = sleep_fn is not None or not external_http_get
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
        delay = max(0.0, settings.arxiv_request_delay_seconds - elapsed)
        if delay <= 0:
            return
        report("waiting", start=start, page=page, percent=percent, wait_seconds=round(delay, 1), retry=False)
        sleep(delay)

    def request_page(start: int, page: int, page_size: int, percent: int) -> httpx.Response:
        nonlocal last_request_at
        attempt = 0
        while True:
            wait_for_rate_limit(start, page, percent)
            response = http_get(
                settings.arxiv_base_url,
                params={
                    "search_query": query,
                    "start": start,
                    "max_results": page_size,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                },
                headers={"User-Agent": "embodied-arxiv-daily/0.1"},
                timeout=settings.request_timeout_seconds,
            )
            last_request_at = time.monotonic()
            if response.status_code != 429:
                response.raise_for_status()
                return response
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
                retry_attempt=attempt + 1,
                retry_count=settings.arxiv_retry_count,
            )
            sleep(wait_seconds)
            last_request_at = None
            attempt += 1

    report("preparing", percent=4)

    for start in range(0, settings.arxiv_max_results, settings.arxiv_page_size):
        page_size = min(settings.arxiv_page_size, settings.arxiv_max_results - start)
        page = start // settings.arxiv_page_size + 1
        request_percent = min(90, int(start / settings.arxiv_max_results * 80) + 8)
        report("requesting", start=start, page=page, percent=request_percent)
        response = request_page(start, page, page_size, request_percent)
        entries = parse_atom_feed(response.text)
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
            created = _upsert_paper(
                session=session,
                entry=entry,
                target_day=target_day,
                score=score.score,
                matched_keywords=score.matched_keywords,
            )
            if created:
                saved += 1

        session.commit()
        report("saving", start=start, page=page, percent=min(95, int((start + len(entries)) / settings.arxiv_max_results * 85) + 10))
        if len(entries) < page_size:
            break

    report("complete", percent=100, page=min(total_pages, (fetched // settings.arxiv_page_size) + 1))
    return FetchResult(
        fetched=fetched,
        saved=saved,
        skipped_no_keyword=skipped_no_keyword,
        skipped_excluded=skipped_excluded,
        query=query,
    )
