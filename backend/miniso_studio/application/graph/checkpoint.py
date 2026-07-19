"""原子 JSON checkpoint 与跨进程 thread reservation。"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Literal, Optional, Tuple

from miniso_studio.application.graph.state import PipelineState
from miniso_studio.common.config import settings

_THREAD_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_CHECKPOINT_LOCK = threading.RLock()
_ACTIVE_RESERVATIONS: dict[Path, int] = {}


class ReservationConflictError(RuntimeError):
    """同一 thread 已被另一个执行者占用。"""


class PendingCheckpointError(RuntimeError):
    """新运行试图覆盖仍在等待批准的 checkpoint。"""


class MissingCheckpointError(RuntimeError):
    """恢复时没有可消费的 checkpoint。"""


class CheckpointGenerationConflictError(RuntimeError):
    """准备消费的 checkpoint 已被另一个世代替换。"""


@dataclass(frozen=True)
class CheckpointSnapshot:
    checkpoint_id: str
    state: PipelineState
    next_node: str


@dataclass
class ThreadReservation:
    checkpointer: "JsonCheckpointer"
    thread_id: str
    operation: Literal["run", "resume"]
    token: str
    path: Path
    handle: IO[str]
    released: bool = False

    def release(self) -> None:
        self.checkpointer.release_reservation(self)

    def __enter__(self) -> "ThreadReservation":
        return self

    def __exit__(self, *_args: object) -> bool:
        self.release()
        return False


class JsonCheckpointer:
    def __init__(self, directory: Optional[str] = None):
        self.dir = Path(directory) if directory else (settings().trace_path / "checkpoints")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.reservation_dir = self.dir / ".reservations"
        self.reservation_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def validate_thread_id(thread_id: str) -> str:
        if _THREAD_ID_RE.fullmatch(thread_id) is None:
            raise ValueError("thread_id 只能包含字母、数字、下划线或连字符，长度 1-64")
        return thread_id

    def _path(self, thread_id: str) -> Path:
        self.validate_thread_id(thread_id)
        return self.dir / f"{thread_id}.json"

    def _reservation_path(self, thread_id: str) -> Path:
        self.validate_thread_id(thread_id)
        return (self.reservation_dir / f"{thread_id}.lock").resolve()

    def checkpoint_exists(self, thread_id: str) -> bool:
        path = self._path(thread_id)
        with _CHECKPOINT_LOCK:
            return path.exists()

    def acquire_reservation(
        self,
        thread_id: str,
        operation: Literal["run", "resume"],
    ) -> ThreadReservation:
        path = self._reservation_path(thread_id)
        handle = path.open("a+", encoding="utf-8")
        pid = os.getpid()
        with _CHECKPOINT_LOCK:
            active_pid = _ACTIVE_RESERVATIONS.get(path)
            if active_pid == pid:
                handle.close()
                raise ReservationConflictError(f"thread_id={thread_id} 已在当前进程执行")
            if active_pid is not None and active_pid != pid:
                _ACTIVE_RESERVATIONS.pop(path, None)
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                handle.close()
                raise ReservationConflictError(f"thread_id={thread_id} 已被其他进程占用") from exc
            except OSError:
                handle.close()
                raise
            _ACTIVE_RESERVATIONS[path] = pid
            token = f"reservation-{uuid.uuid4()}"
            try:
                handle.seek(0)
                handle.truncate()
                handle.write(
                    json.dumps(
                        {
                            "token": token,
                            "thread_id": thread_id,
                            "operation": operation,
                            "pid": pid,
                            "acquired_at": time.time(),
                        },
                        ensure_ascii=False,
                    )
                )
                handle.flush()
                os.fsync(handle.fileno())
            except Exception:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                handle.close()
                _ACTIVE_RESERVATIONS.pop(path, None)
                raise
        return ThreadReservation(
            checkpointer=self,
            thread_id=thread_id,
            operation=operation,
            token=token,
            path=path,
            handle=handle,
        )

    def reserve_for_run(self, thread_id: str) -> ThreadReservation:
        reservation = self.acquire_reservation(thread_id, "run")
        try:
            has_checkpoint = self.checkpoint_exists(thread_id)
        except Exception:
            reservation.release()
            raise
        if has_checkpoint:
            reservation.release()
            raise PendingCheckpointError(
                f"thread_id={thread_id} 仍有等待批准的 checkpoint"
            )
        return reservation

    def reserve_for_resume(self, thread_id: str) -> ThreadReservation:
        reservation = self.acquire_reservation(thread_id, "resume")
        try:
            has_checkpoint = self.checkpoint_exists(thread_id)
        except Exception:
            reservation.release()
            raise
        if not has_checkpoint:
            reservation.release()
            raise MissingCheckpointError(f"thread_id={thread_id} 没有 checkpoint")
        return reservation

    def validate_reservation(
        self,
        reservation: ThreadReservation,
        thread_id: str,
        operation: Literal["run", "resume"],
    ) -> None:
        if reservation.released:
            raise ReservationConflictError("reservation 已释放")
        if reservation.thread_id != thread_id or reservation.operation != operation:
            raise ReservationConflictError("reservation 与 thread 或操作不匹配")
        if reservation.path != self._reservation_path(thread_id):
            raise ReservationConflictError("reservation 不属于当前 checkpoint 目录")

    def release_reservation(self, reservation: ThreadReservation) -> None:
        with _CHECKPOINT_LOCK:
            if reservation.released:
                return
            try:
                fcntl.flock(reservation.handle.fileno(), fcntl.LOCK_UN)
            finally:
                reservation.handle.close()
                reservation.released = True
                if _ACTIVE_RESERVATIONS.get(reservation.path) == os.getpid():
                    _ACTIVE_RESERVATIONS.pop(reservation.path, None)

    @staticmethod
    def _checkpoint_id(payload: dict, raw: bytes) -> str:
        checkpoint_id = payload.get("checkpoint_id")
        if isinstance(checkpoint_id, str) and checkpoint_id:
            return checkpoint_id
        return f"legacy-{hashlib.sha256(raw).hexdigest()}"

    def save(self, thread_id: str, state: PipelineState, next_node: str) -> str:
        checkpoint_id = f"cp-{uuid.uuid4()}"
        payload = {
            "checkpoint_id": checkpoint_id,
            "next_node": next_node,
            "state": state.model_dump(mode="json"),
        }
        destination = self._path(thread_id)
        temporary = self.dir / f".{thread_id}.{uuid.uuid4().hex}.tmp"
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        with _CHECKPOINT_LOCK:
            try:
                with temporary.open("wb") as fp:
                    fp.write(encoded)
                    fp.flush()
                    os.fsync(fp.fileno())
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        return checkpoint_id

    def load_snapshot(self, thread_id: str) -> Optional[CheckpointSnapshot]:
        path = self._path(thread_id)
        with _CHECKPOINT_LOCK:
            if not path.exists():
                return None
            raw = path.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
        return CheckpointSnapshot(
            checkpoint_id=self._checkpoint_id(payload, raw),
            state=PipelineState.model_validate(payload["state"]),
            next_node=payload["next_node"],
        )

    def load(self, thread_id: str) -> Optional[Tuple[PipelineState, str]]:
        snapshot = self.load_snapshot(thread_id)
        if snapshot is None:
            return None
        return snapshot.state, snapshot.next_node

    def delete_if_checkpoint_id(
        self,
        reservation: ThreadReservation,
        expected_checkpoint_id: str,
    ) -> bool:
        self.validate_reservation(
            reservation,
            reservation.thread_id,
            "resume",
        )
        path = self._path(reservation.thread_id)
        with _CHECKPOINT_LOCK:
            if not path.exists():
                raise CheckpointGenerationConflictError("checkpoint 已不存在")
            raw = path.read_bytes()
            payload = json.loads(raw.decode("utf-8"))
            current_id = self._checkpoint_id(payload, raw)
            if current_id != expected_checkpoint_id:
                raise CheckpointGenerationConflictError(
                    "checkpoint 世代已变化，拒绝删除"
                )
            path.unlink()
            return True

    def delete(self, thread_id: str) -> bool:
        path = self._path(thread_id)
        with _CHECKPOINT_LOCK:
            if not path.exists():
                return False
            path.unlink()
            return True
