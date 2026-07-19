"""爆款评分卡的确定性量表验收测试。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from miniso_studio.application.scoring.hit_score import build_scorecard, verdict_for
from miniso_studio.common.models import DecisionVerdict, ProductConcept


EXPECTED_DIMENSIONS = [
    "trend_fit",
    "demand_strength",
    "differentiation",
    "social_virality",
    "margin_potential",
    "supply_feasibility",
    "ip_compliance",
    "localization_fit",
]

EXPECTED_WEIGHTS = [0.20, 0.20, 0.15, 0.15, 0.10, 0.10, 0.05, 0.05]


def test_scorecard_contains_all_weighted_dimensions():
    concept = ProductConcept(id="C1", name="测试 SKU", category="interest_goods")

    scorecard = build_scorecard(
        concept,
        opportunity_rank=0,
        trend_hits=2,
        evidence_ids=["E1", "E2"],
    )

    assert [item.key for item in scorecard.dimensions] == EXPECTED_DIMENSIONS
    assert [item.weight for item in scorecard.dimensions] == pytest.approx(EXPECTED_WEIGHTS)
    assert sum(item.weight for item in scorecard.dimensions) == pytest.approx(1.0)
    assert all(0 <= item.score <= 100 for item in scorecard.dimensions)
    assert all(item.rationale for item in scorecard.dimensions)
    assert scorecard.evidence_ids == ["E1", "E2"]
    assert all(item.evidence_ids == ["E1", "E2"] for item in scorecard.dimensions)
    assert scorecard.total_score == pytest.approx(
        round(sum(item.score * item.weight for item in scorecard.dimensions), 2),
    )


def test_scorecard_inputs_have_monotonic_effect_on_total_score():
    concept = ProductConcept(id="C1", name="测试 SKU", category="interest_goods")

    highest_rank = build_scorecard(concept, opportunity_rank=0, trend_hits=0, evidence_ids=[])
    lower_rank = build_scorecard(concept, opportunity_rank=3, trend_hits=0, evidence_ids=[])
    fewer_trends = build_scorecard(concept, opportunity_rank=0, trend_hits=0, evidence_ids=[])
    more_trends = build_scorecard(concept, opportunity_rank=0, trend_hits=3, evidence_ids=[])

    assert highest_rank.total_score > lower_rank.total_score
    assert more_trends.total_score > fewer_trends.total_score


@pytest.mark.parametrize(
    ("total", "severe_risk", "expected"),
    [
        (75, False, DecisionVerdict.GO),
        (74.99, False, DecisionVerdict.CONDITIONAL_GO),
        (60, False, DecisionVerdict.CONDITIONAL_GO),
        (59.99, False, DecisionVerdict.NO_GO),
        (90, True, DecisionVerdict.CONDITIONAL_GO),
    ],
)
def test_verdict_thresholds_and_severe_risk_guard(total, severe_risk, expected):
    assert verdict_for(total, severe_risk=severe_risk) == expected
