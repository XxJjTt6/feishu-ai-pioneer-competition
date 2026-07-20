"""Qwen 动态策略在既有确定性评分链上的 Agent 适配器。"""
from __future__ import annotations

from miniso_studio.application.agents.decision_officer import DecisionOfficerAgent
from miniso_studio.application.agents.industry_expert import IndustryExpertAgent
from miniso_studio.application.agents.product_manager import ProductManagerAgent
from miniso_studio.application.agents.user_proxy import UserProxyAgent
from miniso_studio.application.graph.state import PipelineState
from miniso_studio.application.llm_decision_dynamic import QwenDecisionEngine
from miniso_studio.application.portfolio.dynamic_candidates import build_dynamic_portfolio
from miniso_studio.common.models import CandidateEvaluation


class LLMProductManagerAgent(ProductManagerAgent):
    """由 Qwen 生成候选、访谈与商品风险草案，失败时显式确定性降级。"""

    def __init__(self, gateway, rag, tracer, decision_engine: QwenDecisionEngine):
        super().__init__(gateway, rag, tracer)
        self.decision_engine = decision_engine

    def run(self, state: PipelineState) -> PipelineState:
        voc = state.voc_report
        if voc is None:
            return state

        revision_context = self._build_revision_context(state)
        state.pm_iteration += 1
        state.clear_candidate_cycle()
        state.revision_context = revision_context
        trends = state.market_intel.trends if state.market_intel else []
        white_space = (
            state.market_intel.white_space_opportunities if state.market_intel else []
        )
        draft = self.decision_engine.generate_strategy(state)
        if draft is None:
            concepts = build_dynamic_portfolio(
                state.decision_input,
                [*voc.opportunities, *white_space],
                trends,
                revision_context=revision_context,
            )
            source = "deterministic_fallback"
        else:
            concepts = self.decision_engine.concepts_from_strategy(state, draft)
            source = "qwen_structured"

        state.concepts = concepts
        state.candidate_evaluations = {
            concept.id: CandidateEvaluation(
                concept_id=concept.id,
                iteration=state.pm_iteration,
            )
            for concept in concepts
        }
        provisional = [
            self._provisional_scorecard(state, concept) for concept in concepts
        ]
        provisional.sort(key=lambda card: (-card.total_score, card.concept_id))
        concept_by_id = {concept.id: concept for concept in concepts}
        state.chosen_concept = concept_by_id[provisional[0].concept_id]

        for concept in concepts:
            for differentiator in concept.differentiators:
                state.add_claim(
                    f"候选 {concept.id} 差异点：{differentiator.statement}",
                    differentiator.evidence_ids,
                )
        if self.tracer:
            self.tracer.emit(
                self.name,
                "result",
                iteration=state.pm_iteration,
                candidates=len(concepts),
                provisional_winner=provisional[0].concept_id,
                generation_source=source,
            )
        return state

class LLMUserProxyAgent(UserProxyAgent):
    """使用同一轮 Qwen 策略草案中的合成访谈，不再拼接固定问答。"""

    def __init__(self, gateway, rag, tracer, decision_engine: QwenDecisionEngine):
        super().__init__(gateway, rag, tracer)
        self.decision_engine = decision_engine

    def run(self, state: PipelineState) -> PipelineState:
        draft = self.decision_engine.latest_strategy
        if draft is None:
            return super().run(state)
        self.decision_engine.apply_interviews(state, draft)
        if self.tracer:
            self.tracer.emit(
                self.name,
                "result",
                personas=len(state.personas),
                candidates=len(state.candidate_evaluations),
                interviews=sum(
                    len(item.interviews)
                    for item in state.candidate_evaluations.values()
                ),
                generation_source="qwen_structured",
            )
        return state


class LLMIndustryExpertAgent(IndustryExpertAgent):
    """保留本地数值和硬风险闸口，使用 Qwen 生成本轮专属商品化叙述。"""

    def __init__(self, gateway, rag, tracer, decision_engine: QwenDecisionEngine):
        super().__init__(gateway, rag, tracer)
        self.decision_engine = decision_engine

    def run(self, state: PipelineState) -> PipelineState:
        state = super().run(state)
        draft = self.decision_engine.latest_strategy
        if draft is not None:
            self.decision_engine.apply_feasibility(state, draft)
            if self.tracer:
                self.tracer.emit(
                    self.name,
                    "llm_enriched",
                    candidates=len(state.candidate_evaluations),
                    generation_source="qwen_structured",
                )
        return state


class LLMDecisionOfficerAgent(DecisionOfficerAgent):
    """本地评分完成后，再由 Qwen 对每个维度和组合结论作针对性批判。"""

    def __init__(self, gateway, rag, tracer, decision_engine: QwenDecisionEngine):
        super().__init__(gateway, rag, tracer)
        self.decision_engine = decision_engine

    def run(self, state: PipelineState) -> PipelineState:
        state = super().run(state)
        if state.decision is None or not state.concept_scorecards:
            return state
        draft = self.decision_engine.generate_decision(state)
        if draft is not None:
            self.decision_engine.apply_decision(state, draft)
            if self.tracer:
                self.tracer.emit(
                    self.name,
                    "llm_enriched",
                    dimensions=sum(
                        len(scorecard.dimensions)
                        for scorecard in state.concept_scorecards
                    ),
                    generation_source="qwen_structured",
                )
        return state
