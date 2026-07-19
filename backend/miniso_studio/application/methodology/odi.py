"""机会量化（Application 层）：Ulwick ODI + VOC Impact Score。

- importance：由提及广度(reach)推导（被越多人提到 = 越重要）。
- satisfaction：由正面率推导。
- opportunity_score = importance + max(importance - satisfaction, 0)  （Ulwick 公式）。
- impact_score = Reach × (Severity + Value + Strategic)               （VOC 优先级）。
全部来自确定性 ABSA 统计，可溯源。
"""
from __future__ import annotations

from typing import Dict, List

from miniso_studio.common.models import AspectInsight, Opportunity
from miniso_studio.infrastructure.nlp.absa import AspectStat

# 战略权重反映兴趣消费商品的设计辨识度、品质红线、价值感和全球经营适配度。
STRATEGIC_WEIGHT: Dict[str, float] = {
    "IP/设计吸引力": 1.0,
    "品质/耐用性": 1.0,
    "价格/价值": 0.9,
    "实用性": 0.8,
    "礼赠性": 0.8,
    "收藏性": 0.8,
    "包装": 0.7,
    "门店可得性": 0.7,
    "本地化": 0.9,
}


def aspect_to_insight(stat: AspectStat, total_reviews: int) -> AspectInsight:
    reach = round(stat.mentions / total_reviews, 4) if total_reviews else 0.0
    # importance：reach 越高越重要，映射到 0-10（reach 0.5 -> ~9）
    importance = round(min(10.0, 2.0 + reach * 14.0), 2)
    satisfaction = round(stat.positive_rate * 10.0, 2)
    opportunity = round(importance + max(importance - satisfaction, 0.0), 2)
    severity = round(stat.negative_rate, 4)
    value = 1.0
    strategic = STRATEGIC_WEIGHT.get(stat.aspect, 0.5)
    impact = round(reach * (severity + value + strategic), 4)
    return AspectInsight(
        aspect=stat.aspect,
        mention_count=stat.mentions,
        reach=reach,
        negative_rate=severity,
        importance=importance,
        satisfaction=satisfaction,
        opportunity_score=opportunity,
        impact_score=impact,
        representative_evidence_ids=(stat.negative_evidence_ids or stat.evidence_ids)[:3],
        summary=(
            f"{stat.aspect}：被 {stat.mentions} 条评论提及（覆盖 {reach:.0%}），"
            f"负面率 {severity:.0%}，机会分 {opportunity}。"
        ),
    )


def insights_to_opportunities(insights: List[AspectInsight]) -> List[Opportunity]:
    """把高机会分的 aspect 转成结构化机会（按机会分降序）。"""
    ranked = sorted(insights, key=lambda a: a.opportunity_score, reverse=True)
    opportunities: List[Opportunity] = []
    for i, ins in enumerate(ranked):
        opportunities.append(
            Opportunity(
                id=f"OPP-{i+1}",
                statement=f"用户在「{ins.aspect}」上存在未被满足的体验差（满意度 {ins.satisfaction}/10）",
                aspect=ins.aspect,
                importance=ins.importance,
                satisfaction=ins.satisfaction,
                reach=ins.reach,
                severity=ins.negative_rate,
                opportunity_score=ins.opportunity_score,
                impact_score=ins.impact_score,
                origin="voc",
                evidence_ids=ins.representative_evidence_ids,
                rationale=ins.summary,
            )
        )
    return opportunities
