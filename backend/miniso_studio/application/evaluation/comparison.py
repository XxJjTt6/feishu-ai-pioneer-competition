"""AI 驱动 vs 经验驱动的离线演示对比（Application 层）。

同一 brief：A 组(经验驱动) vs B 组(AI 原生)。在统一维度上量化"本质不同"。
两组均使用合成演示样本计算过程指标，不代表真实 NPS、销量或业务收益。
"""
from __future__ import annotations

from typing import List

from miniso_studio.application.baseline.experience_driven import BaselineResult
from miniso_studio.application.graph.state import PipelineState
from miniso_studio.application.platforms.experience_validation import predict_nps
from miniso_studio.common.models import ArmMetrics, ComparisonReport


def _coverage(addressed_aspects: List[str], top_aspects: List[str]) -> float:
    if not top_aspects:
        return 0.0
    hit = len(set(addressed_aspects) & set(top_aspects))
    return round(hit / min(5, len(top_aspects)), 4)


def _hit_rate(addressed_aspects: List[str], top_aspects: List[str]) -> float:
    if not addressed_aspects:
        return 0.0
    hit = len(set(addressed_aspects) & set(top_aspects))
    return round(hit / len(addressed_aspects), 4)


def build_comparison(state: PipelineState, baseline: BaselineResult, brief: str) -> ComparisonReport:
    voc = state.voc_report
    top_aspects = [o.aspect for o in voc.opportunities[:5]] if voc else []

    # ---- B 组：AI 原生 ----
    b_addressed = []
    if voc and state.chosen_concept:
        opp_by_id = {o.id: o for o in voc.opportunities}
        b_addressed = [opp_by_id[i].aspect for i in state.chosen_concept.addressed_opportunity_ids if i in opp_by_id]
    distinct_evidence = len({eid for _, ids in state.claims for eid in ids})
    candidate_evaluations = list(state.candidate_evaluations.values())
    portfolio_interviews = sum(
        len(evaluation.interviews)
        for evaluation in candidate_evaluations
    )
    portfolio_risks = sum(
        len(evaluation.feasibility.risks)
        for evaluation in candidate_evaluations
        if evaluation.feasibility
    )
    arm_b = ArmMetrics(
        arm="B_ai_native",
        opportunity_coverage=_coverage(b_addressed, top_aspects),
        evidence_citations=distinct_evidence,
        validated_assumptions=portfolio_interviews,
        real_pain_hit_rate=_hit_rate(b_addressed, top_aspects),
        feasibility_risks_identified=portfolio_risks,
        nps_prediction=state.nps.score if state.nps else 0.0,
        elapsed_seconds=0.0,  # 由 runner 填入
        distinct_personas_consulted=len(state.personas),
    )

    # ---- A 组：经验驱动（同样用演示样本计算离线模拟 NPS）----
    a_addressed = baseline.assumed_pains
    a_nps = predict_nps(voc, [], a_addressed).score if voc else 0.0
    arm_a = ArmMetrics(
        arm="A_experience_driven",
        opportunity_coverage=_coverage(a_addressed, top_aspects),
        evidence_citations=baseline.citations,
        validated_assumptions=baseline.validated_assumptions,
        real_pain_hit_rate=_hit_rate(a_addressed, top_aspects),
        feasibility_risks_identified=0,
        nps_prediction=a_nps,
        elapsed_seconds=baseline.elapsed_seconds,
        distinct_personas_consulted=0,
    )

    deltas = {
        "opportunity_coverage": round(arm_b.opportunity_coverage - arm_a.opportunity_coverage, 4),
        "evidence_citations": arm_b.evidence_citations - arm_a.evidence_citations,
        "validated_assumptions": arm_b.validated_assumptions - arm_a.validated_assumptions,
        "real_pain_hit_rate": round(arm_b.real_pain_hit_rate - arm_a.real_pain_hit_rate, 4),
        "feasibility_risks_identified": arm_b.feasibility_risks_identified - arm_a.feasibility_risks_identified,
        "nps_prediction": round(arm_b.nps_prediction - arm_a.nps_prediction, 1),
    }

    narrative = (
        f"经验驱动凭直觉聚焦 {a_addressed}，其中 {int(arm_a.real_pain_hit_rate*100)}% "
        "命中演示样本中的机会项，未引用证据、未做用户验证；"
        "AI 原生榜首候选的离线命中率为 "
        f"{int(arm_b.real_pain_hit_rate*100)}%，组合共引用 {arm_b.evidence_citations} 条合成演示证据、"
        f"完成 {arm_b.validated_assumptions} 次候选-画像模拟访谈、识别全部候选共 "
        f"{arm_b.feasibility_risks_identified} 项商品风险。NPS 差值 {deltas['nps_prediction']} 分"
        "属于离线模拟指标，不代表真实用户反馈或业务收益；"
        "本对比只说明流程具备可溯源、"
        "可验证、可量化和可迭代能力。"
    )

    return ComparisonReport(
        category=state.category,
        brief=brief,
        arm_a=arm_a,
        arm_b=arm_b,
        deltas=deltas,
        narrative=narrative,
    )
