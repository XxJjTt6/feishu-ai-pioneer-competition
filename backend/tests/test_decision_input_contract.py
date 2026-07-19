"""结构化决策输入、状态兼容与 Runner 边界契约。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from miniso_studio.application.graph.state import PipelineState
from miniso_studio.application.runner import run_studio
from miniso_studio.common.config import DEFAULT_BRIEF
from miniso_studio.common.decision_input import DecisionInput


def test_decision_input_normalizes_defaults_and_exposes_chinese_labels():
    value = DecisionInput(
        brief="  设计一款开学季礼赠新品  ",
        custom_category="  非其他品类时会被清空  ",
        objectives=["social", "margin", "social"],
        constraints="  单件包装，四周交付  ",
    )

    assert value.model_dump(mode="json") == {
        "brief": "设计一款开学季礼赠新品",
        "product_category": "fragrance_accessory",
        "custom_category": "",
        "target_segment": "young_professional",
        "target_market": "global",
        "price_band": "mid",
        "ip_strategy": "original",
        "objectives": ["social", "margin"],
        "constraints": "单件包装，四周交付",
    }
    assert value.category_label == "香氛配饰"
    assert value.segment_label == "年轻职场人"
    assert value.market_label == "全球市场"
    assert value.price_label == "中端价格带"
    assert value.ip_strategy_label == "原创 IP"
    assert value.objective_labels == ["社交传播", "毛利潜力"]


def test_other_category_requires_and_uses_trimmed_custom_category():
    with pytest.raises(ValidationError):
        DecisionInput(
            brief="设计新品",
            product_category="other",
            custom_category="   ",
        )

    value = DecisionInput(
        brief="设计新品",
        product_category="other",
        custom_category="  露营用品  ",
    )

    assert value.custom_category == "露营用品"
    assert value.category_label == "露营用品"


@pytest.mark.parametrize(
    "payload",
    [
        {"brief": "   "},
        {"brief": "x" * 501},
        {"brief": "设计新品", "product_category": "invalid"},
        {"brief": "设计新品", "target_segment": "invalid"},
        {"brief": "设计新品", "target_market": "invalid"},
        {"brief": "设计新品", "price_band": "invalid"},
        {"brief": "设计新品", "ip_strategy": "invalid"},
        {"brief": "设计新品", "objectives": []},
        {
            "brief": "设计新品",
            "objectives": [
                "emotional",
                "social",
                "margin",
                "supply_chain",
                "localization",
            ],
        },
        {"brief": "设计新品", "constraints": "约" * 301},
        {"brief": "设计新品", "unknown_field": "forbidden"},
    ],
)
def test_decision_input_rejects_values_outside_the_contract(payload):
    with pytest.raises(ValidationError):
        DecisionInput(**payload)


def test_decision_input_default_objectives_are_not_shared():
    first = DecisionInput(brief="第一个输入")
    second = DecisionInput(brief="第二个输入")

    first.objectives.append("margin")

    assert second.objectives == ["emotional", "social"]


def test_pipeline_state_synchronizes_structured_and_legacy_briefs():
    decision = DecisionInput(brief="  结构化输入为准  ", product_category="plush")
    structured = PipelineState(brief="不得覆盖结构化输入", decision_input=decision)
    legacy = PipelineState(brief="  兼容旧 checkpoint  ")
    empty = PipelineState()

    assert structured.brief == "结构化输入为准"
    assert structured.decision_input == decision
    assert PipelineState.model_validate(structured.model_dump()).decision_input == decision
    assert legacy.brief == "兼容旧 checkpoint"
    assert legacy.decision_input.brief == legacy.brief
    assert empty.brief == DEFAULT_BRIEF
    assert empty.decision_input.brief == DEFAULT_BRIEF


def test_run_studio_prefers_structured_input_and_normalizes_legacy_brief():
    decision = DecisionInput(brief="  结构化 Runner 输入  ", product_category="plush")

    structured = run_studio(
        brief="不得覆盖结构化输入",
        decision_input=decision,
        thread_id="decision-input-contract-structured",
    )
    legacy = run_studio(
        brief="  旧 brief 入口  ",
        thread_id="decision-input-contract-legacy",
    )

    assert structured.state.decision_input == decision
    assert structured.state.brief == "结构化 Runner 输入"
    assert legacy.state.brief == "旧 brief 入口"
    assert legacy.state.decision_input.brief == "旧 brief 入口"
