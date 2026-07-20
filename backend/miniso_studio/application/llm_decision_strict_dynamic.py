"""只接受完整 Qwen 产物的动态决策引擎，不回退固定叙述。"""
from __future__ import annotations

import re

from miniso_studio.application.llm_decision_dynamic import (
    PATH_TO_ID_,
    LLMStrategyDraft,
    QwenDecisionEngine,
)
from miniso_studio.application.graph.state import PipelineState
from miniso_studio.common.models import RiskItem


class QwenGenerationRequiredError(RuntimeError):
    """公开工作台缺少某一阶段的完整 Qwen 结构化结果。"""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(f"qwen_generation_required:{stage}")


class QwenStrictDecisionEngine(QwenDecisionEngine):
    """候选与全部叙述必须来自 Qwen；本地代码只保留数值和硬闸口。"""

    def _complete(
        self,
        schema,
        *,
        system: str,
        prompt: str,
        task: str,
        max_tokens: int,
        temperature: float,
    ):
        system = (
            f"{system}\n所有面向评委的内容必须使用简体中文；候选名称、价值主张、"
            "访谈、风险、判断依据、FAQ 与提案不得只使用英文，不得返回中英双份答案。"
        )
        result = super()._complete(
            schema,
            system=system,
            prompt=prompt,
            task=task,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if result is None:
            raise QwenGenerationRequiredError(task)
        if task == "strategy" and any(
            not self._contains_han(candidate.name)
            or not self._contains_han(candidate.one_liner)
            or not self._contains_han(candidate.value_proposition)
            for candidate in result.candidates
        ):
            raise QwenGenerationRequiredError("strategy_language")
        if task == "decision" and (
            not self._contains_han(result.portfolio_rationale)
            or not self._contains_han(result.proposal.headline)
            or not self._contains_han(result.proposal.summary)
        ):
            raise QwenGenerationRequiredError("decision_language")
        return result

    @staticmethod
    def _contains_han(value: str) -> bool:
        return re.search(r"[\u3400-\u9fff]", str(value or "")) is not None

    def apply_feasibility(self, state: PipelineState, draft: LLMStrategyDraft) -> None:
        """用 Qwen 风险替换非阻断模板，只保留本地高风险硬闸口。"""
        for candidate in draft.candidates:
            concept_id = PATH_TO_ID_[candidate.path]
            evaluation = state.candidate_evaluations.get(concept_id)
            if evaluation is None or evaluation.feasibility is None:
                continue
            current = evaluation.feasibility.model_copy(deep=True)
            narrative = candidate.feasibility
            for field_name in (
                "technical",
                "supply_chain",
                "bom_cost",
                "compliance",
                "quality",
                "gross_margin",
                "supplier_lead_time",
                "ip_authorization",
                "regional_compliance",
                "localization",
            ):
                setattr(current, field_name, getattr(narrative, field_name))

            guardrail_risks = [
                risk.model_copy(deep=True)
                for risk in current.risks
                if risk.severity == "high"
            ]
            dynamic_risks = []
            seen = {(risk.area, risk.description.strip()) for risk in guardrail_risks}
            for risk in narrative.risks:
                key = (risk.area, risk.description.strip())
                if key in seen:
                    continue
                dynamic_risks.append(
                    RiskItem(
                        area=risk.area,
                        description=risk.description,
                        severity=(risk.severity if risk.severity in {"low", "medium"} else "medium"),
                        mitigation=risk.mitigation,
                    )
                )
                seen.add(key)
            current.risks = [*guardrail_risks, *dynamic_risks]
            evaluation.feasibility = current
            state.candidate_evaluations[concept_id] = evaluation

        winner_id = state.chosen_concept.id if state.chosen_concept else ""
        winner = state.candidate_evaluations.get(winner_id)
        state.feasibility = winner.feasibility if winner else None
