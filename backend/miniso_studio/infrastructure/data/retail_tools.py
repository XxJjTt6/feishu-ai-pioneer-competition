"""兴趣消费工作流使用的确定性只读工具。"""
from __future__ import annotations

import re
from typing import List

from miniso_studio.common.models import (
    CandidateRevisionContext,
    Differentiator,
    Evidence,
    FeasibilityAssessment,
    Opportunity,
    ProductConcept,
    RiskItem,
    TrendSignal,
)
from miniso_studio.common.tools import ToolType, tool
from miniso_studio.infrastructure.data.connectors import fetch_trends


_TERM_RE = re.compile(r"[a-zA-Z]{2,}|[\u4e00-\u9fff]{2,}")


def _dedup(values: List[str]) -> List[str]:
    return list(dict.fromkeys(value for value in values if value))


def _query_terms(query: str) -> List[str]:
    text = (query or "").lower()
    terms = _TERM_RE.findall(text)
    aliases = {
        "IP": ["ip", "character", "design", "颜值", "联名"],
        "礼赠": ["礼物", "送礼", "gift", "present"],
        "收藏": ["收藏", "系列", "collect", "series"],
        "分享": ["分享", "展示", "开箱", "display", "unboxing"],
        "本地化": ["本地", "城市", "regional", "local"],
        "品质": ["品质", "做工", "耐用", "quality", "durable"],
        "价格": ["价格", "性价比", "price", "value"],
        "包装": ["包装", "package", "packaging"],
    }
    for label, extra in aliases.items():
        if label.lower() in text:
            terms.extend(extra)
    return _dedup([term.lower() for term in terms])


@tool(ToolType.READ)
def search_retail_evidence(
    evidences: List[Evidence],
    query: str,
    top_k: int = 6,
) -> List[Evidence]:
    """按商品、评论文本与品牌检索兴趣消费证据。"""
    terms = _query_terms(query)
    ranked = []
    for evidence in evidences:
        haystack = f"{evidence.product} {evidence.text} {evidence.brand}".lower()
        overlap = sum(term in haystack for term in terms)
        if overlap:
            ranked.append((-overlap, -evidence.helpful_votes, evidence.source_id, evidence))
    ranked.sort(key=lambda item: item[:3])
    if not ranked:
        fallback = sorted(evidences, key=lambda item: (-item.helpful_votes, item.source_id))
        return fallback[: max(0, top_k)]
    return [item[3] for item in ranked[: max(0, top_k)]]


@tool(ToolType.READ)
def get_retail_trends(keywords: List[str]) -> "tuple[List[TrendSignal], List[Evidence]]":
    """获取带来源的可复现兴趣消费趋势信号。"""
    return fetch_trends(keywords)


def build_candidate_portfolio(
    category: str,
    opportunities: List[Opportunity],
    trends: List[TrendSignal],
    white_space: List[Opportunity],
    revision_context: List[CandidateRevisionContext] | None = None,
) -> List[ProductConcept]:
    """候选生成的确定性内核，供工具失败时复用。"""
    top_opportunities = opportunities[:3]
    top_aspects = [item.aspect for item in top_opportunities]
    top_ids = [item.id for item in top_opportunities]
    opportunity_evidence = _dedup(
        [source_id for item in top_opportunities for source_id in item.evidence_ids]
    )
    trend_names = [item.name for item in trends[:4]]
    trend_evidence = _dedup([source_id for item in trends for source_id in item.evidence_ids])
    whitespace_aspects = [item.aspect for item in white_space[:2]] or ["包装", "实用性"]
    whitespace_evidence = _dedup(
        [source_id for item in white_space[:2] for source_id in item.evidence_ids]
    )
    focus = "、".join(top_aspects[:2]) or "情绪价值与礼赠"
    trend_focus = "、".join(trend_names[:3]) or "IP联名、社交传播、全球本地化"
    whitespace_focus = "、".join(whitespace_aspects)

    concepts = [
        ProductConcept(
            id="C-VOC",
            name="心情补给站多用挂件",
            category=category,
            path="voc_driven",
            one_liner=f"把用户在{focus}上的真实需求，做成每天都能使用的小型情绪礼物。",
            target_segment="18-30 岁、重视日常自我奖励与轻礼赠的年轻消费者",
            value_proposition="一件商品同时满足随身实用、情绪陪伴和低负担送礼。",
            key_features=[
                "可替换心情角色牌，兼顾包挂、钥匙扣与桌面展示",
                "可写祝福的礼赠内卡与可回收小包装",
                "基础款与限定配色并行，支持低门槛复购收藏",
            ],
            differentiators=[
                Differentiator(
                    statement=f"以评论机会排序验证{focus}，而非只靠造型直觉",
                    evidence_ids=opportunity_evidence[:6],
                ),
                Differentiator(
                    statement="从自用到轻礼赠可切换，提升单品使用频次",
                    evidence_ids=opportunity_evidence[:6],
                ),
            ],
            tech_enablers=["模块化小件供应链", "小批量配色柔性排产", "可回收纸塑包装"],
            addressed_opportunity_ids=top_ids,
        ),
        ProductConcept(
            id="C-TREND",
            name="世界甜心城市限定香氛挂件",
            category=category,
            path="trend_driven",
            one_liner=f"把{trend_focus}组合成可闻、可挂、可分享的城市记忆。",
            target_segment="喜欢 IP 故事、旅行纪念、系列收藏和社交分享的全球年轻客群",
            value_proposition=(
                "以全球统一角色资产承载区域香型与城市故事，兼顾规模化和本地共鸣。"
            ),
            key_features=[
                "统一角色轮廓搭配城市限定色、香型与双语故事卡",
                "可补充香芯与编号收藏机制，降低重复购买的浪费感",
                "包装内置拍照场景与分享话题，支持门店首发活动",
            ],
            differentiators=[
                Differentiator(
                    statement="全球角色资产与区域文化共创采用双层设计体系",
                    evidence_ids=trend_evidence[:6],
                ),
                Differentiator(
                    statement="香氛消耗、挂件展示与城市收藏形成持续复购闭环",
                    evidence_ids=trend_evidence[:6],
                ),
            ],
            tech_enablers=["已授权或原创角色资产库", "区域香型共创模板", "社媒趋势标签监测"],
            addressed_opportunity_ids=top_ids[:2],
        ),
        ProductConcept(
            id="C-WHITESPACE",
            name="一盒三用礼赠收纳剧场",
            category=category,
            path="whitespace_driven",
            one_liner=(
                f"针对竞品在{whitespace_focus}上的空白，"
                "让包装本身成为可展示的实用商品。"
            ),
            target_segment="关注礼物体面度、居家收纳和价格价值感的家庭及职场送礼人群",
            value_proposition=(
                "礼盒拆开后转为桌面收纳与角色展示台，"
                "减少一次性包装并放大礼赠价值。"
            ),
            key_features=[
                "折叠盒体可切换礼盒、抽屉收纳和角色展示台三种形态",
                "组件可自由组合，适配文具、香氛与小摆件多品类",
                "按节日和区域替换外套纸，不改变核心结构与模具",
            ],
            differentiators=[
                Differentiator(
                    statement=f"直接补齐竞品在{whitespace_focus}上的体验空白",
                    evidence_ids=whitespace_evidence[:6],
                ),
                Differentiator(
                    statement="包装二次使用同时提升礼赠仪式感与实用价值",
                    evidence_ids=_dedup(whitespace_evidence + opportunity_evidence)[:6],
                ),
            ],
            tech_enablers=["免胶折叠结构", "通用内托尺寸体系", "区域纸套数码印刷"],
            addressed_opportunity_ids=top_ids[1:3],
        ),
    ]
    revision_by_id = {
        context.concept_id: context
        for context in (revision_context or [])
    }
    for concept in concepts:
        context = revision_by_id.get(concept.id)
        if context is None:
            continue
        constraints = _dedup(
            [
                *context.must_fixes,
                *context.objections,
                *context.decision_conditions,
                *context.risks,
            ]
        )
        if not constraints:
            continue
        concept.revision_notes = [
            (
                f"第 {context.source_iteration + 1} 轮验证计划：{constraint}"
                "；仅在取得结构化验证结果后更新评分。"
            )
            for constraint in constraints
        ]
    return concepts


@tool(ToolType.READ)
def generate_candidate_portfolio(
    category: str,
    opportunities: List[Opportunity],
    trends: List[TrendSignal],
    white_space: List[Opportunity],
    revision_context: List[CandidateRevisionContext] | None = None,
) -> List[ProductConcept]:
    """从 VOC、趋势与竞品空白生成三条互异候选路径。"""
    return build_candidate_portfolio(
        category,
        opportunities,
        trends,
        white_space,
        revision_context=revision_context,
    )


_MERCH_PROFILES = {
    "C-VOC": (76.0, 84.0, 92.0, 80.0),
    "C-TREND": (70.0, 68.0, 78.0, 92.0),
    "C-WHITESPACE": (82.0, 78.0, 95.0, 86.0),
}


def build_merchandise_assessment(
    concept: ProductConcept,
    evidence_ids: List[str],
) -> FeasibilityAssessment:
    """商品可行性评估的确定性内核。"""
    margin, supply, ip_score, localization = _MERCH_PROFILES.get(
        concept.id,
        (65.0, 65.0, 65.0, 65.0),
    )
    text = " ".join(
        [concept.name, concept.one_liner, *concept.key_features, *concept.tech_enablers]
    )
    risks: List[RiskItem] = []
    if "未授权IP" in text or "未授权 IP" in text:
        risks.append(
            RiskItem(
                area="ip_authorization",
                description="候选包含未完成授权链路的 IP 元素，禁止进入量产。",
                severity="high",
                mitigation="取得书面授权并完成权利地域、品类和期限核验。",
            )
        )
        ip_score = min(ip_score, 25.0)
    elif concept.path == "trend_driven":
        risks.append(
            RiskItem(
                area="ip_authorization",
                description="城市共创素材与角色资产需逐区域核验授权边界。",
                severity="medium",
                mitigation="优先原创角色；建立授权地域、品类与期限台账。",
            )
        )
    if "质量红线" in text:
        risks.append(
            RiskItem(
                area="quality",
                description="候选存在未关闭的耐用性质量红线，禁止上市。",
                severity="high",
                mitigation="完成跌落、耐磨与小部件安全复测后再评审。",
            )
        )
    if concept.path == "whitespace_driven":
        risks.append(
            RiskItem(
                area="quality",
                description="多次折叠后结构强度与印刷耐磨需要打样验证。",
                severity="medium",
                mitigation="开展 200 次折叠与运输振动测试，设定验收抽检标准。",
            )
        )
    if concept.path == "voc_driven":
        risks.append(
            RiskItem(
                area="supply_chain",
                description="多配色小批量可能增加备料复杂度。",
                severity="low",
                mitigation="共用主体物料，限定首发配色数量并滚动补单。",
            )
        )

    severe = any(
        risk.severity == "high" and risk.area in {"ip_authorization", "quality"}
        for risk in risks
    )
    overall = "red" if severe else ("yellow" if any(r.severity == "medium" for r in risks) else "green")
    return FeasibilityAssessment(
        concept_id=concept.id,
        technical="商品结构与现有兴趣消费工艺兼容，关键假设通过样件和门店小测验证。",
        supply_chain=(
            f"供应链可行性 {supply:.0f}/100；核心结构共用，"
            "区域款以表面工艺和纸品差异化。"
        ),
        bom_cost=f"成本与毛利潜力 {margin:.0f}/100；在目标零售价带内保留促销和渠道空间。",
        compliance=f"IP/合规 {ip_score:.0f}/100；按销售区域完成材料、标签和授权审核。",
        quality="量产前执行跌落、耐磨、小部件安全与包装运输测试，并设质量红线闸口。",
        gross_margin=(
            f"目标零售价与物料组合的模拟毛利潜力为 {margin:.0f}/100，"
            "需用企业成本数据校准。"
        ),
        supplier_lead_time=(
            f"供应商成熟度与交期可控度为 {supply:.0f}/100，"
            "建议首轮 6-8 周打样与备料。"
        ),
        ip_authorization=f"IP 授权及权利边界完整度为 {ip_score:.0f}/100，原创与已授权资产优先。",
        regional_compliance=(
            "按区域检查材料安全、年龄标识、香氛成分、语言标签和营销表述。"
        ),
        localization=(
            f"全球本地化适配度为 {localization:.0f}/100，"
            "保留统一结构并替换区域内容层。"
        ),
        gross_margin_score=margin,
        supply_feasibility_score=supply,
        ip_compliance_score=ip_score,
        localization_score=localization,
        overall=overall,
        risks=risks,
        evidence_ids=_dedup(evidence_ids)[:8],
    )


@tool(ToolType.READ)
def assess_merchandise_candidate(
    concept: ProductConcept,
    evidence_ids: List[str],
) -> FeasibilityAssessment:
    """评估候选的质量、毛利、交期、IP、区域合规与本地化。"""
    return build_merchandise_assessment(concept, evidence_ids)
