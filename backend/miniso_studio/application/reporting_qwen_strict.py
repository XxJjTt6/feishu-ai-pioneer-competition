"""Qwen 严格动态模式的视图、生成来源与报告。"""
from __future__ import annotations

from miniso_studio.application.reporting import to_view
from miniso_studio.application.reporting_llm_dynamic import (
    render_full_report_llm_dynamic,
    render_opening_report_llm_dynamic,
)
from miniso_studio.application.runner import RunArtifacts


REQUIRED_TASKS = ("strategy", "decision")


class IncompleteQwenGenerationError(RuntimeError):
    """运行未同时取得策略和决策两个 Qwen 结构化产物。"""

    def __init__(self) -> None:
        super().__init__("qwen_generation_incomplete")


def generation_provenance(artifacts: RunArtifacts) -> dict:
    successful_tasks = {
        str(event.get("task", ""))
        for event in artifacts.trace_events
        if event.get("kind") == "llm_call"
        and event.get("provider") == "qwen"
        and event.get("model") == "qwen3.7-plus"
        and event.get("status") == "success"
    }
    completed = [task for task in REQUIRED_TASKS if task in successful_tasks]
    fallback_used = any(
        event.get("kind") == "provider_fallback"
        for event in artifacts.trace_events
    )
    qwen_complete = (
        completed == list(REQUIRED_TASKS)
        and not fallback_used
        and artifacts.configured_provider == "qwen"
        and artifacts.effective_provider == "qwen"
        and artifacts.model == "qwen3.7-plus"
    )
    return {
        "mode": "qwen_strict_dynamic",
        "qwen_complete": qwen_complete,
        "model": artifacts.model,
        "required_tasks": list(REQUIRED_TASKS),
        "completed_tasks": completed,
        "fallback_used": fallback_used,
        "content_source": "qwen3.7-plus" if qwen_complete else "unavailable",
        "numeric_source": "deterministic_guardrails",
    }


def to_view_qwen_strict(artifacts: RunArtifacts) -> dict:
    provenance = generation_provenance(artifacts)
    if not provenance["qwen_complete"]:
        raise IncompleteQwenGenerationError()
    view = to_view(artifacts)
    view["generation_provenance"] = provenance
    view["audit"]["generation"] = provenance
    view["launch_validation"]["mode"] = "qwen_strict_dynamic"
    view["quality_audit"]["mode"] = "qwen_strict_dynamic"

    for candidate in view["candidate_skus"]:
        candidate["content_source"] = "qwen3.7-plus"
    for scorecard in view["scorecards"]:
        for dimension in scorecard["dimensions"]:
            dimension["score_source"] = "deterministic_guardrails"
            dimension["rationale_source"] = "qwen3.7-plus"
    winner_card = view.get("winner_scorecard") or {}
    for dimension in winner_card.get("dimensions", []):
        dimension["score_source"] = "deterministic_guardrails"
        dimension["rationale_source"] = "qwen3.7-plus"
    for assessment in view["quality_audit"]["by_candidate"].values():
        if not assessment:
            continue
        for risk in assessment.get("risks", []):
            risk["source"] = (
                "deterministic_guardrail"
                if risk.get("severity") == "high"
                else "qwen_dynamic"
            )
    return view


def _with_source_note(report: str) -> str:
    lines = report.splitlines()
    note = (
        "> 生成来源：候选、访谈、非阻断风险、八维判断依据与提案均由 "
        "qwen3.7-plus 本轮实时生成；分数、权重、证据白名单和高风险闸口由本地代码锁定。"
    )
    return "\n".join([lines[0], "", note, *lines[1:]]) if lines else note


def render_full_report_qwen_strict(artifacts: RunArtifacts) -> str:
    to_view_qwen_strict(artifacts)
    return _with_source_note(render_full_report_llm_dynamic(artifacts))


def render_opening_report_qwen_strict(artifacts: RunArtifacts) -> str:
    to_view_qwen_strict(artifacts)
    return _with_source_note(render_opening_report_llm_dynamic(artifacts))
