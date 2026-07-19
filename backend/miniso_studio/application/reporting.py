"""Trend2SKU API 视图与 Markdown 报告渲染。"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from miniso_studio.application.runner import RunArtifacts
from miniso_studio.common.models import Evidence, ProductScorecard
from miniso_studio.infrastructure.data.connectors import (
    ANNUAL_REPORT_2025_URL,
    Q1_RESULTS_URL,
)
from miniso_studio.infrastructure.data.loader import index_evidence_by_source_id
from miniso_studio.infrastructure.observability.trace import public_trace_event

PRODUCT_NAME = "Trend2SKU"
SCHEMA_VERSION = "1.0"
DEMO_NOTICE = (
    "400 条固定种子合成离线演示，不是企业内部数据或真实用户评论，不代表爆款概率/销售/ROI"
)


def _dump(value: Any) -> Any:
    return value.model_dump(mode="json") if value is not None else None


def _dedup(values: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(value for value in values if value))


def build_data_provenance(art: RunArtifacts) -> dict:
    state = art.state
    index_evidence_by_source_id(
        state.all_evidences(),
        context="报告全局证据集合",
        allow_identical_duplicates=True,
    )
    reviews = list(state.target_evidences)
    for items in state.competitor_evidences.values():
        reviews.extend(items)
    reviews = list(
        index_evidence_by_source_id(
            reviews,
            context="报告评论集合",
            allow_identical_duplicates=True,
        ).values()
    )
    normalized_scopes = []
    for item in reviews:
        raw_scope = (item.data_provenance or "unspecified").strip()
        normalized_scopes.append(
            raw_scope if raw_scope in {"synthetic_demo", "public"} else "unknown"
        )
    scopes = set(normalized_scopes)
    if not scopes:
        review_scope = "unknown"
    elif len(scopes) == 1:
        review_scope = next(iter(scopes))
    else:
        review_scope = "mixed"
    if review_scope == "synthetic_demo" and len(reviews) == 400:
        notice = DEMO_NOTICE
    elif review_scope == "synthetic_demo":
        notice = (
            f"{len(reviews)} 条合成离线演示样本，不是企业内部数据或真实用户评论，"
            "不代表爆款概率/销售/ROI"
        )
    elif review_scope == "public":
        notice = (
            f"{len(reviews)} 条调用方提供的公开来源样本，不是企业内部数据，"
            "不代表全量用户、爆款概率、销售或 ROI"
        )
    elif review_scope == "unknown":
        notice = (
            f"{len(reviews)} 条样本的来源未确认，不能按公开数据或合成数据口径使用，"
            "不代表企业内部数据、爆款概率、销售或 ROI"
        )
    else:
        unknown_copy = "，且部分来源未确认" if "unknown" in scopes else ""
        notice = (
            f"{len(reviews)} 条混合来源研究样本{unknown_copy}，需逐条核验授权与来源，"
            "不代表企业内部数据、爆款概率、销售或 ROI"
        )

    official_sources = []
    seen = set()
    for item in sorted(state.trend_evidences, key=lambda ev: (ev.date or "", ev.source_id)):
        if not item.url or not item.url.startswith("https://ir.miniso.com/"):
            continue
        if item.source_id in seen:
            continue
        seen.add(item.source_id)
        official_sources.append(
            {
                "id": item.source_id,
                "date": item.date,
                "url": item.url,
                "text": item.text,
            }
        )
    return {
        "review_scope": review_scope,
        "review_count": len(reviews),
        "review_scope_counts": {
            scope: normalized_scopes.count(scope)
            for scope in ("synthetic_demo", "public", "unknown")
            if scope in normalized_scopes
        },
        "disclaimer": notice,
        "official_trend_cutoff": "2026-05-26",
        "official_trend_sources": official_sources,
    }


def _opportunity_view(opportunity: Any) -> dict:
    return {
        "id": opportunity.id,
        "aspect": opportunity.aspect,
        "statement": opportunity.statement,
        "opportunity_score": opportunity.opportunity_score,
        "impact_score": opportunity.impact_score,
        "origin": opportunity.origin,
        "rationale": opportunity.rationale,
        "evidence_ids": list(opportunity.evidence_ids),
    }


def _winner_scorecard(art: RunArtifacts, sorted_cards: List[ProductScorecard]) -> Optional[ProductScorecard]:
    state = art.state
    winner_id = state.chosen_concept.id if state.chosen_concept else ""
    winner = next((card for card in sorted_cards if card.concept_id == winner_id), None)
    if winner is None and state.proposal is not None:
        winner = state.proposal.scorecard
    return winner or (sorted_cards[0] if sorted_cards else None)


def _evidence_ids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "evidence_ids" and isinstance(nested, list):
                found.update(item for item in nested if isinstance(item, str))
            else:
                found.update(_evidence_ids(nested))
    elif isinstance(value, list):
        for nested in value:
            found.update(_evidence_ids(nested))
    return found


def _evidence_view(item: Evidence) -> dict:
    is_demo = item.data_provenance == "synthetic_demo" or bool(
        item.url and item.url.startswith("demo://")
    )
    return {
        "source_id": item.source_id,
        "source_type": item.source_type.value,
        "brand": item.brand,
        "product": item.product,
        "rating": item.rating,
        "text": item.text,
        "date": item.date,
        "url": None if is_demo else item.url,
        "helpful_votes": item.helpful_votes,
        "data_provenance": item.data_provenance,
        "is_demo": is_demo,
    }


def to_view(art: RunArtifacts) -> dict:
    """构造稳定的 Trend2SKU 1.0 API 视图。"""
    state = art.state
    evidence_by_id = index_evidence_by_source_id(
        state.all_evidences(),
        context="API 全局证据集合",
        allow_identical_duplicates=True,
    )
    voc = state.voc_report
    market = state.market_intel
    sorted_cards = sorted(
        state.concept_scorecards,
        key=lambda card: (-card.total_score, card.concept_id),
    )
    concept_ids = {concept.id for concept in state.concepts}
    scorecard_ids = {card.concept_id for card in sorted_cards}
    if concept_ids != scorecard_ids or len(scorecard_ids) != len(sorted_cards):
        raise ValueError("候选 SKU 与评分卡必须一一对应且 concept_id 唯一")
    winner_card = _winner_scorecard(art, sorted_cards)
    winner = state.chosen_concept
    if winner is None and winner_card is not None:
        winner = next(
            (concept for concept in state.concepts if concept.id == winner_card.concept_id),
            None,
        )
    winner_id = winner.id if winner is not None else (winner_card.concept_id if winner_card else None)

    candidate_skus = [_dump(concept) for concept in state.concepts]
    scorecards = [_dump(card) for card in sorted_cards]
    decision = state.decision
    proposal = state.proposal
    if proposal is not None:
        linked_ids = {
            proposal.concept.id,
            proposal.scorecard.concept_id,
            winner_id,
        }
        if None in linked_ids or len(linked_ids) != 1:
            raise ValueError("榜首、提案概念与提案评分卡未按 concept_id 联动")
    if decision is not None and winner_card is not None:
        if decision.verdict != winner_card.recommendation:
            raise ValueError("组合决策与榜首评分卡建议不一致")
    prfaq = proposal.prfaq if proposal is not None else state.prfaq
    portfolio_decision = {
        "winner_id": winner_id,
        "winner_name": winner.name if winner is not None else None,
        "verdict": decision.verdict.value if decision is not None else None,
        "confidence": decision.confidence if decision is not None else None,
        "rationale": decision.rationale if decision is not None else "",
        "conditions": list(decision.conditions) if decision is not None else [],
        "evidence_ids": list(decision.evidence_ids) if decision is not None else [],
        "reviewer": decision.reviewer if decision is not None else None,
        "timestamp": decision.timestamp if decision is not None else None,
        "prfaq": _dump(prfaq),
    }

    launch_by_candidate: Dict[str, dict] = {}
    quality_by_candidate: Dict[str, Any] = {}
    for concept in state.concepts:
        evaluation = state.candidate_evaluations.get(concept.id)
        interviews = list(evaluation.interviews) if evaluation is not None else []
        average_acceptance = (
            round(sum(item.acceptance for item in interviews) / len(interviews), 4)
            if interviews
            else 0.0
        )
        launch_by_candidate[concept.id] = {
            "concept_id": concept.id,
            "interviews": [_dump(item) for item in interviews],
            "nps": _dump(evaluation.nps) if evaluation is not None else None,
            "average_acceptance": average_acceptance,
            "mode": "offline_demo",
        }
        quality_by_candidate[concept.id] = (
            _dump(evaluation.feasibility) if evaluation is not None else None
        )

    winner_launch = launch_by_candidate.get(winner_id) if winner_id else None
    winner_assessment = quality_by_candidate.get(winner_id) if winner_id else None
    consumer_insights = {
        "review_count": voc.review_count if voc is not None else 0,
        "aspects": [_dump(item) for item in (voc.aspects if voc is not None else [])],
        "opportunities": [
            _opportunity_view(item) for item in (voc.opportunities if voc is not None else [])
        ],
        "ost": _dump(voc.ost) if voc is not None else None,
        "white_space": [
            _opportunity_view(item)
            for item in (market.white_space_opportunities if market is not None else [])
        ],
    }
    quality_audit = {
        "by_candidate": quality_by_candidate,
        "winner_assessment": winner_assessment,
        "rubric": _dump(art.rubric),
        "evidence_count": 0,
        "claim_count": len(state.claims),
        "mode": "offline_demo",
    }
    trace_events = [public_trace_event(event) for event in art.trace_events]
    audit = {
        "tool_calls": [event for event in trace_events if event.get("kind") == "tool_call"],
        "trace": trace_events,
        "experience_baseline": _dump(art.comparison),
    }
    visible = {
        "candidate_skus": candidate_skus,
        "scorecards": scorecards,
        "winner_scorecard": _dump(winner_card),
        "portfolio_decision": portfolio_decision,
        "trend_signals": [_dump(item) for item in (market.trends if market is not None else [])],
        "consumer_insights": consumer_insights,
        "launch_validation": {
            "by_candidate": launch_by_candidate,
            "winner_id": winner_id,
            "winner": winner_launch,
            "disclaimer": "访谈、接受度与 NPS 均为离线演示推演，不是实测结果。",
        },
        "quality_audit": quality_audit,
    }

    referenced_ids = _evidence_ids(visible)
    missing = sorted(referenced_ids - set(evidence_by_id))
    if missing:
        raise ValueError(f"视图引用了不存在的 Evidence：{', '.join(missing[:5])}")
    evidence_index = {
        source_id: _evidence_view(evidence_by_id[source_id])
        for source_id in sorted(referenced_ids)
    }
    quality_audit["evidence_count"] = len(evidence_index)

    return {
        "schema_version": SCHEMA_VERSION,
        "product": PRODUCT_NAME,
        "run_id": art.run_id,
        "thread_id": art.thread_id,
        "status": "awaiting_human" if art.awaiting_human else "completed",
        "awaiting_human": art.awaiting_human,
        "elapsed_seconds": art.elapsed_seconds,
        "provider": art.effective_provider,
        "configured_provider": art.configured_provider,
        "effective_provider": art.effective_provider,
        "category": state.category,
        "target_brand": state.target_brand,
        "data_provenance": build_data_provenance(art),
        **visible,
        "evidence_index": evidence_index,
        "audit": audit,
    }


def _official_context_lines() -> List[str]:
    return [
        (
            "- **2026-05-26（2026 年一季度未经审计业绩）**：集团收入 56.884 亿元，"
            "同比增长 28.5%；MINISO 品牌收入同比增长 26.6%，中国内地收入同比增长 29.6%，"
            "海外收入同比增长 21.9%。截至 2026-03-31，"
            "集团门店 8,565 家，MINISO 门店 8,210 家，其中中国内地 4,593 家、海外 3,617 家；"
            "过去十二个月新增 MINISO 门店约 56% 位于海外。IP 授权费用同比增长 42.0%，约占收入 2.6%。"
            f"[官方来源]({Q1_RESULTS_URL})"
        ),
        (
            "- **2026-04-24（2025 年年报）**：2025 年平均每月推出约 1,600 个 SKU；"
            "截至 2025-12-31，MINISO 门店 8,151 家，其中海外 3,583 家；集团 GMV 约 371 亿元，"
            "收入 214.438 亿元，同比增长 26.2%，毛利率 45.0%，海外收入占 MINISO 品牌收入 44.2%；"
            "IP 授权费用同比增长 44.6%，约占收入 2.5%-2.8%。"
            f"[官方来源]({ANNUAL_REPORT_2025_URL})"
        ),
        "- **研究边界**：情绪价值与社交传播是基于公开经营材料形成的产品研究假设，仍需公开内容数据和小规模试购继续验证。",
    ]


def render_full_report(art: RunArtifacts) -> str:
    """渲染完整经营决策报告；所有预测数值均标注为离线演示。"""
    view = to_view(art)
    state = art.state
    decision = view["portfolio_decision"]
    out: List[str] = [
        f"# {PRODUCT_NAME} 爆款产品决策 Agent · 运行报告",
        "",
        f"> Run ID：`{art.run_id}`　目标品牌：MINISO　品类：`{state.category}`",
        (
            f"> Configured Provider：{art.configured_provider}　"
            f"Effective Provider：{art.effective_provider}"
        ),
        f"> Brief：{state.brief}",
        f"> 数据边界：{view['data_provenance']['disclaimer']}。",
        "",
        "## 1. 2026 公开经营信号与研究假设",
        "",
        *_official_context_lines(),
        "",
        "## 2. 候选 SKU 组合与榜首（离线演示评分）",
        "",
        "| 排名 | 候选 SKU | 创意路径 | 八维总分（离线演示） | 建议 |",
        "|---:|---|---|---:|---|",
    ]
    concepts = {item["id"]: item for item in view["candidate_skus"]}
    for rank, card in enumerate(view["scorecards"], 1):
        concept = concepts[card["concept_id"]]
        out.append(
            f"| {rank} | {concept['name']} (`{concept['id']}`) | {concept['path']} | "
            f"{card['total_score']:.2f} | {card['recommendation']} |"
        )
    out.extend(
        [
            "",
            f"**榜首 SKU：{decision['winner_name']} (`{decision['winner_id']}`)**",
            f"组合决策：`{decision['verdict']}`，置信度 {decision['confidence']}（离线演示）。",
            f"决策理由：{decision['rationale']}",
        ]
    )
    if decision["conditions"]:
        out.append("进入下一阶段的条件：" + "；".join(decision["conditions"]))

    out.extend(
        [
            "",
            "## 3. 八维商业评分矩阵（离线演示）",
            "",
            "| 候选 | 维度 | 权重 | 得分 | 判分依据 |",
            "|---|---|---:|---:|---|",
        ]
    )
    for card in view["scorecards"]:
        for dimension in card["dimensions"]:
            out.append(
                f"| {concepts[card['concept_id']]['name']} | {dimension['label']} | "
                f"{dimension['weight']:.0%} | {dimension['score']:.2f} | {dimension['rationale']} |"
            )

    insights = view["consumer_insights"]
    scope = view["data_provenance"]["review_scope"]
    scope_copy = (
        "全部属于固定种子合成离线演示"
        if scope == "synthetic_demo"
        else f"来源范围为 {scope}，具体边界见第 8 节"
    )
    out.extend(
        [
            "",
            "## 4. 趋势感知与用户机会",
            "",
            f"本次分析使用 MINISO 目标样本 {insights['review_count']} 条；{scope_copy}。",
            "",
            "**趋势信号**",
        ]
    )
    for trend in view["trend_signals"]:
        out.append(f"- {trend['name']}：{trend['summary']}（证据：{', '.join(trend['evidence_ids'])}）")
    out.append("")
    out.append("**优先机会**")
    for opportunity in insights["opportunities"][:5]:
        out.append(
            f"- `{opportunity['id']}` {opportunity['statement']}，机会分 "
            f"{opportunity['opportunity_score']:.2f}（离线演示；证据：{', '.join(opportunity['evidence_ids'][:3])}）"
        )

    out.extend(["", "## 5. 上市验证（离线演示）", ""])
    for concept_id, validation in view["launch_validation"]["by_candidate"].items():
        nps = validation["nps"] or {}
        out.append(
            f"- **{concepts[concept_id]['name']}**：模拟访谈 {len(validation['interviews'])} 次，"
            f"平均接受度 {validation['average_acceptance']:.0%}，预测 NPS {nps.get('score', 0):.1f}。"
        )
    out.append(f"> {view['launch_validation']['disclaimer']}")

    out.extend(["", "## 6. 商品风险与决策条件", ""])
    for concept_id, assessment in view["quality_audit"]["by_candidate"].items():
        if assessment is None:
            out.append(f"- **{concepts[concept_id]['name']}**：尚无商品可行性评估。")
            continue
        risks = assessment.get("risks", [])
        risk_copy = "；".join(
            f"[{risk['severity']}] {risk['description']} -> {risk['mitigation']}" for risk in risks
        ) or "未识别到结构化风险"
        out.append(
            f"- **{concepts[concept_id]['name']}**：毛利 {assessment['gross_margin_score']:.0f}，"
            f"供应链 {assessment['supply_feasibility_score']:.0f}，IP/合规 {assessment['ip_compliance_score']:.0f}，"
            f"全球本地化 {assessment['localization_score']:.0f}；{risk_copy}（均为离线演示评估）。"
        )

    tool_calls = view["audit"]["tool_calls"]
    out.extend(
        [
            "",
            "## 7. 工具调用与证据审计",
            "",
            f"本次记录 {len(tool_calls)} 次只读工具调用，视图实际引用 {len(view['evidence_index'])} 条证据。",
            "",
            "| 工具 | 状态 | 是否降级 |",
            "|---|---|---|",
        ]
    )
    for event in tool_calls:
        out.append(
            f"| `{event.get('tool_name', '')}` | {event.get('status', '')} | "
            f"{'是' if event.get('used_fallback') else '否'} |"
        )
    out.extend(
        [
            "",
            "## 8. 数据边界",
            "",
            f"- {view['data_provenance']['disclaimer']}。",
            "- 官方经营数字用于说明决策场景和趋势背景，不用于直接推导单品销量、爆款概率或投资回报。",
            "- 情绪价值与社交传播为研究假设；候选评分、接受度、NPS 与风险分均为离线演示结果。",
        ]
    )
    return "\n".join(out)


def render_opening_report(art: RunArtifacts) -> str:
    """渲染供后续报名材料引用的开题底稿，不宣称已满足表单字数。"""
    view = to_view(art)
    decision = view["portfolio_decision"]
    out = [
        f"# {PRODUCT_NAME} 爆款产品决策 Agent · 开题底稿",
        "",
        f"> Brief：{art.state.brief}",
        (
            f"> Configured Provider：{art.configured_provider}　"
            f"Effective Provider：{art.effective_provider}"
        ),
        f"> 数据边界：{view['data_provenance']['disclaimer']}。",
        "",
        "## Part 1 命题前置分析与洞察",
        "",
        "MINISO 在全球门店扩张、IP 投入和高频上新的经营背景下，需要同时处理趋势速度、创意规模、"
        "供应链约束与区域偏好。2026-05-26 发布的 2026 年一季度未经审计业绩显示，MINISO 门店达到 "
        "8,210 家，其中海外 3,617 家；2026-04-24 发布的 2025 年年报披露平均每月推出约 1,600 个 SKU。"
        "因此，命题不只是生成创意，而是把趋势感知、产品创意、上市验证和证据审计连接为可复核的决策链。"
        "情绪价值与社交传播只作为研究假设，需通过后续公开内容数据与小规模试购验证。",
        "",
        "## Part 2 整体解决方案设计",
        "",
        f"**1. 方案整体概述**：构建 {PRODUCT_NAME}，由趋势雷达、用户镜像、创意工坊、商品专家、"
        "爆款评审与提案生成六类 Agent 协作，将公开趋势和离线演示样本转成三个候选 SKU，再形成榜首提案。",
        "",
        "**2. 整体架构与核心模块**：Evidence 数据层统一来源；洞察层生成趋势、机会与白空间；创意层并行生成 "
        "VOC、趋势和白空间三条路径；验证层按候选隔离模拟访谈、NPS 与商品可行性；决策层按八维量表稳定排序，"
        "严重 IP/质量风险禁止直接 GO；审计层记录工具调用、引用与 HITL checkpoint。",
        "",
        "**3. 核心创新点**：数值评分由确定性工具控制，模型只负责批判与叙述；候选、验证与风险始终按 concept_id "
        "关联；同一轮同时保留多候选，避免过早收敛；每个可见引用均可在证据索引中解析。",
        "",
        f"**4. 可量化预期价值**：本次离线演示生成 {len(view['candidate_skus'])} 个候选，完成 "
        f"{sum(len(item['interviews']) for item in view['launch_validation']['by_candidate'].values())} 次模拟访谈，"
        f"榜首为 {decision['winner_name']}，八维总分 {view['winner_scorecard']['total_score']:.2f}，"
        f"建议 {decision['verdict']}。这些数字仅验证流程可运行，不代表销售、爆款概率或 ROI。",
        "",
        "**5. 落地可行性与推广性**：离线模式可固定种子复现，在线模式可接入 MiniMax 做文本批判但不改写数值评分；"
        "替换品类词典、证据连接器和商品规则即可推广到其他兴趣消费品类，并以小规模试购逐步校准阈值。",
        "",
        "## 2026 官方资料口径",
        "",
        *_official_context_lines(),
        "",
        "## 数据边界",
        "",
        f"{view['data_provenance']['disclaimer']}。所有评分、访谈、NPS 与风险数值均为离线演示。",
    ]
    return "\n".join(out)
