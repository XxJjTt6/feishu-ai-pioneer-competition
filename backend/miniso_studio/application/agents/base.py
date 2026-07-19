"""Agent 基类（Application 层）。

每个 Agent 通过注入的 LLMGateway / RagService 访问外部能力，禁止自行 import provider。
产出的论断都应带 evidence_ids。
"""
from __future__ import annotations

from typing import Any, Callable, List, Optional

from pydantic import BaseModel

from miniso_studio.application.graph.state import PipelineState
from miniso_studio.common.tools import ToolType, get_tool
from miniso_studio.infrastructure.llm.gateway import LLMGateway
from miniso_studio.infrastructure.observability.trace import Tracer


class Agent:
    name: str = "agent"
    role: str = ""
    _SENSITIVE_ARGUMENT_MARKERS = ("secret", "token", "password", "api_key", "credential")

    def __init__(
        self,
        gateway: LLMGateway,
        rag=None,
        tracer: Optional[Tracer] = None,
    ):
        self.gw = gateway
        self.rag = rag
        self.tracer = tracer

    def run(self, state: PipelineState) -> PipelineState:  # pragma: no cover - 抽象
        raise NotImplementedError

    def call_read_tool(
        self,
        tool_name: str,
        *,
        fallback: Any,
        validator: Optional[Callable[[Any], bool]] = None,
        **kwargs: Any,
    ) -> Any:
        """通过注册器调用只读工具，并只把结构摘要写入 trace。"""
        status = "success"
        used_fallback = False
        output: Any
        try:
            registered = get_tool(tool_name)
            if registered.tool_type != ToolType.READ:
                raise PermissionError(f"工具 {tool_name} 不是只读工具")
            output = registered(**kwargs)
            if isinstance(output, str) and output.startswith("[TOOL_ERROR]"):
                raise RuntimeError("registered tool returned an error")
            if validator is not None and not validator(output):
                raise ValueError("registered tool returned an invalid result")
        except Exception:  # noqa: BLE001 - 工具错误必须确定性降级
            status = "error"
            used_fallback = True
            output = fallback() if callable(fallback) else fallback

        if self.tracer:
            self.tracer.emit(
                self.name,
                "tool_call",
                tool_name=tool_name,
                status=status,
                used_fallback=used_fallback,
                input_summary=self._safe_input_summary(kwargs),
                output_summary=self._safe_shape(output),
            )
        return output

    @classmethod
    def _safe_input_summary(cls, values: dict[str, Any]) -> dict:
        summary = {}
        redacted_index = 0
        for key, value in values.items():
            if any(marker in key.lower() for marker in cls._SENSITIVE_ARGUMENT_MARKERS):
                redacted_index += 1
                summary[f"redacted_arg_{redacted_index}"] = {
                    **cls._safe_shape(value),
                    "redacted": True,
                }
            else:
                summary[key] = cls._safe_shape(value)
        return summary

    @classmethod
    def _safe_shape(cls, value: Any) -> dict:
        """仅描述类型与规模，不序列化 brief、评论、访谈或模型全文。"""
        if isinstance(value, BaseModel):
            return {"type": value.__class__.__name__}
        if isinstance(value, dict):
            return {"type": "dict", "count": len(value)}
        if isinstance(value, (list, tuple, set)):
            item_types = sorted({item.__class__.__name__ for item in value})[:6]
            return {"type": value.__class__.__name__, "count": len(value), "item_types": item_types}
        if isinstance(value, str):
            return {"type": "str", "chars": len(value)}
        if value is None:
            return {"type": "none"}
        return {"type": value.__class__.__name__}

    @staticmethod
    def dedup(items: List[str]) -> List[str]:
        seen, out = set(), []
        for x in items:
            if x and x not in seen:
                seen.add(x)
                out.append(x)
        return out
