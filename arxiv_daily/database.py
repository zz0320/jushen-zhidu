from __future__ import annotations

from pathlib import Path
from typing import Optional

from sqlalchemy import text
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
    _migrate_sqlite_schema(engine)


def _migrate_sqlite_schema(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        abstract_translation_columns = connection.execute(
            text("PRAGMA table_info(paperabstracttranslation)")
        ).mappings().all()
        if abstract_translation_columns:
            column_names = {str(column["name"]) for column in abstract_translation_columns}
            if "title_content" not in column_names:
                connection.execute(
                    text("ALTER TABLE paperabstracttranslation ADD COLUMN title_content TEXT NOT NULL DEFAULT ''")
                )

        paper_columns = connection.execute(text("PRAGMA table_info(paper)")).mappings().all()
        if paper_columns:
            column_names = {str(column["name"]) for column in paper_columns}
            if "affiliations_json" not in column_names:
                connection.execute(text("ALTER TABLE paper ADD COLUMN affiliations_json TEXT NOT NULL DEFAULT '[]'"))

        fetch_run_columns = connection.execute(text("PRAGMA table_info(arxivfetchrun)")).mappings().all()
        if fetch_run_columns:
            column_names = {str(column["name"]) for column in fetch_run_columns}
            if "saved_papers" not in column_names:
                connection.execute(text("ALTER TABLE arxivfetchrun ADD COLUMN saved_papers INTEGER NOT NULL DEFAULT 0"))

        full_text_summary_columns = connection.execute(
            text("PRAGMA table_info(paperfulltextsummary)")
        ).mappings().all()
        if full_text_summary_columns:
            column_names = {str(column["name"]) for column in full_text_summary_columns}
            if "figures_json" not in column_names:
                connection.execute(
                    text("ALTER TABLE paperfulltextsummary ADD COLUMN figures_json TEXT NOT NULL DEFAULT '[]'")
                )


def session_for(engine: Engine) -> Session:
    return Session(engine)
