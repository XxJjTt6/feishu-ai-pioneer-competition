"""Trend2SKU 命令行入口。"""
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path
from typing import List

from miniso_studio.application.reporting import render_full_report, render_opening_report
from miniso_studio.application.runner import (
    DEFAULT_BRIEF,
    MissingTargetEvidenceError,
    resume_studio,
    run_studio,
)
from miniso_studio.common.config import settings
from miniso_studio.common.logging import log
from miniso_studio.infrastructure.data.loader import EvidenceIdConflictError


def _next_report_path(directory: Path, legacy_name: str, migrated_stem: str) -> Path:
    legacy = directory / legacy_name
    if not legacy.exists():
        return legacy
    version = 1
    while True:
        candidate = directory / f"{migrated_stem}_v{version}.md"
        if not candidate.exists():
            return candidate
        version += 1


def _write_reports(art) -> List[Path]:
    """写入新报告；任何已有文件都不做原地覆盖。"""
    out_dir = Path(settings().project_root) / "docs" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    full_path = _next_report_path(out_dir, "运行报告.md", "运行报告_名创优品")
    opening_path = _next_report_path(
        out_dir,
        "开题报告_自动生成.md",
        "开题报告_名创优品",
    )
    full_path.write_text(render_full_report(art), encoding="utf-8")
    opening_path.write_text(render_opening_report(art), encoding="utf-8")
    paths = [full_path, opening_path]
    log.bind(node="cli").info("新报告已写入：" + "、".join(str(path) for path in paths))
    return paths


def _print_summary(art) -> None:
    state = art.state
    print("\n" + "=" * 64)
    print("Trend2SKU 爆款产品决策 Agent · 运行摘要")
    print("=" * 64)
    if state.voc_report:
        print(
            f"目标样本：{state.voc_report.review_count}　优先机会："
            + "、".join(item.aspect for item in state.voc_report.opportunities[:3])
            + "（离线演示）"
        )
    for rank, card in enumerate(
        sorted(state.concept_scorecards, key=lambda item: (-item.total_score, item.concept_id)),
        1,
    ):
        concept = next(item for item in state.concepts if item.id == card.concept_id)
        print(
            f"候选 {rank}：{concept.name}　{card.total_score:.2f}　{card.recommendation.value}"
        )
    if state.decision and state.chosen_concept:
        print(
            f"榜首：{state.chosen_concept.name}　决策：{state.decision.verdict.value}　"
            f"预测 NPS：{state.decision.nps_prediction:.1f}（离线演示）"
        )
    if art.rubric:
        print(
            f"审计分：{art.rubric.overall}（引用命中={art.rubric.citation_hit_rate}, "
            f"机会覆盖={art.rubric.opportunity_coverage}）"
        )
    print("=" * 64 + "\n")


def main() -> int:
    cfg = settings()
    parser = argparse.ArgumentParser(description="Trend2SKU 爆款产品决策 Agent")
    commands = parser.add_subparsers(dest="cmd", required=True)
    run_parser = commands.add_parser("run", help="运行完整决策工作流")
    run_parser.add_argument("--brief", default=cfg.default_brief or DEFAULT_BRIEF)
    run_parser.add_argument("--category", choices=["interest_goods"], default=cfg.category)
    run_parser.add_argument(
        "--hitl",
        action="store_true",
        default=None,
        help="在决策复核点等待 approve；省略时服从 MINISO_HITL",
    )
    run_parser.add_argument("--thread", default=f"cli-{uuid.uuid4().hex}")
    resume_parser = commands.add_parser("resume", help="批准并恢复 HITL checkpoint")
    resume_parser.add_argument("--thread", required=True)
    args = parser.parse_args()

    try:
        if args.cmd == "run":
            artifacts = run_studio(
                category=args.category,
                brief=args.brief,
                hitl=args.hitl,
                thread_id=args.thread,
            )
            if artifacts.awaiting_human:
                print(
                    "[HITL] 决策与风险已生成，当前等待 approve。运行："
                    f"python -m miniso_studio.starter.cli resume --thread {args.thread}"
                )
                return 0
            _print_summary(artifacts)
            _write_reports(artifacts)
            return 0

        if args.cmd == "resume":
            artifacts = resume_studio(thread_id=args.thread)
            if artifacts.awaiting_human:
                print(
                    "[HITL] 新一轮决策仍需 approve。再次运行："
                    f"python -m miniso_studio.starter.cli resume --thread {args.thread}"
                )
                return 0
            _print_summary(artifacts)
            _write_reports(artifacts)
            return 0
    except (MissingTargetEvidenceError, EvidenceIdConflictError) as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
