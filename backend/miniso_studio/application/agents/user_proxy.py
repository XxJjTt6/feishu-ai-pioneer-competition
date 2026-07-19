"""用户镜像 Agent：按候选隔离的兴趣消费合成访谈。"""
from __future__ import annotations

import hashlib
from typing import List

from miniso_studio.application.agents.base import Agent
from miniso_studio.application.graph.state import PipelineState
from miniso_studio.common.models import (
    CandidateEvaluation,
    Evidence,
    InterviewTurn,
    Persona,
    PersonaInterview,
    ProductConcept,
)
from miniso_studio.infrastructure.data import retail_tools as _retail_tools  # noqa: F401


_OCEAN = ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"]


def _ocean_from(seed: str) -> dict:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return {dimension: round((digest[index] % 100) / 100.0, 2) for index, dimension in enumerate(_OCEAN)}


class UserProxyAgent(Agent):
    name = "用户镜像 Agent"
    role = "用途 / 视觉 IP / 价格 / 礼赠收藏 / 分享意愿验证"

    def run(self, state: PipelineState) -> PipelineState:
        voc = state.voc_report
        if voc is None or not state.concepts:
            return state

        state.personas = self._build_personas(state)
        all_evidence = state.all_evidences()
        for concept in state.concepts:
            query = (
                f"{concept.name} {concept.target_segment} IP 视觉 价格 礼赠 收藏 分享 "
                + " ".join(concept.key_features)
            )
            def fallback_evidence():
                return sorted(
                    state.target_evidences,
                    key=lambda item: (-item.helpful_votes, item.source_id),
                )[:6]

            retrieved = self.call_read_tool(
                "search_retail_evidence",
                fallback=fallback_evidence,
                validator=self._valid_evidence_result,
                evidences=all_evidence,
                query=query,
                top_k=6,
            )
            if not isinstance(retrieved, list) or not all(
                isinstance(item, Evidence) for item in retrieved
            ):
                retrieved = fallback_evidence()
            retrieved_ids = [item.source_id for item in retrieved]
            interviews = [
                self._interview(persona, concept, retrieved_ids)
                for persona in state.personas
            ]
            evaluation = state.candidate_evaluations.get(concept.id) or CandidateEvaluation(
                concept_id=concept.id,
                iteration=state.pm_iteration,
            )
            evaluation.interviews = interviews
            state.candidate_evaluations[concept.id] = evaluation

            for interview in interviews:
                state.add_claim(
                    f"候选 {concept.id} 的用户镜像 {interview.persona_id} 判定：{interview.verdict}",
                    interview.evidence_ids,
                )

        winner_id = state.chosen_concept.id if state.chosen_concept else ""
        winner_evaluation = state.candidate_evaluations.get(winner_id)
        state.interviews = list(winner_evaluation.interviews) if winner_evaluation else []

        if self.tracer:
            averages = {
                concept_id: round(
                    sum(item.acceptance for item in evaluation.interviews)
                    / max(1, len(evaluation.interviews)),
                    2,
                )
                for concept_id, evaluation in state.candidate_evaluations.items()
            }
            self.tracer.emit(
                self.name,
                "result",
                personas=len(state.personas),
                candidates=len(state.candidate_evaluations),
                acceptance_by_candidate=averages,
            )
        return state

    @staticmethod
    def _valid_evidence_result(value: object) -> bool:
        return isinstance(value, list) and all(isinstance(item, Evidence) for item in value)

    def _build_personas(self, state: PipelineState) -> List[Persona]:
        personas: List[Persona] = []
        for index, opportunity in enumerate(state.voc_report.opportunities[:4]):
            segment = self._segment_for(opportunity.aspect)
            personas.append(
                Persona(
                    id=f"P-{index + 1}",
                    name=f"兴趣消费用户{index + 1}",
                    segment=segment,
                    demographics="18-40 岁，覆盖中国内地与重点海外市场的兴趣消费人群",
                    ocean=_ocean_from(f"{opportunity.aspect}-{index}"),
                    behaviors=["会在线上线下比较设计与价格", "购买兼顾自用、轻礼赠或收藏"],
                    pains=[opportunity.statement],
                    derived_from_evidence_ids=opportunity.evidence_ids,
                    summary=(
                        f"最关注{opportunity.aspect}；当前满意度 {opportunity.satisfaction}/10，"
                        f"机会分 {opportunity.opportunity_score}。"
                    ),
                )
            )
        return personas

    @staticmethod
    def _segment_for(aspect: str) -> str:
        mapping = {
            "IP/设计吸引力": "追求角色审美与视觉辨识度的年轻客群",
            "品质/耐用性": "重视做工、耐用与安全感的理性客群",
            "价格/价值": "对价格带和获得感敏感的高频消费客群",
            "礼赠性": "重视礼物体面度与情感表达的轻礼赠客群",
            "收藏性": "追求系列完整度与稀缺感的收藏客群",
            "包装": "重视开箱仪式与包装二次利用的体验客群",
            "本地化": "期待区域文化真实表达的海外与旅行客群",
        }
        return mapping.get(aspect, f"对{aspect}高度敏感的兴趣消费客群")

    def _interview(
        self,
        persona: Persona,
        concept: ProductConcept,
        retrieved_evidence_ids: List[str],
    ) -> PersonaInterview:
        concept_copy = " ".join(
            [concept.one_liner, concept.value_proposition, *concept.key_features]
        )
        visual_fit = any(term in concept_copy for term in ("角色", "设计", "城市", "配色", "IP"))
        gift_fit = any(term in concept_copy for term in ("礼赠", "礼物", "礼盒", "祝福"))
        collect_fit = any(term in concept_copy for term in ("收藏", "限定", "编号", "系列"))
        share_fit = any(term in concept_copy for term in ("分享", "拍照", "展示", "开箱", "话题"))
        base_acceptance = {
            "voc_driven": 0.67,
            "trend_driven": 0.72,
            "whitespace_driven": 0.69,
        }.get(concept.path, 0.60)
        evidence_bonus = min(0.06, len(retrieved_evidence_ids) * 0.01)
        signal_bonus = 0.015 * sum([visual_fit, gift_fit, collect_fit, share_fit])
        persona_adjustment = ((int(persona.id.split("-")[-1]) - 1) % 3 - 1) * 0.02
        acceptance = round(
            max(0.0, min(1.0, base_acceptance + evidence_bonus + signal_bonus + persona_adjustment)),
            2,
        )
        turns = [
            InterviewTurn(
                question="你会在什么使用场景中购买或使用它？",
                answer=f"我会把它用于日常自用，也会关注它是否真正解决：{persona.pains[0]}",
                sentiment="positive" if acceptance >= 0.65 else "neutral",
            ),
            InterviewTurn(
                question="你对视觉与 IP 风格有什么偏好？",
                answer=(
                    "角色和区域设计有辨识度，但必须说明原创或授权来源。"
                    if visual_fit
                    else "功能清楚，但视觉记忆点还不够。"
                ),
                sentiment="positive" if visual_fit else "neutral",
            ),
            InterviewTurn(
                question="你对这类商品的价格敏感度如何？",
                answer=(
                    "会比较同价位的做工和可重复使用价值，价格透明才愿意下单。"
                    if concept.path != "trend_driven"
                    else "限定设计可以小幅溢价，但补充件和普通款要保持可负担。"
                ),
                sentiment="neutral",
            ),
            InterviewTurn(
                question="你会把它用于礼赠或收藏吗？",
                answer=(
                    "包装体面且系列不重复时，我会送人也会继续收藏。"
                    if gift_fit or collect_fit
                    else "目前更像自用品，礼赠和收藏理由需要加强。"
                ),
                sentiment="positive" if gift_fit or collect_fit else "neutral",
            ),
            InterviewTurn(
                question="它是否值得拍照分享或推荐给朋友？",
                answer=(
                    "有可展示的细节和城市故事，我愿意拍照分享。"
                    if share_fit
                    else "需要一个更鲜明的开箱或展示瞬间。"
                ),
                sentiment="positive" if share_fit else "neutral",
            ),
        ]
        verdict = "would_buy" if acceptance >= 0.65 else ("maybe" if acceptance >= 0.48 else "would_not_buy")
        objections = (
            []
            if acceptance >= 0.70
            else ["需要用真实价格、样件做工和授权信息完成上市前验证"]
        )
        must_fixes = []
        if not visual_fit:
            must_fixes.append("增强视觉辨识度并说明 IP 权利来源")
        if not gift_fit and not collect_fit:
            must_fixes.append("补充礼赠或系列收藏机制")
        if not share_fit:
            must_fixes.append("设计可被拍照分享的展示瞬间")
        evidence_ids = self.dedup(
            [*persona.derived_from_evidence_ids, *retrieved_evidence_ids]
        )[:10]
        return PersonaInterview(
            concept_id=concept.id,
            persona_id=persona.id,
            persona_name=persona.name,
            segment=persona.segment,
            transcript=turns,
            verdict=verdict,
            objections=objections,
            must_fixes=must_fixes,
            acceptance=acceptance,
            evidence_ids=evidence_ids,
        )
