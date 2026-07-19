"""趋势雷达 Agent：竞品白空间、公开趋势与证据检索。"""
from __future__ import annotations

from miniso_studio.application.agents.base import Agent
from miniso_studio.application.graph.state import PipelineState
from miniso_studio.application.platforms.market_intelligence import build_market_intel
from miniso_studio.common.models import Evidence, TrendSignal
from miniso_studio.infrastructure.data import retail_tools as _retail_tools  # noqa: F401
from miniso_studio.infrastructure.data.connectors import fetch_trends
from miniso_studio.infrastructure.data.loader import (
    EvidenceIdConflictError,
    index_evidence_by_source_id,
)
from miniso_studio.infrastructure.nlp.lexicons import ASPECT_LEXICON


def _aspect_query(aspect: str) -> str:
    keywords = [keyword for keyword in ASPECT_LEXICON.get(aspect, []) if keyword.isascii()]
    return " ".join(keywords[:4]) or aspect


class SuperThinkTankAgent(Agent):
    name = "趋势雷达 Agent"
    role = "兴趣消费趋势感知 / 竞品白空间 / 证据审计"

    def run(self, state: PipelineState) -> PipelineState:
        keywords = ["IP联名", "情绪价值", "社交传播", "全球本地化"]
        def fallback_trends():
            return fetch_trends(keywords)

        tool_result = self.call_read_tool(
            "get_retail_trends",
            fallback=fallback_trends,
            validator=self._valid_trend_result,
            keywords=keywords,
        )
        if not self._valid_trend_result(tool_result):
            tool_result = fallback_trends()
        trends, trend_evidence = tool_result
        reviews = list(state.target_evidences)
        for items in state.competitor_evidences.values():
            reviews.extend(items)
        state.trend_evidences = self._merge_evidence(
            state.trend_evidences,
            trend_evidence,
            reviews,
        )

        intel = build_market_intel(state.competitor_evidences, trends)
        searchable = state.all_evidences()
        for opportunity in intel.white_space_opportunities:
            def fallback_evidence(opportunity=opportunity):
                if self.rag is None:
                    return []
                evidence, meta = self.rag.agentic_search(
                    _aspect_query(opportunity.aspect),
                    top_k=5,
                    min_hits=2,
                )
                state.retrieval_iters += int(meta.get("iterations", 1))
                return evidence

            retrieved = self.call_read_tool(
                "search_retail_evidence",
                fallback=fallback_evidence,
                validator=self._valid_evidence_result,
                evidences=searchable,
                query=opportunity.aspect,
                top_k=5,
            )
            if not isinstance(retrieved, list) or not all(
                isinstance(item, Evidence) for item in retrieved
            ):
                retrieved = fallback_evidence()
            opportunity.evidence_ids = self.dedup(
                [*opportunity.evidence_ids, *(item.source_id for item in retrieved[:3])]
            )

        state.market_intel = intel
        for finding in intel.competitors:
            for weakness in finding.weaknesses:
                state.add_claim(f"{finding.brand} 的商品体验短板：{weakness}", finding.evidence_ids)
        for opportunity in intel.white_space_opportunities:
            state.add_claim(opportunity.statement, opportunity.evidence_ids)
        for trend in trends:
            state.add_claim(f"趋势：{trend.name}；{trend.summary}", trend.evidence_ids)

        if self.tracer:
            self.tracer.emit(
                self.name,
                "result",
                competitors=len(intel.competitors),
                white_space=len(intel.white_space_opportunities),
                trends=len(trends),
            )
        return state

    @staticmethod
    def _valid_trend_result(value: object) -> bool:
        return (
            isinstance(value, tuple)
            and len(value) == 2
            and isinstance(value[0], list)
            and isinstance(value[1], list)
            and all(isinstance(item, TrendSignal) for item in value[0])
            and all(isinstance(item, Evidence) for item in value[1])
        )

    @staticmethod
    def _merge_evidence(
        existing: list[Evidence],
        incoming: list[Evidence],
        reviews: list[Evidence],
    ) -> list[Evidence]:
        review_by_id = index_evidence_by_source_id(
            reviews,
            context="目标与竞品评论集合",
        )
        for item in [*existing, *incoming]:
            if item.source_id in review_by_id:
                raise EvidenceIdConflictError(
                    f"趋势证据 source_id={item.source_id} 与评论样本冲突，拒绝覆盖"
                )
        by_id = index_evidence_by_source_id(
            [*existing, *incoming],
            context="趋势证据集合",
            allow_identical_duplicates=True,
        )
        return [by_id[source_id] for source_id in sorted(by_id)]

    @staticmethod
    def _valid_evidence_result(value: object) -> bool:
        return isinstance(value, list) and all(isinstance(item, Evidence) for item in value)
