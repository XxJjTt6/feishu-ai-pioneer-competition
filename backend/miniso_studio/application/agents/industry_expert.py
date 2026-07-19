"""商品专家 Agent：逐候选评估商品化、供应链、IP 与质量风险。"""
from __future__ import annotations

from miniso_studio.application.agents.base import Agent
from miniso_studio.application.graph.state import PipelineState
from miniso_studio.common.models import CandidateEvaluation, FeasibilityAssessment
from miniso_studio.infrastructure.data.retail_tools import build_merchandise_assessment


class IndustryExpertAgent(Agent):
    name = "商品专家 Agent"
    role = "质量 / 毛利 / 交期 / IP授权 / 区域合规 / 本地化"

    def run(self, state: PipelineState) -> PipelineState:
        if not state.concepts:
            return state

        for concept in state.concepts:
            evaluation = state.candidate_evaluations.get(concept.id) or CandidateEvaluation(
                concept_id=concept.id,
                iteration=state.pm_iteration,
            )
            evidence_ids = self.dedup(
                [
                    *(source_id for item in concept.differentiators for source_id in item.evidence_ids),
                    *(source_id for item in evaluation.interviews for source_id in item.evidence_ids),
                ]
            )[:10]
            def fallback_assessment(
                concept=concept,
                evidence_ids=evidence_ids,
            ):
                return build_merchandise_assessment(concept, evidence_ids)

            assessment = self.call_read_tool(
                "assess_merchandise_candidate",
                fallback=fallback_assessment,
                validator=lambda value, concept_id=concept.id: (
                    isinstance(value, FeasibilityAssessment)
                    and value.concept_id == concept_id
                ),
                concept=concept,
                evidence_ids=evidence_ids,
            )
            if not isinstance(assessment, FeasibilityAssessment) or assessment.concept_id != concept.id:
                assessment = fallback_assessment()
            evaluation.feasibility = assessment
            state.candidate_evaluations[concept.id] = evaluation

            state.add_claim(
                f"候选 {concept.id} 商品化评估：{assessment.overall}",
                assessment.evidence_ids,
            )
            for risk in assessment.risks:
                state.add_claim(
                    f"候选 {concept.id} 风险（{risk.area}）：{risk.description}",
                    assessment.evidence_ids,
                )

        winner_id = state.chosen_concept.id if state.chosen_concept else ""
        winner_evaluation = state.candidate_evaluations.get(winner_id)
        state.feasibility = winner_evaluation.feasibility if winner_evaluation else None

        if self.tracer:
            self.tracer.emit(
                self.name,
                "result",
                candidates=len(state.candidate_evaluations),
                risk_counts={
                    concept_id: len(evaluation.feasibility.risks)
                    if evaluation.feasibility
                    else 0
                    for concept_id, evaluation in state.candidate_evaluations.items()
                },
            )
        return state
