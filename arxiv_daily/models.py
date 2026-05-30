from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _loads_list(raw: str) -> List[Any]:
    try:
        value = json.loads(raw or "[]")
        return value if isinstance(value, list) else []
    except json.JSONDecodeError:
        return []


class Category(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(index=True, unique=True)
    enabled: bool = True
    created_at: datetime = Field(default_factory=utc_now)


class KeywordGroup(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    weight: float = 1.0
    enabled: bool = True
    created_at: datetime = Field(default_factory=utc_now)


class Keyword(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="keywordgroup.id", index=True)
    value: str = Field(index=True)
    kind: str = Field(default="include", index=True)
    enabled: bool = True
    created_at: datetime = Field(default_factory=utc_now)


class AppSetting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str = Field(sa_column=Column(Text))
    updated_at: datetime = Field(default_factory=utc_now)


class ArxivPageCache(SQLModel, table=True):
    cache_key: str = Field(primary_key=True)
    query: str = Field(index=True)
    start: int = Field(index=True)
    page_size: int
    response_text: str = Field(sa_column=Column(Text))
    fetched_at: datetime = Field(default_factory=utc_now)


class ArxivFetchRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    target_date: str = Field(index=True)
    run_date: str = Field(index=True)
    status: str = Field(default="running", index=True)
    force_refresh: bool = False
    network_requests: int = 0
    cached_pages: int = 0
    saved_papers: int = 0
    message: str = Field(default="", sa_column=Column(Text))
    created_at: datetime = Field(default_factory=utc_now)
    finished_at: Optional[datetime] = None


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    display_name: str = ""
    password_hash: str = Field(sa_column=Column(Text))
    role: str = Field(default="viewer", index=True)
    enabled: bool = Field(default=True, index=True)
    must_change_password: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    last_login_at: Optional[datetime] = None


class UserSession(SQLModel, table=True):
    token_hash: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime = Field(index=True)
    last_seen_at: datetime = Field(default_factory=utc_now)
    revoked_at: Optional[datetime] = Field(default=None, index=True)
    user_agent: str = Field(default="", sa_column=Column(Text))


class UserPaperFavorite(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("user_id", "arxiv_id", name="uq_user_paper_favorite"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    arxiv_id: str = Field(foreign_key="paper.arxiv_id", index=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class Paper(SQLModel, table=True):
    arxiv_id: str = Field(primary_key=True)
    title: str
    abstract: str = Field(sa_column=Column(Text))
    authors_json: str = Field(default="[]", sa_column=Column(Text))
    affiliations_json: str = Field(default="[]", sa_column=Column(Text))
    primary_category: str = Field(default="", index=True)
    categories_json: str = Field(default="[]", sa_column=Column(Text))
    published_at: Optional[datetime] = Field(default=None, index=True)
    updated_at: Optional[datetime] = Field(default=None)
    abs_url: str = ""
    pdf_url: str = ""
    doi: str = ""
    comment: str = ""
    fetched_for_date: str = Field(index=True)
    relevance_score: float = Field(default=0.0, index=True)
    matched_keywords_json: str = Field(default="[]", sa_column=Column(Text))
    created_at: datetime = Field(default_factory=utc_now)
    refreshed_at: datetime = Field(default_factory=utc_now)

    @property
    def authors(self) -> List[str]:
        return [str(item) for item in _loads_list(self.authors_json)]

    @property
    def affiliations(self) -> List[str]:
        values: List[str] = []
        seen = set()
        for item in _loads_list(self.affiliations_json):
            text = str(item).strip()
            if text and text not in seen:
                seen.add(text)
                values.append(text)
        return values

    @property
    def categories(self) -> List[str]:
        return [str(item) for item in _loads_list(self.categories_json)]

    @property
    def matched_keywords(self) -> List[Dict[str, Any]]:
        return [item for item in _loads_list(self.matched_keywords_json) if isinstance(item, dict)]

    @property
    def matched_terms(self) -> str:
        terms = [str(item.get("keyword")) for item in self.matched_keywords if item.get("keyword")]
        return ", ".join(terms)


class PaperSummary(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    arxiv_id: str = Field(foreign_key="paper.arxiv_id", index=True, unique=True)
    content: str = Field(sa_column=Column(Text))
    model: str
    generated_at: datetime = Field(default_factory=utc_now)


class PaperAbstractTranslation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    arxiv_id: str = Field(foreign_key="paper.arxiv_id", index=True, unique=True)
    title_content: str = Field(default="", sa_column=Column(Text))
    content: str = Field(sa_column=Column(Text))
    model: str
    generated_at: datetime = Field(default_factory=utc_now)


class PaperFullTextSummary(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    arxiv_id: str = Field(foreign_key="paper.arxiv_id", index=True, unique=True)
    content: str = Field(sa_column=Column(Text))
    model: str
    source_url: str = ""
    source_chars: int = 0
    used_chars: int = 0
    truncated: bool = False
    figures_json: str = Field(default="[]", sa_column=Column(Text))
    generated_at: datetime = Field(default_factory=utc_now)

    @property
    def figures(self) -> List[Dict[str, Any]]:
        return [item for item in _loads_list(self.figures_json) if isinstance(item, dict)]
