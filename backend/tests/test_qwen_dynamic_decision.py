"""Qwen 动态决策链：结构化调用、全链路文案与安全降级契约。"""
from __future__ import annotations

import json

import pytest

from miniso_studio.application import runner as runner_module
from miniso_studio.application.graph.pipeline_llm_dynamic import build_llm_studio_graph_dynamic
from miniso_studio.application.reporting import to_view
from miniso_studio.application.reporting_llm_dynamic import render_full_report_llm_dynamic
from miniso_studio.common.config import settings
from miniso_studio.common.decision_input import DecisionInput
from miniso_studio.infrastructure.llm.structured_qwen_dynamic import (
    StructuredQwenClientError,
    StructuredQwenClient,
)


DIMENSION_KEYS = [
    "trend_fit",
    "demand_strength",
    "differentiation",
    "social_virality",
    "margin_potential",
    "supply_feasibility",
    "ip_compliance",
    "localization_fit",
]


class _Response:
    def __init__(self, payload: dict, status_code: int = 200, request_id: str = "req-test"):
        self._payload = payload
        self.status_code = status_code
        self.headers = {"x-request-id": request_id}
        self.text = "response body must never enter an exception"

    def json(self) -> dict:
        return self._payload


def _candidate(path: str, label: str, acceptance: float) -> dict:
    return {
        "path": path,
        "name": f"Qwen动态{label}方案",
        "one_liner": f"针对学生用品任务生成的{label}差异化解法",
        "target_segment": "需要兼顾学习、自我表达与轻礼赠的学生人群",
        "value_proposition": f"用{label}机制把用品需求转成可验证的购买理由",
        "key_features": [
            f"{label}可替换模块",
            "校园场景组合包装",
            "低门槛个性化标记",
        ],
        "differentiators": [
            {
                "statement": f"围绕{label}形成与普通货架用品不同的使用闭环",
                "opportunity_ids": [],
                "evidence_ids": [],
            },
            {
                "statement": "把自用、分享和轻礼赠放入同一产品系统",
                "opportunity_ids": [],
                "evidence_ids": [],
            },
        ],
        "tech_enablers": ["模块化结构", "小批量柔性包装"],
        "addressed_opportunity_ids": [],
        "interviews": [
            {
                "persona_name": f"{label}型学生用户",
                "persona_segment": "在校学生",
                "persona_summary": f"会用{label}判断产品是否值得带进校园",
                "turns": [
                    {
                        "question": "它在真实校园里解决什么问题？",
                        "answer": f"Qwen访谈回答：{label}让我能同时处理学习和表达需求。",
                        "sentiment": "positive",
                    },
                    {
                        "question": "为什么愿意购买？",
                        "answer": "组合明确、价格理由清楚，而且不是把现成产品换名字。",
                        "sentiment": "positive",
                    },
                    {
                        "question": "最大的犹豫是什么？",
                        "answer": "需要先看样件耐用度、真实价格和包装体积。",
                        "sentiment": "neutral",
                    },
                ],
                "verdict": "would_buy",
                "acceptance": acceptance,
                "objections": ["尚未看到真实样件与价格"],
                "must_fixes": ["用校园任务测试验证连续使用意愿"],
                "evidence_ids": [],
            }
        ],
        "feasibility": {
            "technical": f"{label}结构可用常见加工方式完成首轮样件",
            "supply_chain": "先用两家成熟供应商做小批量并行打样",
            "bom_cost": "BOM 需在结构确认后按模块逐项核价",
            "compliance": "按目标市场拆分材料与标签检查清单",
            "quality": "重点验证连接件寿命、跌落与小部件边界",
            "gross_margin": "通过模块数量和包装层级控制成本暴露",
            "supplier_lead_time": "首轮样件周期作为假设，不承诺真实交期",
            "ip_authorization": "原创元素仍需完成近似检索和权属留档",
            "regional_compliance": "进入不同市场前分别完成标签与材料核验",
            "localization": "保留核心结构，用颜色和语言完成区域适配",
            "risks": [
                {
                    "area": "quality",
                    "description": f"Qwen识别的{label}连接耐久风险",
                    "severity": "high",
                    "mitigation": "用三轮样件测试记录失效位置再锁定结构",
                }
            ],
        },
    }


def _strategy_payload() -> dict:
    return {
        "strategy_schema_version": "1",
        "candidates": [
            _candidate("voc_driven", "需求共创", 0.91),
            _candidate("trend_driven", "趋势转译", 0.83),
            _candidate("whitespace_driven", "场景白空间", 0.86),
        ],
        "synthesis_note": "三条方案由 Qwen 根据本轮结构化输入和证据上下文实时生成。",
    }


def _decision_payload() -> dict:
    return {
        "decision_schema_version": "1",
        "candidate_rationales": [
            {
                "concept_id": concept_id,
                "dimensions": {
                    key: f"Qwen结合本轮候选、验证和风险解释 {concept_id} 的 {key}。"
                    for key in DIMENSION_KEYS
                },
            }
            for concept_id in ("C-VOC", "C-TREND", "C-WHITESPACE")
        ],
        "portfolio_rationale": "Qwen综合三条候选的实时验证反馈与确定性分数后形成组合判断。",
        "conditions": ["先完成真实学生任务测试，再决定首发组合深度"],
        "proposal": {
            "headline": "Qwen动态学生用品组合提案",
            "subheading": "从校园任务而不是固定模板生成候选",
            "summary": "Qwen根据本轮输入、候选验证和风险结果生成这份动态提案摘要。",
            "customer_quote": "我需要的是能持续使用并表达自己的用品，而不是换皮套装。",
            "maker_quote": "先用小批量样件关闭连接寿命和成本假设。",
            "call_to_action": "进入两周校园任务测试",
            "external_faq": [
                {"question": "它和普通学生用品有什么不同？", "answer": "差异来自可验证的校园任务与模块组合。"}
            ],
            "internal_faq": [
                {"question": "现在能承诺销量吗？", "answer": "不能，当前只有假设和模拟验证，需真实测试。"}
            ],
        },
    }


def test_structured_qwen_uses_json_mode_and_never_exposes_response_body(monkeypatch) -> None:
    captured: list[dict] = []

    def fake_post(url, *, headers, json, timeout):
        captured.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return _Response(
            {
                "choices": [{"message": {"content": '{"value":"动态"}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 4},
            }
        )

    monkeypatch.setattr("requests.post", fake_post)
    client = StructuredQwenClient(
        api_key="unit-test-secret",
        base_url="https://coding.example/v1/",
        model="qwen3.7-plus",
    )
    result = client.complete_json(
        system="返回 JSON。",
        prompt="请输出 JSON 对象。",
        max_tokens=128,
    )

    assert result.payload == {"value": "动态"}
    assert result.model == "qwen3.7-plus"
    assert captured[0]["url"] == "https://coding.example/v1/chat/completions"
    assert captured[0]["json"]["response_format"] == {"type": "json_object"}
    assert captured[0]["json"]["enable_thinking"] is False
    assert "unit-test-secret" not in json.dumps(captured[0]["json"], ensure_ascii=False)

    monkeypatch.setattr(
        "requests.post",
        lambda *args, **kwargs: _Response(
            {"error": {"message": "unit-test-secret and response body"}},
            status_code=401,
        ),
    )
    with pytest.raises(StructuredQwenClientError) as exc_info:
        client.complete_json(system="返回 JSON。", prompt="JSON", max_tokens=64)
    assert "unit-test-secret" not in str(exc_info.value)
    assert "response body" not in str(exc_info.value)


def test_live_pipeline_uses_qwen_for_candidates_validation_risks_and_decision(
    monkeypatch,
    tmp_path,
) -> None:
    calls: list[dict] = []

    def fake_post(url, *, headers, json, timeout):
        calls.append({"url": url, "json": json, "timeout": timeout})
        prompt = "\n".join(item["content"] for item in json["messages"])
        content = _decision_payload() if "decision_schema_version" in prompt else _strategy_payload()
        return _Response(
            {
                "choices": [{"message": {"content": json_module.dumps(content, ensure_ascii=False)}}],
                "usage": {"prompt_tokens": 600, "completion_tokens": 900},
            },
            request_id=f"req-{len(calls)}",
        )

    json_module = json
    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setenv("MINISO_LLM_PROVIDER", "qwen")
    monkeypatch.setenv("QWEN_API_KEY", "unit-test-secret")
    monkeypatch.setenv("QWEN_BASE_URL", "https://coding.example/v1")
    monkeypatch.setenv("QWEN_MODEL", "qwen3.7-plus")
    monkeypatch.setenv("MINISO_TRACE_DIR", str(tmp_path / "runs"))
    settings.cache_clear()
    monkeypatch.setattr(runner_module, "build_studio_graph", build_llm_studio_graph_dynamic)

    try:
        artifacts = runner_module.run_studio(
            decision_input=DecisionInput(
                brief="为学生生成真正动态的校园用品组合",
                product_category="stationery",
                target_segment="student",
                target_market="china",
                price_band="entry",
                ip_strategy="original",
                objectives=["emotional", "social"],
                constraints="六周内完成小批量样件验证",
            ),
            thread_id="llm-live-contract",
        )
    finally:
        settings.cache_clear()

    view = to_view(artifacts)
    names = [item["name"] for item in view["candidate_skus"]]
    assert names == [
        "Qwen动态需求共创方案",
        "Qwen动态趋势转译方案",
        "Qwen动态场景白空间方案",
    ]
    assert any(
        "Qwen访谈回答" in turn.answer
        for evaluation in artifacts.state.candidate_evaluations.values()
        for interview in evaluation.interviews
        for turn in interview.transcript
    )
    assert any(
        "Qwen识别" in risk.description
        for evaluation in artifacts.state.candidate_evaluations.values()
        for risk in evaluation.feasibility.risks
    )
    assert all(
        risk.severity != "high"
        for evaluation in artifacts.state.candidate_evaluations.values()
        for risk in evaluation.feasibility.risks
        if "Qwen识别" in risk.description
    )
    assert all(
        all("Qwen识别" not in risk for risk in scorecard.blocking_risks)
        for scorecard in artifacts.state.concept_scorecards
    )
    assert all(
        dimension.rationale.startswith("Qwen结合本轮候选")
        for scorecard in artifacts.state.concept_scorecards
        for dimension in scorecard.dimensions
    )
    assert artifacts.state.decision.rationale.startswith("Qwen综合三条候选")
    assert artifacts.state.prfaq.headline == "Qwen动态学生用品组合提案"
    assert "Qwen根据本轮输入" in artifacts.state.prfaq.summary
    assert view["configured_provider"] == "qwen"
    assert view["effective_provider"] == "qwen"
    assert view["model"] == "qwen3.7-plus"
    assert "Qwen动态学生用品组合提案" in render_full_report_llm_dynamic(artifacts)
    assert artifacts.state.pm_iteration == 1
    assert len(calls) == 2
    assert all(call["json"]["response_format"] == {"type": "json_object"} for call in calls)
    assert all(call["json"]["model"] == "qwen3.7-plus" for call in calls)
    assert [call["json"]["max_tokens"] for call in calls] == [4300, 3000]

    strategy_prompt = calls[0]["json"]["messages"][1]["content"]
    decision_prompt = calls[1]["json"]["messages"][1]["content"]
    assert "每个功能、差异点、异议和修正项不超过 40 汉字" in strategy_prompt
    assert "商品化字段不超过 60 汉字" in strategy_prompt
    assert "每条维度依据不超过 55 汉字" in decision_prompt
    assert "组合理由不超过 180 汉字" in decision_prompt
    assert '"candidate_validation"' in decision_prompt
    assert '"candidate_evaluations"' not in decision_prompt
    assert '"technical"' not in decision_prompt
