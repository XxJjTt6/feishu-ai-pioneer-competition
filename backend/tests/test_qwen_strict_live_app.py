"""Qwen 严格动态工作台入口与真实浏览器渲染验收。"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.tests.test_frontend_copy import CHROME, _chrome_dump, _mock_view
from miniso_studio.common.config import settings
from miniso_studio.starter.live_app_qwen_strict import app


ROOT = Path(__file__).resolve().parents[2]
HTML = ROOT / "frontend/index-qwen-strict.html"


def _strict_view() -> dict:
    view = _mock_view()
    view["configured_provider"] = "qwen"
    view["effective_provider"] = "qwen"
    view["provider"] = "qwen"
    view["model"] = "qwen3.7-plus"
    view["generation_provenance"] = {
        "mode": "qwen_strict_dynamic",
        "qwen_complete": True,
        "model": "qwen3.7-plus",
        "required_tasks": ["strategy", "decision"],
        "completed_tasks": ["strategy", "decision"],
        "fallback_used": False,
        "content_source": "qwen3.7-plus",
        "numeric_source": "deterministic_guardrails",
    }
    for candidate in view["candidate_skus"]:
        candidate["content_source"] = "qwen3.7-plus"
    for scorecard in view["scorecards"]:
        for dimension in scorecard["dimensions"]:
            dimension["score_source"] = "deterministic_guardrails"
            dimension["rationale_source"] = "qwen3.7-plus"
    for dimension in view["winner_scorecard"]["dimensions"]:
        dimension["score_source"] = "deterministic_guardrails"
        dimension["rationale_source"] = "qwen3.7-plus"
    for assessment in view["quality_audit"]["by_candidate"].values():
        for risk in assessment["risks"]:
            risk["source"] = (
                "deterministic_guardrail"
                if risk["severity"] == "high"
                else "qwen_dynamic"
            )
    return view


def test_strict_live_root_and_health_never_advertise_offline_decisions(monkeypatch) -> None:
    monkeypatch.setenv("MINISO_LLM_PROVIDER", "qwen")
    monkeypatch.setenv("QWEN_API_KEY", "unit-test-secret")
    monkeypatch.setenv("QWEN_MODEL", "qwen3.7-plus")
    settings.cache_clear()
    try:
        client = TestClient(app)
        root = client.get("/")
        health = client.get("/api/health").json()
    finally:
        settings.cache_clear()

    assert root.status_code == 200
    assert 'src="static/app-qwen-strict.js"' in root.text
    assert "offline-pages" not in root.text
    assert health["effective_provider"] == "qwen"
    assert health["model"] == "qwen3.7-plus"
    assert health["decision_mode"] == "qwen_strict_dynamic_with_deterministic_guardrails"


@pytest.mark.skipif(not CHROME.exists(), reason="本机未安装 Google Chrome")
@pytest.mark.parametrize(("width", "height"), [(375, 812), (390, 844), (1121, 800), (1440, 900)])
def test_strict_live_frontend_renders_provenance_without_fixed_images_or_page_overflow(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    site = tmp_path / "site"
    static = site / "static"
    shutil.copytree(ROOT / "frontend", static)
    payload = json.dumps(_strict_view(), ensure_ascii=False).replace("</", "<\\/")
    probe = f"""
<script>
window.addEventListener('load', () => {{
  window.Trend2SKUApp.renderViewForTest({payload});
  window.setTimeout(() => {{
    document.body.dataset.generation = document.getElementById('generationBadge')?.textContent || '';
    document.body.dataset.fixedImages = String(document.querySelectorAll('.concept-thumb, .candidate-visual').length);
    document.body.dataset.riskSources = Array.from(document.querySelectorAll('.risk-source')).map((node) => node.textContent).join('|');
    document.body.dataset.rationaleSources = String(document.querySelectorAll('.rationale-source').length);
    document.body.dataset.overflow = String(document.documentElement.scrollWidth > document.documentElement.clientWidth);
    document.body.dataset.probe = 'ready';
  }}, 100);
}});
</script>
"""
    (site / "index.html").write_text(
        HTML.read_text(encoding="utf-8").replace("</body>", probe + "</body>"),
        encoding="utf-8",
    )

    stdout, stderr = _chrome_dump(site / "index.html", tmp_path, width, height)

    body = re.search(r"<body\b([^>]*)>", stdout)
    assert body, stderr
    attrs = body.group(1)
    assert 'data-probe="ready"' in attrs
    assert "Qwen 动态生成 2/2" in attrs
    assert 'data-fixed-images="0"' in attrs
    assert "Qwen 动态风险假设" in attrs
    assert 'data-rationale-sources="8"' in attrs
    assert 'data-overflow="false"' in attrs
