"""Qwen 严格动态模式：拒绝固定内容回退并公开逐字段生成来源。"""
from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path

import pytest

from backend.tests.test_qwen_dynamic_decision import (
    _Response,
    _decision_payload,
    _strategy_payload,
)
from miniso_studio.application import runner as runner_module
from miniso_studio.common.config import settings
from miniso_studio.common.decision_input import DecisionInput


ROOT = Path(__file__).resolve().parents[2]
ENGINE_FILE = ROOT / "backend/miniso_studio/application/llm_decision_strict_dynamic.py"
PIPELINE_FILE = ROOT / "backend/miniso_studio/application/graph/pipeline_qwen_strict.py"
REPORTING_FILE = ROOT / "backend/miniso_studio/application/reporting_qwen_strict.py"
APP_FILE = ROOT / "backend/miniso_studio/starter/live_app_qwen_strict.py"
HTML_FILE = ROOT / "frontend/index-qwen-strict.html"
SCRIPT_FILE = ROOT / "frontend/app-qwen-strict.js"
RUNNER_FILE = ROOT / "run_qwen_strict.py"
BUILDER_FILE = ROOT / "scripts/build_qwen_strict_pages.py"
WORKFLOW_FILE = ROOT / ".github/workflows/deploy-qwen-strict-pages.yml"


def _load(name: str):
    return importlib.import_module(name)


def _node(script: str) -> dict:
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_strict_dynamic_mode_is_a_separate_version() -> None:
    paths = (
        ENGINE_FILE,
        PIPELINE_FILE,
        REPORTING_FILE,
        APP_FILE,
        HTML_FILE,
        SCRIPT_FILE,
        RUNNER_FILE,
        BUILDER_FILE,
        WORKFLOW_FILE,
    )
    for path in paths:
        assert path.exists(), f"缺少 Qwen 严格动态新版文件：{path.name}"

    assert 'src="static/app-qwen-strict.js"' in HTML_FILE.read_text(encoding="utf-8")
    workflow = WORKFLOW_FILE.read_text(encoding="utf-8")
    assert "build_qwen_strict_pages.py" in workflow
    assert "deploy-pages@v4" in workflow


def test_strict_pipeline_fails_closed_instead_of_returning_fixed_candidates(
    monkeypatch,
    tmp_path: Path,
) -> None:
    strict_pipeline = _load("miniso_studio.application.graph.pipeline_qwen_strict")
    strict_reporting = _load("miniso_studio.application.reporting_qwen_strict")
    monkeypatch.setenv("MINISO_LLM_PROVIDER", "qwen")
    monkeypatch.setenv("QWEN_API_KEY", "")
    monkeypatch.setenv("MINISO_TRACE_DIR", str(tmp_path / "runs"))
    settings.cache_clear()
    monkeypatch.setattr(
        runner_module,
        "build_studio_graph",
        strict_pipeline.build_qwen_strict_graph,
    )

    try:
        artifacts = runner_module.run_studio(
            decision_input=DecisionInput(
                brief="必须由模型实时生成而不是返回固定候选",
                product_category="stationery",
                target_segment="student",
            ),
            thread_id="strict-no-fixed-fallback",
        )
    finally:
        settings.cache_clear()

    assert artifacts.state.concepts == []
    with pytest.raises(strict_reporting.IncompleteQwenGenerationError):
        strict_reporting.to_view_qwen_strict(artifacts)
    errors = [
        str(event.get("error", ""))
        for event in artifacts.trace_events
        if event.get("kind") == "node_error"
    ]
    assert errors == ["qwen_generation_required:strategy"]
    assert "api" not in errors[0].lower()
    assert "key" not in errors[0].lower()


def test_strict_pipeline_uses_qwen_for_all_narrative_fields_and_marks_sources(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[dict] = []

    def fake_post(url, *, headers, json, timeout):
        calls.append({"url": url, "json": json, "timeout": timeout})
        prompt = "\n".join(item["content"] for item in json["messages"])
        payload = _decision_payload() if "decision_schema_version" in prompt else _strategy_payload()
        return _Response(
            {
                "choices": [{"message": {"content": json_module.dumps(payload, ensure_ascii=False)}}],
                "usage": {"prompt_tokens": 500, "completion_tokens": 700},
            },
            request_id=f"req-strict-{len(calls)}",
        )

    json_module = json
    strict_pipeline = _load("miniso_studio.application.graph.pipeline_qwen_strict")
    strict_reporting = _load("miniso_studio.application.reporting_qwen_strict")
    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setenv("MINISO_LLM_PROVIDER", "qwen")
    monkeypatch.setenv("QWEN_API_KEY", "unit-test-secret")
    monkeypatch.setenv("QWEN_BASE_URL", "https://coding.example/v1")
    monkeypatch.setenv("QWEN_MODEL", "qwen3.7-plus")
    monkeypatch.setenv("MINISO_TRACE_DIR", str(tmp_path / "runs"))
    settings.cache_clear()
    monkeypatch.setattr(
        runner_module,
        "build_studio_graph",
        strict_pipeline.build_qwen_strict_graph,
    )

    try:
        artifacts = runner_module.run_studio(
            decision_input=DecisionInput(
                brief="为大学新生实时生成可验证的开学用品",
                product_category="stationery",
                target_segment="student",
                target_market="china",
                price_band="entry",
                ip_strategy="original",
                objectives=["emotional", "social"],
                constraints="首批只允许两个配色并验证耐用度",
            ),
            thread_id="strict-qwen-provenance",
        )
    finally:
        settings.cache_clear()

    view = strict_reporting.to_view_qwen_strict(artifacts)
    provenance = view["generation_provenance"]
    assert provenance == {
        "mode": "qwen_strict_dynamic",
        "qwen_complete": True,
        "model": "qwen3.7-plus",
        "required_tasks": ["strategy", "decision"],
        "completed_tasks": ["strategy", "decision"],
        "fallback_used": False,
        "content_source": "qwen3.7-plus",
        "numeric_source": "deterministic_guardrails",
    }
    assert len(calls) == 2
    assert all(call["json"]["model"] == "qwen3.7-plus" for call in calls)
    assert all(
        "所有面向评委的内容必须使用简体中文" in call["json"]["messages"][0]["content"]
        for call in calls
    )
    assert all(
        risk["source"] == "qwen_dynamic" and "Qwen识别" in risk["description"]
        for assessment in view["quality_audit"]["by_candidate"].values()
        for risk in assessment["risks"]
    )
    assert all(
        dimension["score_source"] == "deterministic_guardrails"
        and dimension["rationale_source"] == "qwen3.7-plus"
        for scorecard in view["scorecards"]
        for dimension in scorecard["dimensions"]
    )
    assert all(
        candidate["content_source"] == "qwen3.7-plus"
        for candidate in view["candidate_skus"]
    )

    incomplete = artifacts.model_copy(
        update={
            "trace_events": [
                event
                for event in artifacts.trace_events
                if not (event.get("kind") == "llm_call" and event.get("task") == "decision")
            ]
        }
    )
    with pytest.raises(strict_reporting.IncompleteQwenGenerationError):
        strict_reporting.to_view_qwen_strict(incomplete)


def test_strict_frontend_rejects_incomplete_generation_and_has_no_fixed_concept_assets() -> None:
    assert SCRIPT_FILE.exists(), "缺少 Qwen 严格动态前端新版"
    result = _node(
        """
const app = require('./frontend/app-qwen-strict.js');
const complete = app.requireStrictGeneration({
  mode: 'qwen_strict_dynamic',
  qwen_complete: true,
  model: 'qwen3.7-plus',
  completed_tasks: ['strategy', 'decision'],
  required_tasks: ['strategy', 'decision'],
  fallback_used: false,
});
let error = '';
try {
  app.requireStrictGeneration({
    mode: 'qwen_strict_dynamic',
    qwen_complete: false,
    model: 'offline-deterministic',
    completed_tasks: ['strategy'],
    required_tasks: ['strategy', 'decision'],
    fallback_used: true,
  });
} catch (caught) {
  error = caught.message;
}
console.log(JSON.stringify({ complete, error }));
"""
    )

    assert result["complete"]["model"] == "qwen3.7-plus"
    assert result["complete"]["qwen_complete"] is True
    assert result["error"] == "qwen_generation_incomplete"

    source = SCRIPT_FILE.read_text(encoding="utf-8")
    html = HTML_FILE.read_text(encoding="utf-8")
    assert "CONCEPT_ASSETS" not in source
    assert "conceptAsset(" not in source
    assert "generationBadge" in source
    assert "Qwen 动态生成" in source
    assert "本地硬闸口" in source
    assert 'id="generationBadge"' in html


def test_strict_pages_builder_publishes_only_strict_frontend(tmp_path: Path) -> None:
    assert BUILDER_FILE.exists(), "缺少 Qwen 严格动态 Pages 构建器新版"
    module = _load("scripts.build_qwen_strict_pages")
    output = tmp_path / "strict-site"

    module.build_site(output, "https://example-tunnel.invalid/")

    html = (output / "index.html").read_text(encoding="utf-8")
    assert 'content="https://example-tunnel.invalid"' in html
    assert 'src="static/app-qwen-strict.js"' in html
    assert "offline-pages" not in html
    assert (output / "static/app-qwen-strict.js").exists()
    assert not (output / "static/app-qwen-resilient.js").exists()
