"""Trend2SKU 端到端 Runner，供 CLI 与 FastAPI 共用。"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from miniso_studio.application.baseline.experience_driven import run_experience_driven
from miniso_studio.application.evaluation.comparison import build_comparison
from miniso_studio.application.evaluation.rubric import evaluate
from miniso_studio.application.graph.checkpoint import (
    JsonCheckpointer,
    MissingCheckpointError,
    PendingCheckpointError,
    ThreadReservation,
)
from miniso_studio.application.graph.pipeline import build_studio_graph
from miniso_studio.application.graph.state import PipelineState
from miniso_studio.common.config import DEFAULT_BRIEF, settings
from miniso_studio.common.logging import log
from miniso_studio.common.models import ComparisonReport, RubricScore
from miniso_studio.infrastructure.data.loader import (
    TARGET_BRAND,
    index_evidence_by_source_id,
    load_evidence,
    split_by_brand,
)
from miniso_studio.infrastructure.llm.gateway import LLMGateway
from miniso_studio.infrastructure.observability.trace import Tracer
from miniso_studio.infrastructure.rag.retrieval import build_rag


class CheckpointNotFoundError(RuntimeError):
    """请求恢复一个不存在或已经消费的 checkpoint。"""


class MissingTargetEvidenceError(RuntimeError):
    """当前数据集中没有目标品牌研究样本。"""


class RunArtifacts(BaseModel):
    run_id: str
    awaiting_human: bool = False
    thread_id: str = "default"
    provider: str = "offline"
    configured_provider: str = "offline"
    effective_provider: str = "offline"
    state: PipelineState
    rubric: Optional[RubricScore] = None
    comparison: Optional[ComparisonReport] = None
    elapsed_seconds: float = 0.0
    trace_events: List[Dict[str, Any]] = Field(default_factory=list)


def _validate_input(category: str, brief: str, thread_id: str) -> None:
    if category != "interest_goods":
        raise ValueError("本版本仅支持 interest_goods 品类")
    if not 1 <= len(brief.strip()) <= 500:
        raise ValueError("brief 长度必须为 1-500 个字符")
    JsonCheckpointer.validate_thread_id(thread_id)


def _artifacts(
    state: PipelineState,
    tracer: Tracer,
    thread_id: str,
    gateway: LLMGateway,
    elapsed: float,
    *,
    awaiting_human: bool,
    rubric: Optional[RubricScore] = None,
    comparison: Optional[ComparisonReport] = None,
) -> RunArtifacts:
    return RunArtifacts(
        run_id=tracer.run_id,
        awaiting_human=awaiting_human,
        thread_id=thread_id,
        provider=gateway.effective_provider,
        configured_provider=gateway.configured_provider,
        effective_provider=gateway.effective_provider,
        state=state,
        rubric=rubric,
        comparison=comparison,
        elapsed_seconds=round(elapsed, 3),
        trace_events=list(tracer.events),
    )


def _persist_pause_elapsed(
    checkpointer: JsonCheckpointer,
    thread_id: str,
    state: PipelineState,
    elapsed: float,
) -> None:
    state.run_elapsed_seconds = round(state.run_elapsed_seconds + elapsed, 3)
    snapshot = checkpointer.load(thread_id)
    if snapshot is not None:
        _, next_node = snapshot
        checkpointer.save(thread_id, state, next_node)


def _finalize(
    state: PipelineState,
    elapsed: float,
    brief: str,
    gateway: LLMGateway,
    tracer: Tracer,
    thread_id: str,
) -> RunArtifacts:
    total_elapsed = round(state.run_elapsed_seconds + elapsed, 3)
    state.run_elapsed_seconds = total_elapsed
    rubric = evaluate(state)
    baseline = run_experience_driven(state.category, brief, gateway)
    comparison = build_comparison(state, baseline, brief)
    comparison.arm_b.elapsed_seconds = total_elapsed
    log.bind(node="runner").info(
        f"完成：决策={state.decision.verdict.value if state.decision else 'n/a'} "
        f"NPS={state.nps.score if state.nps else 'n/a'} 总分={rubric.overall}"
    )
    return _artifacts(
        state,
        tracer,
        thread_id,
        gateway,
        total_elapsed,
        awaiting_human=False,
        rubric=rubric,
        comparison=comparison,
    )


def run_studio(
    category: str = "interest_goods",
    brief: str = DEFAULT_BRIEF,
    hitl: Optional[bool] = None,
    thread_id: str = "default",
    tracer: Optional[Tracer] = None,
    run_id: Optional[str] = None,
    reservation: Optional[ThreadReservation] = None,
) -> RunArtifacts:
    """启动一次独立运行；调用方可显式注入 tracer 或 run_id。"""
    _validate_input(category, brief, thread_id)
    checkpointer = JsonCheckpointer()
    owns_reservation = reservation is None
    active_reservation = reservation or checkpointer.reserve_for_run(thread_id)
    try:
        checkpointer.validate_reservation(active_reservation, thread_id, "run")
        if checkpointer.checkpoint_exists(thread_id):
            raise PendingCheckpointError(f"thread_id={thread_id} 仍有 checkpoint")
    except Exception:
        if owns_reservation:
            active_reservation.release()
        raise
    try:
        cfg = settings()
        hitl_enabled = cfg.hitl if hitl is None else hitl
        if tracer is not None and run_id is not None and tracer.run_id != run_id:
            raise ValueError("tracer.run_id 与显式 run_id 不一致")
        tracer = tracer or Tracer(run_id=run_id)
        gateway = LLMGateway.from_settings(cfg, tracer=tracer)

        evidences = load_evidence(category)
        index_evidence_by_source_id(evidences, context=f"{category} 评论集合")
        split = split_by_brand(evidences)
        if not split["target"]:
            raise MissingTargetEvidenceError(
                f"未找到 {TARGET_BRAND} 目标样本；请补充明确标注品牌的目标数据后重试"
            )
        state = PipelineState(
            category=category,
            target_brand=TARGET_BRAND,
            brief=brief,
            target_evidences=split["target"],
            competitor_evidences=split["competitors"],
            trace_run_id=tracer.run_id,
            hitl_enabled=hitl_enabled,
        )

        rag = build_rag(evidences)
        graph = build_studio_graph(gateway, rag, tracer, hitl=hitl_enabled)
        started = time.perf_counter()
        state = graph.run(state, checkpointer=checkpointer, thread_id=thread_id)
        elapsed = time.perf_counter() - started
        if state.awaiting_human:
            _persist_pause_elapsed(checkpointer, thread_id, state, elapsed)
            log.bind(node="runner").warning("流程在决策复核点暂停，等待 approve。")
            return _artifacts(
                state,
                tracer,
                thread_id,
                gateway,
                state.run_elapsed_seconds,
                awaiting_human=True,
            )
        return _finalize(state, elapsed, brief, gateway, tracer, thread_id)
    finally:
        if owns_reservation:
            active_reservation.release()


def resume_studio(
    thread_id: str = "default",
    tracer: Optional[Tracer] = None,
    reservation: Optional[ThreadReservation] = None,
) -> RunArtifacts:
    """批准当前决策 checkpoint，并保持同一 run_id 继续执行。"""
    JsonCheckpointer.validate_thread_id(thread_id)
    checkpointer = JsonCheckpointer()
    owns_reservation = reservation is None
    if reservation is None:
        try:
            active_reservation = checkpointer.reserve_for_resume(thread_id)
        except MissingCheckpointError as exc:
            raise CheckpointNotFoundError(
                f"无 checkpoint 可恢复：thread_id={thread_id}"
            ) from exc
    else:
        active_reservation = reservation
    try:
        checkpointer.validate_reservation(active_reservation, thread_id, "resume")
    except Exception:
        if owns_reservation:
            active_reservation.release()
        raise
    try:
        snapshot = checkpointer.load_snapshot(thread_id)
        if snapshot is None:
            raise CheckpointNotFoundError(f"无 checkpoint 可恢复：thread_id={thread_id}")

        state = snapshot.state
        saved_run_id = state.trace_run_id
        if tracer is not None and saved_run_id and tracer.run_id != saved_run_id:
            raise ValueError("恢复 tracer 必须沿用 checkpoint 的 run_id")
        tracer = tracer or Tracer(run_id=saved_run_id or None, load_existing=True)
        state.trace_run_id = tracer.run_id
        tracer.emit(
            "decision_review",
            "human_approval",
            checkpoint_id=snapshot.checkpoint_id,
            iteration=state.pm_iteration,
            action="approve",
            approved_at=datetime.now(timezone.utc).isoformat(),
        )
        if state.decision is not None:
            state.decision.reviewer = "human"

        cfg = settings()
        gateway = LLMGateway.from_settings(cfg, tracer=tracer)
        rag = build_rag(state.all_evidences())
        graph = build_studio_graph(gateway, rag, tracer, hitl=state.hitl_enabled)
        started = time.perf_counter()
        state = graph.run(
            state,
            checkpointer=checkpointer,
            thread_id=thread_id,
            resume=True,
            checkpoint_snapshot=(state, snapshot.next_node),
        )
        elapsed = time.perf_counter() - started
        if state.awaiting_human:
            _persist_pause_elapsed(checkpointer, thread_id, state, elapsed)
            return _artifacts(
                state,
                tracer,
                thread_id,
                gateway,
                state.run_elapsed_seconds,
                awaiting_human=True,
            )

        artifacts = _finalize(state, elapsed, state.brief, gateway, tracer, thread_id)
        checkpointer.delete_if_checkpoint_id(
            active_reservation,
            snapshot.checkpoint_id,
        )
        return artifacts
    finally:
        if owns_reservation:
            active_reservation.release()
