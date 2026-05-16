from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence

from sqlmodel import Session, select

from .models import Keyword, KeywordGroup


@dataclass(frozen=True)
class KeywordRule:
    group_id: int
    group_name: str
    weight: float
    value: str
    kind: str


@dataclass(frozen=True)
class ScoreResult:
    score: float
    matched_keywords: List[Dict[str, object]]
    excluded_keywords: List[Dict[str, object]]

    @property
    def is_relevant(self) -> bool:
        return self.score > 0 and not self.excluded_keywords


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").lower()


def _matches(text: str, keyword: str) -> bool:
    needle = _normalize_text(keyword)
    if not needle:
        return False
    if len(needle) <= 4 and needle.isalnum():
        return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", text) is not None
    return needle in text


def load_keyword_rules(session: Session) -> List[KeywordRule]:
    groups = session.exec(select(KeywordGroup).where(KeywordGroup.enabled == True)).all()  # noqa: E712
    group_map = {group.id: group for group in groups if group.id is not None}
    if not group_map:
        return []

    rules: List[KeywordRule] = []
    keywords = session.exec(select(Keyword).where(Keyword.enabled == True)).all()  # noqa: E712
    for keyword in keywords:
        group = group_map.get(keyword.group_id)
        if group is None:
            continue
        rules.append(
            KeywordRule(
                group_id=int(group.id),
                group_name=group.name,
                weight=group.weight,
                value=keyword.value,
                kind=keyword.kind,
            )
        )
    return rules


def score_text(title: str, abstract: str, rules: Sequence[KeywordRule]) -> ScoreResult:
    text = _normalize_text(f"{title}\n{abstract}")
    matched: List[Dict[str, object]] = []
    excluded: List[Dict[str, object]] = []
    score = 0.0
    seen_include = set()

    for rule in rules:
        if not _matches(text, rule.value):
            continue
        item = {
            "group": rule.group_name,
            "keyword": rule.value,
            "weight": rule.weight,
            "kind": rule.kind,
        }
        if rule.kind == "exclude":
            excluded.append(item)
            continue

        dedupe_key = (rule.group_id, rule.value.lower())
        if dedupe_key in seen_include:
            continue
        seen_include.add(dedupe_key)
        matched.append(item)
        score += float(rule.weight)

    return ScoreResult(score=round(score, 2), matched_keywords=matched, excluded_keywords=excluded)


def collect_terms(rules: Iterable[KeywordRule], kind: str = "include") -> List[str]:
    seen = set()
    terms: List[str] = []
    for rule in rules:
        if rule.kind != kind:
            continue
        key = rule.value.lower()
        if key in seen:
            continue
        seen.add(key)
        terms.append(rule.value)
    return terms

