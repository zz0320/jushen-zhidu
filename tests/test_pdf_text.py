from arxiv_daily.models import Paper
from arxiv_daily.pdf_text import normalize_pdf_text, paper_pdf_url, trim_full_text


def test_paper_pdf_url_uses_existing_or_fallback():
    assert paper_pdf_url(Paper(arxiv_id="2605.00001v1", title="A", abstract="B", fetched_for_date="2026-05-15")) == (
        "https://arxiv.org/pdf/2605.00001v1"
    )
    assert (
        paper_pdf_url(
            Paper(
                arxiv_id="2605.00002v1",
                title="A",
                abstract="B",
                fetched_for_date="2026-05-15",
                pdf_url="https://arxiv.org/pdf/2605.00002v1",
            )
        )
        == "https://arxiv.org/pdf/2605.00002v1"
    )


def test_trim_full_text_tracks_truncation():
    extraction = trim_full_text("a" * 20, "https://example.test/paper.pdf", max_chars=12)

    assert extraction.text == "a" * 12
    assert extraction.source_chars == 20
    assert extraction.used_chars == 12
    assert extraction.truncated is True


def test_normalize_pdf_text_compacts_noise():
    assert normalize_pdf_text("A\x00  B\n\n\n\nC") == "A B\n\nC"
