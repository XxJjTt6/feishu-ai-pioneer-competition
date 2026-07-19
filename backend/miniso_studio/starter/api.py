"""Trend2SKU FastAPI 入口：运行、流式审计、HITL 恢复与报告。"""
from __future__ import annotations

import json
import queue
import threading
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Annotated, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from miniso_studio.application.reporting import (
    PRODUCT_NAME,
    SCHEMA_VERSION,
    build_data_provenance,
    render_full_report,
    render_opening_report,
    to_view,
)
from miniso_studio.application.graph.checkpoint import (
    CheckpointGenerationConflictError,
    JsonCheckpointer,
    MissingCheckpointError,
    PendingCheckpointError,
    ReservationConflictError,
)
from miniso_studio.application.runner import (
    DEFAULT_BRIEF,
    CheckpointNotFoundError,
    MissingTargetEvidenceError,
    RunArtifacts,
    resume_studio,
    run_studio,
)
from miniso_studio.common.config import settings
from miniso_studio.common.decision_input import (
    DecisionInput,
    IPStrategy,
    Objective,
    PriceBand,
    ProductCategory,
    TargetMarket,
    TargetSegment,
)
from miniso_studio.common.logging import log
from miniso_studio.infrastructure.data.loader import EvidenceIdConflictError
from miniso_studio.infrastructure.llm.gateway import LLMGateway
from miniso_studio.infrastructure.observability.trace import Tracer, public_trace_event

THREAD_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
RUN_CACHE_CAPACITY = 20
SSE_QUEUE_CAPACITY = 256

app = FastAPI(title="Trend2SKU 爆款产品决策 Agent", version=SCHEMA_VERSION)

FRONTEND_DIR = Path(settings().project_root) / "frontend"
ASSETS_DIR = Path(settings().project_root) / "assets"


class _RunStore:
    """进程内有界运行仓储；锁只保护快速读写，不包工作流执行。"""

    def __init__(self, capacity: int = RUN_CACHE_CAPACITY):
        self.capacity = capacity
        self._runs: "OrderedDict[str, RunArtifacts]" = OrderedDict()
        self._thread_to_run: Dict[str, str] = {}
        self._active_threads: set[str] = set()
        self._resuming_threads: set[str] = set()
        self._lock = threading.RLock()

    def clear(self) -> None:
        with self._lock:
            self._runs.clear()
            self._thread_to_run.clear()
            self._active_threads.clear()
            self._resuming_threads.clear()

    def save(self, artifacts: RunArtifacts) -> None:
        with self._lock:
            self._runs[artifacts.run_id] = artifacts
            self._runs.move_to_end(artifacts.run_id)
            self._thread_to_run[artifacts.thread_id] = artifacts.run_id
            while len(self._runs) > self.capacity:
                expired_run_id, expired = self._runs.popitem(last=False)
                if self._thread_to_run.get(expired.thread_id) == expired_run_id:
                    self._thread_to_run.pop(expired.thread_id, None)

    def get(self, run_id: str) -> Optional[RunArtifacts]:
        with self._lock:
            return self._runs.get(run_id)

    def get_by_thread(self, thread_id: str) -> Optional[RunArtifacts]:
        with self._lock:
            run_id = self._thread_to_run.get(thread_id)
            return self._runs.get(run_id) if run_id else None

    def begin_run(self, thread_id: str) -> bool:
        with self._lock:
            if thread_id in self._active_threads or thread_id in self._resuming_threads:
                return False
            self._active_threads.add(thread_id)
            return True

    def end_run(self, thread_id: str) -> None:
        with self._lock:
            self._active_threads.discard(thread_id)

    def begin_resume(self, thread_id: str) -> bool:
        with self._lock:
            if thread_id in self._active_threads or thread_id in self._resuming_threads:
                return False
            self._resuming_threads.add(thread_id)
            return True

    def end_resume(self, thread_id: str) -> None:
        with self._lock:
            self._resuming_threads.discard(thread_id)


_RUNS = _RunStore()
_SSE_WORKERS = threading.BoundedSemaphore(value=4)


class _StreamTicketStore:
    """把敏感决策正文留在 POST body，SSE URL 只携带一次性随机票据。"""

    def __init__(self, capacity: int = 64):
        self.capacity = capacity
        self._tickets: "OrderedDict[str, tuple[DecisionInput, str, Optional[bool]]]" = OrderedDict()
        self._lock = threading.RLock()

    def issue(
        self,
        decision_input: DecisionInput,
        thread_id: str,
        hitl: Optional[bool],
    ) -> str:
        token = uuid.uuid4().hex
        with self._lock:
            self._tickets[token] = (decision_input, thread_id, hitl)
            while len(self._tickets) > self.capacity:
                self._tickets.popitem(last=False)
        return token

    def consume(self, token: str) -> tuple[DecisionInput, str, Optional[bool]] | None:
        with self._lock:
            return self._tickets.pop(token, None)

    def clear(self) -> None:
        with self._lock:
            self._tickets.clear()


_STREAM_TICKETS = _StreamTicketStore()


def _reset_runtime_state() -> None:
    """测试与本地重载使用的显式状态重置入口。"""
    _RUNS.clear()
    _STREAM_TICKETS.clear()


def _new_thread_id() -> str:
    return f"thread-{uuid.uuid4()}"


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brief: Optional[str] = Field(default=None, min_length=1, max_length=500)
    category: Literal["interest_goods"] = "interest_goods"
    product_category: ProductCategory = "fragrance_accessory"
    custom_category: str = Field(default="", max_length=40)
    target_segment: TargetSegment = "young_professional"
    target_market: TargetMarket = "global"
    price_band: PriceBand = "mid"
    ip_strategy: IPStrategy = "original"
    objectives: List[Objective] = Field(default_factory=lambda: ["emotional", "social"])
    constraints: str = Field(default="", max_length=300)
    hitl: Optional[bool] = None
    thread_id: Optional[str] = Field(default=None, pattern=THREAD_ID_PATTERN)

    @field_validator("brief")
    @classmethod
    def validate_brief(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("brief 不能只包含空白字符")
        return value

    @model_validator(mode="after")
    def validate_decision_fields(self) -> "RunRequest":
        self.to_decision_input()
        return self

    def to_decision_input(self) -> DecisionInput:
        return DecisionInput(
            brief=self.brief if self.brief is not None else DEFAULT_BRIEF,
            product_category=self.product_category,
            custom_category=self.custom_category,
            target_segment=self.target_segment,
            target_market=self.target_market,
            price_band=self.price_band,
            ip_strategy=self.ip_strategy,
            objectives=self.objectives,
            constraints=self.constraints,
        )


class ResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thread_id: str = Field(pattern=THREAD_ID_PATTERN)
    action: Literal["approve"]


@app.get("/api/health")
def health() -> dict:
    configured_provider, effective_provider = LLMGateway.provider_status(settings())
    return {
        "status": "ok",
        "product": PRODUCT_NAME,
        "schema_version": SCHEMA_VERSION,
        "provider": effective_provider,
        "configured_provider": configured_provider,
        "effective_provider": effective_provider,
    }


@app.post("/api/run")
def run(req: Optional[RunRequest] = None) -> dict:
    request = req or RunRequest()
    thread_id = request.thread_id or _new_thread_id()
    checkpointer = JsonCheckpointer()
    try:
        reservation = checkpointer.reserve_for_run(thread_id)
    except (PendingCheckpointError, ReservationConflictError) as exc:
        raise HTTPException(
            status_code=409,
            detail="该 thread 正在运行或等待人工批准",
        ) from exc
    if not _RUNS.begin_run(thread_id):
        reservation.release()
        raise HTTPException(status_code=409, detail="该 thread 正在运行或等待人工批准")
    try:
        try:
            artifacts = run_studio(
                category=request.category,
                decision_input=request.to_decision_input(),
                hitl=request.hitl,
                thread_id=thread_id,
                reservation=reservation,
            )
            view = to_view(artifacts)
        except (MissingTargetEvidenceError, EvidenceIdConflictError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _RUNS.save(artifacts)
        return view
    finally:
        _RUNS.end_run(thread_id)
        reservation.release()


@app.post("/api/resume")
def resume(req: ResumeRequest) -> dict:
    _ = req.action  # 当前版本唯一合法动作是 approve，校验由模型完成。
    thread_id = req.thread_id
    checkpointer = JsonCheckpointer()
    try:
        reservation = checkpointer.reserve_for_resume(thread_id)
    except ReservationConflictError as exc:
        raise HTTPException(status_code=409, detail="该 thread 正在恢复") from exc
    except MissingCheckpointError as exc:
        existing = _RUNS.get_by_thread(thread_id)
        if existing is not None and not existing.awaiting_human:
            raise HTTPException(status_code=409, detail="该 checkpoint 已完成并被消费") from exc
        raise HTTPException(status_code=404, detail="未找到可恢复的 checkpoint") from exc
    if not _RUNS.begin_resume(thread_id):
        reservation.release()
        raise HTTPException(status_code=409, detail="该 thread 正在恢复")
    try:
        try:
            artifacts = resume_studio(
                thread_id=thread_id,
                reservation=reservation,
            )
            view = to_view(artifacts)
        except CheckpointNotFoundError as exc:
            raise HTTPException(status_code=404, detail="未找到可恢复的 checkpoint") from exc
        except CheckpointGenerationConflictError as exc:
            raise HTTPException(status_code=409, detail="checkpoint 世代已变化") from exc
        except EvidenceIdConflictError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _RUNS.save(artifacts)
        return view
    finally:
        _RUNS.end_resume(thread_id)
        reservation.release()


def _sse_payload(item: dict) -> str:
    return f"data: {json.dumps(item, ensure_ascii=False, default=str)}\n\n"


@app.post("/api/stream/ticket")
def create_stream_ticket(req: RunRequest) -> dict:
    thread_id = req.thread_id or _new_thread_id()
    token = _STREAM_TICKETS.issue(
        req.to_decision_input(),
        thread_id,
        req.hitl,
    )
    return {
        "thread_id": thread_id,
        "stream_url": f"api/stream?ticket={token}",
    }


@app.get("/api/stream")
def stream(
    ticket: Annotated[Optional[str], Query(pattern=r"^[a-f0-9]{32}$")] = None,
    brief: Annotated[str, Query(min_length=1, max_length=500)] = DEFAULT_BRIEF,
    product_category: ProductCategory = "fragrance_accessory",
    custom_category: Annotated[str, Query(max_length=40)] = "",
    target_segment: TargetSegment = "young_professional",
    target_market: TargetMarket = "global",
    price_band: PriceBand = "mid",
    ip_strategy: IPStrategy = "original",
    objectives: Annotated[Optional[List[Objective]], Query()] = None,
    constraints: Annotated[str, Query(max_length=300)] = "",
    hitl: Optional[bool] = None,
    thread_id: Annotated[Optional[str], Query(pattern=THREAD_ID_PATTERN)] = None,
) -> StreamingResponse:
    """EventSource 兼容 SSE：trace 后输出一个 result/error，再输出 done。"""
    selected_thread_id = thread_id or _new_thread_id()
    selected_hitl = hitl
    if ticket is not None:
        staged = _STREAM_TICKETS.consume(ticket)
        if staged is None:
            raise HTTPException(status_code=404, detail="SSE 票据不存在或已消费")
        decision_input, selected_thread_id, selected_hitl = staged
    else:
        if not brief.strip():
            raise HTTPException(status_code=422, detail="brief 不能只包含空白字符")
        try:
            decision_input = DecisionInput(
                brief=brief,
                product_category=product_category,
                custom_category=custom_category,
                target_segment=target_segment,
                target_market=target_market,
                price_band=price_band,
                ip_strategy=ip_strategy,
                objectives=objectives if objectives is not None else ["emotional", "social"],
                constraints=constraints,
            )
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="决策输入不合法") from exc
    if not _SSE_WORKERS.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="SSE 执行槽已满，请稍后重试")

    slot_lock = threading.Lock()
    slot_released = False

    def release_slot() -> None:
        nonlocal slot_released
        with slot_lock:
            if slot_released:
                return
            slot_released = True
            _SSE_WORKERS.release()

    reservation = None
    run_registered = False
    try:
        tracer = Tracer()
        run_id = tracer.run_id
        events: "queue.Queue[dict]" = queue.Queue(maxsize=SSE_QUEUE_CAPACITY)
        stopped = threading.Event()

        checkpointer = JsonCheckpointer()
        try:
            reservation = checkpointer.reserve_for_run(selected_thread_id)
        except (PendingCheckpointError, ReservationConflictError) as exc:
            raise HTTPException(
                status_code=409,
                detail="该 thread 正在运行或等待人工批准",
            ) from exc
        if not _RUNS.begin_run(selected_thread_id):
            raise HTTPException(
                status_code=409,
                detail="该 thread 正在运行或等待人工批准",
            )
        run_registered = True
    except Exception:
        try:
            if run_registered:
                _RUNS.end_run(selected_thread_id)
        finally:
            try:
                if reservation is not None:
                    reservation.release()
            finally:
                release_slot()
        raise

    cleanup_lock = threading.Lock()
    cleaned = False

    def cleanup() -> None:
        nonlocal cleaned
        with cleanup_lock:
            if cleaned:
                return
            cleaned = True
        try:
            _RUNS.end_run(selected_thread_id)
        finally:
            try:
                reservation.release()
            finally:
                release_slot()

    def enqueue(item: dict, *, terminal: bool = False) -> None:
        envelope = {"run_id": run_id, "thread_id": selected_thread_id, **item}
        if stopped.is_set() and not terminal:
            return
        try:
            events.put(envelope, timeout=0.05 if terminal else 0)
            return
        except queue.Full:
            if not terminal:
                return
        while True:
            try:
                events.get_nowait()
            except queue.Empty:
                pass
            try:
                events.put_nowait(envelope)
                return
            except queue.Full:
                continue

    tracer.subscribe(
        lambda event: enqueue({"type": "trace", "event": public_trace_event(event)})
    )

    def worker() -> None:
        try:
            try:
                artifacts = run_studio(
                    decision_input=decision_input,
                    hitl=selected_hitl,
                    thread_id=selected_thread_id,
                    tracer=tracer,
                    reservation=reservation,
                )
                view = to_view(artifacts)
                _RUNS.save(artifacts)
                enqueue({"type": "result", "view": view}, terminal=True)
            except Exception as exc:  # noqa: BLE001 - 外部固定文案，完整异常只入内部日志/trace
                log.bind(node="api_stream").exception(f"SSE 运行失败：{exc}")
                tracer.emit_internal("api_stream", "error", error=str(exc))
                enqueue({"type": "error", "message": "运行失败，请稍后重试"}, terminal=True)
            finally:
                enqueue({"type": "done"}, terminal=True)
        finally:
            cleanup()

    worker_thread = threading.Thread(
        target=worker,
        name=f"trend2sku-sse-{run_id}",
        daemon=True,
    )
    try:
        worker_thread.start()
    except Exception:
        cleanup()
        raise

    def generate():
        try:
            while True:
                try:
                    item = events.get(timeout=0.5)
                except queue.Empty:
                    item = {
                        "type": "heartbeat",
                        "run_id": run_id,
                        "thread_id": selected_thread_id,
                    }
                yield _sse_payload(item)
                if item.get("type") == "done":
                    break
        finally:
            stopped.set()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/report")
def report(
    run_id: str = Query(..., min_length=1),
    kind: Literal["full", "opening"] = Query(default="full"),
) -> dict:
    artifacts = _RUNS.get(run_id)
    if artifacts is None:
        raise HTTPException(status_code=404, detail="未找到该 run_id 的运行结果")
    try:
        markdown = (
            render_opening_report(artifacts)
            if kind == "opening"
            else render_full_report(artifacts)
        )
    except EvidenceIdConflictError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "run_id": artifacts.run_id,
        "kind": kind,
        "markdown": markdown,
        "data_provenance": build_data_provenance(artifacts),
    }


if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(FRONTEND_DIR / "index.html"))


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
