from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, Text
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


class Paper(SQLModel, table=True):
    arxiv_id: str = Field(primary_key=True)
    title: str
    abstract: str = Field(sa_column=Column(Text))
    authors_json: str = Field(default="[]", sa_column=Column(Text))
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
    generated_at: datetime = Field(default_factory=utc_now)


class DailyReport(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    report_date: str = Field(index=True, unique=True)
    content: str = Field(sa_column=Column(Text))
    model: str
    paper_count: int = 0
    generated_at: datetime = Field(default_factory=utc_now)
