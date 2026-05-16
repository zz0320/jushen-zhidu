from __future__ import annotations

from pathlib import Path
from typing import Optional

from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, Session, create_engine

from .config import Settings, get_settings


def build_engine(settings: Optional[Settings] = None) -> Engine:
    settings = settings or get_settings()
    if settings.database_path != Path(":memory:"):
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
    )


def create_db_and_tables(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)


def session_for(engine: Engine) -> Session:
    return Session(engine)
