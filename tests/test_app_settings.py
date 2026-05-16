from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from arxiv_daily.app_settings import resolve_runtime_settings, save_qwen_form
from arxiv_daily.config import Settings


def test_resolve_runtime_settings_prefers_saved_qwen_values(tmp_path: Path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    base = Settings(database_path=tmp_path / "db.sqlite3", report_dir=tmp_path, qwen_api_key="env-key")

    with Session(engine) as session:
        save_qwen_form(
            session=session,
            api_key="saved-key",
            base_url="https://example.test/v1",
            model="qwen-test",
            temperature=0.4,
            max_tokens_single=900,
            max_tokens_full_text=4096,
            max_tokens_daily=1800,
            daily_top_n=12,
            daily_abstract_chars=900,
            full_text_max_chars=80000,
        )

        resolved = resolve_runtime_settings(session, base)

    assert resolved.qwen_api_key == "saved-key"
    assert resolved.qwen_base_url == "https://example.test/v1"
    assert resolved.qwen_model == "qwen-test"
    assert resolved.qwen_temperature == 0.4
    assert resolved.qwen_max_tokens_single == 900
    assert resolved.qwen_max_tokens_full_text == 4096
    assert resolved.qwen_max_tokens_daily == 1800
    assert resolved.daily_top_n == 12
    assert resolved.daily_abstract_chars == 900
    assert resolved.full_text_max_chars == 80000


def test_blank_model_keeps_existing_runtime_model(tmp_path: Path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    base = Settings(database_path=tmp_path / "db.sqlite3", report_dir=tmp_path, qwen_model="base-model")

    with Session(engine) as session:
        save_qwen_form(
            session=session,
            api_key="",
            base_url="https://example.test/v1",
            model="",
            temperature=0.2,
            max_tokens_single=1800,
            max_tokens_full_text=4096,
            max_tokens_daily=4096,
            daily_top_n=40,
            daily_abstract_chars=1200,
            full_text_max_chars=90000,
        )

        resolved = resolve_runtime_settings(session, base)

    assert resolved.qwen_model == "base-model"
