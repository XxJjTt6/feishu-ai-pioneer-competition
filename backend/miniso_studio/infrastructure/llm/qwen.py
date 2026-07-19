"""Qwen3.7 Plus OpenAI 兼容客户端。

客户端只发起单次 chat completions 请求并返回仓库通用的
``LLMResponse``。任何失败都只暴露可审计的错误类别、HTTP 状态和
经过校验的 request ID，交由网关执行离线降级。
"""
from __future__ import annotations

import re
import time
from typing import List, Optional

from miniso_studio.common.models import LLMResponse

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class QwenClientError(RuntimeError):
    """Qwen 客户端的脱敏错误。"""

    def __init__(
        self,
        category: str,
        *,
        request_id: str,
        status: Optional[int] = None,
    ):
        self.category = category
        self.request_id = request_id
        self.status = status
        status_part = f" status={status}" if status is not None else ""
        super().__init__(
            f"Qwen {category}{status_part} request_id={request_id}"
        )


def _safe_request_id(response) -> str:
    try:
        headers = response.headers
        value = headers.get("x-request-id") or headers.get("X-Request-Id")
    except Exception:  # noqa: BLE001 - 不信任远程响应对象
        return "unavailable"
    if not isinstance(value, str):
        return "unavailable"
    request_id = value.strip()
    if not _REQUEST_ID_PATTERN.fullmatch(request_id):
        return "unavailable"
    return request_id


def _token_count(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


class QwenClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        enable_thinking: bool = False,
    ):
        self.api_key = api_key
        self.base_url = base_url.strip().rstrip("/")
        self.model = model
        self.enable_thinking = bool(enable_thinking)
        self.last_request_id = "unavailable"
        self.last_total_tokens = 0

    def chat(
        self,
        system: str,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.6,
    ) -> LLMResponse:
        import requests  # 局部导入：offline 模式无需加载网络依赖

        url = f"{self.base_url}/chat/completions"
        messages: List[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": model or self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            # Coding Plan 的非流式 OpenAI 兼容路径固定关闭思考模式。
            "enable_thinking": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        self.last_request_id = "unavailable"
        self.last_total_tokens = 0
        start = time.time()
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=90,
            )
        except requests.Timeout:
            raise QwenClientError(
                "transport_timeout",
                request_id="unavailable",
            ) from None
        except requests.RequestException:
            raise QwenClientError(
                "transport_error",
                request_id="unavailable",
            ) from None
        except Exception:  # noqa: BLE001 - 测试替身/底层适配器也需脱敏
            raise QwenClientError(
                "transport_error",
                request_id="unavailable",
            ) from None

        self.last_request_id = _safe_request_id(response)
        try:
            status_code = int(response.status_code)
        except (TypeError, ValueError, OverflowError):
            raise QwenClientError(
                "invalid_http_status",
                request_id=self.last_request_id,
            ) from None
        if not 200 <= status_code < 300:
            raise QwenClientError(
                "http_error",
                status=status_code,
                request_id=self.last_request_id,
            )

        try:
            data = response.json()
        except Exception:  # noqa: BLE001 - 不向异常传递响应正文
            raise QwenClientError(
                "response_decode_error",
                request_id=self.last_request_id,
            ) from None

        try:
            text = data["choices"][0]["message"]["content"]
            if text is None:
                text = ""
            if not isinstance(text, str):
                raise TypeError("content must be a string")
        except (KeyError, IndexError, TypeError):
            raise QwenClientError(
                "response_schema_error",
                request_id=self.last_request_id,
            ) from None

        usage = data.get("usage", {})
        if not isinstance(usage, dict):
            usage = {}
        tokens_in = _token_count(usage.get("prompt_tokens"))
        tokens_out = _token_count(usage.get("completion_tokens"))
        self.last_total_tokens = _token_count(usage.get("total_tokens"))

        return LLMResponse(
            text=text,
            model=payload["model"],
            provider="qwen",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=round((time.time() - start) * 1000, 1),
        )
