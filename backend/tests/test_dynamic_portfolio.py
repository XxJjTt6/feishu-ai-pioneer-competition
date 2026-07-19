"""结构化决策输入驱动候选、用户镜像与商品风险的契约测试。"""
from __future__ import annotations

from miniso_studio.application.agents.industry_expert import IndustryExpertAgent
from miniso_studio.application.agents.product_manager import ProductManagerAgent
from miniso_studio.application.agents.user_proxy import UserProxyAgent
from miniso_studio.application.graph.state import PipelineState
from miniso_studio.application.portfolio.dynamic_candidates import build_dynamic_portfolio
from miniso_studio.common.decision_input import DecisionInput
from miniso_studio.common.models import (
    Evidence,
    MarketIntel,
    Opportunity,
    TrendSignal,
    VocReport,
)
from miniso_studio.common.tools import get_tool
from miniso_studio.infrastructure.llm.gateway import LLMGateway


def _opportunities() -> list[Opportunity]:
    return [
        Opportunity(
            id="OPP-1",
            statement="用户希望品质稳定且耐用",
            aspect="品质/耐用性",
            origin="voc",
            evidence_ids=["EV-QUALITY"],
        ),
        Opportunity(
            id="OPP-2",
            statement="用户希望价格与获得感匹配",
            aspect="价格/价值",
            origin="voc",
            evidence_ids=["EV-PRICE"],
        ),
        Opportunity(
            id="OPP-3",
            statement="用户希望商品适合轻礼赠",
            aspect="礼赠性",
            origin="voc",
            evidence_ids=["EV-GIFT"],
        ),
        Opportunity(
            id="WS-1",
            statement="竞品包装缺少二次使用价值",
            aspect="包装",
            origin="competitor",
            evidence_ids=["EV-WHITESPACE"],
        ),
    ]


def _trends() -> list[TrendSignal]:
    return [
        TrendSignal(name="IP联名", evidence_ids=["EV-TREND-IP"]),
        TrendSignal(name="情绪价值", evidence_ids=["EV-TREND-EMOTION"]),
        TrendSignal(name="社交传播", evidence_ids=["EV-TREND-SOCIAL"]),
        TrendSignal(name="全球本地化", evidence_ids=["EV-TREND-LOCAL"]),
    ]


def _decision(**overrides: object) -> DecisionInput:
    values = {
        "brief": "开发一款真实可量产的兴趣消费新品",
        "product_category": "plush",
        "target_segment": "family",
        "target_market": "china",
        "price_band": "mid",
        "ip_strategy": "licensed",
        "objectives": ["emotional", "supply_chain"],
        "constraints": "可拆洗，避免细小部件",
    }
    values.update(overrides)
    return DecisionInput(**values)


def _concept_copy(concepts) -> str:
    return " ".join(
        part
        for concept in concepts
        for part in (
            concept.name,
            concept.one_liner,
            concept.target_segment,
            concept.value_proposition,
            *concept.key_features,
            *concept.tech_enablers,
        )
    )


def _state(decision: DecisionInput) -> PipelineState:
    opportunities = _opportunities()
    trends = _trends()
    evidences = [
        Evidence(source_id=source_id, text=source_id, helpful_votes=1)
        for source_id in (
            "EV-QUALITY",
            "EV-PRICE",
            "EV-GIFT",
            "EV-WHITESPACE",
            "EV-TREND-IP",
            "EV-TREND-EMOTION",
            "EV-TREND-SOCIAL",
            "EV-TREND-LOCAL",
        )
    ]
    return PipelineState(
        decision_input=decision,
        target_evidences=evidences,
        voc_report=VocReport(
            category="interest_goods",
            target_brand="MINISO",
            review_count=len(evidences),
            opportunities=opportunities[:3],
        ),
        market_intel=MarketIntel(
            trends=trends,
            white_space_opportunities=opportunities[3:],
        ),
    )


def test_distinct_decisions_change_every_customer_facing_candidate_field():
    plush = build_dynamic_portfolio(_decision(), _opportunities(), _trends())
    stationery = build_dynamic_portfolio(
        _decision(
            brief="开发开学季新品",
            product_category="stationery",
            target_segment="student",
            target_market="southeast_asia",
            price_band="entry",
            ip_strategy="original",
            objectives=["social", "localization"],
            constraints="适配潮湿气候和校园渠道",
        ),
        _opportunities(),
        _trends(),
    )

    expected_ids = ["C-VOC", "C-TREND", "C-WHITESPACE"]
    assert [concept.id for concept in plush] == expected_ids
    assert [concept.id for concept in stationery] == expected_ids
    for field in (
        "name",
        "one_liner",
        "value_proposition",
        "key_features",
        "target_segment",
    ):
        assert [getattr(concept, field) for concept in plush] != [
            getattr(concept, field) for concept in stationery
        ]
    assert "毛绒" in _concept_copy(plush)
    assert "文创文具" in _concept_copy(stationery)

    allowed_evidence_ids = {
        source_id
        for opportunity in _opportunities()
        for source_id in opportunity.evidence_ids
    } | {source_id for trend in _trends() for source_id in trend.evidence_ids}
    for concept in [*plush, *stationery]:
        cited = {
            source_id
            for differentiator in concept.differentiators
            for source_id in differentiator.evidence_ids
        }
        assert cited <= allowed_evidence_ids
        assert set(concept.addressed_opportunity_ids) <= {"OPP-1", "OPP-2", "OPP-3"}


def test_all_seven_category_profiles_supply_product_form_module_and_scene_copy():
    expected_terms = {
        "plush": ("毛绒", "抱枕", "陪伴", "亲子"),
        "fragrance_accessory": ("香氛", "挂件", "替换香芯", "通勤"),
        "stationery": ("文创文具", "笔袋", "书写", "校园"),
        "home_storage": ("家居收纳", "收纳盒", "分区", "居家"),
        "beauty_tool": ("美妆工具", "工具组", "上妆", "梳妆"),
        "digital_accessory": ("数码配件", "支架", "理线", "移动办公"),
        "other": ("露营用品", "组合套装", "模块", "户外"),
    }

    for category, terms in expected_terms.items():
        decision = _decision(
            product_category=category,
            custom_category="露营用品" if category == "other" else "",
        )
        copy = _concept_copy(build_dynamic_portfolio(decision, _opportunities(), _trends()))
        assert all(term in copy for term in terms)


def test_brief_changes_safe_task_tags_without_injecting_raw_keywords():
    from miniso_studio.common.models import CandidateRevisionContext

    first = _decision(brief="IP联名 情绪价值 社交传播 全球本地化")
    second = _decision(brief="完全不同但不应成为评分关键词的说明")
    first_portfolio = build_dynamic_portfolio(first, _opportunities(), _trends())
    second_portfolio = build_dynamic_portfolio(second, _opportunities(), _trends())
    assert [item.name for item in first_portfolio] != [item.name for item in second_portfolio]
    assert [item.key_features for item in first_portfolio] != [
        item.key_features for item in second_portfolio
    ]
    first_copy = _concept_copy(first_portfolio)
    second_copy = _concept_copy(second_portfolio)
    assert first.brief not in first_copy
    assert second.brief not in second_copy

    revised = build_dynamic_portfolio(
        first,
        _opportunities(),
        _trends(),
        revision_context=[
            CandidateRevisionContext(
                concept_id="C-VOC",
                source_iteration=1,
                objections=["补充真实价格验证"],
                evidence_ids=["EV-PRICE"],
            )
        ],
    )
    assert revised[0].revision_notes
    assert "补充真实价格验证" in revised[0].revision_notes[0]
    assert not revised[1].revision_notes and not revised[2].revision_notes


def test_product_manager_uses_dynamic_fallback_when_read_tool_fails(monkeypatch):
    registered = get_tool("generate_candidate_portfolio")
    monkeypatch.setattr(
        registered,
        "fn",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("unavailable")),
    )
    state = _state(_decision(product_category="stationery", target_segment="student"))

    ProductManagerAgent(LLMGateway()).run(state)

    assert [concept.id for concept in state.concepts] == [
        "C-VOC",
        "C-TREND",
        "C-WHITESPACE",
    ]
    assert "文创文具" in _concept_copy(state.concepts)


def test_user_and_industry_contexts_vary_without_fabricating_evidence_ids():
    plush_state = _state(_decision())
    stationery_state = _state(
        _decision(
            product_category="stationery",
            target_segment="student",
            target_market="southeast_asia",
            price_band="entry",
            ip_strategy="original",
            objectives=["social", "localization"],
            constraints="适配潮湿气候和校园渠道",
        )
    )
    for state in (plush_state, stationery_state):
        ProductManagerAgent(LLMGateway()).run(state)
        UserProxyAgent(LLMGateway()).run(state)
        IndustryExpertAgent(LLMGateway()).run(state)

    plush_interview = plush_state.candidate_evaluations["C-VOC"].interviews[0]
    stationery_interview = stationery_state.candidate_evaluations["C-VOC"].interviews[0]
    plush_transcript = " ".join(
        turn.question + turn.answer for turn in plush_interview.transcript
    )
    stationery_transcript = " ".join(
        turn.question + turn.answer for turn in stationery_interview.transcript
    )
    assert plush_interview.transcript != stationery_interview.transcript
    assert "亲子家庭" in plush_transcript and "毛绒" in plush_transcript
    assert "学生" in stationery_transcript and "文创文具" in stationery_transcript

    plush_feasibility = plush_state.candidate_evaluations["C-VOC"].feasibility
    stationery_feasibility = stationery_state.candidate_evaluations["C-VOC"].feasibility
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
    assert "掉毛" in plush_risk_copy
    assert "油墨" in stationery_risk_copy
    assert plush_risk_copy != stationery_risk_copy

    known_ids = {evidence.source_id for evidence in plush_state.all_evidences()}
    for state in (plush_state, stationery_state):
        for evaluation in state.candidate_evaluations.values():
            assert evaluation.feasibility is not None
            assert set(evaluation.feasibility.evidence_ids) <= known_ids
