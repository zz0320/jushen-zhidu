from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from .config import Settings, get_settings
from .models import DailyReport, Paper
from .text import clean_latex_text, link_arxiv_ids_markdown, strip_first_markdown_heading


def render_daily_markdown(session: Session, report_date: date) -> str:
    report_date_text = report_date.isoformat()
    report = session.exec(select(DailyReport).where(DailyReport.report_date == report_date_text)).first()
    papers = session.exec(
        select(Paper)
        .where(Paper.fetched_for_date == report_date_text)
        .order_by(Paper.relevance_score.desc(), Paper.published_at.desc())
    ).all()

    lines = [f"# {report_date_text} arXiv 具身智能论文日报", ""]
    if report:
        report_body = link_arxiv_ids_markdown(strip_first_markdown_heading(report.content).strip())
        lines.extend([report_body, ""])
    else:
        lines.extend(["尚未生成智能日报。", ""])

    lines.extend(["## 命中论文", ""])
    if not papers:
        lines.append("当前日期没有匹配论文。")
        return "\n".join(lines).strip() + "\n"

    for index, paper in enumerate(papers, start=1):
        authors = ", ".join(paper.authors[:6])
        if len(paper.authors) > 6:
            authors += " et al."
        lines.extend(
            [
                f"### {index}. {clean_latex_text(paper.title)}",
                "",
                f"- arXiv: [{paper.arxiv_id}]({paper.abs_url})",
                f"- PDF: {paper.pdf_url or '-'}",
                f"- Authors: {authors}",
                f"- Category: {paper.primary_category}",
                f"- Score: {paper.relevance_score}",
                f"- Matched keywords: {paper.matched_terms or '-'}",
                "",
                paper.abstract,
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def export_daily_markdown(
    session: Session,
    report_date: date,
    settings: Optional[Settings] = None,
) -> Path:
    settings = settings or get_settings()
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    path = settings.report_dir / f"{report_date.isoformat()}.md"
    path.write_text(render_daily_markdown(session, report_date), encoding="utf-8")
    return path
