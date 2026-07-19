"""用户镜像 Agent：按候选隔离的兴趣消费合成访谈。"""
from __future__ import annotations

import hashlib
from typing import List

from miniso_studio.application.agents.base import Agent
from miniso_studio.application.graph.state import PipelineState
from miniso_studio.application.portfolio.dynamic_candidates import category_profile
from miniso_studio.common.decision_input import DecisionInput
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
                self._interview(
                    persona,
                    concept,
                    retrieved_ids,
                    state.decision_input,
                    legacy_input=state.legacy_input,
                )
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
        decision = state.decision_input
        profile = category_profile(decision)
        scenarios = "、".join(profile.scenarios)
        personas: List[Persona] = []
        for index, opportunity in enumerate(state.voc_report.opportunities[:4]):
            segment = (
                f"{decision.target_segment_label}："
                f"{self._segment_for(opportunity.aspect)}"
            )
            personas.append(
                Persona(
                    id=f"P-{index + 1}",
                    name=f"{decision.target_segment_label}镜像{index + 1}",
                    segment=segment,
                    demographics=(
                        f"面向{decision.target_market_label}的{decision.target_segment_label}，"
                        f"选购{decision.category_label}时关注{decision.price_label}。"
                    ),
                    ocean=_ocean_from(
                        "-".join(
                            [
                                str(decision.product_category),
                                str(decision.target_segment),
                                str(decision.target_market),
                                opportunity.aspect,
                                str(index),
                            ]
                        )
                    ),
                    behaviors=[
                        f"会在{scenarios}比较{decision.category_label}的设计、做工与价格",
                        f"按{decision.ip_strategy_label}核验权利说明，并兼顾自用、轻礼赠或收藏",
                    ],
                    pains=[opportunity.statement],
                    derived_from_evidence_ids=opportunity.evidence_ids,
                    summary=(
                        f"{decision.target_segment_label}在{scenarios}使用{decision.category_label}，"
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
        decision: DecisionInput,
        *,
        legacy_input: bool = False,
    ) -> PersonaInterview:
        profile = category_profile(decision)
        scenarios = "、".join(profile.scenarios)
        if legacy_input:
            concept_copy = " ".join(
                [concept.one_liner, concept.value_proposition, *concept.key_features]
            )
            visual_fit = any(
                term in concept_copy for term in ("角色", "设计", "城市", "配色", "IP")
            )
            gift_fit = any(term in concept_copy for term in ("礼赠", "礼物", "礼盒", "祝福"))
            collect_fit = any(term in concept_copy for term in ("收藏", "限定", "编号", "系列"))
            share_fit = any(term in concept_copy for term in ("分享", "拍照", "展示", "开箱", "话题"))
        else:
            # 动态输入只由稳定候选路径形成接受度信号，避免自由文本通过概念文案刷分。
            path_signals = {
                "voc_driven": (True, True, False, False),
                "trend_driven": (True, False, True, True),
                "whitespace_driven": (False, True, False, True),
            }
            visual_fit, gift_fit, collect_fit, share_fit = path_signals.get(
                concept.path,
                (False, False, False, False),
            )
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
                question=(
                    f"围绕“{decision.brief}”，作为{decision.target_segment_label}，"
                    f"你会在{decision.target_market_label}的"
                    f"哪些{scenarios}使用场景购买这款{decision.category_label}？"
                ),
                answer=(
                    f"我会在{scenarios}使用这款{profile.form}，并确认它真正解决："
                    f"{persona.pains[0]}；同时要满足{decision.constraints or '常规零售验收条件'}。"
                ),
                sentiment="positive" if acceptance >= 0.65 else "neutral",
            ),
            InterviewTurn(
                question=(
                    f"你对这款{decision.category_label}的视觉与 IP 风格有什么偏好？"
                ),
                answer=(
                    f"角色和区域设计要有辨识度，并按{decision.ip_strategy_label}说明权利来源。"
                    if visual_fit
                    else f"{decision.category_label}功能清楚，但视觉记忆点还不够。"
                ),
                sentiment="positive" if visual_fit else "neutral",
            ),
            InterviewTurn(
                question=(
                    f"作为{decision.target_segment_label}，你对{decision.price_label}的"
                    f"{decision.category_label}价格敏感度如何？"
                ),
                answer=(
                    f"我会比较{decision.price_label}的做工和可重复使用价值，价格透明才愿意下单。"
                    if concept.path != "trend_driven"
                    else f"{decision.price_label}的限定设计可以有差异，但补充件和普通款仍要可负担。"
                ),
                sentiment="neutral",
            ),
            InterviewTurn(
                question=(
                    f"你会在{scenarios}把这款{decision.category_label}用于礼赠或收藏吗？"
                ),
                answer=(
                    f"包装体面且系列不重复时，我会把{profile.noun}送人，也会继续收藏。"
                    if gift_fit or collect_fit
                    else f"这款{profile.noun}目前更像自用品，礼赠和收藏理由需要加强。"
                ),
                sentiment="positive" if gift_fit or collect_fit else "neutral",
            ),
            InterviewTurn(
                question=(
                    f"这款{decision.category_label}在{decision.target_market_label}是否值得拍照分享或推荐？"
                ),
                answer=(
                    f"有可展示的细节和场景故事，我愿意向其他{decision.target_segment_label}分享。"
                    if share_fit
                    else f"{profile.noun}需要一个更鲜明的开箱或展示瞬间。"
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
