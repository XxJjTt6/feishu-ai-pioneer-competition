"""按品类画像与规范化决策输入生成稳定的三路径候选组合。"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from typing import Iterable, Sequence

from miniso_studio.common.decision_input import DecisionInput
from miniso_studio.common.models import (
    CandidateRevisionContext,
    Differentiator,
    Opportunity,
    ProductConcept,
    TrendSignal,
)


@dataclass(frozen=True)
class CategoryProfile:
    """一个品类的商品词汇、结构模块、材料风险与核心场景。"""

    noun: str
    form: str
    modules: tuple[str, ...]
    material_risks: tuple[str, ...]
    scenarios: tuple[str, ...]
    enablers: tuple[str, ...]


_CATEGORY_PROFILES = {
    "plush": CategoryProfile(
        noun="毛绒玩偶",
        form="可拆洗抱枕挂件",
        modules=("情感陪伴模块", "可拆洗外套", "可替换表情配件"),
        material_risks=("掉毛", "色牢度", "缝线强度", "细小部件安全"),
        scenarios=("亲子互动", "睡前陪伴", "节日礼赠"),
        enablers=("短绒面料柔性打样", "可拆洗结构", "小部件拉力测试"),
    ),
    "fragrance_accessory": CategoryProfile(
        noun="香氛配饰",
        form="可补充香芯挂件",
        modules=("替换香芯", "浓度提示", "挂扣展示模块"),
        material_risks=("香精致敏", "渗漏", "挥发稳定性", "易燃标识"),
        scenarios=("日常通勤", "衣橱留香", "旅行纪念"),
        enablers=("标准香芯仓", "低渗透密封", "区域香型小批量灌装"),
    ),
    "stationery": CategoryProfile(
        noun="文创文具",
        form="分区笔袋文具组",
        modules=("顺滑书写模块", "课程分区标签", "同伴交换配件"),
        material_risks=("油墨迁移", "笔尖安全", "纸张受潮", "塑化剂控制"),
        scenarios=("校园课堂", "开学整理", "同学交换"),
        enablers=("水性油墨", "通用笔芯", "防潮纸品包装"),
    ),
    "home_storage": CategoryProfile(
        noun="家居收纳",
        form="可叠放分区收纳盒",
        modules=("可调分区模块", "标签视窗", "折叠扩容结构"),
        material_risks=("承重变形", "边缘毛刺", "材料异味", "夹手风险"),
        scenarios=("居家整理", "租住空间", "桌面归类"),
        enablers=("通用箱体尺寸", "圆角模具", "承重与跌落测试"),
    ),
    "beauty_tool": CategoryProfile(
        noun="美妆工具",
        form="便携分区工具组",
        modules=("快速上妆模块", "干湿分离收纳", "替换清洁配件"),
        material_risks=("皮肤接触安全", "刷毛脱落", "金属镀层迁移", "清洁残留"),
        scenarios=("日常梳妆", "差旅补妆", "新手练习"),
        enablers=("皮肤接触材料检测", "刷毛拉力测试", "可清洁结构"),
    ),
    "digital_accessory": CategoryProfile(
        noun="数码配件",
        form="折叠支架理线套件",
        modules=("多角度支架", "桌面理线模块", "设备识别标签"),
        material_risks=("发热", "阻燃", "接口寿命", "夹持磨损"),
        scenarios=("移动办公", "宿舍娱乐", "差旅收纳"),
        enablers=("通用接口规范", "阻燃材料验证", "开合寿命测试"),
    ),
    "other": CategoryProfile(
        noun="兴趣用品",
        form="可组合套装",
        modules=("可替换功能模块", "分类收纳结构", "场景识别标签"),
        material_risks=("材料适配", "结构耐久", "标签合规", "运输防护"),
        scenarios=("户外活动", "日常使用", "轻量礼赠"),
        enablers=("通用模块接口", "小批量打样", "场景化验收清单"),
    ),
}

_OBJECTIVE_COPY = {
    "emotional": ("情感", "体验温度"),
    "social": ("互动", "互动扩散"),
    "margin": ("效益", "成本纪律"),
    "supply_chain": ("交付", "稳定交付"),
    "localization": ("适配", "区域适配"),
}

_IP_COPY = {
    "original": ("原创", "原创角色体系"),
    "licensed": ("授权", "已授权角色体系"),
    "none": ("无IP", "无角色授权依赖的图形体系"),
    "evaluate": ("待评", "权利策略待评审的视觉体系"),
}

_PATH_NAMES = {
    "C-VOC": "共鸣",
    "C-TREND": "新潮",
    "C-WHITESPACE": "空白",
}


def _as_text(value: object) -> str:
    return getattr(value, "value", value) or ""


def _dedup(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def category_profile(decision: DecisionInput) -> CategoryProfile:
    """返回不可变品类画像；自定义品类只替换商品名词。"""
    category = str(_as_text(decision.product_category))
    profile = _CATEGORY_PROFILES.get(category, _CATEGORY_PROFILES["other"])
    if category != "other":
        return profile
    return replace(profile, noun=decision.category_label)


def _constraint_tag(constraints: str) -> str:
    if not constraints:
        return "标准"
    digest = hashlib.sha256(constraints.encode("utf-8")).hexdigest()[:12]
    return f"约束{digest}"


def _decision_copy(decision: DecisionInput) -> dict[str, str]:
    objective_values = [_as_text(item) for item in decision.objectives]
    objective_pairs = [_OBJECTIVE_COPY[item] for item in objective_values]
    objective_tag = "".join(item[0] for item in objective_pairs)
    objective_phrase = "、".join(item[1] for item in objective_pairs)
    ip_tag, ip_phrase = _IP_COPY[_as_text(decision.ip_strategy)]
    constraints = decision.constraints or "常规零售验收条件"
    brief_tag = hashlib.sha256(decision.brief.encode("utf-8")).hexdigest()[:16].upper()
    return {
        "segment": decision.target_segment_label,
        "market": decision.target_market_label,
        "price": decision.price_label,
        "ip_tag": ip_tag,
        "ip": ip_phrase,
        "objective_tag": objective_tag,
        "objectives": objective_phrase,
        "constraint_tag": _constraint_tag(decision.constraints),
        "constraints": constraints,
        "brief_tag": brief_tag,
    }


def _evidence(opportunities: Sequence[Opportunity]) -> list[str]:
    return _dedup(
        source_id
        for opportunity in opportunities
        for source_id in opportunity.evidence_ids
    )


def _name(
    concept_id: str,
    profile: CategoryProfile,
    context: dict[str, str],
) -> str:
    market = context["market"].removesuffix("市场")
    price = context["price"].removesuffix("价格带")
    return (
        f"{market}{context['segment']}·{price}{context['ip_tag']}·"
        f"{context['objective_tag']}{context['constraint_tag']}·任务{context['brief_tag']}·"
        f"{_PATH_NAMES[concept_id]}{profile.noun}"
    )


def _apply_revisions(
    concepts: list[ProductConcept],
    revision_context: list[CandidateRevisionContext] | None,
) -> None:
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
        concept.revision_notes = [
            (
                f"第 {context.source_iteration + 1} 轮验证计划：{constraint}"
                "；仅在取得结构化验证结果后更新评分。"
            )
            for constraint in constraints
        ]


def build_dynamic_portfolio(
    decision: DecisionInput,
    opportunities: list[Opportunity],
    trends: list[TrendSignal],
    revision_context: list[CandidateRevisionContext] | None = None,
) -> list[ProductConcept]:
    """按固定顺序返回 VOC、趋势和白空间三条动态候选路径。"""
    profile = category_profile(decision)
    context = _decision_copy(decision)
    voc_opportunities = [item for item in opportunities if item.origin == "voc"]
    if not voc_opportunities:
        voc_opportunities = [item for item in opportunities if item.origin != "competitor"]
    whitespace = [item for item in opportunities if item.origin == "competitor"]
    top_voc = voc_opportunities[:3]
    top_ids = [item.id for item in top_voc]
    voc_evidence = _evidence(top_voc)
    whitespace_evidence = _evidence(whitespace[:2]) or voc_evidence
    trend_evidence = _dedup(
        source_id
        for trend in trends
        for source_id in trend.evidence_ids
    )
    focus = "、".join(item.aspect for item in top_voc[:2]) or "品质与价值"
    trend_focus = "、".join(item.name for item in trends[:3]) or "市场趋势组合"
    whitespace_focus = "、".join(item.aspect for item in whitespace[:2]) or "包装、实用性"
    module_offset = int(context["brief_tag"][:2], 16) % len(profile.modules)
    ordered_modules = profile.modules[module_offset:] + profile.modules[:module_offset]
    modules = "、".join(ordered_modules)
    scenarios = "、".join(profile.scenarios)
    constraint_copy = "定制验收条件" if decision.constraints else "常规零售验收条件"

    concepts = [
        ProductConcept(
            id="C-VOC",
            name=_name("C-VOC", profile, context),
            category=decision.category_label,
            path="voc_driven",
            one_liner=(
                f"围绕任务{context['brief_tag']}，为{context['market']}的{context['segment']}把{focus}做成"
                f"{profile.form}，以{context['price']}落实{context['objectives']}，"
                f"并满足{constraint_copy}。"
            ),
            target_segment=(
                f"{context['market']}的{context['segment']}，在{scenarios}选购"
                f"{context['price']}的{profile.noun}，关注{context['objectives']}与"
                f"{context['constraints']}。"
            ),
            value_proposition=(
                f"以{context['ip']}承载角色、礼赠、系列收藏与展示体验，"
                f"让{profile.noun}兼顾{modules}和{context['objectives']}，"
                f"适配{constraint_copy}。"
            ),
            key_features=[
                f"{profile.form}集成{modules}，覆盖{scenarios}",
                f"{context['ip']}配合礼赠卡、系列配件与桌面展示结构",
                f"按{context['price']}控制组合深度，以{context['objectives']}响应{constraint_copy}",
            ],
            differentiators=[
                Differentiator(
                    statement=f"以评论机会排序验证{focus}，而非直接采用用户简报关键词",
                    evidence_ids=voc_evidence[:6],
                ),
                Differentiator(
                    statement=f"用{profile.form}连接{scenarios}中的真实使用频次",
                    evidence_ids=voc_evidence[:6],
                ),
            ],
            tech_enablers=[*profile.enablers, f"{constraint_copy}清单"],
            addressed_opportunity_ids=top_ids,
        ),
        ProductConcept(
            id="C-TREND",
            name=_name("C-TREND", profile, context),
            category=decision.category_label,
            path="trend_driven",
            one_liner=(
                f"围绕任务{context['brief_tag']}，面向{context['market']}的{context['segment']}，把{trend_focus}转化为"
                f"{profile.form}，在{context['price']}下兼顾{context['objectives']}和"
                f"{constraint_copy}。"
            ),
            target_segment=(
                f"{context['market']}的{context['segment']}，愿意在{scenarios}尝试"
                f"{context['price']}的{profile.noun}，并核验{context['ip']}、"
                f"{context['objectives']}和{context['constraints']}。"
            ),
            value_proposition=(
                f"以{context['ip']}统一视觉轮廓，用区域内容驱动系列收藏和分享，"
                f"并通过{modules}承接{context['objectives']}与{constraint_copy}。"
            ),
            key_features=[
                f"{profile.form}采用统一角色轮廓与区域内容层，适配{scenarios}",
                f"{modules}支持编号系列、补充件和分享话题",
                f"按{context['price']}设置基础与限定组合，以{context['objectives']}响应{constraint_copy}",
            ],
            differentiators=[
                Differentiator(
                    statement=f"把{trend_focus}放入统一结构与区域内容双层体系",
                    evidence_ids=trend_evidence[:6],
                ),
                Differentiator(
                    statement=f"用{profile.form}连接使用、补充与系列复购",
                    evidence_ids=trend_evidence[:6],
                ),
            ],
            tech_enablers=[*profile.enablers, context["ip"], "区域内容模板"],
            addressed_opportunity_ids=top_ids[:2],
        ),
        ProductConcept(
            id="C-WHITESPACE",
            name=_name("C-WHITESPACE", profile, context),
            category=decision.category_label,
            path="whitespace_driven",
            one_liner=(
                f"围绕任务{context['brief_tag']}，针对{context['market']}竞品在{whitespace_focus}上的空白，把"
                f"{profile.form}与可展示礼赠包装合一，以{context['price']}落实"
                f"{context['objectives']}并满足{constraint_copy}。"
            ),
            target_segment=(
                f"{context['market']}的{context['segment']}，在{scenarios}重视"
                f"{profile.noun}的{whitespace_focus}、{context['price']}、"
                f"{context['objectives']}和{context['constraints']}。"
            ),
            value_proposition=(
                f"以{context['ip']}和可展示礼赠包装放大{profile.noun}的二次使用价值，"
                f"通过{modules}补齐{whitespace_focus}，同时响应{context['objectives']}"
                f"与{constraint_copy}。"
            ),
            key_features=[
                f"{profile.form}与包装切换为使用、收纳和展示三种形态",
                f"{modules}采用通用接口，覆盖{scenarios}",
                f"按{context['price']}和{context['ip']}替换内容层，以{context['objectives']}响应{constraint_copy}",
            ],
            differentiators=[
                Differentiator(
                    statement=f"直接补齐竞品在{whitespace_focus}上的体验空白",
                    evidence_ids=whitespace_evidence[:6],
                ),
                Differentiator(
                    statement=f"让{profile.form}与包装二次使用共同提升实用价值",
                    evidence_ids=_dedup([*whitespace_evidence, *voc_evidence])[:6],
                ),
            ],
            tech_enablers=[*profile.enablers, "通用包装内托", "区域纸套印刷"],
            addressed_opportunity_ids=top_ids[1:3],
        ),
    ]
    _apply_revisions(concepts, revision_context)
    return concepts
