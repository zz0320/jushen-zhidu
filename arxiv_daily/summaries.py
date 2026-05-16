from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, List, Optional

from sqlmodel import Session, select

from .config import Settings, get_settings
from .models import DailyReport, Paper, PaperAbstractTranslation, PaperFullTextSummary, PaperSummary, utc_now
from .pdf_text import FullTextExtraction, fetch_paper_full_text
from .text import clean_latex_text


@dataclass(frozen=True)
class CompletionResult:
    content: str
    model: str


CompletionFn = Callable[[List[dict], int], CompletionResult]


def _paper_context(paper: Paper) -> str:
    authors = ", ".join(paper.authors[:8])
    if len(paper.authors) > 8:
        authors += " et al."
    return "\n".join(
        [
            f"arXiv ID: {paper.arxiv_id}",
            f"Title: {clean_latex_text(paper.title)}",
            f"Authors: {authors}",
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


def qwen_completion(settings: Settings, messages: List[dict], max_tokens: int) -> CompletionResult:
    _require_qwen_settings(settings)
    from openai import OpenAI

    client = OpenAI(api_key=settings.qwen_api_key, base_url=settings.qwen_base_url)
    completion = client.chat.completions.create(
        model=settings.qwen_model,
        messages=messages,
        temperature=settings.qwen_temperature,
        max_tokens=max_tokens,
    )
    content = completion.choices[0].message.content or ""
    return CompletionResult(content=content.strip(), model=settings.qwen_model)


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
                "请将下面 arXiv 摘要翻译成中文。只输出译文，不要添加标题、项目符号或额外说明。\n\n"
                f"Title: {clean_latex_text(paper.title)}\n"
                f"Abstract: {paper.abstract}"
            ),
        },
    ]


def build_full_text_paper_messages(paper: Paper, extraction: FullTextExtraction) -> List[dict]:
    basis = "arXiv PDF 全文文本提取"
    if extraction.truncated:
        basis += f"（因文本过长，仅使用前 {extraction.used_chars} / {extraction.source_chars} 字符）"
    return [
        {
            "role": "system",
            "content": (
                "你是具身智能、机器人学习和多模态模型方向的研究助理。"
                "请只基于用户提供的 arXiv 元数据、摘要和 PDF 提取文本总结，不要编造论文中没有的信息。"
                "如果提取文本存在缺页、乱码或截断，请明确说明不确定性。"
                "中文输出，保留关键英文术语。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"请按以下结构进行全文深度总结，并在开头注明：基于 {basis}。\n\n"
                "1. 研究问题\n"
                "2. 方法概述\n"
                "3. 数据 / benchmark\n"
                "4. 机器人平台或任务\n"
                "5. 实验设置与主要结果\n"
                "6. 实现细节或关键设计\n"
                "7. 值得关注点\n"
                "8. 局限性或需要深读的问题\n\n"
                f"{_paper_full_text_context(paper, extraction)}"
            ),
        },
    ]


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
    if existing is not None and not force:
        return existing

    complete = completion_fn or (lambda messages, max_tokens: qwen_completion(settings, messages, max_tokens))
    result = complete(build_abstract_translation_messages(paper), settings.qwen_max_tokens_single)
    if existing is None:
        translation = PaperAbstractTranslation(arxiv_id=arxiv_id, content=result.content, model=result.model)
    else:
        translation = existing
        translation.content = result.content
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
) -> PaperFullTextSummary:
    settings = settings or get_settings()
    paper = session.get(Paper, arxiv_id)
    if paper is None:
        raise ValueError(f"Paper not found: {arxiv_id}")

    existing = session.exec(select(PaperFullTextSummary).where(PaperFullTextSummary.arxiv_id == arxiv_id)).first()
    if existing is not None and not force:
        return existing

    if completion_fn is None:
        _require_qwen_settings(settings)
    extraction = extraction or fetch_paper_full_text(paper, max_chars=settings.full_text_max_chars)
    complete = completion_fn or (lambda messages, max_tokens: qwen_completion(settings, messages, max_tokens))
    result = complete(build_full_text_paper_messages(paper, extraction), settings.qwen_max_tokens_full_text)
    if existing is None:
        summary = PaperFullTextSummary(
            arxiv_id=arxiv_id,
            content=result.content,
            model=result.model,
            source_url=extraction.source_url,
            source_chars=extraction.source_chars,
            used_chars=extraction.used_chars,
            truncated=extraction.truncated,
        )
    else:
        summary = existing
        summary.content = result.content
        summary.model = result.model
        summary.source_url = extraction.source_url
        summary.source_chars = extraction.source_chars
        summary.used_chars = extraction.used_chars
        summary.truncated = extraction.truncated
        summary.generated_at = utc_now()
    session.add(summary)
    session.commit()
    session.refresh(summary)
    return summary


def _truncate_text(value: str, max_chars: int) -> str:
    value = (value or "").strip()
    if len(value) <= max_chars:
        return value
    return value[:max_chars].rstrip() + "..."


def _daily_context(papers: List[Paper], abstract_chars: int) -> str:
    blocks = []
    for index, paper in enumerate(papers, start=1):
        authors = ", ".join(paper.authors[:5])
        if len(paper.authors) > 5:
            authors += " et al."
        abstract = _truncate_text(paper.abstract, abstract_chars)
        blocks.append(
            "\n".join(
                [
                    f"{index}. {clean_latex_text(paper.title)}",
                    f"   arXiv: {paper.arxiv_id}",
                    f"   Authors: {authors}",
                    f"   Category: {paper.primary_category}",
                    f"   Score: {paper.relevance_score}",
                    f"   Keywords: {paper.matched_terms}",
                    f"   Abstract: {abstract}",
                ]
            )
        )
    return "\n\n".join(blocks)


def build_daily_messages(report_date: date, papers: List[Paper], abstract_chars: int = 1200) -> List[dict]:
    return [
        {
            "role": "system",
            "content": (
                "你是具身智能、机器人学习、VLA、world model 和机器人数据集方向的研究助理。"
                "请只基于用户提供的 arXiv 元数据和摘要总结，不要编造。"
                "中文输出，保留关键英文术语，面向需要快速判断是否深读的研究者。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"请生成 {report_date.isoformat()} 的 arXiv 具身智能论文日报。"
                "结构必须包含：\n\n"
                "1. 今日主题趋势\n"
                "2. 重点论文\n"
                "3. 数据集 / benchmark 线索\n"
                "4. VLA / world model / 机器人本体相关亮点\n"
                "5. 建议深读列表\n\n"
                "每篇重点论文给出一句为什么值得关注。"
                "注明：基于 arXiv 元数据和摘要。\n\n"
                f"候选论文如下：\n\n{_daily_context(papers, abstract_chars)}"
            ),
        },
    ]


def generate_daily_report(
    session: Session,
    report_date: date,
    settings: Optional[Settings] = None,
    force: bool = False,
    completion_fn: Optional[CompletionFn] = None,
) -> DailyReport:
    settings = settings or get_settings()
    report_date_text = report_date.isoformat()
    existing = session.exec(select(DailyReport).where(DailyReport.report_date == report_date_text)).first()
    if existing is not None and not force:
        return existing

    papers = session.exec(
        select(Paper)
        .where(Paper.fetched_for_date == report_date_text)
        .order_by(Paper.relevance_score.desc(), Paper.published_at.desc())
    ).all()
    top_papers = list(papers[: settings.daily_top_n])
    if not top_papers:
        content = "当天没有匹配当前关键词配置的论文。"
        model = "local"
    else:
        complete = completion_fn or (lambda messages, max_tokens: qwen_completion(settings, messages, max_tokens))
        result = complete(
            build_daily_messages(report_date, top_papers, settings.daily_abstract_chars),
            settings.qwen_max_tokens_daily,
        )
        content = result.content
        model = result.model

    if existing is None:
        report = DailyReport(
            report_date=report_date_text,
            content=content,
            model=model,
            paper_count=len(top_papers),
        )
    else:
        report = existing
        report.content = content
        report.model = model
        report.paper_count = len(top_papers)
        report.generated_at = utc_now()

    session.add(report)
    session.commit()
    session.refresh(report)
    return report
