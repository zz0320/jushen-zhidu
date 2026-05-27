from __future__ import annotations

from sqlmodel import Session, select

from .models import Category, Keyword, KeywordGroup
from .taxonomy import DEFAULT_CATEGORIES, EMBODIED_TOPICS, LEGACY_KEYWORD_GROUP_NAMES

DEFAULT_KEYWORD_GROUPS = [
    {
        "name": topic.label,
        "weight": topic.weight,
        "include": list(topic.include),
        "exclude": list(topic.exclude),
    }
    for topic in EMBODIED_TOPICS
]


def init_default_config(session: Session) -> None:
    default_group_names = {group_data["name"] for group_data in DEFAULT_KEYWORD_GROUPS}

    for code in DEFAULT_CATEGORIES:
        existing = session.exec(select(Category).where(Category.code == code)).first()
        if existing is None:
            session.add(Category(code=code, enabled=True))

    for group_data in DEFAULT_KEYWORD_GROUPS:
        group = session.exec(select(KeywordGroup).where(KeywordGroup.name == group_data["name"])).first()
        if group is None:
            group = KeywordGroup(name=group_data["name"], weight=float(group_data["weight"]), enabled=True)
            session.add(group)
            session.flush()
        for kind in ("include", "exclude"):
            for value in group_data[kind]:
                existing = session.exec(
                    select(Keyword).where(
                        Keyword.group_id == group.id,
                        Keyword.kind == kind,
                        Keyword.value == value,
                    )
                ).first()
                if existing is None:
                    session.add(Keyword(group_id=group.id, kind=kind, value=value, enabled=True))

    for legacy_name in LEGACY_KEYWORD_GROUP_NAMES - default_group_names:
        legacy_group = session.exec(select(KeywordGroup).where(KeywordGroup.name == legacy_name)).first()
        if legacy_group is not None and legacy_group.enabled:
            legacy_group.enabled = False
            session.add(legacy_group)

    session.commit()
