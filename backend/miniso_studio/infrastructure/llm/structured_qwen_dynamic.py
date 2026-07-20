"""Qwen JSON 模式客户端，用于动态决策链的结构化产物。"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Optional


_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class StructuredQwenClientError(RuntimeError):
    """不携带请求正文、响应正文、请求头或密钥的远程错误。"""

    def __init__(
        self,
        category: str,
        *,
        request_id: str = "unavailable",
        status: Optional[int] = None,
    ) -> None:
        self.category = category
        self.request_id = request_id
        self.status = status
        status_part = f" status={status}" if status is not None else ""
        super().__init__(
            f"Qwen structured {category}{status_part} request_id={request_id}"
        )

@dataclass(frozen=True)
class StructuredQwenResult:
    payload: dict[str, Any]
    model: str
    provider: str
    tokens_in: int
    tokens_out: int
    latency_ms: float
    request_id: str


def _request_id(response: object) -> str:
    try:
        headers = response.headers
        raw = headers.get("x-request-id") or headers.get("X-Request-Id")
    except Exception:  # noqa: BLE001 - 远程对象不可信
        return "unavailable"
    if not isinstance(raw, str):
        return "unavailable"
    value = raw.strip()
    return value if _REQUEST_ID_PATTERN.fullmatch(value) else "unavailable"


def _token_count(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


class StructuredQwenClient:
    """只接受 JSON 对象响应的 OpenAI Chat Completions 客户端。"""

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.strip().rstrip("/")
        self.model = model.strip()

    def complete_json(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int = 6000,
        temperature: float = 0.45,
    ) -> StructuredQwenResult:
        import requests

        if "json" not in f"{system}\n{prompt}".lower():
            prompt = f"{prompt}\n\n必须只返回一个 JSON 对象。"
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "enable_thinking": False,
            "max_tokens": max(64, int(max_tokens)),
            "temperature": max(0.0, min(1.0, float(temperature))),
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        started = time.perf_counter()
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=body,
                timeout=90,
            )
        except requests.Timeout:
            raise StructuredQwenClientError("transport_timeout") from None
        except requests.RequestException:
            raise StructuredQwenClientError("transport_error") from None
        except Exception:  # noqa: BLE001 - 测试替身和网络栈同样需要脱敏
            raise StructuredQwenClientError("transport_error") from None

        request_id = _request_id(response)
        try:
            status = int(response.status_code)
        except (TypeError, ValueError, OverflowError):
            raise StructuredQwenClientError(
                "invalid_http_status",
                request_id=request_id,
            ) from None
        if not 200 <= status < 300:
            raise StructuredQwenClientError(
                "http_error",
                request_id=request_id,
                status=status,
            )

        try:
            envelope = response.json()
            content = envelope["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise TypeError("empty content")
            payload = json.loads(content)
            if not isinstance(payload, dict):
                raise TypeError("JSON response must be an object")
        except json.JSONDecodeError:
            raise StructuredQwenClientError(
                "json_decode_error",
                request_id=request_id,
            ) from None
        except (KeyError, IndexError, TypeError, AttributeError):
            raise StructuredQwenClientError(
                "response_schema_error",
                request_id=request_id,
            ) from None

        usage = envelope.get("usage", {})
        if not isinstance(usage, dict):
            usage = {}
        return StructuredQwenResult(
            payload=payload,
            model=self.model,
            provider="qwen",
            tokens_in=_token_count(usage.get("prompt_tokens")),
            tokens_out=_token_count(usage.get("completion_tokens")),
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            request_id=request_id,
        )
