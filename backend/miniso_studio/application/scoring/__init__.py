"""候选 SKU 的确定性爆款评分。"""
from __future__ import annotations

from miniso_studio.application.scoring.hit_score import (
    CandidateScoreInput,
    WEIGHTS,
    build_portfolio_scorecards,
    build_scorecard,
    score_candidate_portfolio,
    verdict_for,
)

__all__ = [
    "CandidateScoreInput",
    "WEIGHTS",
    "build_portfolio_scorecards",
    "build_scorecard",
    "score_candidate_portfolio",
    "verdict_for",
]
