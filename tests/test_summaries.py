from datetime import date

from sqlmodel import Session, SQLModel, create_engine

from arxiv_daily.config import Settings
from arxiv_daily.models import Paper
from arxiv_daily.pdf_text import FullTextExtraction
from arxiv_daily.summaries import (
    CompletionResult,
    generate_abstract_translation,
    generate_daily_report,
    generate_paper_full_text_summary,
    generate_paper_summary,
)


def test_generate_paper_summary_uses_injected_completion(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    settings = Settings(database_path=tmp_path / "test.sqlite3", report_dir=tmp_path)

    with Session(engine) as session:
        session.add(
            Paper(
                arxiv_id="2605.00001v1",
                title="Robot Dataset Benchmark",
                abstract="A robot dataset benchmark for manipulation.",
                fetched_for_date="2026-05-15",
            )
        )
        session.commit()

        def fake_completion(messages, max_tokens):
            assert "Robot Dataset Benchmark" in messages[1]["content"]
            assert max_tokens == settings.qwen_max_tokens_single
            return CompletionResult(content="基于 arXiv 元数据和摘要。总结。", model="fake-qwen")

        summary = generate_paper_summary(
            session,
            "2605.00001v1",
            settings=settings,
            completion_fn=fake_completion,
        )

        assert summary.content.startswith("基于 arXiv")
        assert summary.model == "fake-qwen"


def test_generate_paper_full_text_summary_uses_extracted_pdf_text(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    settings = Settings(database_path=tmp_path / "test.sqlite3", report_dir=tmp_path)

    with Session(engine) as session:
        session.add(
            Paper(
                arxiv_id="2605.00002v1",
                title="Full Text Robot Policy",
                abstract="Short abstract.",
                fetched_for_date="2026-05-15",
                pdf_url="https://arxiv.org/pdf/2605.00002v1",
            )
        )
        session.commit()
        extraction = FullTextExtraction(
            text="[Page 1]\nThe method trains a robot policy with force feedback.",
            source_url="https://arxiv.org/pdf/2605.00002v1",
            source_chars=64,
            used_chars=64,
            truncated=False,
        )

        def fake_completion(messages, max_tokens):
            user_content = messages[1]["content"]
            assert "PDF 全文文本提取" in user_content
            assert "force feedback" in user_content
            assert max_tokens == settings.qwen_max_tokens_full_text
            return CompletionResult(content="基于 arXiv PDF 全文文本提取。总结。", model="fake-qwen")

        summary = generate_paper_full_text_summary(
            session,
            "2605.00002v1",
            settings=settings,
            completion_fn=fake_completion,
            extraction=extraction,
        )

        assert summary.content.startswith("基于 arXiv PDF")
        assert summary.model == "fake-qwen"
        assert summary.source_chars == 64
        assert summary.used_chars == 64
    assert summary.truncated is False


def test_generate_abstract_translation_uses_abstract_only(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    settings = Settings(database_path=tmp_path / "test.sqlite3", report_dir=tmp_path)

    with Session(engine) as session:
        session.add(
            Paper(
                arxiv_id="2605.00003v1",
                title="Embodied Robot Translation",
                abstract="A dexterous robot learns from teleoperation.",
                fetched_for_date="2026-05-15",
            )
        )
        session.commit()

        def fake_completion(messages, max_tokens):
            assert "翻译成中文" in messages[1]["content"]
            assert "A dexterous robot learns from teleoperation." in messages[1]["content"]
            assert "项目符号" in messages[1]["content"]
            assert max_tokens == settings.qwen_max_tokens_single
            return CompletionResult(content="一个灵巧机器人从遥操作中学习。", model="fake-qwen")

        translation = generate_abstract_translation(
            session,
            "2605.00003v1",
            settings=settings,
            completion_fn=fake_completion,
        )

        assert translation.content == "一个灵巧机器人从遥操作中学习。"
        assert translation.model == "fake-qwen"


def test_generate_daily_report_without_papers_is_local(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    settings = Settings(database_path=tmp_path / "test.sqlite3", report_dir=tmp_path)

    with Session(engine) as session:
        report = generate_daily_report(session, date(2026, 5, 15), settings=settings)

    assert report.model == "local"
    assert "没有匹配" in report.content
