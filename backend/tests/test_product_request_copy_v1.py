"""“你想做什么产品”表单文案与 GitHub Pages 产物契约测试。"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HTML = ROOT / "frontend/index-qwen-strict.html"
SCRIPT = ROOT / "frontend/app-qwen-strict.js"
BUILDER = ROOT / "scripts/build_qwen_strict_pages.py"

FIELD_LABEL = "你想做什么产品"
FIELD_PLACEHOLDER = (
    "例如：为年轻职场人设计一款适合办公桌摆放、"
    "主打治愈和解压的原创毛绒玩具"
)


class ProductRequestCopyTest(unittest.TestCase):
    def assert_plain_copy(self, html: str, script: str) -> None:
        self.assertIn(f'<label for="brief">{FIELD_LABEL}</label>', html)
        self.assertIn(f'placeholder="{FIELD_PLACEHOLDER}"', html)
        self.assertIn('请描述你想做的产品。', script)
        self.assertIn('产品描述最多 500 字。', script)
        self.assertNotIn("决策简报", html)
        self.assertNotIn("决策简报", script)

    def test_strict_form_uses_plain_product_request_copy(self) -> None:
        self.assert_plain_copy(
            HTML.read_text(encoding="utf-8"),
            SCRIPT.read_text(encoding="utf-8"),
        )

    def test_strict_pages_build_publishes_the_same_plain_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "site"
            subprocess.run(
                [sys.executable, str(BUILDER), "--output", str(output)],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assert_plain_copy(
                (output / "index.html").read_text(encoding="utf-8"),
                (output / "static/app-qwen-strict.js").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
