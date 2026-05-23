from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Optional

from markupsafe import Markup, escape

ARXIV_ID_PATTERN = re.compile(r"(?<![\w/.-])(?P<prefix>arXiv:\s*)?(?P<id>\d{4}\.\d{4,5}(?:v\d+)?)(?![\w.-])", re.IGNORECASE)
HTML_LINK_SKIP_PATTERN = re.compile(r"(<a\b[^>]*>.*?</a>|<code>.*?</code>)", re.IGNORECASE | re.DOTALL)
MARKDOWN_LINK_SKIP_PATTERN = re.compile(r"(`[^`]*`|\[[^\]]+\]\([^)]+\))")

GREEK_REPLACEMENTS = {
    r"\alpha": "α",
    r"\beta": "β",
    r"\gamma": "γ",
    r"\delta": "δ",
    r"\epsilon": "ε",
    r"\theta": "θ",
    r"\lambda": "λ",
    r"\mu": "μ",
    r"\pi": "π",
    r"\rho": "ρ",
    r"\sigma": "σ",
    r"\tau": "τ",
    r"\phi": "φ",
    r"\omega": "ω",
    r"\Gamma": "Γ",
    r"\Delta": "Δ",
    r"\Theta": "Θ",
    r"\Lambda": "Λ",
    r"\Pi": "Π",
    r"\Sigma": "Σ",
    r"\Phi": "Φ",
    r"\Omega": "Ω",
}
GREEK_CHARACTERS = "".join(GREEK_REPLACEMENTS.values())

LATEX_SYMBOL_REPLACEMENTS = {
    r"\leq": "≤",
    r"\le": "≤",
    r"\geq": "≥",
    r"\ge": "≥",
    r"\lt": "<",
    r"\gt": ">",
    r"\to": "→",
    r"\rightarrow": "→",
    r"\leftarrow": "←",
    r"\times": "×",
    r"\cdot": "·",
    r"\pm": "±",
    r"\approx": "≈",
    r"\sim": "∼",
    r"\infty": "∞",
}

LATEX_COMMANDS_WITH_TEXT = (
    "mathrm",
    "mathbf",
    "mathit",
    "mathsf",
    "text",
    "textrm",
    "textit",
    "textbf",
    "emph",
)

TRANSLATION_TITLE_LABEL_PATTERN = re.compile(r"^\s*(?:#{1,6}\s*)?(?:标题|题目|Title)\s*[:：]", re.IGNORECASE)
TRANSLATION_BODY_LABEL_PATTERN = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:中文译文|译文|摘要|Abstract|Translation|Summary)\s*[:：]\s*",
    re.IGNORECASE,
)
TRANSLATION_BODY_HEADING_PATTERN = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:中文译文|译文|摘要|Abstract|Translation|Summary)\s*$",
    re.IGNORECASE,
)
TRANSLATION_TITLE_CLEAN_PATTERN = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:中文标题|标题译文|题目译文|论文标题|标题|题目|Title)\s*[:：]\s*",
    re.IGNORECASE,
)


def _clean_latex_fragment(value: str) -> str:
    cleaned = value
    for command, replacement in GREEK_REPLACEMENTS.items():
        cleaned = cleaned.replace(command, replacement)
    for command, replacement in LATEX_SYMBOL_REPLACEMENTS.items():
        cleaned = cleaned.replace(command, replacement)
    for command in LATEX_COMMANDS_WITH_TEXT:
        cleaned = re.sub(rf"\\{command}\{{([^{{}}]+)\}}", r"\1", cleaned)
    cleaned = re.sub(r"[_^]\{([^{}]+)\}", r"\1", cleaned)
    cleaned = re.sub(rf"([{re.escape(GREEK_CHARACTERS)}])_([A-Za-z0-9.]+)", r"\1\2", cleaned)
    cleaned = cleaned.replace(r"\&", "&").replace(r"\%", "%").replace(r"\_", "_")
    cleaned = cleaned.replace(r"\,", " ").replace(r"\;", " ").replace(r"\:", " ")
    cleaned = cleaned.replace("{", "").replace("}", "")
    cleaned = re.sub(r"_([<>≤≥][^\s_]+)", r"\1", cleaned)
    cleaned = re.sub(r"\\([A-Za-z]+)", r"\1", cleaned)
    cleaned = re.sub(r"\s*([≤≥<>])\s*", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def clean_latex_text(value: str) -> str:
    """Convert common arXiv title LaTeX snippets to readable plain text."""
    cleaned = html.unescape(value or "")
    cleaned = re.sub(r"\$([^$]{1,120})\$", lambda match: _clean_latex_fragment(match.group(1)), cleaned)
    cleaned = re.sub(r"\\\(([^)]{1,120})\\\)", lambda match: _clean_latex_fragment(match.group(1)), cleaned)
    cleaned = _clean_latex_fragment(cleaned)
    cleaned = cleaned.replace(" - ", " - ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def clean_translation_text(value: str) -> str:
    """Normalize model-generated abstract translations for compact display."""
    text = (value or "").strip()
    text = _drop_leading_translation_title(text)
    for _ in range(4):
        lines = text.splitlines()
        while lines and not lines[0].strip():
            lines.pop(0)
        if lines and TRANSLATION_BODY_HEADING_PATTERN.match(lines[0].strip()):
            lines.pop(0)
            text = "\n".join(lines).strip()
            continue
        cleaned = TRANSLATION_BODY_LABEL_PATTERN.sub("", text).strip()
        if cleaned == text:
            break
        text = cleaned
    return clean_latex_text(text)


def clean_translation_title(value: str) -> str:
    """Normalize model-generated title translations for compact display."""
    text = (value or "").strip()
    text = TRANSLATION_TITLE_CLEAN_PATTERN.sub("", text).strip()
    text = text.strip("\"'“”‘’")
    return clean_latex_text(text)


def summary_excerpt(value: str, max_chars: int = 280) -> str:
    """Turn model-generated markdown-ish summaries into a compact plain-text preview."""
    max_chars = max(40, int(max_chars or 280))
    text = re.sub(r"```.*?```", " ", value or "", flags=re.DOTALL)
    text = re.sub(r"!\[[^\]]*]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)]\([^)]+\)", r"\1", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)
    text = re.sub(r"(\*|_)(.*?)\1", r"\2", text)
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or _is_horizontal_rule(line) or _is_table_line(line):
            continue
        line = re.sub(r"^#{1,6}\s+", "", line)
        line = re.sub(r"^>\s*", "", line)
        line = re.sub(r"^[-*]\s+", "", line)
        line = re.sub(r"^\d+[.、]\s*", "", line)
        if line:
            lines.append(line)
    plain = clean_latex_text(" ".join(lines))
    if len(plain) <= max_chars:
        return plain
    cutoff = max_chars
    for index in range(max_chars, max(int(max_chars * 0.65), 1), -1):
        if plain[index - 1] in "。.!?！？；;，, ":
            cutoff = index
            break
    return plain[:cutoff].rstrip(" ，,；;") + "..."


def _drop_leading_translation_title(value: str) -> str:
    lines = (value or "").splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines or not TRANSLATION_TITLE_LABEL_PATTERN.match(lines[0]):
        return "\n".join(lines).strip()

    body_label = re.search(r"(?:中文译文|译文|摘要|Abstract|Translation|Summary)\s*[:：]", lines[0], re.IGNORECASE)
    if body_label:
        lines[0] = lines[0][body_label.start() :]
    else:
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    return "\n".join(lines).strip()


def summary_to_html(value: str) -> Markup:
    """Render a small, safe subset of markdown-like model output for summaries."""
    lines = (value or "").splitlines()
    html_parts = []
    list_tag = ""
    list_class = ""
    seen_section = False

    def close_list() -> None:
        nonlocal list_tag, list_class
        if list_tag:
            html_parts.append(f"</{list_tag}>")
            list_tag = ""
            list_class = ""

    def ensure_list(tag: str, class_name: str = "") -> None:
        nonlocal list_tag, list_class
        if list_tag == tag and list_class == class_name:
            return
        close_list()
        class_attr = f' class="{class_name}"' if class_name else ""
        html_parts.append(f"<{tag}{class_attr}>")
        list_tag = tag
        list_class = class_name

    i = 0
    while i < len(lines):
        raw_line = lines[i]
        line = raw_line.strip()
        if not line:
            close_list()
            i += 1
            continue

        if _is_table_line(line):
            close_list()
            table_lines = []
            while i < len(lines) and _is_table_line(lines[i].strip()):
                table_lines.append(lines[i].strip())
                i += 1
            html_parts.append(_render_table(table_lines))
            continue

        if _is_horizontal_rule(line):
            close_list()
            html_parts.append('<hr class="summary-divider">')
            i += 1
            continue

        if line.startswith(">"):
            close_list()
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_line = lines[i].strip()[1:].strip()
                if quote_line:
                    quote_lines.append(quote_line)
                i += 1
            callout = _render_callout(quote_lines)
            if callout:
                html_parts.append(callout)
            continue

        heading_match = re.match(r"^#{1,4}\s+(.+)$", line)
        heading_text = heading_match.group(1).strip() if heading_match else line
        numbered_heading = re.match(r"^(\d+)[.、]\s*(.+)$", heading_text)
        bullet = re.match(r"^[-*]\s+(.+)$", line)

        if heading_match and not numbered_heading:
            close_list()
            html_parts.append(f"<h3>{_inline_markup(heading_text)}</h3>")
            seen_section = True
        elif numbered_heading and _is_ranked_ordered_item(numbered_heading.group(2)):
            item_text = _ranked_ordered_item_body(numbered_heading.group(2))
            ensure_list("ol", "summary-ranked-list")
            html_parts.append(f"<li>{_inline_markup(item_text)}</li>")
        elif numbered_heading:
            close_list()
            index, text = numbered_heading.groups()
            html_parts.append(
                f"<h3><span class=\"summary-index\">{escape(index)}</span> {_inline_markup(text)}</h3>"
            )
            seen_section = True
        elif bullet:
            ensure_list("ul")
            html_parts.append(f"<li>{_inline_markup(bullet.group(1))}</li>")
        else:
            close_list()
            paragraph_class = _summary_paragraph_class(line, seen_section)
            class_attr = f' class="{paragraph_class}"' if paragraph_class else ""
            html_parts.append(f"<p{class_attr}>{_inline_markup(line)}</p>")
        i += 1

    close_list()
    return Markup("\n".join(html_parts))


def daily_report_to_html(value: str) -> Markup:
    """Render daily reports as grouped reading cards instead of one long markdown stream."""
    text = strip_first_markdown_heading(value)
    sections = _split_daily_sections(text)
    if not sections:
        return summary_to_html(text)

    parts = ['<div class="daily-report-structured">']
    for section in sections:
        title = section["title"]
        body = section["body"].strip()
        if not title:
            if body:
                parts.append(f'<section class="daily-report-lede">{summary_to_html(body)}</section>')
            continue
        section_type = _daily_section_type(title)
        parts.append(f'<section class="daily-report-section daily-report-section-{section_type}">')
        parts.append('<div class="daily-report-section-head">')
        parts.append(f'<span>{escape(section["index"] or "•")}</span>')
        parts.append(f"<h3>{_inline_markup(title)}</h3>")
        parts.append("</div>")
        if body:
            parts.append(f'<div class="daily-report-section-body">{summary_to_html(body)}</div>')
        parts.append("</section>")
    parts.append("</div>")
    return Markup("\n".join(str(part) for part in parts))


def markdown_to_html(value: str) -> Markup:
    """Render exported daily markdown into a readable, safe preview."""
    lines = (value or "").splitlines()
    html_parts = []
    list_tag = ""
    list_class = ""
    in_code = False
    code_lines = []

    def close_list() -> None:
        nonlocal list_tag, list_class
        if list_tag:
            html_parts.append(f"</{list_tag}>")
            list_tag = ""
            list_class = ""

    def ensure_list(tag: str, class_name: str = "") -> None:
        nonlocal list_tag, list_class
        if list_tag == tag and list_class == class_name:
            return
        close_list()
        class_attr = f' class="{class_name}"' if class_name else ""
        html_parts.append(f"<{tag}{class_attr}>")
        list_tag = tag
        list_class = class_name

    def close_code() -> None:
        nonlocal in_code, code_lines
        if in_code:
            html_parts.append(f"<pre><code>{escape(chr(10).join(code_lines))}</code></pre>")
            code_lines = []
            in_code = False

    i = 0
    while i < len(lines):
        raw_line = lines[i]
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            close_list()
            if in_code:
                close_code()
            else:
                in_code = True
                code_lines = []
            i += 1
            continue

        if in_code:
            code_lines.append(line)
            i += 1
            continue

        if not stripped:
            close_list()
            i += 1
            continue

        if _is_table_line(stripped):
            close_list()
            table_lines = []
            while i < len(lines) and _is_table_line(lines[i].strip()):
                table_lines.append(lines[i].strip())
                i += 1
            html_parts.append(_render_table(table_lines))
            continue

        if _is_horizontal_rule(stripped):
            close_list()
            html_parts.append('<hr class="summary-divider">')
            i += 1
            continue

        if stripped.startswith(">"):
            close_list()
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_line = lines[i].strip()[1:].strip()
                if quote_line:
                    quote_lines.append(quote_line)
                i += 1
            callout = _render_callout(quote_lines)
            if callout:
                html_parts.append(callout)
            continue

        heading_match = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        bullet = re.match(r"^[-*]\s+(.+)$", stripped)
        numbered = re.match(r"^\d+[.、]\s+(.+)$", stripped)

        if heading_match:
            close_list()
            level = min(len(heading_match.group(1)), 3)
            html_parts.append(f"<h{level}>{_inline_markup(heading_match.group(2))}</h{level}>")
        elif bullet:
            ensure_list("ul")
            html_parts.append(f"<li>{_inline_markup(bullet.group(1))}</li>")
        elif numbered:
            item_text = numbered.group(1)
            ranked = _is_ranked_ordered_item(item_text)
            ensure_list("ol", "summary-ranked-list" if ranked else "")
            if ranked:
                item_text = _ranked_ordered_item_body(item_text)
            html_parts.append(f"<li>{_inline_markup(item_text)}</li>")
        else:
            close_list()
            html_parts.append(f"<p>{_inline_markup(stripped)}</p>")
        i += 1

    close_list()
    close_code()
    return Markup("\n".join(html_parts))


def _split_daily_sections(value: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    current = {"index": "", "title": "", "body_lines": []}

    def push_current() -> None:
        if current["title"] or any(line.strip() for line in current["body_lines"]):
            sections.append(
                {
                    "index": current["index"],
                    "title": current["title"],
                    "body": "\n".join(current["body_lines"]).strip(),
                }
            )

    for raw_line in (value or "").splitlines():
        line = raw_line.strip()
        heading = re.match(r"^#{2,4}\s+(.+)$", line)
        if heading:
            title = heading.group(1).strip()
            index_match = re.match(r"^(\d+)[.、]\s*(.+)$", title)
            push_current()
            current = {
                "index": index_match.group(1) if index_match else "",
                "title": index_match.group(2).strip() if index_match else title,
                "body_lines": [],
            }
        else:
            current["body_lines"].append(raw_line)
    push_current()
    return sections


def _daily_section_type(title: str) -> str:
    lowered = (title or "").lower()
    if any(token in lowered for token in ("主题", "趋势", "总览", "结论")):
        return "overview"
    if any(token in lowered for token in ("分类", "关键点", "方向")):
        return "taxonomy"
    if any(token in lowered for token in ("重点", "论文")):
        return "papers"
    if any(token in lowered for token in ("数据", "benchmark", "bench")):
        return "data"
    if any(token in lowered for token in ("vla", "world model", "本体", "亮点", "交叉", "信号")):
        return "signals"
    if any(token in lowered for token in ("深读", "建议", "推荐", "略读", "暂缓")):
        return "reading"
    return "default"


def strip_first_markdown_heading(value: str) -> str:
    lines = (value or "").splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and re.match(r"^#{1,3}\s+", lines[0].strip()):
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    return "\n".join(lines).strip()


def format_datetime(value: Optional[datetime]) -> str:
    if value is None:
        return "-"
    return value.strftime("%Y-%m-%d %H:%M")


def link_arxiv_ids_markdown(value: str) -> str:
    """Link arXiv identifiers in generated markdown without touching existing links or code."""
    output_lines = []
    in_code = False
    for line in (value or "").splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            output_lines.append(line)
            continue
        if in_code:
            output_lines.append(line)
            continue
        output_lines.append(_link_arxiv_ids_markdown_line(line))
    return "\n".join(output_lines)


def _inline_markup(value: str) -> Markup:
    safe = str(escape(_clean_inline_latex(value)))
    safe = re.sub(r"&lt;br\s*/?&gt;", "<br>", safe, flags=re.IGNORECASE)
    safe = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        r'<a href="\2" target="_blank" rel="noreferrer">\1</a>',
        safe,
    )
    safe = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", safe)
    safe = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", safe)
    safe = re.sub(r"`([^`]+)`", r"<code>\1</code>", safe)
    safe = safe.replace("**", "").replace("__", "")
    safe = _link_arxiv_ids_html(safe)
    return Markup(safe)


def _clean_inline_latex(value: str) -> str:
    parts = MARKDOWN_LINK_SKIP_PATTERN.split(value or "")
    return "".join(
        part if MARKDOWN_LINK_SKIP_PATTERN.fullmatch(part) else _clean_inline_latex_segment(part)
        for part in parts
    )


def _clean_inline_latex_segment(value: str) -> str:
    cleaned = re.sub(r"\$\$([^$]{1,240})\$\$", lambda match: _clean_latex_fragment(match.group(1)), value)
    cleaned = re.sub(r"\$([^$\n]{1,160})\$", lambda match: _clean_latex_fragment(match.group(1)), cleaned)
    cleaned = re.sub(r"\\\(([^)]{1,160})\\\)", lambda match: _clean_latex_fragment(match.group(1)), cleaned)
    return cleaned


def _link_arxiv_ids_html(value: str) -> str:
    parts = HTML_LINK_SKIP_PATTERN.split(value)
    return "".join(part if HTML_LINK_SKIP_PATTERN.fullmatch(part) else _link_arxiv_ids_html_segment(part) for part in parts)


def _link_arxiv_ids_html_segment(value: str) -> str:
    def replace(match: re.Match) -> str:
        arxiv_id = match.group("id")
        label = match.group(0)
        return (
            f'<a class="paper-ref" href="https://arxiv.org/abs/{arxiv_id}" '
            f'target="_blank" rel="noreferrer">{label}</a>'
        )

    return ARXIV_ID_PATTERN.sub(replace, value)


def _link_arxiv_ids_markdown_line(value: str) -> str:
    parts = MARKDOWN_LINK_SKIP_PATTERN.split(value)
    return "".join(
        part if MARKDOWN_LINK_SKIP_PATTERN.fullmatch(part) else _link_arxiv_ids_markdown_segment(part)
        for part in parts
    )


def _link_arxiv_ids_markdown_segment(value: str) -> str:
    def replace(match: re.Match) -> str:
        arxiv_id = match.group("id")
        label = match.group(0)
        return f"[{label}](https://arxiv.org/abs/{arxiv_id})"

    return ARXIV_ID_PATTERN.sub(replace, value)


def _summary_paragraph_class(line: str, seen_section: bool) -> str:
    if seen_section:
        return ""
    if re.match(r"^\*\*.+\*\*$", line):
        return "summary-lead"
    if re.match(r"^\*[^*].+\*$", line):
        return "summary-sublead"
    if line.startswith(("（", "(")):
        return "summary-note"
    return ""


def _is_ranked_ordered_item(value: str) -> bool:
    return _ranked_ordered_item_body(value) != (value or "").strip()


def _ranked_ordered_item_body(value: str) -> str:
    text = (value or "").strip()
    patterns = (
        r"^\*\*\s*#\d+\s*\*\*\s*(?:[—–-]+|[:：])?\s*(.+)$",
        r"^#\d+\s*(?:[—–-]+|[:：])\s*(.+)$",
    )
    for pattern in patterns:
        match = re.match(pattern, text)
        if match:
            return match.group(1).strip()
    return text


def _is_horizontal_rule(line: str) -> bool:
    return bool(re.fullmatch(r"[-*_]{3,}", line.strip()))


def _is_table_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.count("|") >= 1


def _split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_table_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def _render_table(table_lines: list[str]) -> str:
    rows = [_split_table_row(line) for line in table_lines if _is_table_line(line)]
    if not rows:
        return ""

    header = []
    body = rows
    if len(rows) >= 2 and _is_table_separator(rows[1]):
        header = rows[0]
        body = rows[2:]

    parts = ['<div class="summary-table-wrap"><table class="summary-table">']
    if header:
        parts.append("<thead><tr>")
        parts.extend(f"<th>{_inline_markup(cell)}</th>" for cell in header)
        parts.append("</tr></thead>")
    if body:
        parts.append("<tbody>")
        for row in body:
            parts.append("<tr>")
            parts.extend(f"<td>{_inline_markup(cell)}</td>" for cell in row)
            parts.append("</tr>")
        parts.append("</tbody>")
    parts.append("</table></div>")
    return "".join(parts)


def _render_callout(lines: list[str]) -> str:
    if not lines:
        return ""
    content = "<br>".join(str(_inline_markup(line)) for line in lines)
    return f'<blockquote class="summary-callout">{content}</blockquote>'
