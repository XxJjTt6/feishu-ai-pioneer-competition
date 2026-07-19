"""结构化决策输入与动态三路径候选的行为契约。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from miniso_studio.application.graph.state import PipelineState
from miniso_studio.application.runner import run_studio
from miniso_studio.common.decision_input import DecisionInput


def test_decision_input_normalizes_defaults_labels_and_duplicates():
    value = DecisionInput(
        brief="  设计开学礼赠  ",
        custom_category="  非 other 时应清空  ",
        objectives=["social", "margin", "social"],
        constraints="  单件包装，四周交付  ",
    )

    assert value.model_dump(mode="json") == {
        "brief": "设计开学礼赠",
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
    assert value.target_segment_label == "年轻职场人"
    assert value.target_market_label == "全球市场"
    assert value.price_band_label == "中端价格带"
    assert value.ip_strategy_label == "原创 IP"
    assert value.objective_labels == ["社交传播", "毛利潜力"]


def test_decision_input_uses_trimmed_custom_category_label_for_other():
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
        {"brief": "设计新品", "product_category": "other", "custom_category": "   "},
        {"brief": "设计新品", "product_category": "other", "custom_category": "类" * 41},
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
def test_decision_input_rejects_invalid_contract(payload):
    with pytest.raises(ValidationError):
        DecisionInput(**payload)


def test_pipeline_state_keeps_brief_consistent_with_decision_input():
    decision = DecisionInput(brief="  结构化输入为准  ", product_category="plush")
    state = PipelineState(brief="不应保留的旧 brief", decision_input=decision)

    assert state.brief == "结构化输入为准"
    assert state.decision_input == decision
    assert PipelineState.model_validate(state.model_dump()).decision_input == decision

    legacy = PipelineState(brief="  兼容旧 brief  ")
    assert legacy.brief == "兼容旧 brief"
    assert legacy.decision_input.brief == legacy.brief


def test_run_studio_accepts_structured_input_and_legacy_brief():
    structured_input = DecisionInput(
        brief="  做一款家庭陪伴新品  ",
        product_category="plush",
        target_segment="family",
    )

    structured = run_studio(
        decision_input=structured_input,
        thread_id="structured-decision-input",
    )
    legacy = run_studio(
        brief="  兼容旧入口  ",
        thread_id="legacy-decision-input",
    )

    assert structured.state.decision_input == structured_input
    assert structured.state.brief == structured_input.brief
    assert legacy.state.brief == "兼容旧入口"
    assert legacy.state.decision_input.brief == legacy.state.brief


def test_plush_family_and_stationery_student_change_the_whole_validation_context():
    plush_input = DecisionInput(
        brief="为亲子家庭做节日陪伴礼物",
        product_category="plush",
        target_segment="family",
        target_market="china",
        price_band="mid",
        ip_strategy="licensed",
        objectives=["emotional", "supply_chain"],
        constraints="可拆洗，避免细小部件",
    )
    stationery_input = DecisionInput(
        brief="为学生做开学季社交文具",
        product_category="stationery",
        target_segment="student",
        target_market="southeast_asia",
        price_band="entry",
        ip_strategy="original",
        objectives=["social", "localization"],
        constraints="适配潮湿气候和校园渠道",
    )

    plush = run_studio(decision_input=plush_input, thread_id="dynamic-plush-family").state
    stationery = run_studio(
        decision_input=stationery_input,
        thread_id="dynamic-stationery-student",
    ).state

    expected_ids = ["C-VOC", "C-TREND", "C-WHITESPACE"]
    assert [concept.id for concept in plush.concepts] == expected_ids
    assert [concept.id for concept in stationery.concepts] == expected_ids
    assert [concept.name for concept in plush.concepts] != [
        concept.name for concept in stationery.concepts
    ]
    assert [concept.key_features for concept in plush.concepts] != [
        concept.key_features for concept in stationery.concepts
    ]

    plush_interview = plush.candidate_evaluations["C-VOC"].interviews[0]
    stationery_interview = stationery.candidate_evaluations["C-VOC"].interviews[0]
    plush_validation_copy = " ".join(
        turn.question + turn.answer for turn in plush_interview.transcript
    )
    stationery_validation_copy = " ".join(
        turn.question + turn.answer for turn in stationery_interview.transcript
    )
    assert plush_interview.transcript != stationery_interview.transcript
    assert "亲子家庭" in plush_validation_copy and "毛绒" in plush_validation_copy
    assert "学生" in stationery_validation_copy and "文创文具" in stationery_validation_copy

    plush_feasibility = plush.candidate_evaluations["C-VOC"].feasibility
    stationery_feasibility = stationery.candidate_evaluations["C-VOC"].feasibility
    assert plush_feasibility is not None and stationery_feasibility is not None
    plush_risk_copy = " ".join(
        [plush_feasibility.quality, *(risk.description for risk in plush_feasibility.risks)]
    )
    stationery_risk_copy = " ".join(
        [
            stationery_feasibility.quality,
            *(risk.description for risk in stationery_feasibility.risks),
        ]
    )
    assert plush_risk_copy != stationery_risk_copy
    assert "掉毛" in plush_risk_copy
    assert "油墨" in stationery_risk_copy


def test_brief_and_objectives_are_context_not_direct_score_inputs():
    common = {
        "product_category": "stationery",
        "target_segment": "student",
        "target_market": "china",
        "price_band": "entry",
        "ip_strategy": "original",
    }
    first = run_studio(
        decision_input=DecisionInput(
            brief="IP联名 情绪价值 社交传播 全球本地化",
            objectives=["emotional"],
            **common,
        ),
        thread_id="score-neutral-context-first",
    ).state
    second = run_studio(
        decision_input=DecisionInput(
            brief="普通开学文具",
            objectives=["margin", "supply_chain"],
            **common,
        ),
        thread_id="score-neutral-context-second",
    ).state

    first_scores = {
        card.concept_id: card.total_score for card in first.concept_scorecards
    }
    second_scores = {
        card.concept_id: card.total_score for card in second.concept_scorecards
    }
    assert first_scores == second_scores
    assert [item.name for item in first.concepts] != [item.name for item in second.concepts]
    assert (
        first.candidate_evaluations["C-VOC"].interviews[0].transcript
        != second.candidate_evaluations["C-VOC"].interviews[0].transcript
    )
    assert all(
        sum(dimension.weight for dimension in card.dimensions) == pytest.approx(1.0)
        for card in first.concept_scorecards
    )


def test_free_text_constraints_cannot_inject_trend_score_keywords():
    common = {
        "product_category": "stationery",
        "target_segment": "student",
        "target_market": "china",
        "price_band": "entry",
        "ip_strategy": "original",
        "objectives": ["margin"],
    }
    injected = run_studio(
        decision_input=DecisionInput(
            brief="约束注入防护",
            constraints="IP联名 情绪价值 社交传播 全球本地化",
            **common,
        ),
        thread_id="constraint-score-injection",
    ).state
    neutral = run_studio(
        decision_input=DecisionInput(
            brief="约束注入防护",
            constraints="四周交付并使用单件包装",
            **common,
        ),
        thread_id="constraint-score-neutral",
    ).state

    injected_scores = {
        card.concept_id: card.total_score for card in injected.concept_scorecards
    }
    neutral_scores = {
        card.concept_id: card.total_score for card in neutral.concept_scorecards
    }
    assert injected_scores == neutral_scores
    assert [item.name for item in injected.concepts] != [item.name for item in neutral.concepts]
    assert "IP联名" in injected.decision_input.constraints
    def scoring_copy(state):
        return " ".join(
            part
            for item in state.concepts
            for part in (
                item.one_liner,
                *item.key_features,
                *(diff.statement for diff in item.differentiators),
            )
        )

    injected_copy = scoring_copy(injected)
    neutral_copy = scoring_copy(neutral)
    for term in ("IP联名", "情绪价值", "社交传播", "全球本地化"):
        assert injected_copy.count(term) == neutral_copy.count(term)


def test_custom_category_free_text_cannot_inject_score_keywords():
    common = {
        "brief": "自定义品类注入防护",
        "product_category": "other",
        "target_segment": "young_professional",
        "target_market": "china",
        "price_band": "mid",
        "ip_strategy": "original",
        "objectives": ["margin"],
    }
    injected = run_studio(
        decision_input=DecisionInput(
            custom_category="IP联名情绪价值社交传播全球本地化",
            **common,
        ),
        thread_id="custom-category-score-injection",
    ).state
    neutral = run_studio(
        decision_input=DecisionInput(custom_category="露营用品", **common),
        thread_id="custom-category-score-neutral",
    ).state

    assert {
        card.concept_id: card.total_score for card in injected.concept_scorecards
    } == {
        card.concept_id: card.total_score for card in neutral.concept_scorecards
    }


def test_evaluate_ip_strategy_is_a_blocking_risk():
    state = run_studio(
        decision_input=DecisionInput(
            brief="评估待定 IP 路径",
            product_category="plush",
            ip_strategy="evaluate",
            objectives=["margin"],
        ),
        thread_id="evaluate-ip-blocking-risk",
    ).state

    for evaluation in state.candidate_evaluations.values():
        assert evaluation.feasibility is not None
        assert any(
            risk.area == "ip_authorization" and risk.severity == "high"
            for risk in evaluation.feasibility.risks
        )
    assert state.decision is not None
    assert state.decision.verdict.value != "GO"
    assert any("关闭阻断风险" in item for item in state.decision.conditions)
