"""商品专家 Agent：逐候选评估商品化、供应链、IP 与质量风险。"""
from __future__ import annotations

from miniso_studio.application.agents.base import Agent
from miniso_studio.application.graph.state import PipelineState
from miniso_studio.application.portfolio.dynamic_candidates import category_profile
from miniso_studio.common.decision_input import DecisionInput
from miniso_studio.common.models import (
    CandidateEvaluation,
    FeasibilityAssessment,
    RiskItem,
)
from miniso_studio.infrastructure.data.retail_tools import build_merchandise_assessment


_MARKET_COMPLIANCE = {
    "china": "核验中国市场材料安全、中文标签、年龄标识与广告表述",
    "southeast_asia": "核验东南亚高温高湿适配、当地语言标签与各国进口要求",
    "japan_korea": "核验日韩材料标准、精细标签、包装回收与当地消费者保护要求",
    "europe_america": "核验欧美材料化学限制、儿童用品边界、包装责任与营销声明",
    "middle_east": "核验中东阿拉伯语标签、高温运输、文化表达与进口要求",
    "global": "按销售国家拆分材料、语言、年龄标识、包装责任与营销合规清单",
}

_PRICE_RISKS = {
    "entry": "入门价格带需限制物料种类、装配工时与首发 SKU 数，防止成本穿透",
    "mid": "中端价格带需平衡材料质感、功能获得感、促销空间与目标毛利",
    "premium": "高端价格带需用材料、工艺和售后体验证明溢价，避免高价低感知",
}

_IP_RISKS = {
    "original": "原创 IP 仍需完成商标、著作权与近似形象检索并保留创作底稿",
    "licensed": "授权 IP 需核验权利主体、地域、品类、期限、素材审批和版税口径",
    "none": "无 IP 路径仍需检查图形、字体与包装元素的第三方权利",
    "evaluate": "IP 策略待评估，权利路径确定前不得锁定角色资产或进入量产",
}


class IndustryExpertAgent(Agent):
    name = "商品专家 Agent"
    role = "质量 / 毛利 / 交期 / IP授权 / 区域合规 / 本地化"

    def run(self, state: PipelineState) -> PipelineState:
        if not state.concepts:
            return state

        for concept in state.concepts:
            evaluation = state.candidate_evaluations.get(concept.id) or CandidateEvaluation(
                concept_id=concept.id,
                iteration=state.pm_iteration,
            )
            evidence_ids = self.dedup(
                [
                    *(source_id for item in concept.differentiators for source_id in item.evidence_ids),
                    *(source_id for item in evaluation.interviews for source_id in item.evidence_ids),
                ]
            )[:10]
            def fallback_assessment(
                concept=concept,
                evidence_ids=evidence_ids,
            ):
                return build_merchandise_assessment(concept, evidence_ids)

            assessment = self.call_read_tool(
                "assess_merchandise_candidate",
                fallback=fallback_assessment,
                validator=lambda value, concept_id=concept.id: (
                    isinstance(value, FeasibilityAssessment)
                    and value.concept_id == concept_id
                ),
                concept=concept,
                evidence_ids=evidence_ids,
            )
            if not isinstance(assessment, FeasibilityAssessment) or assessment.concept_id != concept.id:
                assessment = fallback_assessment()
            assessment = self._merge_decision_context(assessment, state.decision_input)
            evaluation.feasibility = assessment
            state.candidate_evaluations[concept.id] = evaluation

            state.add_claim(
                f"候选 {concept.id} 商品化评估：{assessment.overall}",
                assessment.evidence_ids,
            )
            for risk in assessment.risks:
                state.add_claim(
                    f"候选 {concept.id} 风险（{risk.area}）：{risk.description}",
                    assessment.evidence_ids,
                )

        winner_id = state.chosen_concept.id if state.chosen_concept else ""
        winner_evaluation = state.candidate_evaluations.get(winner_id)
        state.feasibility = winner_evaluation.feasibility if winner_evaluation else None

        if self.tracer:
            self.tracer.emit(
                self.name,
                "result",
                candidates=len(state.candidate_evaluations),
                risk_counts={
                    concept_id: len(evaluation.feasibility.risks)
                    if evaluation.feasibility
                    else 0
                    for concept_id, evaluation in state.candidate_evaluations.items()
                },
            )
        return state

    @staticmethod
    def _merge_decision_context(
        assessment: FeasibilityAssessment,
        decision: DecisionInput,
    ) -> FeasibilityAssessment:
        """保留工具评分和证据，只合并规范化输入暴露的商品化风险。"""
        merged = assessment.model_copy(deep=True)
        profile = category_profile(decision)
        category_risk = (
            f"{decision.category_label}材料/质量需验证"
            f"{'、'.join(profile.material_risks)}"
        )
        ip_risk = _IP_RISKS[str(decision.ip_strategy)]
        market_risk = _MARKET_COMPLIANCE[str(decision.target_market)]
        price_risk = _PRICE_RISKS[str(decision.price_band)]
        constraint_risk = (
            f"用户约束需转为打样验收项：{decision.constraints}"
            if decision.constraints
            else "未提供额外约束，沿用常规零售打样与量产验收"
        )
        risk_context = "；".join(
            [category_risk, ip_risk, market_risk, price_risk, constraint_risk]
        )

        if merged.risks:
            merged.risks[0].description = (
                f"{merged.risks[0].description}；{risk_context}。"
            )
            merged.risks[0].mitigation = (
                f"{merged.risks[0].mitigation}；按品类、IP、市场、价格带和用户约束逐项签样。"
            ).strip("；")
        else:
            merged.risks.append(
                RiskItem(
                    area="market",
                    description=risk_context,
                    severity="low",
                    mitigation="按品类、IP、市场、价格带和用户约束逐项签样。",
                )
            )

        if decision.ip_strategy == "evaluate":
            merged.risks.append(
                RiskItem(
                    area="ip_authorization",
                    description="IP 权利路径尚未确定，授权或原创权属关闭前禁止进入量产。",
                    severity="high",
                    mitigation="先完成权利主体、地域、品类、期限与素材来源核验，再恢复量产评审。",
                )
            )
            merged.ip_compliance_score = min(merged.ip_compliance_score, 25.0)
            merged.overall = "red"

        merged.technical = (
            f"{merged.technical} 当前商品形态为{profile.form}，功能模块包括"
            f"{'、'.join(profile.modules)}。"
        )
        merged.quality = f"{merged.quality} {category_risk}。"
        merged.bom_cost = f"{merged.bom_cost} {price_risk}。"
        merged.gross_margin = f"{merged.gross_margin} {price_risk}。"
        merged.supplier_lead_time = (
            f"{merged.supplier_lead_time} {constraint_risk}。"
        )
        merged.ip_authorization = f"{merged.ip_authorization} {ip_risk}。"
        merged.compliance = (
            f"{merged.compliance} {ip_risk}；{market_risk}。"
        )
        merged.regional_compliance = (
            f"{merged.regional_compliance} 目标为{decision.target_market_label}："
            f"{market_risk}。"
        )
        merged.localization = (
            f"{merged.localization} 面向{decision.target_market_label}的"
            f"{decision.target_segment_label}保留{'、'.join(profile.scenarios)}场景词。"
        )
        return merged
