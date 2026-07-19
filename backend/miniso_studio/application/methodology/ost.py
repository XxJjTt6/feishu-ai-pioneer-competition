"""机会解决方案树（Application 层）：Teresa Torres OST。

结果(outcome) → 机会(opportunity) → 方案(solution) → 实验(experiment)。
方案候选按兴趣消费 aspect 使用确定性模板生成，每个方案都附带小规模验证实验。
"""
from __future__ import annotations

from typing import Dict, List

from miniso_studio.common.models import (
    Experiment,
    Opportunity,
    OpportunityNode,
    OpportunitySolutionTree,
    SolutionNode,
)

# 按兴趣消费 aspect 给出商品、供应链与零售验证方案。
SOLUTION_TEMPLATES: Dict[str, List[str]] = {
    "IP/设计吸引力": [
        "以原创角色或已核验授权 IP 构建系列化设计语言，首发三款控制测试变量",
        "建立授权地域、品类与期限台账，并用包装主视觉 A/B 测试设计辨识度",
    ],
    "品质/耐用性": [
        "收敛关键材料和连接结构，在量产前完成跌落、耐磨与运输振动验证",
        "把品质红线转成供应商验收表，并对首批货实施加严抽检",
    ],
    "价格/价值": [
        "围绕目标零售价反推 BOM 与包装预算，优先保留高感知价值部件",
        "设计基础款与礼盒款价格梯度，用试购转化验证价格接受区间",
    ],
    "实用性": [
        "通过可拆换或一物多用结构提升日常使用频次，避免只承担装饰功能",
        "以高频使用任务制作样件测试，记录完成率、耗时与结构失败点",
    ],
    "礼赠性": [
        "提供节日卡片、可复用礼袋与免二次包装结构，强化低门槛礼赠场景",
        "对自用与送礼两类用户分别测试礼赠理由、预算和包装完整性",
    ],
    "收藏性": [
        "建立统一系列编号与可展示收纳结构，用小系列降低重复购买疲劳",
        "测试常规款、区域限定款组合对收藏意愿与社交分享的影响",
    ],
    "包装": [
        "采用可回收且适合陈列的包装结构，同时满足礼赠与运输保护要求",
        "执行开箱偏好、堆码和运输振动测试，校准包装材料与印刷工艺",
    ],
    "门店可得性": [
        "共用主体物料并延后区域化装配，缩短热门款补货周期",
        "按门店等级设置首发配额和补货触发线，验证缺货率与周转天数",
    ],
    "本地化": [
        "保留全球通用主体，以城市文化、节日与语言模块形成区域限定版本",
        "与当地创作者共创并完成文化敏感性复核，再比较本地化版本试购表现",
    ],
}


def _solutions_for(aspect: str) -> List[SolutionNode]:
    nodes: List[SolutionNode] = []
    for tmpl in SOLUTION_TEMPLATES.get(aspect, [f"针对「{aspect}」的差异化方案"]):
        nodes.append(
            SolutionNode(
                statement=tmpl,
                rationale=f"直接回应「{aspect}」的高机会分痛点。",
                experiments=[
                    Experiment(
                        statement=f"对「{aspect}」改进做 A/B 偏好测试",
                        assumption="目标用户愿意为该改进支付溢价/给更高 NPS",
                        method="合成用户面板 + 公开招募小样本实物测试",
                    )
                ],
            )
        )
    return nodes


def build_ost(outcome: str, opportunities: List[Opportunity], top_n: int = 5) -> OpportunitySolutionTree:
    nodes: List[OpportunityNode] = []
    for opp in sorted(opportunities, key=lambda o: o.opportunity_score, reverse=True)[:top_n]:
        nodes.append(
            OpportunityNode(
                opportunity_id=opp.id,
                statement=opp.statement,
                opportunity_score=opp.opportunity_score,
                solutions=_solutions_for(opp.aspect),
            )
        )
    return OpportunitySolutionTree(outcome=outcome, opportunities=nodes)
