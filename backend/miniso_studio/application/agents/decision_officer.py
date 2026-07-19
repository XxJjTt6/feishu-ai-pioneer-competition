"""爆款评审 Agent：逐候选评分、稳定排序并联动最终决策。"""
from __future__ import annotations

import math
import re
from typing import List

from miniso_studio.application.agents.base import Agent
from miniso_studio.application.graph.state import PipelineState
from miniso_studio.application.platforms.experience_validation import predict_nps
from miniso_studio.application.scoring.hit_score import (
    CandidateScoreInput,
    LABELS,
    WEIGHTS,
    build_portfolio_scorecards,
    verdict_for,
)
from miniso_studio.common.models import (
    CandidateEvaluation,
    DecisionRecord,
    DecisionVerdict,
    FeasibilityAssessment,
    ProductConcept,
    ProductScorecard,
)


class DecisionOfficerAgent(Agent):
    name = "爆款评审 Agent"
    role = "八维评分 / 候选排序 / GO-NO-GO / 决策审计"

    def run(self, state: PipelineState) -> PipelineState:
        voc = state.voc_report
        if voc is None or not state.concepts:
            return state

        score_inputs: List[CandidateScoreInput] = []
        for concept in state.concepts:
            evaluation = state.candidate_evaluations.get(concept.id) or CandidateEvaluation(
                concept_id=concept.id,
                iteration=state.pm_iteration,
            )
            addressed_aspects = self._addressed_aspects(state, concept)
            nps = predict_nps(voc, evaluation.interviews, addressed_aspects)
            nps.concept_id = concept.id
            evaluation.nps = nps
            state.candidate_evaluations[concept.id] = evaluation
            score_inputs.append(self._score_input(state, concept, evaluation))

        def fallback_scorecards():
            return build_portfolio_scorecards(score_inputs)

        tool_inputs = [item.model_copy(deep=True) for item in score_inputs]
        scorecards = self.call_read_tool(
            "score_candidate_portfolio",
            fallback=fallback_scorecards,
            validator=lambda value: self._valid_scorecards(value, score_inputs),
            inputs=tool_inputs,
        )
        if not self._valid_scorecards(scorecards, score_inputs):
            scorecards = fallback_scorecards()
        scorecards = sorted(scorecards, key=lambda card: (-card.total_score, card.concept_id))
        state.concept_scorecards = scorecards

        for scorecard in scorecards:
            state.candidate_evaluations[scorecard.concept_id].scorecard = scorecard
            state.add_claim(
                (
                    f"候选 {scorecard.concept_id} 爆款评分 {scorecard.total_score:.2f}，"
                    f"建议 {scorecard.recommendation.value}"
                ),
                scorecard.evidence_ids,
            )

        winner_scorecard = scorecards[0]
        concept_by_id = {concept.id: concept for concept in state.concepts}
        winner = concept_by_id[winner_scorecard.concept_id]
        winner_evaluation = state.candidate_evaluations[winner.id]
        state.chosen_concept = winner
        state.interviews = list(winner_evaluation.interviews)
        state.feasibility = winner_evaluation.feasibility
        state.nps = winner_evaluation.nps

        conditions = self._conditions(winner_scorecard, winner_evaluation.feasibility)
        confidence = round(min(0.95, 0.55 + winner_scorecard.total_score / 250.0), 2)
        state.decision = DecisionRecord(
            verdict=winner_scorecard.recommendation,
            confidence=confidence,
            nps_prediction=winner_evaluation.nps.score if winner_evaluation.nps else 0.0,
            rationale=(
                f"候选 {winner.id} 在三条路径中以 {winner_scorecard.total_score:.2f} 分排名第一；"
                f"用户镜像、商品可行性与八维量表按 concept_id 联合评审。"
            ),
            conditions=conditions,
            evidence_ids=winner_scorecard.evidence_ids,
            reviewer="ai",
        )
        state.add_claim(
            f"组合决策：{state.decision.verdict.value}，榜首候选 {winner.id}",
            winner_scorecard.evidence_ids,
        )

        if self.tracer:
            self.tracer.emit(
                self.name,
                "result",
                verdict=state.decision.verdict.value,
                winner_id=winner.id,
                winner_score=winner_scorecard.total_score,
                candidates=len(scorecards),
            )
        return state

    def _score_input(
        self,
        state: PipelineState,
        concept: ProductConcept,
        evaluation: CandidateEvaluation,
    ) -> CandidateScoreInput:
        opportunities = state.voc_report.opportunities if state.voc_report else []
        rank_by_id = {opportunity.id: index for index, opportunity in enumerate(opportunities)}
        ranks = [rank_by_id[item] for item in concept.addressed_opportunity_ids if item in rank_by_id]
        opportunity_rank = min(ranks) if ranks else len(opportunities)

        concept_copy = " ".join(
            [concept.name, concept.one_liner, *concept.key_features, *(d.statement for d in concept.differentiators)]
        )
        trends = state.market_intel.trends if state.market_intel else []
        matching_trends = [trend for trend in trends if trend.name in concept_copy]
        acceptance = (
            sum(item.acceptance for item in evaluation.interviews) / len(evaluation.interviews)
            if evaluation.interviews
            else 0.5
        )
        share_turns = [
            turn
            for interview in evaluation.interviews
            for turn in interview.transcript
            if "分享" in turn.question
        ]
        social_intent = (
            sum(turn.sentiment == "positive" for turn in share_turns) / len(share_turns)
            if share_turns
            else 0.5
        )
        feasibility = evaluation.feasibility or FeasibilityAssessment(concept_id=concept.id)
        severe_risks = [
            risk.description
            for risk in feasibility.risks
            if self._is_blocking_risk(risk.area, risk.description, risk.severity)
        ]
        evidence_ids = self.dedup(
            [
                *(source_id for item in concept.differentiators for source_id in item.evidence_ids),
                *(source_id for item in evaluation.interviews for source_id in item.evidence_ids),
                *feasibility.evidence_ids,
                *(source_id for trend in matching_trends for source_id in trend.evidence_ids),
            ]
        )[:16]
        path_bonus = {"trend_driven": 4.0, "whitespace_driven": 3.0}.get(concept.path, 0.0)
        differentiation = min(100.0, 58.0 + 9.0 * len(concept.differentiators) + path_bonus)
        return CandidateScoreInput(
            concept=concept,
            opportunity_rank=opportunity_rank,
            trend_hits=len(matching_trends),
            demand_acceptance=round(acceptance, 4),
            social_intent=round(social_intent, 4),
            differentiation_score=differentiation,
            margin_score=feasibility.gross_margin_score,
            supply_score=feasibility.supply_feasibility_score,
            ip_score=feasibility.ip_compliance_score,
            localization_score=feasibility.localization_score,
            severe_risk=bool(severe_risks),
            blocking_risks=severe_risks,
            evidence_ids=evidence_ids,
        )

    @staticmethod
    def _is_blocking_risk(area: str, description: str, severity: str) -> bool:
        if severity.lower() not in {"high", "critical"}:
            return False
        normalized_area = re.sub(r"[^a-z0-9]+", "_", area.lower()).strip("_")
        description_lower = description.lower()
        return (
            normalized_area
            in {
                "ip",
                "ip_authorization",
                "ip_compliance",
                "intellectual_property",
                "quality",
                "quality_assurance",
                "quality_control",
                "quality_safety",
            }
            or re.search(r"(?<![a-z])ip(?![a-z])", description_lower) is not None
            or re.search(r"(?<![a-z])quality(?![a-z])", description_lower) is not None
            or any(
                keyword in description
                for keyword in ("授权", "侵权", "知识产权", "质量", "品质红线")
            )
        )

    @staticmethod
    def _addressed_aspects(state: PipelineState, concept: ProductConcept) -> List[str]:
        by_id = {
            opportunity.id: opportunity
            for opportunity in (state.voc_report.opportunities if state.voc_report else [])
        }
        return [
            by_id[opportunity_id].aspect
            for opportunity_id in concept.addressed_opportunity_ids
            if opportunity_id in by_id
        ]

    @staticmethod
    def _valid_scorecards(
        value: object,
        score_inputs: List[CandidateScoreInput],
    ) -> bool:
        if not isinstance(value, list) or not all(
            isinstance(item, ProductScorecard) for item in value
        ):
            return False
        input_by_id = {item.concept.id: item for item in score_inputs}
        if len(input_by_id) != len(score_inputs) or len(value) != len(score_inputs):
            return False
        if {item.concept_id for item in value} != set(input_by_id):
            return False
        if len({item.concept_id for item in value}) != len(value):
            return False

        expected_keys = list(WEIGHTS)
        for scorecard in value:
            score_input = input_by_id[scorecard.concept_id]
            expected_evidence = list(
                dict.fromkeys(item for item in score_input.evidence_ids if item)
            )
            expected_risks = list(
                dict.fromkeys(item for item in score_input.blocking_risks if item)
            )
            if scorecard.evidence_ids != expected_evidence:
                return False
            if scorecard.blocking_risks != expected_risks:
                return False
            if [item.key for item in scorecard.dimensions] != expected_keys:
                return False
            for dimension in scorecard.dimensions:
                if not math.isclose(
                    dimension.weight,
                    WEIGHTS[dimension.key],
                    rel_tol=0.0,
                    abs_tol=1e-9,
                ):
                    return False
                if dimension.label != LABELS[dimension.key] or not dimension.rationale:
                    return False
                if dimension.evidence_ids != expected_evidence:
                    return False
            weighted_total = round(
                sum(item.score * item.weight for item in scorecard.dimensions),
                2,
            )
            if not math.isfinite(scorecard.total_score) or not math.isclose(
                scorecard.total_score,
                weighted_total,
                rel_tol=0.0,
                abs_tol=1e-9,
            ):
                return False
            severe_risk = score_input.severe_risk or bool(expected_risks)
            if scorecard.recommendation != verdict_for(
                scorecard.total_score,
                severe_risk=severe_risk,
            ):
                return False
        return True

    @staticmethod
    def _conditions(
        scorecard: ProductScorecard,
        feasibility: FeasibilityAssessment | None,
    ) -> List[str]:
        if scorecard.recommendation == DecisionVerdict.GO:
            return []
        if scorecard.blocking_risks:
            return [f"关闭阻断风险：{item}" for item in scorecard.blocking_risks]
        if feasibility:
            mitigations = [
                risk.mitigation
                for risk in feasibility.risks
                if risk.severity in {"high", "medium"} and risk.mitigation
            ]
            if mitigations:
                return mitigations[:3]
        return ["完成样件、价格与目标市场小规模试购验证后再进入量产"]
