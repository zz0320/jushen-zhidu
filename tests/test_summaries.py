from datetime import date

from sqlmodel import Session, SQLModel, create_engine

from arxiv_daily.config import Settings
from arxiv_daily import summaries as summary_module
from arxiv_daily.models import Paper, PaperFullTextSummary
from arxiv_daily.pdf_text import FullTextExtraction, PaperFigure
from arxiv_daily.summaries import (
    CompletionResult,
    build_full_text_pdf_messages,
    build_full_text_paper_messages,
    generate_abstract_translation,
    generate_daily_report,
    generate_paper_full_text_summary,
    generate_paper_summary,
    parse_full_text_pdf_result,
    qwen_figure_image_parts,
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
                affiliations_json='["Embodied AI Lab"]',
                fetched_for_date="2026-05-15",
            )
        )
        session.commit()

        def fake_completion(messages, max_tokens):
            assert "Robot Dataset Benchmark" in messages[1]["content"]
            assert "Affiliations: Embodied AI Lab" in messages[1]["content"]
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
            figures=[
                PaperFigure(
                    url="/static/generated/figures/2605.00002v1-figure-1-p2.png",
                    page=2,
                    index=1,
                    caption="PDF 第 2 页图片摘选",
                    source_name="Im1.png",
                    byte_size=20000,
                )
            ],
        )

        def fake_completion(messages, max_tokens):
            user_content = messages[1]["content"]
            if isinstance(user_content, list):
                user_content = user_content[0]["text"]
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
        assert summary.figures[0]["page"] == 2
        assert "figure-1" in summary.figures[0]["url"]
    assert summary.truncated is False


def test_full_text_messages_can_include_qwen_multimodal_images(tmp_path, monkeypatch):
    static_root = tmp_path / "static"
    figure_dir = static_root / "generated" / "figures"
    figure_dir.mkdir(parents=True)
    figure_path = figure_dir / "2605.00005v1-figure-1-p2.png"
    figure_path.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?"
        b"\x00\x05\xfe\x02\xfeA\xef\x9a\x9b\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    monkeypatch.setattr(summary_module, "STATIC_DIR", static_root)
    paper = Paper(
        arxiv_id="2605.00005v1",
        title="Vision Robot Policy",
        abstract="Short abstract.",
        fetched_for_date="2026-05-15",
    )
    extraction = FullTextExtraction(
        text="[Page 2]\nThe architecture is shown in Figure 1.",
        source_url="https://arxiv.org/pdf/2605.00005v1",
        source_chars=52,
        used_chars=52,
        truncated=False,
        figures=[
            PaperFigure(
                url="/static/generated/figures/2605.00005v1-figure-1-p2.png",
                page=2,
                index=1,
                caption="PDF 第 2 页图片摘选",
            )
        ],
    )

    image_parts = qwen_figure_image_parts(extraction.figures)
    messages = build_full_text_paper_messages(paper, extraction, image_parts=image_parts)

    assert image_parts[0]["type"] == "image_url"
    assert image_parts[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert isinstance(messages[1]["content"], list)
    assert "图文线索" in messages[1]["content"][0]["text"]
    assert messages[1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_full_text_pdf_messages_use_file_id_and_pdf_first_prompt():
    paper = Paper(
        arxiv_id="2605.00006v1",
        title="PDF Native Robot Policy",
        abstract="Short abstract.",
        fetched_for_date="2026-05-15",
    )
    extraction = FullTextExtraction(
        text="[Page 1]\nExtracted text.",
        source_url="https://arxiv.org/pdf/2605.00006v1",
        source_chars=28,
        used_chars=28,
        truncated=False,
        figures=[],
    )

    messages = build_full_text_pdf_messages(paper, extraction, "file-abc")

    assert messages[1] == {"role": "system", "content": "fileid://file-abc"}
    assert "必须只输出 JSON" in messages[2]["content"]
    assert "key_image_summary_markdown" in messages[2]["content"]
    assert "关键图片总结" in messages[2]["content"]
    assert "上传的完整 PDF 文件为主" in messages[2]["content"]


def test_parse_full_text_pdf_result_extracts_summary_and_model_selected_figures():
    content = """```json
{"key_image_summary_markdown":"基于 arXiv PDF 原文文件的关键图片总结。\\n\\n图表总结。","key_figures":[{"page":4,"label":"Figure 2","caption":"方法框架","reason":"解释整体架构"},{"page":"bad","label":"","caption":"","reason":""}]}
```"""

    summary, figures = parse_full_text_pdf_result(content)

    assert summary.startswith("基于 arXiv PDF 原文文件的关键图片总结")
    assert figures == [{"page": 4, "label": "Figure 2", "caption": "方法框架", "reason": "解释整体架构"}]


def test_pdf_full_text_summary_uses_model_selected_figures(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    settings = Settings(
        database_path=tmp_path / "test.sqlite3",
        report_dir=tmp_path,
        qwen_api_key="test-key",
        full_text_pdf_upload_enabled=True,
        full_text_figure_limit=3,
    )

    with Session(engine) as session:
        session.add(
            Paper(
                arxiv_id="2605.00007v1",
                title="Model Selected Figures",
                abstract="Short abstract.",
                fetched_for_date="2026-05-15",
                pdf_url="https://arxiv.org/pdf/2605.00007v1",
            )
        )
        session.commit()
        extraction = FullTextExtraction(
            text="[Page 4]\nFigure 2 shows the architecture.",
            source_url="https://arxiv.org/pdf/2605.00007v1",
            source_chars=44,
            used_chars=44,
            truncated=False,
            figures=[
                PaperFigure(
                    url="/static/generated/figures/fallback.jpg",
                    page=1,
                    index=1,
                    caption="fallback",
                )
            ],
        )

        def fake_text_completion(settings, messages, max_tokens, model=None):
            assert "PDF 全文文本提取" in messages[1]["content"]
            return CompletionResult(
                content="基于 PDF 提取正文的文字总结。",
                model="qwen-plus",
            )

        def fake_pdf_completion(settings, paper, extraction, pdf_bytes, max_tokens):
            assert pdf_bytes == b"%PDF fake"
            return CompletionResult(
                content="基于 arXiv PDF 原文文件的关键图片总结。\n\n模型选择了核心图。",
                model="qwen-doc-turbo",
                visuals=[{"page": 4, "label": "Figure 2", "caption": "方法框架", "reason": "解释整体架构"}],
            )

        def fake_render(paper, pdf_bytes, selections, limit):
            assert selections[0]["page"] == 4
            assert limit == 3
            return [
                PaperFigure(
                    url="/static/generated/figures/2605.00007v1-selected-1-p4.jpg",
                    page=4,
                    index=1,
                    caption="Figure 2 · PDF 第 4 页 · 方法框架 · 解释整体架构",
                    source_name="model-selected:Figure 2",
                )
            ]

        monkeypatch.setattr(summary_module, "qwen_completion", fake_text_completion)
        monkeypatch.setattr(summary_module, "qwen_pdf_completion", fake_pdf_completion)
        monkeypatch.setattr(summary_module, "render_paper_pdf_selected_pages", fake_render)

        summary = generate_paper_full_text_summary(
            session,
            "2605.00007v1",
            settings=settings,
            force=True,
            extraction=extraction,
            pdf_bytes=b"%PDF fake",
        )

    assert summary.content == "基于 PDF 提取正文的文字总结。"
    assert summary.model == "qwen-plus + qwen-doc-turbo"
    assert summary.figures[0]["page"] == 4
    assert "selected-1-p4" in summary.figures[0]["url"]
    assert summary.figures[0]["source_name"] == "model-selected:Figure 2"


def test_existing_full_text_summary_backfills_figures_without_model(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    settings = Settings(database_path=tmp_path / "test.sqlite3", report_dir=tmp_path)

    with Session(engine) as session:
        session.add(
            Paper(
                arxiv_id="2605.00004v1",
                title="Existing Full Text",
                abstract="Short abstract.",
                fetched_for_date="2026-05-15",
                pdf_url="https://arxiv.org/pdf/2605.00004v1",
            )
        )
        session.add(
            PaperFullTextSummary(
                arxiv_id="2605.00004v1",
                content="已有全文总结。",
                model="fake-qwen",
                figures_json="[]",
            )
        )
        session.commit()
        extraction = FullTextExtraction(
            text="[Page 1]\nExisting text.",
            source_url="https://arxiv.org/pdf/2605.00004v1",
            source_chars=20,
            used_chars=20,
            truncated=False,
            figures=[
                PaperFigure(
                    url="/static/generated/figures/2605.00004v1-page-2-preview.jpg",
                    page=2,
                    index=1,
                    caption="PDF 第 2 页图文预览",
                )
            ],
        )

        def should_not_call_model(messages, max_tokens):  # pragma: no cover - assertion helper
            raise AssertionError("Existing summary should only backfill figures.")

        summary = generate_paper_full_text_summary(
            session,
            "2605.00004v1",
            settings=settings,
            completion_fn=should_not_call_model,
            extraction=extraction,
        )

        assert summary.content == "已有全文总结。"
        assert summary.figures[0]["caption"] == "PDF 第 2 页图文预览"


def test_generate_abstract_translation_saves_title_and_abstract(tmp_path):
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
            assert "Embodied Robot Translation" in messages[1]["content"]
            assert "A dexterous robot learns from teleoperation." in messages[1]["content"]
            assert "title_zh" in messages[1]["content"]
            assert max_tokens == settings.qwen_max_tokens_single
            return CompletionResult(
                content='{"title_zh":"具身机器人翻译","abstract_zh":"一个灵巧机器人使用 $\\\\pi_{0.5}$ 和 $\\\\pi_0$。"}',
                model="fake-qwen",
            )

        translation = generate_abstract_translation(
            session,
            "2605.00003v1",
            settings=settings,
            completion_fn=fake_completion,
        )

        assert translation.title_content == "具身机器人翻译"
        assert translation.content == "一个灵巧机器人使用 π0.5 和 π0。"
        assert translation.model == "fake-qwen"


def test_generate_daily_report_without_papers_is_local(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    settings = Settings(database_path=tmp_path / "test.sqlite3", report_dir=tmp_path)

    with Session(engine) as session:
        report = generate_daily_report(session, date(2026, 5, 15), settings=settings)

    assert report.model == "local"
    assert "没有匹配" in report.content
