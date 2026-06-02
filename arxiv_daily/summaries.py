from __future__ import annotations

import base64
import json
import mimetypes
import re
import tempfile
from dataclasses import asdict, dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Callable, List, Optional

from sqlmodel import Session, select

from .config import Settings, get_settings
from .models import Paper, PaperAbstractTranslation, PaperFullTextSummary, PaperSummary, utc_now
from .pdf_text import (
    FullTextExtraction,
    download_paper_pdf,
    extract_paper_pdf_text,
    fetch_paper_full_text,
    render_paper_pdf_selected_pages,
)
from .text import clean_latex_text, clean_translation_text, clean_translation_title

PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"
QWEN_FULL_TEXT_IMAGE_LIMIT = 6
QWEN_IMAGE_DATA_URL_MAX_BYTES = 9_500_000


@dataclass(frozen=True)
class CompletionResult:
    content: str
    model: str
    visuals: List[dict] = field(default_factory=list)


CompletionFn = Callable[[List[dict], int], CompletionResult]


def _paper_context(paper: Paper) -> str:
    authors = ", ".join(paper.authors[:8])
    if len(paper.authors) > 8:
        authors += " et al."
    affiliations = "; ".join(paper.affiliations[:6])
    if len(paper.affiliations) > 6:
        affiliations += " 等"
    affiliation_line = f"Affiliations: {affiliations}" if affiliations else "Affiliations: not available from arXiv metadata"
    return "\n".join(
        [
            f"arXiv ID: {paper.arxiv_id}",
            f"Title: {clean_latex_text(paper.title)}",
            f"Authors: {authors}",
            affiliation_line,
            f"Primary category: {paper.primary_category}",
            f"Categories: {', '.join(paper.categories)}",
            f"Matched keywords: {paper.matched_terms}",
            f"Abstract: {paper.abstract}",
        ]
    )


def _paper_full_text_context(paper: Paper, extraction: FullTextExtraction) -> str:
    truncation_note = (
        f"PDF text was truncated from {extraction.source_chars} to {extraction.used_chars} characters."
        if extraction.truncated
        else f"PDF text length: {extraction.used_chars} characters."
    )
    return "\n".join(
        [
            _paper_context(paper),
            f"PDF source: {extraction.source_url}",
            truncation_note,
            "",
            "Extracted PDF text:",
            extraction.text,
        ]
    )


def _require_qwen_settings(settings: Settings) -> None:
    if not settings.qwen_api_key:
        raise RuntimeError("DASHSCOPE_API_KEY is not set. Configure it before generating summaries.")


def qwen_completion(
    settings: Settings,
    messages: List[dict],
    max_tokens: int,
    model: Optional[str] = None,
) -> CompletionResult:
    _require_qwen_settings(settings)
    from openai import OpenAI

    selected_model = model or settings.qwen_model
    client = OpenAI(api_key=settings.qwen_api_key, base_url=settings.qwen_base_url)
    completion = client.chat.completions.create(
        model=selected_model,
        messages=messages,
        temperature=settings.qwen_temperature,
        max_tokens=max_tokens,
    )
    content = completion.choices[0].message.content or ""
    return CompletionResult(content=content.strip(), model=selected_model)


def qwen_pdf_completion(
    settings: Settings,
    paper: Paper,
    extraction: FullTextExtraction,
    pdf_bytes: bytes,
    max_tokens: int,
) -> CompletionResult:
    _require_qwen_settings(settings)
    from openai import OpenAI

    client = OpenAI(api_key=settings.qwen_api_key, base_url=settings.qwen_base_url)
    file_id = ""
    temp_path: Optional[Path] = None
    try:
        safe_id = re.sub(r"[^0-9A-Za-z_.-]+", "_", paper.arxiv_id)
        with tempfile.NamedTemporaryFile(prefix=f"{safe_id}-", suffix=".pdf", delete=False) as temp_file:
            temp_file.write(pdf_bytes)
            temp_path = Path(temp_file.name)
        file_object = client.files.create(file=temp_path, purpose="file-extract")
        file_id = str(file_object.id)
        completion = client.chat.completions.create(
            model=settings.qwen_pdf_model,
            messages=build_full_text_pdf_messages(paper, extraction, file_id),
            temperature=settings.qwen_temperature,
            max_tokens=max_tokens,
        )
        content = completion.choices[0].message.content or ""
        summary_content, visuals = parse_full_text_pdf_result(content)
        return CompletionResult(content=summary_content, model=settings.qwen_pdf_model, visuals=visuals)
    finally:
        if file_id:
            try:
                client.files.delete(file_id)
            except Exception:
                pass
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def build_single_paper_messages(paper: Paper) -> List[dict]:
    return [
        {
            "role": "system",
            "content": (
                "你是具身智能、机器人学习和多模态模型方向的研究助理。"
                "请只基于用户提供的 arXiv 元数据和摘要总结，不要编造论文中没有的信息。"
                "中文输出，保留关键英文术语。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请按以下结构总结这篇论文，并在开头注明：基于 arXiv 元数据和摘要。\n\n"
                "1. 研究问题\n"
                "2. 方法概述\n"
                "3. 数据 / benchmark\n"
                "4. 机器人平台或任务\n"
                "5. 主要结果\n"
                "6. 值得关注点\n"
                "7. 局限性或需要深读的问题\n\n"
                f"{_paper_context(paper)}"
            ),
        },
    ]


def build_abstract_translation_messages(paper: Paper) -> List[dict]:
    return [
        {
            "role": "system",
            "content": (
                "你是专业的英中科研论文翻译助手，熟悉具身智能、机器人学习、VLA 和多模态模型术语。"
                "请忠实翻译，不扩写、不总结、不加入原文没有的信息。"
                "中文为主，保留必要英文术语、缩写、模型名、数据集名和数学符号。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请将下面 arXiv 论文标题和 Abstract 翻译成中文。\n"
                "严格要求：只输出 JSON，不要输出 Markdown、解释或额外文本；"
                "JSON 字段必须是 title_zh 和 abstract_zh；保留必要英文术语、模型名、benchmark 名和链接。\n\n"
                f"Title: {clean_latex_text(paper.title)}\n\n"
                f"Abstract: {clean_latex_text(paper.abstract)}"
            ),
        },
    ]


def parse_abstract_translation_result(content: str) -> tuple[str, str]:
    raw = (content or "").strip()
    json_text = _strip_json_fence(raw)
    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        title = clean_translation_title(
            str(payload.get("title_zh") or payload.get("title") or payload.get("标题") or "")
        )
        abstract = clean_translation_text(
            str(payload.get("abstract_zh") or payload.get("abstract") or payload.get("摘要") or payload.get("content") or "")
        )
        if title or abstract:
            return title, abstract

    return _parse_labeled_translation(raw)


def _strip_json_fence(value: str) -> str:
    text = value.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else text


def _parse_labeled_translation(value: str) -> tuple[str, str]:
    lines = (value or "").splitlines()
    title = ""
    abstract_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if abstract_lines:
                abstract_lines.append("")
            continue
        title_match = re.match(r"^(?:中文标题|标题译文|题目译文|标题|题目|Title)\s*[:：]\s*(.+)$", stripped, re.I)
        if title_match and not title:
            title = clean_translation_title(title_match.group(1))
            continue
        abstract_match = re.match(r"^(?:中文摘要|摘要译文|摘要|译文|Abstract|Translation)\s*[:：]\s*(.*)$", stripped, re.I)
        if abstract_match:
            abstract_lines.append(abstract_match.group(1))
            continue
        abstract_lines.append(stripped)
    abstract = clean_translation_text("\n".join(abstract_lines).strip())
    return title, abstract


def build_full_text_paper_messages(
    paper: Paper,
    extraction: FullTextExtraction,
    image_parts: Optional[List[dict]] = None,
) -> List[dict]:
    basis = "arXiv PDF 全文文本提取"
    if extraction.truncated:
        basis += f"（因文本过长，仅使用前 {extraction.used_chars} / {extraction.source_chars} 字符）"
    image_parts = image_parts or []
    figure_instruction = ""
    if image_parts:
        figure_names = "、".join(f"图 {index}" for index in range(1, len(image_parts) + 1))
        figure_instruction = (
            f"\n你还会收到来自论文 PDF 的图片输入。请按输入顺序称为 {figure_names}，"
            "在总结中加入“图文线索”小节，说明这些图对方法、系统架构、实验或结果的补充信息。"
            "如果某张图看不清、信息不足或与正文关系不明确，请直接说明不确定性，不要臆测。"
        )
    figure_heading = "9. 图文线索\n" if image_parts else ""
    user_text = (
        f"请按以下结构进行全文深度总结，并在开头注明：基于 {basis}。\n\n"
        "1. 研究问题\n"
        "2. 方法概述\n"
        "3. 数据 / benchmark\n"
        "4. 机器人平台或任务\n"
        "5. 实验设置与主要结果\n"
        "6. 实现细节或关键设计\n"
        "7. 值得关注点\n"
        "8. 局限性或需要深读的问题\n"
        f"{figure_heading}\n"
        f"{figure_instruction}\n\n"
        f"{_paper_full_text_context(paper, extraction)}"
    )
    return [
        {
            "role": "system",
            "content": (
                "你是具身智能、机器人学习和多模态模型方向的研究助理。"
                "请只基于用户提供的 arXiv 元数据、摘要、PDF 提取文本和图片总结，不要编造论文中没有的信息。"
                "如果提取文本存在缺页、乱码或截断，请明确说明不确定性。"
                "中文输出，保留关键英文术语。"
            ),
        },
        {
            "role": "user",
            "content": [{"type": "text", "text": user_text}, *image_parts] if image_parts else user_text,
        },
    ]


def build_full_text_pdf_messages(paper: Paper, extraction: FullTextExtraction, file_id: str) -> List[dict]:
    figure_count = len(extraction.figures)
    truncation_note = (
        f"本地文本提取曾截断为 {extraction.used_chars} / {extraction.source_chars} 字符；"
        "但你应优先阅读上传的完整 PDF 文件。"
        if extraction.truncated
        else f"本地文本提取长度为 {extraction.used_chars} 字符；你应优先阅读上传的完整 PDF 文件。"
    )
    return [
        {
            "role": "system",
            "content": (
                "你是具身智能、机器人学习和多模态模型方向的研究助理。"
                "请直接基于上传的论文 PDF 原文进行全文理解，包括正文、图、表、公式和页面结构。"
                "不要只复述摘要，不要编造论文中没有的信息；图表看不清或无法判断时说明不确定性。"
                "中文输出，保留关键英文术语。严格输出 JSON，不要输出 Markdown fence 或额外解释。"
            ),
        },
        {"role": "system", "content": f"fileid://{file_id}"},
        {
            "role": "user",
            "content": (
                "请阅读上传的 arXiv PDF 原文，只完成关键图片总结：选择论文里最核心、最值得展示的图或表所在页面，"
                "并解释每张图/表为什么重要。全文文字总结会由另一次基于 PDF 提取文本的请求生成。"
                "必须只输出 JSON，字段为 key_image_summary_markdown 和 key_figures。\n\n"
                "key_image_summary_markdown 是中文 Markdown 字符串，开头注明：基于 arXiv PDF 原文文件的关键图片总结。"
                "请概括这些核心图表如何支撑方法、系统设计、实验结果或局限性。\n\n"
                "key_figures 是数组，最多 6 个对象，每个对象必须包含："
                "page（PDF 页码，整数，必须尽量填写）、label（如 Figure 2/Table 1/第 5 页架构图）、"
                "caption（这张图或表展示什么）、reason（为什么它是核心图）。"
                "关键图片总结要求：识别论文中最关键的图、表或页面区域，尽量给出 Figure/Table 编号和 PDF 页码；"
                "说明它展示了什么、支撑了哪个方法或实验结论，以及为什么值得读者关注。"
                "如果 PDF 内部图号识别不稳定，请使用“疑似第 N 页图示”这类谨慎表述。\n\n"
                "输出示例格式："
                "{\"key_image_summary_markdown\":\"基于 arXiv PDF 原文文件的关键图片总结。\\n\\n...\","
                "\"key_figures\":[{\"page\":3,\"label\":\"Figure 1\",\"caption\":\"系统框架图\","
                "\"reason\":\"概括方法整体结构\"}]}\n\n"
                f"{_paper_context(paper)}\n"
                f"PDF source: {extraction.source_url}\n"
                f"{truncation_note}\n"
                f"本地页面会展示 {figure_count} 张自动摘取/渲染的论文图片作为阅读辅助；"
                "你的总结仍应以上传的完整 PDF 文件为主。"
            ),
        },
    ]


def parse_full_text_pdf_result(content: str) -> tuple[str, List[dict]]:
    raw = (content or "").strip()
    json_text = _strip_json_fence(raw)
    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError:
        payload = None
    if not isinstance(payload, dict):
        return raw, []

    summary = str(
        payload.get("key_image_summary_markdown")
        or payload.get("visual_summary_markdown")
        or payload.get("summary_markdown")
        or payload.get("summary")
        or payload.get("content")
        or payload.get("关键图片总结")
        or payload.get("全文总结")
        or raw
    ).strip()
    figures_value = (
        payload.get("key_figures")
        or payload.get("key_visuals")
        or payload.get("figures")
        or payload.get("核心图")
        or []
    )
    figures = _normalize_key_figures(figures_value)
    return summary, figures


def _normalize_key_figures(value: object) -> List[dict]:
    if not isinstance(value, list):
        return []
    figures: List[dict] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        page = _optional_positive_int(item.get("page") or item.get("page_number") or item.get("pdf_page"))
        label = str(item.get("label") or item.get("figure") or item.get("name") or "").strip()
        caption = str(item.get("caption") or item.get("description") or item.get("summary") or "").strip()
        reason = str(item.get("reason") or item.get("why") or item.get("importance") or "").strip()
        if page is None and not (label or caption or reason):
            continue
        figures.append({"page": page, "label": label, "caption": caption, "reason": reason})
    return figures


def _optional_positive_int(value: object) -> Optional[int]:
    try:
        parsed = int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
    if parsed is None or parsed < 1:
        return None
    return parsed


def qwen_figure_image_parts(figures: List[object], limit: int = QWEN_FULL_TEXT_IMAGE_LIMIT) -> List[dict]:
    parts: List[dict] = []
    for figure in figures[:limit]:
        url = _figure_value(figure, "url")
        data_url = _figure_data_url(url)
        if not data_url:
            continue
        parts.append({"type": "image_url", "image_url": {"url": data_url}})
    return parts


def _figure_value(figure: object, key: str) -> str:
    if isinstance(figure, dict):
        return str(figure.get(key) or "")
    return str(getattr(figure, key, "") or "")


def _figure_data_url(url: str) -> str:
    path = _figure_path_from_url(url)
    if path is None or not path.exists() or not path.is_file():
        return ""
    payload = _qwen_image_payload(path)
    if payload is None:
        return ""
    mime_type, data = payload
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _figure_path_from_url(url: str) -> Optional[Path]:
    raw = (url or "").strip()
    if raw.startswith("/static/"):
        relative = raw.removeprefix("/static/")
        static_root = STATIC_DIR.resolve()
        path = (static_root / relative).resolve()
        if path == static_root or static_root in path.parents:
            return path
    return None


def _qwen_image_payload(path: Path) -> Optional[tuple[str, bytes]]:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    mime_type = _image_mime_type(path)
    if _base64_size(data) <= QWEN_IMAGE_DATA_URL_MAX_BYTES:
        return mime_type, data
    compact = _compact_image_bytes(data)
    if compact is None:
        return None
    compact_mime, compact_data = compact
    if _base64_size(compact_data) > QWEN_IMAGE_DATA_URL_MAX_BYTES:
        return None
    return compact_mime, compact_data


def _image_mime_type(path: Path) -> str:
    guessed = mimetypes.guess_type(path.name)[0] or ""
    if guessed in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
        return guessed
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if path.suffix.lower() == ".webp":
        return "image/webp"
    if path.suffix.lower() == ".gif":
        return "image/gif"
    return "image/png"


def _base64_size(data: bytes) -> int:
    return ((len(data) + 2) // 3) * 4


def _compact_image_bytes(data: bytes) -> Optional[tuple[str, bytes]]:
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(BytesIO(data)) as image:
            image.thumbnail((1400, 1400))
            if image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")
            output = BytesIO()
            image.save(output, format="JPEG", quality=84, optimize=True)
            return "image/jpeg", output.getvalue()
    except Exception:
        return None


def _full_text_extraction_from_pdf(
    paper: Paper,
    settings: Settings,
    extraction: Optional[FullTextExtraction] = None,
    pdf_bytes: Optional[bytes] = None,
    source_url: str = "",
    figure_output_dir: Optional[Path] = None,
) -> tuple[FullTextExtraction, Optional[bytes]]:
    if extraction is not None:
        return extraction, pdf_bytes
    if pdf_bytes is None:
        source_url, pdf_bytes = download_paper_pdf(paper)
    extraction = extract_paper_pdf_text(
        paper,
        pdf_bytes,
        source_url=source_url,
        max_chars=settings.full_text_max_chars,
        figure_limit=settings.full_text_figure_limit,
        figure_output_dir=figure_output_dir,
    )
    return extraction, pdf_bytes


def generate_paper_summary(
    session: Session,
    arxiv_id: str,
    settings: Optional[Settings] = None,
    force: bool = False,
    completion_fn: Optional[CompletionFn] = None,
) -> PaperSummary:
    settings = settings or get_settings()
    paper = session.get(Paper, arxiv_id)
    if paper is None:
        raise ValueError(f"Paper not found: {arxiv_id}")

    existing = session.exec(select(PaperSummary).where(PaperSummary.arxiv_id == arxiv_id)).first()
    if existing is not None and not force:
        return existing

    complete = completion_fn or (lambda messages, max_tokens: qwen_completion(settings, messages, max_tokens))
    result = complete(build_single_paper_messages(paper), settings.qwen_max_tokens_single)
    if existing is None:
        summary = PaperSummary(arxiv_id=arxiv_id, content=result.content, model=result.model)
    else:
        summary = existing
        summary.content = result.content
        summary.model = result.model
        summary.generated_at = utc_now()
    session.add(summary)
    session.commit()
    session.refresh(summary)
    return summary


def generate_abstract_translation(
    session: Session,
    arxiv_id: str,
    settings: Optional[Settings] = None,
    force: bool = False,
    completion_fn: Optional[CompletionFn] = None,
) -> PaperAbstractTranslation:
    settings = settings or get_settings()
    paper = session.get(Paper, arxiv_id)
    if paper is None:
        raise ValueError(f"Paper not found: {arxiv_id}")

    existing = session.exec(
        select(PaperAbstractTranslation).where(PaperAbstractTranslation.arxiv_id == arxiv_id)
    ).first()
    if existing is not None and not force and existing.title_content:
        return existing

    complete = completion_fn or (lambda messages, max_tokens: qwen_completion(settings, messages, max_tokens))
    result = complete(build_abstract_translation_messages(paper), settings.qwen_max_tokens_single)
    title_content, content = parse_abstract_translation_result(result.content)
    if existing is None:
        translation = PaperAbstractTranslation(
            arxiv_id=arxiv_id,
            title_content=title_content,
            content=content,
            model=result.model,
        )
    else:
        translation = existing
        translation.title_content = title_content
        translation.content = content
        translation.model = result.model
        translation.generated_at = utc_now()
    session.add(translation)
    session.commit()
    session.refresh(translation)
    return translation


def generate_paper_full_text_summary(
    session: Session,
    arxiv_id: str,
    settings: Optional[Settings] = None,
    force: bool = False,
    completion_fn: Optional[CompletionFn] = None,
    extraction: Optional[FullTextExtraction] = None,
    pdf_bytes: Optional[bytes] = None,
    source_url: str = "",
    figure_output_dir: Optional[Path] = None,
) -> PaperFullTextSummary:
    settings = settings or get_settings()
    paper = session.get(Paper, arxiv_id)
    if paper is None:
        raise ValueError(f"Paper not found: {arxiv_id}")

    existing = session.exec(select(PaperFullTextSummary).where(PaperFullTextSummary.arxiv_id == arxiv_id)).first()
    if existing is not None and not force:
        if not existing.figures:
            try:
                extraction = extraction or fetch_paper_full_text(
                    paper,
                    max_chars=settings.full_text_max_chars,
                    figure_limit=settings.full_text_figure_limit,
                    figure_output_dir=figure_output_dir,
                )
            except Exception:
                return existing
            existing.source_url = extraction.source_url or existing.source_url
            existing.source_chars = extraction.source_chars or existing.source_chars
            existing.used_chars = extraction.used_chars or existing.used_chars
            existing.truncated = extraction.truncated
            existing.figures_json = json.dumps([asdict(figure) for figure in extraction.figures], ensure_ascii=False)
            session.add(existing)
            session.commit()
            session.refresh(existing)
        return existing

    if completion_fn is None:
        _require_qwen_settings(settings)
    extraction, pdf_bytes = _full_text_extraction_from_pdf(
        paper,
        settings,
        extraction=extraction,
        pdf_bytes=pdf_bytes,
        source_url=source_url,
        figure_output_dir=figure_output_dir,
    )
    display_figures = extraction.figures
    visual_result: Optional[CompletionResult] = None
    if completion_fn is not None:
        messages = build_full_text_paper_messages(paper, extraction)
        result = completion_fn(messages, settings.qwen_max_tokens_full_text)
    elif settings.full_text_pdf_upload_enabled and pdf_bytes:
        result = qwen_completion(
            settings,
            build_full_text_paper_messages(paper, extraction),
            settings.qwen_max_tokens_full_text,
            model=settings.qwen_model,
        )
        visual_result = qwen_pdf_completion(
            settings,
            paper,
            extraction,
            pdf_bytes,
            settings.qwen_max_tokens_full_text,
        )
        render_kwargs: dict[str, object] = {"limit": settings.full_text_figure_limit}
        if figure_output_dir is not None:
            render_kwargs["output_dir"] = figure_output_dir
        selected_figures = render_paper_pdf_selected_pages(paper, pdf_bytes, visual_result.visuals, **render_kwargs)
        if selected_figures:
            display_figures = selected_figures
    else:
        image_parts = (
            qwen_figure_image_parts(extraction.figures, limit=settings.full_text_figure_limit)
            if settings.qwen_vision_model and settings.full_text_figure_limit > 0
            else []
        )
        selected_model = settings.qwen_vision_model if image_parts else settings.qwen_model
        messages = build_full_text_paper_messages(paper, extraction, image_parts=image_parts)
        result = qwen_completion(settings, messages, settings.qwen_max_tokens_full_text, model=selected_model)
    if existing is None:
        summary = PaperFullTextSummary(
            arxiv_id=arxiv_id,
            content=result.content,
            model=_combined_full_text_model(result.model, visual_result),
            source_url=extraction.source_url,
            source_chars=extraction.source_chars,
            used_chars=extraction.used_chars,
            truncated=extraction.truncated,
            figures_json=json.dumps([asdict(figure) for figure in display_figures], ensure_ascii=False),
        )
    else:
        summary = existing
        summary.content = result.content
        summary.model = _combined_full_text_model(result.model, visual_result)
        summary.source_url = extraction.source_url
        summary.source_chars = extraction.source_chars
        summary.used_chars = extraction.used_chars
        summary.truncated = extraction.truncated
        summary.figures_json = json.dumps([asdict(figure) for figure in display_figures], ensure_ascii=False)
        summary.generated_at = utc_now()
    session.add(summary)
    session.commit()
    session.refresh(summary)
    return summary


def _combined_full_text_model(text_model: str, visual_result: Optional[CompletionResult]) -> str:
    if visual_result is None:
        return text_model
    if not visual_result.model or visual_result.model == text_model:
        return text_model
    return f"{text_model} + {visual_result.model}"
