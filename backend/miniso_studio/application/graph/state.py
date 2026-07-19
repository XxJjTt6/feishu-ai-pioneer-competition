"""流水线共享状态（Application 层）。

贯穿整个 AI 原生工作流的状态对象。节点读取并增量更新它。
`claims` 收集 (论断, evidence_ids) 供评测计算 groundedness/faithfulness。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

from miniso_studio.common.config import DEFAULT_BRIEF
from miniso_studio.common.decision_input import DecisionInput
from miniso_studio.common.models import (
    CandidateEvaluation,
    CandidateRevisionContext,
    DecisionRecord,
    Evidence,
    ExperiencePoint,
    FeasibilityAssessment,
    MarketIntel,
    NPSPrediction,
    Persona,
    PersonaInterview,
    PRFAQ,
    ProductConcept,
    ProductProposal,
    ProductScorecard,
    VocReport,
)


class PipelineState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # 输入
    category: str = "interest_goods"
    target_brand: str = "MINISO"
    brief: str = DEFAULT_BRIEF
    decision_input: DecisionInput = Field(
        default_factory=lambda: DecisionInput(brief=DEFAULT_BRIEF)
    )
    legacy_input: bool = False

    # 数据
    target_evidences: List[Evidence] = Field(default_factory=list)
    competitor_evidences: Dict[str, List[Evidence]] = Field(default_factory=dict)
    trend_evidences: List[Evidence] = Field(default_factory=list)

    # 平台产物
    voc_report: Optional[VocReport] = None
    market_intel: Optional[MarketIntel] = None
    experience_trend: List[ExperiencePoint] = Field(default_factory=list)

    # 概念与验证
    concepts: List[ProductConcept] = Field(default_factory=list)
    concept_scorecards: List[ProductScorecard] = Field(default_factory=list)
    candidate_evaluations: Dict[str, CandidateEvaluation] = Field(default_factory=dict)
    revision_context: List[CandidateRevisionContext] = Field(default_factory=list)
    chosen_concept: Optional[ProductConcept] = None
    personas: List[Persona] = Field(default_factory=list)
    interviews: List[PersonaInterview] = Field(default_factory=list)
    feasibility: Optional[FeasibilityAssessment] = None
    nps: Optional[NPSPrediction] = None

    # 决策与产出
    prfaq: Optional[PRFAQ] = None
    decision: Optional[DecisionRecord] = None
    proposal: Optional[ProductProposal] = None

    # 控制 / 评测
    pm_iteration: int = 0
    max_pm_iterations: int = 2
    retrieval_iters: int = 0
    claims: List[Tuple[str, List[str]]] = Field(default_factory=list)
    candidate_claim_start: Optional[int] = None
    awaiting_human: bool = False
    trace_run_id: str = ""
    hitl_enabled: bool = False
    run_elapsed_seconds: float = 0.0

    @model_validator(mode="before")
    @classmethod
    def synchronize_decision_input(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        raw_decision_input = normalized.get("decision_input")
        if raw_decision_input is None:
            decision_input = DecisionInput(
                brief=normalized.get("brief", DEFAULT_BRIEF)
            )
            normalized["legacy_input"] = normalized.get("legacy_input", True)
        else:
            decision_input = DecisionInput.model_validate(raw_decision_input)
        normalized["decision_input"] = decision_input
        normalized["brief"] = decision_input.brief
        return normalized

    def add_claim(self, text: str, evidence_ids: List[str]) -> None:
        self.claims.append((text, list(evidence_ids or [])))

    def all_evidences(self) -> List[Evidence]:
        evs: List[Evidence] = list(self.target_evidences) + list(self.trend_evidences)
        for lst in self.competitor_evidences.values():
            evs.extend(lst)
        return evs

    def clear_candidate_cycle(self) -> None:
        """开始新一轮创意时清空上一轮候选验证，防止按位置串线。"""
        if self.candidate_claim_start is None:
            self.candidate_claim_start = len(self.claims)
        else:
            del self.claims[self.candidate_claim_start :]
        self.concepts = []
        self.concept_scorecards = []
        self.candidate_evaluations = {}
        self.revision_context = []
        self.chosen_concept = None
        self.personas = []
        self.interviews = []
        self.feasibility = None
        self.nps = None
        self.prfaq = None
        self.decision = None
        self.proposal = None
