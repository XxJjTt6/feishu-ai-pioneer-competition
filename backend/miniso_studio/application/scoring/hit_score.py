"""候选 SKU 的确定性八维评分与组合排序。"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from miniso_studio.common.models import (
    DecisionVerdict,
    ProductConcept,
    ProductScorecard,
    ScoreDimension,
)
from miniso_studio.common.tools import ToolType, tool


WEIGHTS = {
    "trend_fit": 0.20,
    "demand_strength": 0.20,
    "differentiation": 0.15,
    "social_virality": 0.15,
    "margin_potential": 0.10,
    "supply_feasibility": 0.10,
    "ip_compliance": 0.05,
    "localization_fit": 0.05,
}

LABELS = {
    "trend_fit": "趋势匹配",
    "demand_strength": "需求强度",
    "differentiation": "差异化",
    "social_virality": "社交传播",
    "margin_potential": "成本与毛利",
    "supply_feasibility": "供应链可行性",
    "ip_compliance": "IP/合规",
    "localization_fit": "全球本地化",
}


class CandidateScoreInput(BaseModel):
    """数值评分所需的结构化、可审计输入。"""

    concept: ProductConcept
    opportunity_rank: int = Field(0, ge=0)
    trend_hits: int = Field(0, ge=0)
    demand_acceptance: float = Field(0.5, ge=0, le=1)
    social_intent: float = Field(0.5, ge=0, le=1)
    differentiation_score: float = Field(65.0, ge=0, le=100)
    margin_score: float = Field(65.0, ge=0, le=100)
    supply_score: float = Field(65.0, ge=0, le=100)
    ip_score: float = Field(65.0, ge=0, le=100)
    localization_score: float = Field(65.0, ge=0, le=100)
    severe_risk: bool = False
    blocking_risks: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, float(value))), 2)


def _dedup(values: List[str]) -> List[str]:
    return list(dict.fromkeys(value for value in values if value))


def verdict_for(total: float, severe_risk: bool = False) -> DecisionVerdict:
    """按固定阈值给出建议；严重 IP/质量风险禁止直接 GO。"""
    if total >= 75 and not severe_risk:
        return DecisionVerdict.GO
    if total >= 60:
        return DecisionVerdict.CONDITIONAL_GO
    return DecisionVerdict.NO_GO


def build_scorecard(
    concept: ProductConcept,
    opportunity_rank: int,
    trend_hits: int,
    evidence_ids: List[str],
    *,
    demand_acceptance: Optional[float] = None,
    social_intent: Optional[float] = None,
    differentiation_score: Optional[float] = None,
    margin_score: float = 65.0,
    supply_score: float = 65.0,
    ip_score: float = 65.0,
    localization_score: float = 65.0,
    severe_risk: bool = False,
    blocking_risks: Optional[List[str]] = None,
) -> ProductScorecard:
    """构建单候选评分卡；相同输入始终返回相同结果。"""
    opportunity_rank = max(0, int(opportunity_rank))
    trend_hits = max(0, int(trend_hits))
    ids = _dedup(evidence_ids)
    risks = _dedup(blocking_risks or [])

    trend_score = _clamp(48 + 12 * trend_hits)
    if demand_acceptance is None:
        demand_score = _clamp(88 - 8 * opportunity_rank)
    else:
        demand_score = _clamp(35 + 60 * demand_acceptance - 2 * opportunity_rank)
    if differentiation_score is None:
        differentiation_score = 52 + 9 * len(concept.differentiators)
    if social_intent is None:
        concept_copy = " ".join(
            [concept.one_liner, *concept.key_features, *(d.statement for d in concept.differentiators)]
        )
        social_hits = sum(term in concept_copy for term in ("分享", "开箱", "展示", "社交", "系列"))
        social_score = _clamp(48 + 8 * social_hits)
    else:
        social_score = _clamp(35 + 60 * social_intent)

    values = {
        "trend_fit": trend_score,
        "demand_strength": demand_score,
        "differentiation": _clamp(differentiation_score),
        "social_virality": social_score,
        "margin_potential": _clamp(margin_score),
        "supply_feasibility": _clamp(supply_score),
        "ip_compliance": _clamp(ip_score),
        "localization_fit": _clamp(localization_score),
    }
    rationales = {
        "trend_fit": f"候选与 {trend_hits} 个已采集趋势信号直接匹配。",
        "demand_strength": (
            f"机会排序第 {opportunity_rank + 1}，"
            + (
                "使用机会优先级形成需求强度基线。"
                if demand_acceptance is None
                else f"用户镜像平均接受度为 {demand_acceptance:.0%}。"
            )
        ),
        "differentiation": f"依据候选的 {len(concept.differentiators)} 项可溯源差异点。",
        "social_virality": (
            "依据候选中的系列化、展示与分享机制。"
            if social_intent is None
            else f"用户镜像分享意愿为 {social_intent:.0%}。"
        ),
        "margin_potential": "依据目标毛利带、物料复杂度和零售价空间评估。",
        "supply_feasibility": "依据供应商成熟度、工艺复杂度和交期评估。",
        "ip_compliance": "依据 IP 授权链路、质量红线和区域合规评估。",
        "localization_fit": "依据全球通用设计与区域限定改款能力评估。",
    }
    dimensions = [
        ScoreDimension(
            key=key,
            label=LABELS[key],
            score=values[key],
            weight=weight,
            rationale=rationales[key],
            evidence_ids=ids,
        )
        for key, weight in WEIGHTS.items()
    ]
    total = round(sum(item.score * item.weight for item in dimensions), 2)
    return ProductScorecard(
        concept_id=concept.id,
        dimensions=dimensions,
        total_score=total,
        recommendation=verdict_for(total, severe_risk=severe_risk or bool(risks)),
        evidence_ids=ids,
        blocking_risks=risks,
    )


def build_portfolio_scorecards(inputs: List[CandidateScoreInput]) -> List[ProductScorecard]:
    cards = [
        build_scorecard(
            item.concept,
            opportunity_rank=item.opportunity_rank,
            trend_hits=item.trend_hits,
            evidence_ids=item.evidence_ids,
            demand_acceptance=item.demand_acceptance,
            social_intent=item.social_intent,
            differentiation_score=item.differentiation_score,
            margin_score=item.margin_score,
            supply_score=item.supply_score,
            ip_score=item.ip_score,
            localization_score=item.localization_score,
            severe_risk=item.severe_risk,
            blocking_risks=item.blocking_risks,
        )
        for item in inputs
    ]
    return sorted(cards, key=lambda card: (-card.total_score, card.concept_id))


@tool(ToolType.READ)
def score_candidate_portfolio(inputs: List[CandidateScoreInput]) -> List[ProductScorecard]:
    """按统一八维量表为候选组合评分并稳定排序。"""
    return build_portfolio_scorecards(inputs)
