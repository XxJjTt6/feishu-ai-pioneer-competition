"""Qwen 驱动的动态决策草案与领域模型映射。"""
from __future__ import annotations

import json
from typing import Annotated, Dict, List, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from miniso_studio.application.graph.state import PipelineState
from miniso_studio.common.models import (
    CandidateEvaluation,
    Differentiator,
    FaqItem,
    InterviewTurn,
    Persona,
    PersonaInterview,
    ProductConcept,
    RiskItem,
)
from miniso_studio.infrastructure.llm.gateway import LLMGateway
from miniso_studio.infrastructure.llm.structured_qwen_dynamic import (
    StructuredQwenClientError,
    StructuredQwenClient,
)
from miniso_studio.infrastructure.observability.trace import Tracer


PathName = Literal["voc_driven", "trend_driven", "whitespace_driven"]
Sentiment = Literal["positive", "neutral", "negative"]
Verdict = Literal["would_buy", "maybe", "would_not_buy"]
Severity = Literal["low", "medium", "high"]
Text40 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=40),
]
Text60 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=60),
]

PATH_TO_ID_: Dict[str, str] = {
    "voc_driven": "C-VOC",
    "trend_driven": "C-TREND",
    "whitespace_driven": "C-WHITESPACE",
}
EXPECTED_DIMENSIONS_ = {
    "trend_fit",
    "demand_strength",
    "differentiation",
    "social_virality",
    "margin_potential",
    "supply_feasibility",
    "ip_compliance",
    "localization_fit",
}


class LLMDifferentiatorDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")

    statement: Text40
    opportunity_ids: List[str] = Field(default_factory=list, max_length=4)
    evidence_ids: List[str] = Field(default_factory=list, max_length=8)


class LLMInterviewTurnDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question: str = Field(min_length=3, max_length=80)
    answer: str = Field(min_length=3, max_length=180)
    sentiment: Sentiment = "neutral"


class LLMInterviewDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")

    persona_name: str = Field(min_length=2, max_length=32)
    persona_segment: str = Field(min_length=2, max_length=48)
    persona_summary: str = Field(min_length=3, max_length=100)
    turns: List[LLMInterviewTurnDraft] = Field(min_length=3, max_length=5)
    verdict: Verdict
    acceptance: float = Field(ge=0, le=1)
    objections: List[Text40] = Field(default_factory=list, max_length=4)
    must_fixes: List[Text40] = Field(default_factory=list, max_length=4)
    evidence_ids: List[str] = Field(default_factory=list, max_length=10)


class LLMRiskDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")

    area: str = Field(min_length=2, max_length=32)
    description: Text60
    severity: Severity = "medium"
    mitigation: Text60


class LLMFeasibilityDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")

    technical: Text60
    supply_chain: Text60
    bom_cost: Text60
    compliance: Text60
    quality: Text60
    gross_margin: Text60
    supplier_lead_time: Text60
    ip_authorization: Text60
    regional_compliance: Text60
    localization: Text60
    risks: List[LLMRiskDraft] = Field(min_length=1, max_length=6)


class LLMCandidateDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: PathName
    name: str = Field(min_length=3, max_length=32)
    one_liner: str = Field(min_length=3, max_length=80)
    target_segment: str = Field(min_length=3, max_length=80)
    value_proposition: str = Field(min_length=3, max_length=100)
    key_features: List[Text40] = Field(min_length=3, max_length=6)
    differentiators: List[LLMDifferentiatorDraft] = Field(min_length=2, max_length=5)
    tech_enablers: List[Text40] = Field(default_factory=list, max_length=5)
    addressed_opportunity_ids: List[str] = Field(default_factory=list, max_length=5)
    revision_notes: List[Text40] = Field(default_factory=list, max_length=6)
    interviews: List[LLMInterviewDraft] = Field(min_length=1, max_length=3)
    feasibility: LLMFeasibilityDraft


class LLMStrategyDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")

    strategy_schema_version: Literal["1"]
    candidates: List[LLMCandidateDraft] = Field(min_length=3, max_length=3)
    synthesis_note: str = Field(min_length=3, max_length=120)

    @model_validator(mode="after")
    def validate_paths(self) -> "LLMStrategyDraft":
        paths = [candidate.path for candidate in self.candidates]
        if set(paths) != set(PATH_TO_ID_) or len(set(paths)) != 3:
            raise ValueError("candidates 必须覆盖三条稳定路径且不得重复")
        if len({candidate.name for candidate in self.candidates}) != 3:
            raise ValueError("候选名称不得重复")
        return self


class LLMCandidateRationalesDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")

    concept_id: Literal["C-VOC", "C-TREND", "C-WHITESPACE"]
    dimensions: Dict[str, str]

    @model_validator(mode="after")
    def validate_dimensions(self) -> "LLMCandidateRationalesDraft":
        if set(self.dimensions) != EXPECTED_DIMENSIONS_:
            raise ValueError("dimensions 必须完整覆盖八维量表")
        if any(not str(value).strip() for value in self.dimensions.values()):
            raise ValueError("dimension rationale 不能为空")
        if any(len(str(value).strip()) > 55 for value in self.dimensions.values()):
            raise ValueError("dimension rationale 不得超过 55 个字符")
        return self


class LLMFaqDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question: str = Field(min_length=3, max_length=80)
    answer: str = Field(min_length=3, max_length=160)


class LLMProposalDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")

    headline: str = Field(min_length=3, max_length=60)
    subheading: str = Field(min_length=3, max_length=100)
    summary: str = Field(min_length=3, max_length=240)
    customer_quote: str = Field(min_length=3, max_length=100)
    maker_quote: str = Field(min_length=3, max_length=100)
    call_to_action: str = Field(min_length=3, max_length=80)
    external_faq: List[LLMFaqDraft] = Field(min_length=1, max_length=5)
    internal_faq: List[LLMFaqDraft] = Field(min_length=1, max_length=5)

    def external_faq_items(self, evidence_ids: List[str]) -> List[FaqItem]:
        return [
            FaqItem(
                question=item.question,
                answer=item.answer,
                evidence_ids=list(evidence_ids),
            )
            for item in self.external_faq
        ]

    def internal_faq_items(self, evidence_ids: List[str]) -> List[FaqItem]:
        return [
            FaqItem(
                question=item.question,
                answer=item.answer,
                evidence_ids=list(evidence_ids),
            )
            for item in self.internal_faq
        ]


class LLMDecisionDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")

    decision_schema_version: Literal["1"]
    candidate_rationales: List[LLMCandidateRationalesDraft] = Field(
        min_length=3,
        max_length=3,
    )
    portfolio_rationale: str = Field(min_length=3, max_length=180)
    conditions: List[Text60] = Field(default_factory=list, max_length=6)
    proposal: LLMProposalDraft

    @model_validator(mode="after")
    def validate_candidate_ids(self) -> "LLMDecisionDraft":
        ids = [item.concept_id for item in self.candidate_rationales]
        if set(ids) != set(PATH_TO_ID_.values()) or len(set(ids)) != 3:
            raise ValueError("candidate_rationales 必须覆盖全部候选")
        return self


class QwenDecisionEngine:
    """两次结构化 Qwen 调用：策略生成，以及评分后的批判与提案。"""

    def __init__(
        self,
        gateway: LLMGateway,
        tracer: Optional[Tracer] = None,
        client: Optional[StructuredQwenClient] = None,
    ) -> None:
        self.gateway = gateway
        self.tracer = tracer
        remote = gateway._remote
        self.client = client
        if self.client is None and gateway.has_remote and remote is not None:
            api_key = str(getattr(remote, "api_key", "") or "")
            base_url = str(getattr(remote, "base_url", "") or "")
            model = str(getattr(remote, "model", gateway.default_model) or "")
            if api_key and base_url and model:
                self.client = StructuredQwenClient(api_key, base_url, model)
        self.latest_strategy: Optional[LLMStrategyDraft] = None
        self.latest_decision: Optional[LLMDecisionDraft] = None

    def generate_strategy(self, state: PipelineState) -> Optional[LLMStrategyDraft]:
        context = self._strategy_context(state)
        system = (
            "你是 Trend2SKU 的多角色商品决策编排器。你的任务是把本轮结构化输入、"
            "研究样本摘要和上一轮反馈转成真正不同的商品候选、合成用户访谈和商品化风险。"
            "所有内容必须针对本轮输入实时推理，禁止复用固定品名或模板答案；不得声称拥有真实销量、"
            "真实用户研究或已验证 ROI。只返回严格 JSON，不要 Markdown，不要解释。"
        )
        prompt = (
            "输出 strategy_schema_version=\"1\" 的 JSON 对象。candidates 必须恰好三项并分别使用 "
            "voc_driven、trend_driven、whitespace_driven。每项必须包含独特名称、价值主张、3-6 个功能、"
            "2-5 个差异点、1-3 个合成访谈、完整商品化叙述和 1-6 个风险。"
            "访谈和风险必须直接回应本轮 brief、品类、人群、市场、价格带、IP 策略、经营目标和约束。"
            "每个功能、差异点、异议和修正项不超过 40 汉字；商品化字段不超过 60 汉字。"
            "只能引用上下文中存在的 opportunity_id 与 evidence_id；不确定时返回空数组。"
            "数值 acceptance 只是待真实研究验证的合成意向，范围 0-1。\n\n"
            "输出必须逐字段匹配下面的 JSON Schema；不得改名、漏字段或改变层级：\n"
            f"{json.dumps(LLMStrategyDraft.model_json_schema(), ensure_ascii=False)}\n\n"
            f"JSON 输入上下文：\n{json.dumps(context, ensure_ascii=False)}"
        )
        draft = self._complete(
            LLMStrategyDraft,
            system=system,
            prompt=prompt,
            task="strategy",
            max_tokens=4300,
            temperature=0.55,
        )
        if draft is not None:
            self.latest_strategy = draft
            self.latest_decision = None
        return draft

    def generate_decision(self, state: PipelineState) -> Optional[LLMDecisionDraft]:
        context = self._decision_context(state)
        system = (
            "你是 Trend2SKU 的首席商品决策官。输入中的候选、八维分数、权重、风险和模拟访谈已经确定。"
            "你只能解释、批判并形成验证提案，绝对不能修改任何分数、权重、候选 ID 或风险等级，"
            "也不能把模拟访谈写成真实用户研究。所有文字必须针对本轮候选，禁止固定模板。"
            "只返回严格 JSON，不要 Markdown，不要解释。"
        )
        prompt = (
            "输出 decision_schema_version=\"1\" 的 JSON 对象。candidate_rationales 必须恰好覆盖 "
            "C-VOC、C-TREND、C-WHITESPACE，并为八个维度逐项给出本轮专属判断依据。"
            "portfolio_rationale 必须比较三条候选；conditions 必须是可执行的真实验证动作。"
            "proposal 必须包含 headline、subheading、summary、两类引语、call_to_action、"
            "external_faq 和 internal_faq。每条维度依据不超过 55 汉字；"
            "组合理由不超过 180 汉字。不得承诺销量、ROI 或未经验证的交期。\n\n"
            "输出必须逐字段匹配下面的 JSON Schema；不得改名、漏字段或改变层级：\n"
            f"{json.dumps(LLMDecisionDraft.model_json_schema(), ensure_ascii=False)}\n\n"
            f"JSON 输入上下文：\n{json.dumps(context, ensure_ascii=False)}"
        )
        draft = self._complete(
            LLMDecisionDraft,
            system=system,
            prompt=prompt,
            task="decision",
            max_tokens=3000,
            temperature=0.35,
        )
        if draft is not None:
            self.latest_decision = draft
        return draft

    def concepts_from_strategy(
        self,
        state: PipelineState,
        draft: LLMStrategyDraft,
    ) -> List[ProductConcept]:
        opportunity_by_id = self._opportunity_by_id(state)
        allowed_evidence_ids = self._allowed_evidence_ids(state)
        fallback_opportunity_ids = list(opportunity_by_id)[:3]
        concepts: List[ProductConcept] = []
        for candidate in sorted(
            draft.candidates,
            key=lambda item: list(PATH_TO_ID_).index(item.path),
        ):
            concept_id = PATH_TO_ID_[candidate.path]
            addressed_ids = self._valid_ids(
                candidate.addressed_opportunity_ids,
                set(opportunity_by_id),
            )
            if not addressed_ids:
                addressed_ids = fallback_opportunity_ids[:2]
            differentiators: List[Differentiator] = []
            for item in candidate.differentiators:
                referenced_opportunities = self._valid_ids(
                    item.opportunity_ids,
                    set(opportunity_by_id),
                )
                evidence_ids = self._valid_ids(
                    item.evidence_ids,
                    allowed_evidence_ids,
                )
                if not evidence_ids:
                    for opportunity_id in [*referenced_opportunities, *addressed_ids]:
                        opportunity = opportunity_by_id.get(opportunity_id)
                        if opportunity is not None:
                            evidence_ids.extend(
                                self._valid_ids(
                                    opportunity.evidence_ids,
                                    allowed_evidence_ids,
                                )
                            )
                differentiators.append(
                    Differentiator(
                        statement=item.statement.strip(),
                        evidence_ids=self._dedup(evidence_ids)[:8],
                    )
                )
            concepts.append(
                ProductConcept(
                    id=concept_id,
                    name=candidate.name.strip(),
                    category=state.decision_input.category_label,
                    path=candidate.path,
                    one_liner=candidate.one_liner.strip(),
                    target_segment=candidate.target_segment.strip(),
                    value_proposition=candidate.value_proposition.strip(),
                    key_features=self._clean_text_list(candidate.key_features, limit=6),
                    differentiators=differentiators,
                    tech_enablers=self._clean_text_list(candidate.tech_enablers, limit=5),
                    addressed_opportunity_ids=addressed_ids,
                    revision_notes=self._clean_text_list(candidate.revision_notes, limit=6),
                )
            )
        return concepts

    def apply_interviews(self, state: PipelineState, draft: LLMStrategyDraft) -> None:
        concepts = {concept.id: concept for concept in state.concepts}
        allowed_evidence_ids = self._allowed_evidence_ids(state)
        personas: List[Persona] = []
        persona_ids: Dict[tuple[str, str], str] = {}
        for candidate in draft.candidates:
            concept_id = PATH_TO_ID_[candidate.path]
            if concept_id not in concepts:
                continue
            evaluation = state.candidate_evaluations.get(concept_id) or CandidateEvaluation(
                concept_id=concept_id,
                iteration=state.pm_iteration,
            )
            interviews: List[PersonaInterview] = []
            concept_evidence = self._dedup(
                source_id
                for differentiator in concepts[concept_id].differentiators
                for source_id in differentiator.evidence_ids
            )
            for interview in candidate.interviews:
                key = (interview.persona_name.strip(), interview.persona_segment.strip())
                persona_id = persona_ids.get(key)
                if persona_id is None:
                    persona_id = f"P-{len(persona_ids) + 1}"
                    persona_ids[key] = persona_id
                    persona_evidence = self._valid_ids(
                        interview.evidence_ids,
                        allowed_evidence_ids,
                    ) or concept_evidence
                    personas.append(
                        Persona(
                            id=persona_id,
                            name=key[0],
                            segment=key[1],
                            demographics=(
                                f"{state.decision_input.target_market_label} · "
                                f"{state.decision_input.target_segment_label} · "
                                f"{state.decision_input.price_label}"
                            ),
                            behaviors=[interview.persona_summary],
                            pains=self._clean_text_list(interview.objections, limit=4),
                            derived_from_evidence_ids=persona_evidence[:10],
                            summary=interview.persona_summary,
                        )
                    )
                evidence_ids = self._valid_ids(
                    interview.evidence_ids,
                    allowed_evidence_ids,
                ) or concept_evidence
                interviews.append(
                    PersonaInterview(
                        concept_id=concept_id,
                        persona_id=persona_id,
                        persona_name=interview.persona_name,
                        segment=interview.persona_segment,
                        transcript=[
                            InterviewTurn(
                                question=turn.question,
                                answer=turn.answer,
                                sentiment=turn.sentiment,
                            )
                            for turn in interview.turns
                        ],
                        verdict=interview.verdict,
                        objections=self._clean_text_list(interview.objections, limit=4),
                        must_fixes=self._clean_text_list(interview.must_fixes, limit=4),
                        acceptance=round(interview.acceptance, 2),
                        evidence_ids=evidence_ids[:10],
                    )
                )
            evaluation.interviews = interviews
            state.candidate_evaluations[concept_id] = evaluation
        state.personas = personas
        winner_id = state.chosen_concept.id if state.chosen_concept else ""
        winner = state.candidate_evaluations.get(winner_id)
        state.interviews = list(winner.interviews) if winner else []

    def apply_feasibility(self, state: PipelineState, draft: LLMStrategyDraft) -> None:
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
            existing_risk_keys = {
                (risk.area, risk.description.strip()) for risk in current.risks
            }
            for risk in narrative.risks:
                key = (risk.area, risk.description.strip())
                if key in existing_risk_keys:
                    continue
                # 模型负责提出风险假设，但不能自行触发本地质量/IP 阻断闸口。
                severity = risk.severity if risk.severity in {"low", "medium"} else "medium"
                current.risks.append(
                    RiskItem(
                        area=risk.area,
                        description=risk.description,
                        severity=severity,
                        mitigation=risk.mitigation,
                    )
                )
                existing_risk_keys.add(key)
            evaluation.feasibility = current
            state.candidate_evaluations[concept_id] = evaluation
        winner_id = state.chosen_concept.id if state.chosen_concept else ""
        winner = state.candidate_evaluations.get(winner_id)
        state.feasibility = winner.feasibility if winner else None

    def apply_decision(self, state: PipelineState, draft: LLMDecisionDraft) -> None:
        rationale_by_id = {
            item.concept_id: item.dimensions for item in draft.candidate_rationales
        }
        for scorecard in state.concept_scorecards:
            rationales = rationale_by_id.get(scorecard.concept_id, {})
            for dimension in scorecard.dimensions:
                value = str(rationales.get(dimension.key, "") or "").strip()
                if value:
                    dimension.rationale = value[:500]
        if state.decision is not None:
            state.decision.rationale = draft.portfolio_rationale
            state.decision.conditions = self._dedup(
                [*state.decision.conditions, *draft.conditions]
            )[:10]

    @staticmethod
    def _clean_text_list(values: List[str], *, limit: int) -> List[str]:
        return QwenDecisionEngine._dedup(
            str(value).strip() for value in values if str(value).strip()
        )[:limit]

    @staticmethod
    def _dedup(values) -> List[str]:
        return list(dict.fromkeys(value for value in values if value))

    @staticmethod
    def _valid_ids(values: List[str], allowed: set[str]) -> List[str]:
        return list(dict.fromkeys(value for value in values if value in allowed))

    @staticmethod
    def _opportunity_by_id(state: PipelineState):
        opportunities = list(state.voc_report.opportunities if state.voc_report else [])
        if state.market_intel is not None:
            opportunities.extend(state.market_intel.white_space_opportunities)
        return {item.id: item for item in opportunities}

    @staticmethod
    def _allowed_evidence_ids(state: PipelineState) -> set[str]:
        ids = {item.source_id for item in state.all_evidences()}
        if state.voc_report is not None:
            for item in state.voc_report.opportunities:
                ids.update(item.evidence_ids)
        if state.market_intel is not None:
            for trend in state.market_intel.trends:
                ids.update(trend.evidence_ids)
            for opportunity in state.market_intel.white_space_opportunities:
                ids.update(opportunity.evidence_ids)
        return ids

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
        if self.client is None or not self.gateway.has_remote:
            return None
        try:
            result = self.client.complete_json(
                system=system,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            parsed = schema.model_validate(result.payload)
        except ValidationError as exc:
            if self.tracer is not None:
                self.tracer.emit_internal(
                    f"Qwen {task}",
                    "structured_validation_error",
                    issues=[
                        {
                            "loc": [str(part) for part in issue.get("loc", ())],
                            "type": str(issue.get("type", "validation_error")),
                        }
                        for issue in exc.errors(
                            include_url=False,
                            include_context=False,
                            include_input=False,
                        )[:24]
                    ],
                )
            error = StructuredQwenClientError("validation_error")
            self.gateway._fallback_to_offline(
                operation=f"structured_{task}",
                reason="invalid_structured_response",
                exc=error,
            )
            return None
        except StructuredQwenClientError as exc:
            self.gateway._fallback_to_offline(
                operation=f"structured_{task}",
                reason="remote_error",
                exc=exc,
            )
            return None
        if self.tracer is not None:
            self.tracer.emit(
                f"Qwen {task}",
                "llm_call",
                provider=result.provider,
                model=result.model,
                task=task,
                status="success",
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                latency_ms=result.latency_ms,
                request_id_available=result.request_id != "unavailable",
            )
        return parsed

    def _strategy_context(self, state: PipelineState) -> dict:
        opportunities = list(self._opportunity_by_id(state).values())[:8]
        trends = list(state.market_intel.trends if state.market_intel else [])[:8]
        evidence = sorted(
            state.all_evidences(),
            key=lambda item: (-item.helpful_votes, item.source_id),
        )[:18]
        return {
            "decision_input": state.decision_input.model_dump(mode="json"),
            "iteration": state.pm_iteration + 1,
            "revision_context": [
                item.model_dump(mode="json") for item in state.revision_context
            ],
            "opportunities": [
                {
                    "opportunity_id": item.id,
                    "statement": item.statement,
                    "aspect": item.aspect,
                    "opportunity_score": item.opportunity_score,
                    "impact_score": item.impact_score,
                    "evidence_ids": item.evidence_ids,
                }
                for item in opportunities
            ],
            "trends": [
                {
                    "name": item.name,
                    "direction": item.direction,
                    "summary": item.summary,
                    "evidence_ids": item.evidence_ids,
                }
                for item in trends
            ],
            "evidence_excerpts": [
                {
                    "evidence_id": item.source_id,
                    "brand": item.brand,
                    "product": item.product,
                    "rating": item.rating,
                    "text": item.text[:220],
                    "data_provenance": item.data_provenance,
                }
                for item in evidence
            ],
        }

    @staticmethod
    def _decision_context(state: PipelineState) -> dict:
        candidate_validation = {}
        for concept_id, evaluation in state.candidate_evaluations.items():
            feasibility = evaluation.feasibility
            candidate_validation[concept_id] = {
                "interviews": [
                    {
                        "verdict": interview.verdict,
                        "acceptance": interview.acceptance,
                        "objections": interview.objections,
                        "must_fixes": interview.must_fixes,
                    }
                    for interview in evaluation.interviews
                ],
                "feasibility": (
                    {
                        "overall": feasibility.overall,
                        "gross_margin_score": feasibility.gross_margin_score,
                        "supply_feasibility_score": feasibility.supply_feasibility_score,
                        "ip_compliance_score": feasibility.ip_compliance_score,
                        "localization_score": feasibility.localization_score,
                        "risks": [
                            {
                                "area": risk.area,
                                "severity": risk.severity,
                                "description": risk.description,
                                "mitigation": risk.mitigation,
                            }
                            for risk in feasibility.risks
                        ],
                    }
                    if feasibility is not None
                    else None
                ),
                "nps_prediction": evaluation.nps.score if evaluation.nps else None,
            }
        return {
            "decision_input": state.decision_input.model_dump(mode="json"),
            "candidates": [
                {
                    "id": item.id,
                    "name": item.name,
                    "one_liner": item.one_liner,
                    "value_proposition": item.value_proposition,
                    "key_features": item.key_features,
                }
                for item in state.concepts
            ],
            "candidate_validation": candidate_validation,
            "scorecards": [
                item.model_dump(mode="json") for item in state.concept_scorecards
            ],
            "deterministic_decision": (
                state.decision.model_dump(mode="json") if state.decision else None
            ),
            "boundary": (
                "用户访谈为合成模拟；分数来自本地确定性量表；当前不得表述为真实销量、"
                "真实用户研究、真实 ROI 或企业最终经营结论。"
            ),
        }
