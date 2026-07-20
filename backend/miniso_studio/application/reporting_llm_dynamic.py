"""Qwen 动态工作台专用报告，不改写原始报告实现。"""
from __future__ import annotations

from miniso_studio.application.reporting import (
    render_full_report,
    render_opening_report,
)
from miniso_studio.application.runner import RunArtifacts


def _proposal_section(artifacts: RunArtifacts) -> str:
    prfaq = artifacts.state.prfaq
    if prfaq is None:
        return ""
    lines = [
        "## 8. Qwen 动态提案",
        "",
        f"### {prfaq.headline}",
        "",
        prfaq.subheading,
        "",
        prfaq.summary,
        "",
        f"> 合成用户表达：{prfaq.customer_quote}",
        "",
        f"> 商品团队行动：{prfaq.maker_quote}",
        "",
        f"**下一步：{prfaq.call_to_action}**",
    ]
    if prfaq.external_faq:
        lines.extend(["", "**外部问答**"])
        for item in prfaq.external_faq:
            lines.append(f"- **{item.question}**：{item.answer}")
    if prfaq.internal_faq:
        lines.extend(["", "**内部问答**"])
        for item in prfaq.internal_faq:
            lines.append(f"- **{item.question}**：{item.answer}")
    return "\n".join(lines)


def render_full_report_llm_dynamic(artifacts: RunArtifacts) -> str:
    """把动态提案加入完整报告，并准确区分模型生成与本地量表。"""

    report = render_full_report(artifacts)
    report = report.replace(
        "## 2. 候选 SKU 组合与榜首（离线演示评分）",
        "## 2. 候选 SKU 组合与榜首（Qwen 动态候选，本地量表评分）",
    )
    report = report.replace(
        "## 3. 八维商业评分矩阵（离线演示）",
        "## 3. 八维商业评分矩阵（Qwen 针对性解释，本地数值锁定）",
    )
    report = report.replace(
        "- 情绪价值与社交传播为研究假设；候选评分、接受度、NPS 与风险分均为离线演示结果。",
        (
            "- 情绪价值与社交传播为研究假设；候选、合成访谈、风险叙述和提案由 "
            f"{artifacts.model} 动态生成，本地代码锁定分数、权重、证据引用和高风险闸口；"
            "所有结果仍需真实用户与样件测试。"
        ),
    )
    section = _proposal_section(artifacts)
    marker = "## 8. 数据边界"
    if section and marker in report:
        report = report.replace(marker, f"{section}\n\n## 9. 数据边界", 1)
    return report

def render_opening_report_llm_dynamic(artifacts: RunArtifacts) -> str:
    """更新开题底稿的真实模型分工描述。"""

    report = render_opening_report(artifacts)
    report = report.replace(
        "数值评分由确定性工具控制，模型只负责批判与叙述",
        (
            f"{artifacts.model} 动态生成候选、合成访谈、风险叙述与提案，"
            "数值评分、权重、证据引用和高风险闸口由确定性工具控制"
        ),
    )
    return report
