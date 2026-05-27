from pathlib import Path

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from arxiv_daily.app import create_app
from arxiv_daily.app_settings import resolve_runtime_settings, save_qwen_form
from arxiv_daily.config import Settings
from auth_helpers import authenticated_client


def test_resolve_runtime_settings_prefers_saved_qwen_values(tmp_path: Path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    base = Settings(database_path=tmp_path / "db.sqlite3", qwen_api_key="env-key")

    with Session(engine) as session:
        save_qwen_form(
            session=session,
            api_key="saved-key",
            base_url="https://example.test/v1",
            model="qwen-test",
            vision_model="qwen-vl-test",
            qwen_pdf_model="qwen-doc-test",
            full_text_pdf_upload_enabled=False,
            temperature=0.4,
            max_tokens_single=900,
            max_tokens_full_text=4096,
            full_text_max_chars=80000,
            full_text_figure_limit=9,
        )

        resolved = resolve_runtime_settings(session, base)

    assert resolved.qwen_api_key == "saved-key"
    assert resolved.qwen_base_url == "https://example.test/v1"
    assert resolved.qwen_model == "qwen-test"
    assert resolved.qwen_vision_model == "qwen-vl-test"
    assert resolved.qwen_pdf_model == "qwen-doc-test"
    assert resolved.full_text_pdf_upload_enabled is False
    assert resolved.qwen_temperature == 0.4
    assert resolved.qwen_max_tokens_single == 900
    assert resolved.qwen_max_tokens_full_text == 4096
    assert resolved.full_text_max_chars == 80000
    assert resolved.full_text_figure_limit == 9


def test_blank_model_keeps_existing_runtime_model(tmp_path: Path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    base = Settings(database_path=tmp_path / "db.sqlite3", qwen_model="base-model")

    with Session(engine) as session:
        save_qwen_form(
            session=session,
            api_key="",
            base_url="https://example.test/v1",
            model="",
            temperature=0.2,
            max_tokens_single=1800,
            max_tokens_full_text=4096,
            full_text_max_chars=90000,
            full_text_figure_limit=20,
            full_text_pdf_upload_enabled=True,
        )

        resolved = resolve_runtime_settings(session, base)

    assert resolved.qwen_model == "base-model"
    assert resolved.full_text_figure_limit == 12


def test_settings_form_allows_missing_optional_model(tmp_path: Path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    settings = Settings(database_path=tmp_path / "db.sqlite3", qwen_model="base-model")
    app = create_app(settings=settings, engine=engine)

    response = authenticated_client(app, engine).post(
        "/settings/qwen",
        data={
            "base_url": "https://example.test/v1",
            "temperature": "0.2",
            "max_tokens_single": "1800",
            "max_tokens_full_text": "4096",
            "full_text_max_chars": "90000",
            "full_text_figure_limit": "6",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    with Session(engine) as session:
        resolved = resolve_runtime_settings(session, settings)
    assert resolved.qwen_model == "base-model"
    assert resolved.qwen_base_url == "https://example.test/v1"
    assert resolved.full_text_figure_limit == 6
    assert resolved.full_text_pdf_upload_enabled is True
