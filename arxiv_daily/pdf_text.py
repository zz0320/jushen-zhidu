from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO

import httpx

from .models import Paper

MAX_FULL_TEXT_CHARS = 70_000
PDF_USER_AGENT = "embodied-arxiv-daily/0.1 (+https://arxiv.org)"


@dataclass(frozen=True)
class FullTextExtraction:
    text: str
    source_url: str
    source_chars: int
    used_chars: int
    truncated: bool


def paper_pdf_url(paper: Paper) -> str:
    if paper.pdf_url:
        return paper.pdf_url
    return f"https://arxiv.org/pdf/{paper.arxiv_id}"


def download_paper_pdf(paper: Paper, timeout: float = 45.0) -> tuple[str, bytes]:
    source_url = paper_pdf_url(paper)
    with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": PDF_USER_AGENT}) as client:
        response = client.get(source_url)
        response.raise_for_status()
    if not response.content:
        raise RuntimeError("PDF 下载为空，无法进行全文总结。")
    return source_url, response.content


def extract_paper_pdf_text(
    paper: Paper,
    pdf_bytes: bytes,
    source_url: str = "",
    max_chars: int = MAX_FULL_TEXT_CHARS,
) -> FullTextExtraction:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("全文总结需要 pypdf，请先运行：.venv/bin/python -m pip install pypdf") from exc

    reader = PdfReader(BytesIO(pdf_bytes))
    page_texts = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = normalize_pdf_text(text)
        if text:
            page_texts.append(f"[Page {index}]\n{text}")

    full_text = "\n\n".join(page_texts).strip()
    if not full_text:
        raise RuntimeError("PDF 文本提取为空，可能是扫描版 PDF 或解析失败。")

    return trim_full_text(full_text, source_url or paper_pdf_url(paper), max_chars=max_chars)


def fetch_paper_full_text(paper: Paper, max_chars: int = MAX_FULL_TEXT_CHARS) -> FullTextExtraction:
    source_url, pdf_bytes = download_paper_pdf(paper)
    return extract_paper_pdf_text(paper, pdf_bytes, source_url=source_url, max_chars=max_chars)


def trim_full_text(text: str, source_url: str, max_chars: int = MAX_FULL_TEXT_CHARS) -> FullTextExtraction:
    normalized = normalize_pdf_text(text)
    source_chars = len(normalized)
    used_text = normalized[:max_chars].strip()
    truncated = source_chars > len(used_text)
    return FullTextExtraction(
        text=used_text,
        source_url=source_url,
        source_chars=source_chars,
        used_chars=len(used_text),
        truncated=truncated,
    )


def normalize_pdf_text(text: str) -> str:
    text = (text or "").replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
