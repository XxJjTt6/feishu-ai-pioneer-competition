"""Trend2SKU 工作流图：洞察、趋势、创意、验证、评审与提案。"""
from __future__ import annotations

from miniso_studio.application.agents.decision_officer import DecisionOfficerAgent
from miniso_studio.application.agents.industry_expert import IndustryExpertAgent
from miniso_studio.application.agents.product_manager import ProductManagerAgent
from miniso_studio.application.agents.super_think_tank import SuperThinkTankAgent
from miniso_studio.application.agents.user_proxy import UserProxyAgent
from miniso_studio.application.graph.engine import END, StateGraph
from miniso_studio.application.graph.state import PipelineState
from miniso_studio.application.methodology.working_backwards import build_prfaq
from miniso_studio.application.platforms.consumer_insights import build_voc_report
from miniso_studio.application.platforms.experience_validation import experience_trend
from miniso_studio.common.models import DecisionVerdict, ProductProposal
from miniso_studio.infrastructure.assets.media import generate_concept_image, synthesize_narration
from miniso_studio.infrastructure.llm.gateway import LLMGateway
from miniso_studio.infrastructure.observability.trace import Tracer


def build_studio_graph(
    gateway: LLMGateway,
    rag,
    tracer: Tracer,
    hitl: bool = False,
) -> StateGraph:
    trend_radar = SuperThinkTankAgent(gateway, rag, tracer)
    ideation = ProductManagerAgent(gateway, rag, tracer)
    user_mirror = UserProxyAgent(gateway, rag, tracer)
    merchandise_expert = IndustryExpertAgent(gateway, rag, tracer)
    hit_judge = DecisionOfficerAgent(gateway, rag, tracer)

    def insight_node(state: PipelineState) -> PipelineState:
        report = build_voc_report(state.category, state.target_brand, state.target_evidences)
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
            competitors=state.market_intel.competitors if state.market_intel else [],
        )
        prfaq.summary = gateway.narrate(
            prfaq.summary,
            "润色兴趣消费新品提案摘要，保留全部事实和模拟数据边界",
            context=concept.value_proposition,
        )
        state.prfaq = prfaq
        addressed = [
            opportunity
            for opportunity in voc.opportunities
            if opportunity.id in concept.addressed_opportunity_ids
        ]
        image_path = generate_concept_image(
            f"MINISO interest goods product concept, {concept.name}, {concept.one_liner}, "
            "bright retail product photography, clean white background"
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
        return state

    def route_after_judgement(state: PipelineState) -> str:
        decision = state.decision
        if decision is None:
            return "proposal"
        if decision.verdict == DecisionVerdict.GO or state.pm_iteration >= state.max_pm_iterations:
            return "proposal"
        return "ideation"

    def decision_review_node(state: PipelineState) -> PipelineState:
        """HITL 恢复落点；评分与风险已生成，批准后只负责继续路由。"""
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
