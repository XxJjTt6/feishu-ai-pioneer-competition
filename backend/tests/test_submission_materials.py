"""报名表可直接粘贴文案的字数验收测试。"""
from __future__ import annotations

from pathlib import Path
import re


def _section(text: str, title: str) -> str:
    match = re.search(rf"## {title}\n\n(.+?)(?=\n## |\Z)", text, re.S)
    assert match
    return re.sub(r"\s+", "", match.group(1))


def test_section_extracts_and_normalizes_a_minimal_markdown_section():
    text = "## Part 1 可直接粘贴文本\n\n甲 乙\n\n## 下一节\n\n丙"

    assert _section(text, "Part 1 可直接粘贴文本") == "甲乙"


def test_form_copy_is_within_required_ranges():
    text = Path("docs/报名提交材料.md").read_text(encoding="utf-8")

    assert 150 <= len(_section(text, "Part 1 可直接粘贴文本")) <= 300
    assert 300 <= len(_section(text, "Part 2 可直接粘贴文本")) <= 600
