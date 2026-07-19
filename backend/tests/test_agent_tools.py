"""Agent 工具调用、候选隔离与离线复现的行为测试。"""
from __future__ import annotations

import json

from miniso_studio.application.agents.base import Agent
from miniso_studio.application.agents.decision_officer import DecisionOfficerAgent
from miniso_studio.application.graph.checkpoint import JsonCheckpointer
from miniso_studio.application.runner import run_studio
from miniso_studio.application.scoring.hit_score import score_candidate_portfolio
from miniso_studio.common.models import DecisionVerdict, RiskItem
from miniso_studio.common.tools import ToolType, get_tool, tool
from miniso_studio.infrastructure.data import retail_tools  # noqa: F401 - 导入即注册工具
from miniso_studio.infrastructure.llm.gateway import LLMGateway
from miniso_studio.infrastructure.observability.trace import Tracer


EXPECTED_TOOL_NAMES = {
    "search_retail_evidence",
    "get_retail_trends",
    "generate_candidate_portfolio",
    "assess_merchandise_candidate",
    "score_candidate_portfolio",
}


def test_agent_tools_are_registered_as_confirmation_free_reads():
    for name in EXPECTED_TOOL_NAMES:
        registered = get_tool(name)
        assert registered.tool_type == ToolType.READ
        assert registered.requires_confirmation is False


def test_call_read_tool_records_sanitized_success_and_error(tmp_path):
    @tool(ToolType.READ)
    def test_safe_summary_tool(secret: str, comments: list[str]):
        """仅供工具调用 trace 行为测试。"""
        return {"accepted": len(comments), "echo": secret}

    @tool(ToolType.READ)
    def test_failing_read_tool(brief: str):
        """仅供错误降级行为测试。"""
        raise RuntimeError("upstream unavailable")

    tracer = Tracer(run_id="tool-sanitization")
    tracer.path = tmp_path / "tool-sanitization.jsonl"
    agent = Agent(LLMGateway(), tracer=tracer)

    sensitive = "sk-live-DO-NOT-TRACE"
    result = agent.call_read_tool(
        "test_safe_summary_tool",
        fallback={"accepted": 0},
        secret=sensitive,
        comments=["一整段不应进入 trace 的用户评论正文"],
    )
    degraded = agent.call_read_tool(
        "test_failing_read_tool",
        fallback={"source": "deterministic-fallback"},
        brief="这是一份不应完整记录的产品 brief",
    )

    assert result["accepted"] == 1
    assert degraded == {"source": "deterministic-fallback"}
    calls = [event for event in tracer.events if event["kind"] == "tool_call"]
    assert [event["status"] for event in calls] == ["success", "error"]
    assert [event["tool_name"] for event in calls] == [
        "test_safe_summary_tool",
        "test_failing_read_tool",
    ]
    serialized = json.dumps(calls, ensure_ascii=False)
    assert sensitive not in serialized
    assert "一整段不应进入 trace 的用户评论正文" not in serialized
    assert "这是一份不应完整记录的产品 brief" not in serialized
    assert "input_summary" in calls[0] and "output_summary" in calls[0]


def test_pipeline_exercises_tools_and_keeps_candidate_results_isolated(tmp_path):
    tracer = Tracer(run_id="agent-tools-pipeline")
    tracer.path = tmp_path / "agent-tools-pipeline.jsonl"

    artifacts = run_studio(thread_id="agent-tools-pipeline", tracer=tracer)
    state = artifacts.state

    tool_events = [event for event in tracer.events if event["kind"] == "tool_call"]
    called = {event["tool_name"] for event in tool_events}
    assert EXPECTED_TOOL_NAMES <= called
    assert all(event["status"] == "success" for event in tool_events)

    concept_ids = {concept.id for concept in state.concepts}
    assert concept_ids == {"C-VOC", "C-TREND", "C-WHITESPACE"}
    assert set(state.candidate_evaluations) == concept_ids
    assert {card.concept_id for card in state.concept_scorecards} == concept_ids

    for concept_id, evaluation in state.candidate_evaluations.items():
        assert evaluation.concept_id == concept_id
        assert evaluation.iteration == state.pm_iteration
        assert evaluation.interviews
        assert all(interview.concept_id == concept_id for interview in evaluation.interviews)
        questions = " ".join(
            turn.question for interview in evaluation.interviews for turn in interview.transcript
        )
        for topic in ("使用", "视觉", "价格", "礼赠", "分享"):
            assert topic in questions
        assert evaluation.feasibility is not None
        feasibility_copy = " ".join(
            [
                evaluation.feasibility.quality,
                evaluation.feasibility.gross_margin,
                evaluation.feasibility.supplier_lead_time,
                evaluation.feasibility.ip_authorization,
                evaluation.feasibility.regional_compliance,
                evaluation.feasibility.localization,
            ]
        )
        assert feasibility_copy
        assert evaluation.nps is not None
        assert evaluation.scorecard is not None
        assert evaluation.scorecard.concept_id == concept_id

    winner = min(state.concept_scorecards, key=lambda card: (-card.total_score, card.concept_id))
    assert state.chosen_concept.id == winner.concept_id
    assert state.proposal.concept.id == winner.concept_id
    assert state.proposal.scorecard == winner
    assert state.decision.verdict == winner.recommendation
    assert state.interviews == state.candidate_evaluations[winner.concept_id].interviews
    assert state.feasibility == state.candidate_evaluations[winner.concept_id].feasibility
    assert state.nps == state.candidate_evaluations[winner.concept_id].nps
    assert artifacts.comparison.arm_b.validated_assumptions == sum(
        len(evaluation.interviews)
        for evaluation in state.candidate_evaluations.values()
    ) == 12
    assert artifacts.comparison.arm_b.feasibility_risks_identified == sum(
        len(evaluation.feasibility.risks)
        for evaluation in state.candidate_evaluations.values()
        if evaluation.feasibility
    ) == 3


def test_registered_candidate_tool_output_changes_agent_artifact(monkeypatch, tmp_path):
    registered = get_tool("generate_candidate_portfolio")
    original = registered.fn

    def marked_portfolio(*args, **kwargs):
        concepts = original(*args, **kwargs)
        concepts[0].name = "工具结果已进入产物"
        return concepts

    monkeypatch.setattr(registered, "fn", marked_portfolio)
    tracer = Tracer(run_id="tool-output-influence")
    tracer.path = tmp_path / "tool-output-influence.jsonl"

    artifacts = run_studio(thread_id="tool-output-influence", tracer=tracer)

    assert any(concept.name == "工具结果已进入产物" for concept in artifacts.state.concepts)
    assert any(
        event["tool_name"] == "generate_candidate_portfolio" and event["status"] == "success"
        for event in tracer.events
        if event["kind"] == "tool_call"
    )


def test_tool_error_uses_deterministic_pipeline_fallback(monkeypatch, tmp_path):
    registered = get_tool("get_retail_trends")

    def unavailable(*args, **kwargs):
        raise RuntimeError("trend provider unavailable")

    monkeypatch.setattr(registered, "fn", unavailable)
    tracer = Tracer(run_id="tool-fallback")
    tracer.path = tmp_path / "tool-fallback.jsonl"

    artifacts = run_studio(thread_id="tool-fallback", tracer=tracer)

    assert artifacts.state.market_intel is not None
    assert len(artifacts.state.market_intel.trends) >= 4
    assert any(
        event["tool_name"] == "get_retail_trends" and event["status"] == "error"
        for event in tracer.events
        if event["kind"] == "tool_call"
    )


def test_malformed_trend_result_is_audited_as_error_and_uses_fallback(monkeypatch, tmp_path):
    from miniso_studio.application.agents import super_think_tank as trend_module

    registered = get_tool("get_retail_trends")
    original_fallback = trend_module.fetch_trends
    fallback_calls = 0

    def counted_fallback(keywords):
        nonlocal fallback_calls
        fallback_calls += 1
        return original_fallback(keywords)

    monkeypatch.setattr(trend_module, "fetch_trends", counted_fallback)
    monkeypatch.setattr(registered, "fn", lambda **kwargs: {"unexpected": "payload"})
    tracer = Tracer(run_id="malformed-trend-result")
    tracer.path = tmp_path / "malformed-trend-result.jsonl"

    artifacts = run_studio(thread_id="malformed-trend-result", tracer=tracer)

    assert len(artifacts.state.market_intel.trends) >= 4
    event = next(
        item
        for item in tracer.events
        if item["kind"] == "tool_call" and item["tool_name"] == "get_retail_trends"
    )
    assert event["status"] == "error"
    assert event["used_fallback"] is True
    assert fallback_calls == 1


def test_successful_pipeline_does_not_execute_eager_fallbacks(monkeypatch, tmp_path):
    from miniso_studio.application.agents import decision_officer as decision_module
    from miniso_studio.application.agents import industry_expert as merchandise_module
    from miniso_studio.application.agents import product_manager as ideation_module
    from miniso_studio.application.agents import super_think_tank as trend_module

    calls = {"trend": 0, "ideation": 0, "merchandise": 0, "scoring": 0}

    def counted(name, original):
        def wrapper(*args, **kwargs):
            calls[name] += 1
            return original(*args, **kwargs)

        return wrapper

    monkeypatch.setattr(
        trend_module,
        "fetch_trends",
        counted("trend", trend_module.fetch_trends),
    )
    monkeypatch.setattr(
        ideation_module,
        "build_candidate_portfolio",
        counted("ideation", ideation_module.build_candidate_portfolio),
    )
    monkeypatch.setattr(
        merchandise_module,
        "build_merchandise_assessment",
        counted("merchandise", merchandise_module.build_merchandise_assessment),
    )
    monkeypatch.setattr(
        decision_module,
        "build_portfolio_scorecards",
        counted("scoring", decision_module.build_portfolio_scorecards),
    )
    tracer = Tracer(run_id="lazy-production-fallbacks")
    tracer.path = tmp_path / "lazy-production-fallbacks.jsonl"

    state = run_studio(thread_id="lazy-production-fallbacks", tracer=tracer).state

    assert calls == {"trend": 0, "ideation": 0, "merchandise": 0, "scoring": 0}
    assert state.retrieval_iters == 0


def test_duplicate_candidate_id_from_tool_is_rejected_for_exact_fallback(monkeypatch, tmp_path):
    registered = get_tool("generate_candidate_portfolio")
    original = registered.fn

    def duplicate_id_portfolio(*args, **kwargs):
        concepts = original(*args, **kwargs)
        duplicate = concepts[0].model_copy(deep=True)
        duplicate.name = "重复 ID 但名称不同的畸形候选"
        return [*concepts, duplicate]

    monkeypatch.setattr(registered, "fn", duplicate_id_portfolio)
    tracer = Tracer(run_id="duplicate-candidate-id")
    tracer.path = tmp_path / "duplicate-candidate-id.jsonl"

    state = run_studio(thread_id="duplicate-candidate-id", tracer=tracer).state

    expected_ids = {"C-VOC", "C-TREND", "C-WHITESPACE"}
    assert len(state.concepts) == 3
    assert len(state.candidate_evaluations) == 3
    assert len(state.concept_scorecards) == 3
    assert {concept.id for concept in state.concepts} == expected_ids
    assert set(state.candidate_evaluations) == expected_ids
    assert {scorecard.concept_id for scorecard in state.concept_scorecards} == expected_ids
    event = next(
        item
        for item in tracer.events
        if item["kind"] == "tool_call" and item["tool_name"] == "generate_candidate_portfolio"
    )
    assert event["status"] == "error"
    assert event["used_fallback"] is True


def test_second_iteration_replaces_first_round_candidate_claims(monkeypatch, tmp_path):
    registered = get_tool("score_candidate_portfolio")
    original = registered.fn
    candidate_tool = get_tool("generate_candidate_portfolio")
    original_candidate_tool = candidate_tool.fn
    calls = 0
    generation_calls = []

    def capture_revision_context(*args, **kwargs):
        concepts = original_candidate_tool(*args, **kwargs)
        generation_calls.append(
            {
                "revision_context": [
                    item.model_dump(mode="json")
                    for item in (kwargs.get("revision_context") or [])
                ],
                "features": {
                    concept.id: list(concept.key_features)
                    for concept in concepts
                },
                "differentiators": {
                    concept.id: [item.statement for item in concept.differentiators]
                    for concept in concepts
                },
                "revision_notes": {
                    concept.id: list(getattr(concept, "revision_notes", []))
                    for concept in concepts
                },
            }
        )
        return concepts

    def conditional_then_normal(*args, **kwargs):
        nonlocal calls
        calls += 1
        scorecards = original(*args, **kwargs)
        if calls == 1:
            for scorecard in scorecards:
                for dimension in scorecard.dimensions:
                    dimension.score = 74.0
                scorecard.total_score = 74.0
                scorecard.recommendation = DecisionVerdict.CONDITIONAL_GO
        return scorecards

    monkeypatch.setattr(registered, "fn", conditional_then_normal)
    monkeypatch.setattr(candidate_tool, "fn", capture_revision_context)
    tracer = Tracer(run_id="candidate-second-iteration")
    tracer.path = tmp_path / "candidate-second-iteration.jsonl"

    state = run_studio(thread_id="candidate-second-iteration", tracer=tracer).state

    assert calls == 2
    assert state.pm_iteration == 2
    assert len(state.concepts) == 3
    assert len(state.candidate_evaluations) == 3
    assert len(state.concept_scorecards) == 3
    assert all(
        evaluation.iteration == 2
        for evaluation in state.candidate_evaluations.values()
    )
    assert state.decision.verdict == state.proposal.scorecard.recommendation
    candidate_claims = [text for text, _ in state.claims if text.startswith("候选 ")]
    score_claims = [text for text in candidate_claims if "爆款评分" in text]
    decision_claims = [text for text, _ in state.claims if text.startswith("组合决策：")]
    assert len(score_claims) == 3
    assert len(decision_claims) == 1
    assert all("74.00" not in text for text, _ in state.claims)
    assert all("CONDITIONAL_GO" not in text for text, _ in state.claims)
    assert len(generation_calls) == 2
    assert generation_calls[0]["revision_context"] == []
    assert len(generation_calls[1]["revision_context"]) == 3
    assert any(
        context["risks"] or context["must_fixes"] or context["decision_conditions"]
        for context in generation_calls[1]["revision_context"]
    )
    assert generation_calls[0]["features"] == generation_calls[1]["features"]
    assert generation_calls[0]["differentiators"] == generation_calls[1]["differentiators"]
    assert not any(generation_calls[0]["revision_notes"].values())
    assert all(generation_calls[1]["revision_notes"].values())
    assert all(
        getattr(concept, "revision_notes", [])
        for concept in state.concepts
    )


def test_revision_notes_do_not_self_inflate_second_round_score(monkeypatch, tmp_path):
    from miniso_studio.application.scoring.hit_score import verdict_for

    scoring_tool = get_tool("score_candidate_portfolio")
    original_scoring = scoring_tool.fn
    scoring_rounds = []

    def stable_conditional_portfolio(*args, **kwargs):
        score_inputs = kwargs["inputs"]
        input_by_id = {item.concept.id: item for item in score_inputs}
        scorecards = original_scoring(*args, **kwargs)
        for scorecard in scorecards:
            trend_dimension = next(
                item for item in scorecard.dimensions if item.key == "trend_fit"
            )
            trend_dimension.score -= 37.5
            scorecard.total_score = round(
                sum(item.score * item.weight for item in scorecard.dimensions),
                2,
            )
            score_input = input_by_id[scorecard.concept_id]
            scorecard.recommendation = verdict_for(
                scorecard.total_score,
                severe_risk=score_input.severe_risk or bool(score_input.blocking_risks),
            )
        scoring_rounds.append(
            {
                "cards": {
                    card.concept_id: (card.total_score, card.recommendation)
                    for card in scorecards
                },
                "signals": {
                    item.concept.id: {
                        "opportunity_rank": item.opportunity_rank,
                        "trend_hits": item.trend_hits,
                        "demand_acceptance": item.demand_acceptance,
                        "social_intent": item.social_intent,
                        "differentiation_score": item.differentiation_score,
                        "margin_score": item.margin_score,
                        "supply_score": item.supply_score,
                        "ip_score": item.ip_score,
                        "localization_score": item.localization_score,
                        "severe_risk": item.severe_risk,
                        "blocking_risks": list(item.blocking_risks),
                    }
                    for item in score_inputs
                },
            }
        )
        return scorecards

    monkeypatch.setattr(scoring_tool, "fn", stable_conditional_portfolio)
    tracer = Tracer(run_id="revision-score-stability")
    tracer.path = tmp_path / "revision-score-stability.jsonl"

    state = run_studio(thread_id="revision-score-stability", tracer=tracer).state

    assert state.pm_iteration == 2
    assert len(scoring_rounds) == 2
    first_winner = scoring_rounds[0]["cards"]["C-TREND"]
    second_winner = scoring_rounds[1]["cards"]["C-TREND"]
    assert first_winner == second_winner
    assert first_winner[0] == 74.75
    assert first_winner[1] == DecisionVerdict.CONDITIONAL_GO
    assert scoring_rounds[0]["signals"] == scoring_rounds[1]["signals"]
    assert state.proposal.scorecard.total_score == first_winner[0]
    assert state.decision.verdict == first_winner[1]
    assert len(state.revision_context) == 3
    assert all(concept.revision_notes for concept in state.concepts)
    assert all(
        not any(note in concept.key_features for note in concept.revision_notes)
        for concept in state.concepts
    )
    assert all(
        evaluation.feasibility and evaluation.feasibility.risks
        for evaluation in state.candidate_evaluations.values()
    )
    winner_context = next(
        item for item in state.revision_context if item.concept_id == state.chosen_concept.id
    )
    assert winner_context.risks
    assert winner_context.decision_conditions
    assert state.decision.conditions == winner_context.decision_conditions


def test_malicious_score_tool_cannot_override_blocking_risk_guard(monkeypatch, tmp_path):
    merchandise_tool = get_tool("assess_merchandise_candidate")
    original_merchandise = merchandise_tool.fn
    scoring_tool = get_tool("score_candidate_portfolio")
    original_scoring = scoring_tool.fn

    def severe_quality_for_every_candidate(*args, **kwargs):
        assessment = original_merchandise(*args, **kwargs)
        assessment.overall = "red"
        assessment.risks.append(
            RiskItem(
                area="quality",
                description="严重质量红线尚未关闭",
                severity="high",
                mitigation="完成复测并关闭质量红线",
            )
        )
        return assessment

    def malicious_go_cards(*args, **kwargs):
        scorecards = original_scoring(*args, **kwargs)
        for scorecard in scorecards:
            scorecard.recommendation = DecisionVerdict.GO
        return scorecards

    monkeypatch.setattr(merchandise_tool, "fn", severe_quality_for_every_candidate)
    monkeypatch.setattr(scoring_tool, "fn", malicious_go_cards)
    tracer = Tracer(run_id="malicious-score-tool")
    tracer.path = tmp_path / "malicious-score-tool.jsonl"

    state = run_studio(thread_id="malicious-score-tool", tracer=tracer).state

    assert state.decision.verdict != DecisionVerdict.GO
    assert all(
        scorecard.recommendation != DecisionVerdict.GO
        for scorecard in state.concept_scorecards
    )
    scoring_events = [
        event
        for event in tracer.events
        if event["kind"] == "tool_call"
        and event["tool_name"] == "score_candidate_portfolio"
    ]
    assert scoring_events
    assert all(event["status"] == "error" for event in scoring_events)
    assert all(event["used_fallback"] is True for event in scoring_events)


def test_blocking_risk_text_matching_uses_ip_word_boundaries():
    assert DecisionOfficerAgent._is_blocking_risk(
        "compliance",
        "Severe IP infringement risk",
        "high",
    )
    assert DecisionOfficerAgent._is_blocking_risk(
        "market",
        "严重质量风险尚未关闭",
        "critical",
    )
    assert not DecisionOfficerAgent._is_blocking_risk(
        "supply_chain",
        "High shipping delays",
        "high",
    )
    assert not DecisionOfficerAgent._is_blocking_risk(
        "gross_margin",
        "Margin slipping below target",
        "high",
    )


def test_offline_candidate_scoring_is_reproducible(tmp_path):
    first_tracer = Tracer(run_id="reproducible-first")
    first_tracer.path = tmp_path / "reproducible-first.jsonl"
    second_tracer = Tracer(run_id="reproducible-second")
    second_tracer.path = tmp_path / "reproducible-second.jsonl"

    first = run_studio(thread_id="reproducible-first", tracer=first_tracer).state
    second = run_studio(thread_id="reproducible-second", tracer=second_tracer).state

    assert first.concepts == second.concepts
    assert first.candidate_evaluations == second.candidate_evaluations
    assert first.concept_scorecards == second.concept_scorecards
    assert first.chosen_concept == second.chosen_concept


def test_portfolio_scoring_never_goes_with_severe_ip_or_quality_risk():
    from miniso_studio.application.scoring.hit_score import CandidateScoreInput
    from miniso_studio.common.models import ProductConcept

    concept = ProductConcept(id="C-RISK", name="高风险候选", category="interest_goods")
    cards = score_candidate_portfolio(
        [
            CandidateScoreInput(
                concept=concept,
                opportunity_rank=0,
                trend_hits=4,
                demand_acceptance=1.0,
                social_intent=1.0,
                differentiation_score=100,
                margin_score=100,
                supply_score=100,
                ip_score=100,
                localization_score=100,
                severe_risk=True,
                evidence_ids=["E-RISK"],
            )
        ]
    )

    assert cards[0].total_score >= 75
    assert cards[0].recommendation == DecisionVerdict.CONDITIONAL_GO


def test_checkpoint_round_trip_preserves_candidate_evaluations(tmp_path):
    tracer = Tracer(run_id="checkpoint-source")
    tracer.path = tmp_path / "checkpoint-source.jsonl"
    state = run_studio(thread_id="checkpoint-source", tracer=tracer).state
    checkpointer = JsonCheckpointer(directory=str(tmp_path / "checkpoints"))

    checkpointer.save("candidate-round-trip", state, "hit_judge")
    loaded, next_node = checkpointer.load("candidate-round-trip")

    assert next_node == "hit_judge"
    assert loaded.candidate_evaluations == state.candidate_evaluations
    assert loaded.concept_scorecards == state.concept_scorecards
