"""Qwen 严格动态内容与本地确定性评分组合的 Trend2SKU 工作流。"""
from __future__ import annotations

from miniso_studio.application.agents.llm_agents_dynamic import (
    LLMDecisionOfficerAgent,
    LLMIndustryExpertAgent,
    LLMProductManagerAgent,
    LLMUserProxyAgent,
)
from miniso_studio.application.agents.super_think_tank import SuperThinkTankAgent
from miniso_studio.application.graph.engine import END, StateGraph
from miniso_studio.application.graph.state import PipelineState
from miniso_studio.application.llm_decision_strict_dynamic import (
    QwenStrictDecisionEngine,
)
from miniso_studio.application.methodology.working_backwards import build_prfaq
from miniso_studio.application.platforms.consumer_insights import build_voc_report
from miniso_studio.application.platforms.experience_validation import experience_trend
from miniso_studio.common.models import ProductProposal
from miniso_studio.infrastructure.assets.media import (
    generate_concept_image,
    synthesize_narration,
)
from miniso_studio.infrastructure.llm.gateway import LLMGateway
from miniso_studio.infrastructure.observability.trace import Tracer


def build_qwen_strict_graph(
    gateway: LLMGateway,
    rag,
    tracer: Tracer,
    hitl: bool = False,
) -> StateGraph:
    """建立严格动态 Qwen 图；远程结果不完整时整轮失败关闭。"""

    decision_engine = QwenStrictDecisionEngine(gateway, tracer)
    trend_radar = SuperThinkTankAgent(gateway, rag, tracer)
    ideation = LLMProductManagerAgent(
        gateway,
        rag,
        tracer,
        decision_engine,
    )
    user_mirror = LLMUserProxyAgent(
        gateway,
        rag,
        tracer,
        decision_engine,
    )
    merchandise_expert = LLMIndustryExpertAgent(
        gateway,
        rag,
        tracer,
        decision_engine,
    )
    hit_judge = LLMDecisionOfficerAgent(
        gateway,
        rag,
        tracer,
        decision_engine,
    )

    def insight_node(state: PipelineState) -> PipelineState:
        report = build_voc_report(
            state.category,
            state.target_brand,
            state.target_evidences,
        )
        state.voc_report = report
        focus = [opportunity.aspect for opportunity in report.opportunities[:3]]
        state.experience_trend = experience_trend(state.target_evidences, focus)
        for opportunity in report.opportunities[:5]:
            state.add_claim(opportunity.statement, opportunity.evidence_ids)
        return state

    def proposal_node(state: PipelineState) -> PipelineState:
        concept = state.chosen_concept
        voc = state.voc_report
        scorecard = next(
            (
                item
                for item in state.concept_scorecards
                if concept is not None and item.concept_id == concept.id
            ),
            None,
        )
        if (
            concept is None
            or voc is None
            or scorecard is None
            or state.decision is None
            or state.feasibility is None
            or state.nps is None
        ):
            return state
        concept_ids = {item.id for item in state.concepts}
        scorecard_ids = {item.concept_id for item in state.concept_scorecards}
        if concept_ids != scorecard_ids:
            return state

        prfaq = build_prfaq(
            concept=concept,
            opportunities=voc.opportunities,
            feasibility=state.feasibility,
            nps=state.nps,
            competitors=(
                state.market_intel.competitors if state.market_intel else []
            ),
        )
        decision_draft = decision_engine.latest_decision
        if decision_draft is not None:
            proposal = decision_draft.proposal
            evidence_ids = list(scorecard.evidence_ids)[:8]
            prfaq.headline = proposal.headline
            prfaq.subheading = proposal.subheading
            prfaq.summary = proposal.summary
            prfaq.customer_quote = proposal.customer_quote
            prfaq.maker_quote = proposal.maker_quote
            prfaq.call_to_action = proposal.call_to_action
            prfaq.external_faq = proposal.external_faq_items(evidence_ids)
            prfaq.internal_faq = proposal.internal_faq_items(evidence_ids)
        state.prfaq = prfaq
        addressed = [
            opportunity
            for opportunity in voc.opportunities
            if opportunity.id in concept.addressed_opportunity_ids
        ]
        image_path = generate_concept_image(
            f"MINISO interest goods product concept, {concept.name}, "
            f"{concept.one_liner}, bright retail product photography, "
            "clean white background"
        )
        narration = synthesize_narration(prfaq.summary)
        state.proposal = ProductProposal(
            concept=concept,
            scorecard=scorecard,
            prfaq=prfaq,
            feasibility=state.feasibility,
            nps=state.nps,
            addressed_opportunities=addressed,
            decision=state.decision,
            concept_image_path=image_path,
            narration_audio_path=narration,
        )
        state.add_claim(
            f"动态提案：{prfaq.headline}；{prfaq.summary}",
            scorecard.evidence_ids,
        )
        return state

    def route_after_judgement(state: PipelineState) -> str:
        # 一次运行只生成一轮策略和一轮决策；条件项进入验证计划，不再触发整轮 LLM 重跑。
        return "proposal"

    def decision_review_node(state: PipelineState) -> PipelineState:
        return state

    graph = StateGraph(tracer=tracer, hitl=hitl)
    graph.add_node("insight", insight_node)
    graph.add_node("trend_radar", trend_radar.run)
    graph.add_node("ideation", ideation.run)
    graph.add_node("user_mirror", user_mirror.run)
    graph.add_node("merchandise_expert", merchandise_expert.run)
    graph.add_node("hit_judge", hit_judge.run)
    graph.add_node("decision_review", decision_review_node)
    graph.add_node("proposal", proposal_node)

    graph.set_entry("insight")
    graph.add_edge("insight", "trend_radar")
    graph.add_edge("trend_radar", "ideation")
    graph.add_edge("ideation", "user_mirror")
    graph.add_edge("user_mirror", "merchandise_expert")
    graph.add_edge("merchandise_expert", "hit_judge")
    graph.add_edge("hit_judge", "decision_review")
    graph.add_conditional("decision_review", route_after_judgement)
    graph.add_edge("proposal", END)
    graph.set_interrupt_before(["decision_review"])
    return graph
