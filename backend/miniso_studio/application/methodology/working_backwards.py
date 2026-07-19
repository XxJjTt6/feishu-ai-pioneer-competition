"""面向兴趣消费候选 SKU 的 Working Backwards PR/FAQ。"""
from __future__ import annotations

from typing import List

from miniso_studio.common.models import (
    CompetitorFinding,
    FaqItem,
    FeasibilityAssessment,
    NPSPrediction,
    Opportunity,
    PRFAQ,
    ProductConcept,
)


def build_prfaq(
    concept: ProductConcept,
    opportunities: List[Opportunity],
    feasibility: FeasibilityAssessment,
    nps: NPSPrediction,
    competitors: List[CompetitorFinding],
) -> PRFAQ:
    addressed_opportunities = [
        opportunity
        for opportunity in opportunities
        if opportunity.id in concept.addressed_opportunity_ids
    ]
    selected = addressed_opportunities[:3] or opportunities[:3]
    addressed = "、".join(opportunity.aspect for opportunity in selected) or "兴趣消费体验"
    competitor_names = "、".join(item.brand for item in competitors) or "主流兴趣消费品牌"
    enablers = "、".join(concept.tech_enablers) or "柔性商品开发与区域化设计能力"

    external_faq = [
        FaqItem(
            question=f"它与 {competitor_names} 的同类商品有什么不同？",
            answer=(
                f"候选围绕{addressed}的高机会需求设计，并把用户验证、商品风险和上市条件"
                "放在创意评审之前，而不是只比较造型。"
            ),
            evidence_ids=[source_id for item in selected for source_id in item.evidence_ids][:6],
        ),
        FaqItem(
            question="为什么目标消费者可能购买或分享？",
            answer=(
                f"离线用户镜像显示该候选对目标用途、礼赠收藏与分享场景形成完整理由；"
                f"预测 NPS 为 {nps.score:.0f}，该数字仅用于模拟候选间比较。"
            ),
            evidence_ids=nps.evidence_ids[:6],
        ),
        FaqItem(
            question="上市前还需要验证什么？",
            answer=(
                "用真实样件、目标价格、授权文件和区域门店小测校准"
                "试购、分享、质量与毛利假设。"
            ),
            evidence_ids=feasibility.evidence_ids[:6],
        ),
    ]
    internal_faq = [
        FaqItem(
            question="质量与供应商交期是否可控？",
            answer=f"{feasibility.quality} {feasibility.supplier_lead_time}",
            evidence_ids=feasibility.evidence_ids[:6],
        ),
        FaqItem(
            question="成本与毛利空间如何？",
            answer=feasibility.gross_margin,
            evidence_ids=feasibility.evidence_ids[:6],
        ),
        FaqItem(
            question="IP 授权与区域合规如何处理？",
            answer=(
                f"{feasibility.ip_authorization} {feasibility.regional_compliance} "
                f"{feasibility.localization}"
            ),
            evidence_ids=feasibility.evidence_ids[:6],
        ),
        FaqItem(
            question="主要风险和放行条件是什么？",
            answer=(
                "；".join(
                    f"{risk.area}：{risk.description}；措施：{risk.mitigation}"
                    for risk in feasibility.risks[:3]
                )
                or "未识别到阻断风险，仍需按质量标准完成样件验证。"
            ),
            evidence_ids=feasibility.evidence_ids[:6],
        ),
    ]
    return PRFAQ(
        headline=f"MINISO {concept.name}：从趋势信号走到可验证候选 SKU",
        subheading=f"面向{concept.target_segment}。{concept.value_proposition}",
        summary=(
            f"Trend2SKU 离线演示从公开资料与模拟评论中识别{addressed}机会，"
            f"通过{enablers}形成 {concept.name}，并在创意阶段同步评估用户意愿、"
            "质量、毛利、供应链、IP 授权和全球本地化。演示分数不代表企业真实收益。"
        ),
        customer_quote=(
            "“它不只好看，还能对应自用、送礼与分享场景；"
            "价格和授权信息清楚后我会考虑购买。”"
            "——离线用户镜像综合反馈"
        ),
        maker_quote=(
            "“每个数值由同一套确定性量表计算，每项判断都保留证据编号和放行条件。”"
            "——Trend2SKU 爆款评审 Agent"
        ),
        call_to_action=f"先对 {concept.name} 开展小批量样件与目标市场试购验证。",
        external_faq=external_faq,
        internal_faq=internal_faq,
    )
