"""名创优品离线工作流迁移验收测试。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from miniso_studio.application.runner import run_studio


def _winner_by_score_then_concept_id(scorecards):
    """最高分优先；同分时按概念 ID 升序，保证决策可复现。"""
    assert scorecards
    return min(scorecards, key=lambda card: (-card.total_score, card.concept_id))


def test_miniso_pipeline_runs_offline():
    art = run_studio(thread_id="migration-test")

    assert art.state.category == "interest_goods"
    assert art.state.target_brand == "MINISO"
    assert len(art.state.concepts) >= 3
    assert len(art.state.concept_scorecards) == len(art.state.concepts)
    assert art.state.proposal is not None
    assert art.state.proposal.scorecard.total_score >= 0
    assert art.state.chosen_concept is not None
    assert art.state.decision is not None

    winner = _winner_by_score_then_concept_id(art.state.concept_scorecards)
    assert art.state.proposal.scorecard.concept_id == winner.concept_id
    assert art.state.proposal.concept.id == winner.concept_id
    assert art.state.chosen_concept.id == winner.concept_id
    assert art.state.decision.verdict == art.state.proposal.scorecard.recommendation


def test_runtime_output_has_no_anker_business_copy():
    art = run_studio(thread_id="copy-test")
    payload = art.model_dump_json()

    for stale in ("安克", "soundcore", "TWS", "Thus™", "JML", "BEES", "AMI"):
        assert stale not in payload


def test_comparison_labels_synthetic_evidence_and_offline_metrics():
    narrative = run_studio(thread_id="comparison-provenance").comparison.narrative

    assert "合成演示证据" in narrative
    assert "演示样本中的机会项" in narrative
    assert "离线模拟指标" in narrative
    assert "真实证据" not in narrative
    assert "真实高机会痛点" not in narrative
