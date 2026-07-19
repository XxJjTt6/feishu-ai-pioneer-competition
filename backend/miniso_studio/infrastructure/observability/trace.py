"""轻量 trace 观测（Infrastructure 层）。

把每个节点的执行写成 JSONL（runs/<run_id>.jsonl）+ 内存事件流，
供评测统计与前端实时可视化（对标 LangSmith/Langfuse 的最小可用形态）。
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from miniso_studio.common.config import settings
from miniso_studio.common.logging import log

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def public_trace_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """生成可下发版本，异常详情只保留在内部 JSONL。"""
    sensitive_keys = {"error", "exception", "traceback"}
    return {
        key: "内部错误已记录" if key.lower() in sensitive_keys else value
        for key, value in event.items()
    }


class Tracer:
    def __init__(self, run_id: Optional[str] = None, *, load_existing: bool = False):
        selected_run_id = f"run-{uuid.uuid4()}" if run_id is None else run_id
        if _RUN_ID_RE.fullmatch(selected_run_id) is None:
            raise ValueError("run_id 只能包含字母、数字、下划线或连字符，长度 1-128")
        self.run_id = selected_run_id
        self.events: List[Dict[str, Any]] = []
        self.path: Path = settings().trace_path / f"{self.run_id}.jsonl"
        self._subscribers: List[Callable[[Dict[str, Any]], None]] = []
        self._lock = threading.RLock()
        if load_existing and self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict):
                    self.events.append(event)

    def subscribe(self, fn: Callable[[Dict[str, Any]], None]) -> None:
        with self._lock:
            self._subscribers.append(fn)

    def emit(self, node: str, kind: str, **data: Any) -> None:
        self._emit(node, kind, notify=True, **data)

    def emit_internal(self, node: str, kind: str, **data: Any) -> None:
        """记录内部诊断但不推送给外部订阅者。"""
        self._emit(node, kind, notify=False, **data)

    def _emit(self, node: str, kind: str, *, notify: bool, **data: Any) -> None:
        event = {
            "ts": round(time.time(), 3),
            "run_id": self.run_id,
            "node": node,
            "kind": kind,
            **data,
        }
        with self._lock:
            self.events.append(event)
            subscribers = list(self._subscribers) if notify else []
        try:
            with self.path.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        except OSError as exc:
            log.bind(node="trace").warning(f"trace 写入失败：{exc}")
        for fn in subscribers:
            try:
                fn(event)
            except Exception as exc:  # noqa: BLE001 - 订阅者异常不影响主流程
                log.bind(node="trace").warning(f"trace 订阅者异常：{exc}")

    def node_span(self, node: str):
        return _Span(self, node)


class _Span:
    def __init__(self, tracer: Tracer, node: str):
        self.tracer = tracer
        self.node = node
        self._start = 0.0

    def __enter__(self) -> "_Span":
        self._start = time.time()
        self.tracer.emit(self.node, "start")
        log.bind(node=self.node).info("开始")
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        elapsed = round((time.time() - self._start) * 1000, 1)
        if exc_type is not None:
            self.tracer.emit(self.node, "error", error=str(exc), elapsed_ms=elapsed)
            log.bind(node=self.node).error(f"失败：{exc}")
            return False
        self.tracer.emit(self.node, "end", elapsed_ms=elapsed)
        log.bind(node=self.node).info(f"完成 ({elapsed}ms)")
        return False

    def info(self, **data: Any) -> None:
        self.tracer.emit(self.node, "info", **data)
