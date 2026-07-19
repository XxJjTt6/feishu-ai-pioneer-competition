"""创意工坊 Agent：并行生成三条候选 SKU 路径并做初筛。"""
from __future__ import annotations

from miniso_studio.application.agents.base import Agent
from miniso_studio.application.graph.state import PipelineState
from miniso_studio.application.portfolio.dynamic_candidates import (
    build_dynamic_portfolio,
)
from miniso_studio.application.scoring.hit_score import build_scorecard
from miniso_studio.common.models import (
    CandidateEvaluation,
    CandidateRevisionContext,
    ProductConcept,
    ProductScorecard,
)
from miniso_studio.infrastructure.data.retail_tools import build_candidate_portfolio


_EXPECTED_IDS = {"C-VOC", "C-TREND", "C-WHITESPACE"}


class ProductManagerAgent(Agent):
    name = "创意工坊 Agent"
    role = "VOC / 趋势 / 白空间三路径候选生成"

    def run(self, state: PipelineState) -> PipelineState:
        voc = state.voc_report
        if voc is None:
            return state

        revision_context = self._build_revision_context(state)
        state.pm_iteration += 1
        state.clear_candidate_cycle()
        state.revision_context = revision_context
        trends = state.market_intel.trends if state.market_intel else []
        white_space = state.market_intel.white_space_opportunities if state.market_intel else []

        def fallback_portfolio():
            return build_dynamic_portfolio(
                state.decision_input,
                [*voc.opportunities, *white_space],
                trends,
                revision_context=revision_context,
            )

        concepts = self.call_read_tool(
            "generate_candidate_portfolio",
            fallback=fallback_portfolio,
            validator=lambda value: self._valid_portfolio(value, revision_context),
            category=state.category,
            opportunities=voc.opportunities,
            trends=trends,
            white_space=white_space,
            revision_context=revision_context,
        )
        if not self._valid_portfolio(concepts, revision_context):
            concepts = fallback_portfolio()
        elif not state.legacy_input:
            concepts = fallback_portfolio()

        state.concepts = concepts
        state.candidate_evaluations = {
            concept.id: CandidateEvaluation(
                concept_id=concept.id,
                iteration=state.pm_iteration,
            )
            for concept in concepts
        }
        provisional = [self._provisional_scorecard(state, concept) for concept in concepts]
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
            revised_candidates = sum(bool(concept.revision_notes) for concept in concepts)
            self.tracer.emit(
                self.name,
                "result",
                iteration=state.pm_iteration,
                candidates=len(concepts),
                provisional_winner=provisional[0].concept_id,
                revised_candidates=revised_candidates,
                revision_notes=sum(len(concept.revision_notes) for concept in concepts),
            )
        return state

    def _build_revision_context(
        self,
        state: PipelineState,
    ) -> list[CandidateRevisionContext]:
        if not state.candidate_evaluations:
            return []
        winner_id = state.chosen_concept.id if state.chosen_concept else ""
        contexts = []
        for concept_id in [concept.id for concept in state.concepts]:
            evaluation = state.candidate_evaluations.get(concept_id)
            if evaluation is None:
                continue
            feasibility = evaluation.feasibility
            risks = [
                (
                    f"{risk.description}；缓解：{risk.mitigation}"
                    if risk.mitigation
                    else risk.description
                )
                for risk in (feasibility.risks if feasibility else [])
            ]
            if evaluation.scorecard:
                risks.extend(evaluation.scorecard.blocking_risks)
            contexts.append(
                CandidateRevisionContext(
                    concept_id=concept_id,
                    source_iteration=max(1, evaluation.iteration),
                    objections=self.dedup(
                        [item for interview in evaluation.interviews for item in interview.objections]
                    ),
                    must_fixes=self.dedup(
                        [item for interview in evaluation.interviews for item in interview.must_fixes]
                    ),
                    decision_conditions=(
                        list(state.decision.conditions)
                        if state.decision and concept_id == winner_id
                        else []
                    ),
                    risks=self.dedup(risks),
                    evidence_ids=self.dedup(
                        [
                            *(
                                source_id
                                for interview in evaluation.interviews
                                for source_id in interview.evidence_ids
                            ),
                            *(feasibility.evidence_ids if feasibility else []),
                        ]
                    )[:12],
                )
            )
        return contexts

    @staticmethod
    def _valid_portfolio(
        value: object,
        revision_context: list[CandidateRevisionContext] | None = None,
    ) -> bool:
        structurally_valid = (
            isinstance(value, list)
            and len(value) == 3
            and all(isinstance(item, ProductConcept) for item in value)
            and {item.id for item in value} == _EXPECTED_IDS
            and len({item.id for item in value}) == len(value)
            and len({item.name for item in value}) == len(value)
        )
        if not structurally_valid:
            return False
        revised_ids = {
            context.concept_id
            for context in (revision_context or [])
            if any(
                [
                    *context.objections,
                    *context.must_fixes,
                    *context.decision_conditions,
                    *context.risks,
                ]
            )
        }
        return all(
            concept.id not in revised_ids
            or bool(concept.revision_notes)
            for concept in value
        )

    @staticmethod
    def _provisional_scorecard(
        state: PipelineState,
        concept: ProductConcept,
    ) -> ProductScorecard:
        opportunities = state.voc_report.opportunities if state.voc_report else []
        rank_by_id = {item.id: index for index, item in enumerate(opportunities)}
        ranks = [rank_by_id[item] for item in concept.addressed_opportunity_ids if item in rank_by_id]
        opportunity_rank = min(ranks) if ranks else len(opportunities)
        trends = state.market_intel.trends if state.market_intel else []
        concept_copy = " ".join(
            [concept.name, concept.one_liner, *concept.key_features, *(d.statement for d in concept.differentiators)]
        )
        matched = [trend for trend in trends if trend.name in concept_copy]
        evidence_ids = [
            source_id
            for differentiator in concept.differentiators
            for source_id in differentiator.evidence_ids
        ]
        evidence_ids.extend(source_id for trend in matched for source_id in trend.evidence_ids)
        return build_scorecard(
            concept,
            opportunity_rank=opportunity_rank,
            trend_hits=len(matched),
            evidence_ids=list(dict.fromkeys(evidence_ids)),
        )
