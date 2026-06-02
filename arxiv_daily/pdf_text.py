from __future__ import annotations

import re
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, List, Optional

import httpx

from .models import Paper

MAX_FULL_TEXT_CHARS = 70_000
PDF_USER_AGENT = "jushen-zhidu/0.1 (+https://arxiv.org)"
PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_FIGURE_OUTPUT_DIR = PACKAGE_DIR / "static" / "generated" / "figures"
DEFAULT_FIGURE_LIMIT = 6
MIN_FIGURE_BYTES = 12_000
FIGURE_PAGE_PATTERN = re.compile(r"\b(?:fig\.?|figure)\s*\d+|图\s*\d+", re.IGNORECASE)


@dataclass(frozen=True)
class PaperFigure:
    url: str
    page: int
    index: int
    caption: str
    source_name: str = ""
    byte_size: int = 0


@dataclass(frozen=True)
class FullTextExtraction:
    text: str
    source_url: str
    source_chars: int
    used_chars: int
    truncated: bool
    figures: List[PaperFigure] = field(default_factory=list)


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
    extract_figures: bool = True,
    figure_limit: int = DEFAULT_FIGURE_LIMIT,
    figure_output_dir: Optional[Path] = None,
) -> FullTextExtraction:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("全文总结需要 pypdf，请先运行：.venv/bin/python -m pip install pypdf") from exc

    reader = PdfReader(BytesIO(pdf_bytes))
    page_texts = []
    candidate_pages = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = normalize_pdf_text(text)
        if text:
            page_texts.append(f"[Page {index}]\n{text}")
            if FIGURE_PAGE_PATTERN.search(text):
                candidate_pages.append(index)

    full_text = "\n\n".join(page_texts).strip()
    if not full_text:
        raise RuntimeError("PDF 文本提取为空，可能是扫描版 PDF 或解析失败。")

    extraction = trim_full_text(full_text, source_url or paper_pdf_url(paper), max_chars=max_chars)
    if not extract_figures:
        return extraction
    figures = extract_paper_pdf_figures(
        paper,
        pdf_bytes,
        output_dir=figure_output_dir or DEFAULT_FIGURE_OUTPUT_DIR,
        limit=figure_limit,
    )
    if not figures:
        figures = render_paper_pdf_figure_pages(
            paper,
            pdf_bytes,
            output_dir=figure_output_dir or DEFAULT_FIGURE_OUTPUT_DIR,
            candidate_pages=candidate_pages,
            limit=figure_limit,
        )
    return FullTextExtraction(
        text=extraction.text,
        source_url=extraction.source_url,
        source_chars=extraction.source_chars,
        used_chars=extraction.used_chars,
        truncated=extraction.truncated,
        figures=figures,
    )


def fetch_paper_full_text(
    paper: Paper,
    max_chars: int = MAX_FULL_TEXT_CHARS,
    figure_limit: int = DEFAULT_FIGURE_LIMIT,
    figure_output_dir: Optional[Path] = None,
) -> FullTextExtraction:
    source_url, pdf_bytes = download_paper_pdf(paper)
    return extract_paper_pdf_text(
        paper,
        pdf_bytes,
        source_url=source_url,
        max_chars=max_chars,
        figure_limit=figure_limit,
        figure_output_dir=figure_output_dir,
    )


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


def figure_static_url(output_dir: Path, filename: str) -> str:
    try:
        relative_dir = output_dir.resolve().relative_to(DEFAULT_FIGURE_OUTPUT_DIR.resolve())
    except ValueError:
        relative_dir = Path()
    if str(relative_dir) in {"", "."}:
        return f"/static/generated/figures/{filename}"
    return f"/static/generated/figures/{relative_dir.as_posix()}/{filename}"


def extract_paper_pdf_figures(
    paper: Paper,
    pdf_bytes: bytes,
    output_dir: Path = DEFAULT_FIGURE_OUTPUT_DIR,
    limit: int = DEFAULT_FIGURE_LIMIT,
    min_bytes: int = MIN_FIGURE_BYTES,
) -> List[PaperFigure]:
    if limit <= 0:
        return []
    try:
        from pypdf import PdfReader
    except ImportError:
        return []

    reader = PdfReader(BytesIO(pdf_bytes))
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_id = re.sub(r"[^0-9A-Za-z_.-]+", "_", paper.arxiv_id)
    figures: List[PaperFigure] = []
    seen_hashes = set()

    for page_index, page in enumerate(reader.pages, start=1):
        try:
            images = list(page.images)
        except Exception:
            continue
        for image in images:
            try:
                data = getattr(image, "data", b"") or b""
            except Exception:
                continue
            if len(data) < min_bytes:
                continue
            signature = (len(data), data[:64])
            if signature in seen_hashes:
                continue
            extension = _image_extension(getattr(image, "name", ""), data)
            if extension not in {"png", "jpg", "jpeg", "webp", "gif"}:
                continue
            seen_hashes.add(signature)
            figure_index = len(figures) + 1
            filename = f"{safe_id}-figure-{figure_index}-p{page_index}.{extension}"
            path = output_dir / filename
            path.write_bytes(data)
            figures.append(
                PaperFigure(
                    url=figure_static_url(output_dir, filename),
                    page=page_index,
                    index=figure_index,
                    caption=f"PDF 第 {page_index} 页图片摘选",
                    source_name=str(getattr(image, "name", "") or ""),
                    byte_size=len(data),
                )
            )
            if len(figures) >= limit:
                return figures
    return figures


def _image_extension(name: str, data: bytes) -> str:
    suffix = Path(name or "").suffix.lower().lstrip(".")
    if suffix in {"png", "jpg", "jpeg", "webp", "gif"}:
        return suffix
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    return suffix


def render_paper_pdf_figure_pages(
    paper: Paper,
    pdf_bytes: bytes,
    output_dir: Path = DEFAULT_FIGURE_OUTPUT_DIR,
    candidate_pages: Optional[List[int]] = None,
    limit: int = DEFAULT_FIGURE_LIMIT,
) -> List[PaperFigure]:
    if limit <= 0:
        return []
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return []

    pdf = None
    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
        page_count = len(pdf)
        pages = _figure_preview_pages(page_count, candidate_pages or [], limit)
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r"[^0-9A-Za-z_.-]+", "_", paper.arxiv_id)
        figures: List[PaperFigure] = []
        for figure_index, page_number in enumerate(pages, start=1):
            try:
                page = pdf[page_number - 1]
                bitmap = page.render(scale=1.8)
                image = bitmap.to_pil()
                image.thumbnail((1200, 1200))
                filename = f"{safe_id}-page-{page_number}-preview.jpg"
                path = output_dir / filename
                image.save(path, format="JPEG", quality=86, optimize=True)
                figures.append(
                    PaperFigure(
                        url=figure_static_url(output_dir, filename),
                        page=page_number,
                        index=figure_index,
                        caption=f"PDF 第 {page_number} 页图文预览",
                        source_name=f"page-{page_number}",
                        byte_size=path.stat().st_size,
                    )
                )
            except Exception:
                continue
        return figures
    finally:
        if pdf is not None:
            try:
                pdf.close()
            except Exception:
                pass


def render_paper_pdf_selected_pages(
    paper: Paper,
    pdf_bytes: bytes,
    selections: List[dict],
    output_dir: Path = DEFAULT_FIGURE_OUTPUT_DIR,
    limit: int = DEFAULT_FIGURE_LIMIT,
) -> List[PaperFigure]:
    if limit <= 0 or not selections:
        return []
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return []

    pdf = None
    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
        page_count = len(pdf)
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r"[^0-9A-Za-z_.-]+", "_", paper.arxiv_id)
        figures: List[PaperFigure] = []
        seen_pages = set()
        for selection in selections:
            page_number = _selection_page(selection)
            if page_number is None or page_number < 1 or page_number > page_count or page_number in seen_pages:
                continue
            seen_pages.add(page_number)
            figure_index = len(figures) + 1
            try:
                page = pdf[page_number - 1]
                bitmap = page.render(scale=2.0)
                image = bitmap.to_pil()
                image.thumbnail((1400, 1400))
                filename = f"{safe_id}-selected-{figure_index}-p{page_number}.jpg"
                path = output_dir / filename
                image.save(path, format="JPEG", quality=88, optimize=True)
                label = _selection_text(selection, "label") or _selection_text(selection, "figure") or f"第 {page_number} 页"
                caption = _selected_figure_caption(selection, label, page_number)
                figures.append(
                    PaperFigure(
                        url=figure_static_url(output_dir, filename),
                        page=page_number,
                        index=figure_index,
                        caption=caption,
                        source_name=f"model-selected:{label}",
                        byte_size=path.stat().st_size,
                    )
                )
            except Exception:
                continue
            if len(figures) >= limit:
                return figures
        return figures
    finally:
        if pdf is not None:
            try:
                pdf.close()
            except Exception:
                pass


def _selection_page(selection: dict[str, Any]) -> Optional[int]:
    for key in ("page", "page_number", "pdf_page"):
        value = selection.get(key)
        try:
            if value not in (None, ""):
                return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _selection_text(selection: dict[str, Any], key: str) -> str:
    return str(selection.get(key) or "").strip()


def _selected_figure_caption(selection: dict[str, Any], label: str, page_number: int) -> str:
    caption = _selection_text(selection, "caption")
    reason = _selection_text(selection, "reason")
    parts = [label or f"PDF 第 {page_number} 页", f"PDF 第 {page_number} 页"]
    if caption:
        parts.append(caption)
    if reason:
        parts.append(reason)
    return " · ".join(parts)


def _figure_preview_pages(page_count: int, candidate_pages: List[int], limit: int) -> List[int]:
    pages: List[int] = []
    for page_number in candidate_pages:
        if 1 <= page_number <= page_count and page_number not in pages:
            pages.append(page_number)
        if len(pages) >= limit:
            return pages
    for page_number in range(2, page_count + 1):
        if page_number not in pages:
            pages.append(page_number)
        if len(pages) >= limit:
            return pages
    if page_count >= 1 and 1 not in pages and len(pages) < limit:
        pages.append(1)
    return pages
