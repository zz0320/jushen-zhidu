from datetime import datetime, timezone

from arxiv_daily.text import (
    clean_latex_text,
    format_datetime,
    link_arxiv_ids_markdown,
    markdown_to_html,
    strip_first_markdown_heading,
    summary_to_html,
)


def test_clean_latex_text_converts_arxiv_math_title():
    assert clean_latex_text(r"VGGT-$\Omega$: A Robot Benchmark") == "VGGT-Ω: A Robot Benchmark"
    assert clean_latex_text("VGGT-$Ω$") == "VGGT-Ω"
    assert clean_latex_text(r"History $o_{\leq t}$ and $a_{<t}$") == "History o≤t and a<t"


def test_clean_latex_text_unwraps_text_commands():
    assert clean_latex_text(r"\textbf{Robot} \& \mathrm{World} Models") == "Robot & World Models"


def test_summary_to_html_renders_numbered_sections_safely():
    html = str(summary_to_html("### 1. 研究问题\n这是 **重点**。\n- bullet"))

    assert '<span class="summary-index">1</span>' in html
    assert "<strong>重点</strong>" in html
    assert "<li>bullet</li>" in html


def test_summary_to_html_cleans_inline_latex_math():
    html = str(summary_to_html(r"历史观测 $o_{\leq t}$、动作历史 $a_{<t}$ 和状态 $s_z$。"))

    assert "$" not in html
    assert r"\leq" not in html
    assert "o≤t" in html
    assert "a&lt;t" in html
    assert "s_z" in html


def test_summary_to_html_renders_daily_markdown_blocks():
    content = """**arXiv 具身智能论文日报 · 2026-05-15**
*面向具身智能研究者*
（严格基于 arXiv 元数据和摘要）

---

> ✅ 关键信号：从 VLA 走向闭环智能。

| 论文 | 一句话 |
| --- | --- |
| **Hand-in-the-Loop** (arXiv:2605.15157v1) | *human-in-the-loop* correction<br>closed loop |
| **SOCC-ICP** | incomplete row
"""
    html = str(summary_to_html(content))

    assert 'class="summary-lead"' in html
    assert 'class="summary-sublead"' in html
    assert 'class="summary-note"' in html
    assert 'class="summary-divider"' in html
    assert 'class="summary-callout"' in html
    assert 'class="summary-table"' in html
    assert "<em>human-in-the-loop</em>" in html
    assert 'href="https://arxiv.org/abs/2605.15157v1"' in html
    assert "correction<br>closed loop" in html
    assert "incomplete row" in html
    assert "---" not in html
    assert "&gt;" not in html


def test_format_datetime_removes_microseconds():
    value = datetime(2026, 5, 15, 3, 10, 42, 190786, tzinfo=timezone.utc)
    assert format_datetime(value) == "2026-05-15 03:10"


def test_markdown_to_html_renders_headings_lists_and_links():
    html = str(markdown_to_html("# Title\n\n- [arXiv](https://arxiv.org/abs/1)\n\nText arXiv:2605.15157v1"))

    assert "<h1>Title</h1>" in html
    assert '<a href="https://arxiv.org/abs/1"' in html
    assert 'href="https://arxiv.org/abs/2605.15157v1"' in html
    assert "<p>Text " in html


def test_markdown_to_html_cleans_inline_latex_math():
    html = str(markdown_to_html(r"- 观测 $o_{\leq t}$ 映射到动作 $a_{<t}$"))

    assert "$" not in html
    assert "o≤t" in html
    assert "a&lt;t" in html


def test_markdown_to_html_renders_tables_and_callouts():
    html = str(markdown_to_html("> signal\n\n| A | B |\n| --- | --- |\n| 1 | 2 |"))

    assert 'class="summary-callout"' in html
    assert 'class="summary-table"' in html


def test_strip_first_markdown_heading_removes_duplicate_daily_title():
    assert strip_first_markdown_heading("# 2026 title\n\nbody") == "body"
    assert strip_first_markdown_heading("body") == "body"


def test_link_arxiv_ids_markdown_skips_existing_links_and_code():
    markdown = (
        "见 arXiv:2605.15157v1，"
        "已有 [2605.00001v1](https://arxiv.org/abs/2605.00001v1)，"
        "代码 `arXiv:2605.00002v1`。"
    )

    linked = link_arxiv_ids_markdown(markdown)

    assert "[arXiv:2605.15157v1](https://arxiv.org/abs/2605.15157v1)" in linked
    assert linked.count("https://arxiv.org/abs/2605.00001v1") == 1
    assert "`arXiv:2605.00002v1`" in linked
