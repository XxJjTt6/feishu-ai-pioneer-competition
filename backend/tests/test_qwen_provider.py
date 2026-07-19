"""Qwen OpenAI 兼容客户端与通用 LLM 网关测试。"""
from __future__ import annotations

from pathlib import Path
import sys

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from miniso_studio.common.config import Settings, settings
from miniso_studio.common.models import LLMResponse
from miniso_studio.infrastructure.llm.gateway import LLMGateway
from miniso_studio.infrastructure.llm.qwen import QwenClient


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: object | None = None,
        request_id: str = "req-qwen-123",
        body: str = "",
    ):
        self.status_code = status_code
        self._payload = payload
        self.headers = {"x-request-id": request_id}
        self.text = body

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def test_qwen_client_uses_openai_contract_and_parses_metadata(monkeypatch):
    captured = {}
    fake_response = FakeResponse(
        payload={
            "choices": [{"message": {"content": "模型回答"}}],
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 7,
                "total_tokens": 18,
            },
        }
    )

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return fake_response

    monkeypatch.setattr(requests, "post", fake_post)
    client = QwenClient(
        api_key="test-qwen-key",
        base_url="https://coding.dashscope.aliyuncs.com/v1/",
        model="qwen3.7-plus",
        enable_thinking=False,
    )

    response = client.chat(
        "系统提示",
        "用户提示",
        max_tokens=321,
        temperature=0.25,
    )

    assert captured == {
        "url": "https://coding.dashscope.aliyuncs.com/v1/chat/completions",
        "headers": {
            "Authorization": "Bearer test-qwen-key",
            "Content-Type": "application/json",
        },
        "json": {
            "model": "qwen3.7-plus",
            "messages": [
                {"role": "system", "content": "系统提示"},
                {"role": "user", "content": "用户提示"},
            ],
            "max_tokens": 321,
            "temperature": 0.25,
            "enable_thinking": False,
        },
        "timeout": 90,
    }
    assert isinstance(response, LLMResponse)
    assert response.text == "模型回答"
    assert response.provider == "qwen"
    assert response.model == "qwen3.7-plus"
    assert response.tokens_in == 11
    assert response.tokens_out == 7
    assert client.last_total_tokens == 18
    assert client.last_request_id == "req-qwen-123"


def test_qwen_non_streaming_client_always_disables_thinking(monkeypatch):
    captured = {}

    def fake_post(_url, **kwargs):
        captured.update(kwargs)
        return FakeResponse(
            payload={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {},
            }
        )

    monkeypatch.setattr(requests, "post", fake_post)
    QwenClient(
        api_key="test-key",
        base_url="https://coding.example/v1",
        model="qwen3.7-plus",
        enable_thinking=True,
    ).chat("system", "prompt")

    assert captured["json"]["enable_thinking"] is False


def test_qwen_client_omits_empty_system_message(monkeypatch):
    captured = {}

    def fake_post(_url, **kwargs):
        captured.update(kwargs)
        return FakeResponse(
            payload={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {},
            }
        )

    monkeypatch.setattr(requests, "post", fake_post)

    QwenClient("test-key", "https://example.test/v1", "qwen3.7-plus").chat(
        "",
        "prompt",
    )

    assert captured["json"]["messages"] == [
        {"role": "user", "content": "prompt"}
    ]


def test_qwen_http_error_is_safely_redacted(monkeypatch):
    key = "test-private-key"
    prompt = "test-private-user-prompt"
    body = f"upstream echoed {key} and {prompt}"
    monkeypatch.setattr(
        requests,
        "post",
        lambda *_args, **_kwargs: FakeResponse(
            status_code=401,
            payload={},
            request_id="req-safe-401",
            body=body,
        ),
    )

    with pytest.raises(RuntimeError) as exc_info:
        QwenClient(key, "https://example.test/v1", "qwen3.7-plus").chat(
            "system",
            prompt,
        )

    error = str(exc_info.value)
    assert error == "Qwen http_error status=401 request_id=req-safe-401"
    assert key not in error
    assert prompt not in error
    assert body not in error


def test_qwen_transport_and_parse_errors_do_not_leak_exception_or_unsafe_id(
    monkeypatch,
):
    secret = "test-private-value"

    def raise_timeout(*_args, **_kwargs):
        raise requests.Timeout(f"timeout echoed {secret}")

    monkeypatch.setattr(requests, "post", raise_timeout)
    client = QwenClient(secret, "https://example.test/v1", "qwen3.7-plus")
    with pytest.raises(RuntimeError) as timeout_info:
        client.chat("system", "private prompt")
    assert str(timeout_info.value) == (
        "Qwen transport_timeout request_id=unavailable"
    )
    assert secret not in str(timeout_info.value)

    monkeypatch.setattr(
        requests,
        "post",
        lambda *_args, **_kwargs: FakeResponse(
            payload=ValueError(f"invalid json {secret}"),
            request_id=f"unsafe id contains {secret}",
        ),
    )
    with pytest.raises(RuntimeError) as parse_info:
        client.chat("system", "private prompt")
    assert str(parse_info.value) == (
        "Qwen response_decode_error request_id=unavailable"
    )
    assert secret not in str(parse_info.value)


def test_qwen_response_schema_error_is_safely_redacted(monkeypatch):
    monkeypatch.setattr(
        requests,
        "post",
        lambda *_args, **_kwargs: FakeResponse(
            payload={"unexpected": "private response body"},
            request_id="req-schema-9",
        ),
    )

    with pytest.raises(RuntimeError) as exc_info:
        QwenClient("test-key", "https://example.test/v1", "qwen3.7-plus").chat(
            "system",
            "private prompt",
        )

    assert str(exc_info.value) == (
        "Qwen response_schema_error request_id=req-schema-9"
    )
    assert "private" not in str(exc_info.value)


def test_qwen_settings_defaults_and_environment_loading(monkeypatch):
    defaults = Settings()
    assert defaults.llm_provider == "offline"
    assert defaults.qwen_api_key == ""
    assert defaults.qwen_base_url == "https://coding.dashscope.aliyuncs.com/v1"
    assert defaults.qwen_model == "qwen3.7-plus"
    assert defaults.qwen_enable_thinking is False

    monkeypatch.setenv("MINISO_LLM_PROVIDER", "qwen")
    monkeypatch.setenv("QWEN_API_KEY", "test-config-key")
    monkeypatch.setenv("QWEN_BASE_URL", "https://qwen.example.test/v1/")
    monkeypatch.setenv("QWEN_MODEL", "qwen-test-model")
    monkeypatch.setenv("QWEN_ENABLE_THINKING", "YES")
    settings.cache_clear()

    configured = settings()
    assert configured.llm_provider == "qwen"
    assert configured.qwen_api_key == "test-config-key"
    assert configured.qwen_base_url == "https://qwen.example.test/v1/"
    assert configured.qwen_model == "qwen-test-model"
    assert configured.qwen_enable_thinking is True

    monkeypatch.setenv("QWEN_ENABLE_THINKING", "not-a-boolean")
    settings.cache_clear()
    assert settings().qwen_enable_thinking is False
    settings.cache_clear()


def test_qwen_missing_key_reports_configured_but_effective_offline():
    cfg = Settings(llm_provider="qwen", qwen_api_key="")
    blank_cfg = Settings(llm_provider="qwen", qwen_api_key="  \t")

    assert LLMGateway.provider_status(cfg) == ("qwen", "offline")
    assert LLMGateway.provider_status(blank_cfg) == ("qwen", "offline")
    gateway = LLMGateway.from_settings(cfg)
    assert gateway.configured_provider == "qwen"
    assert gateway.effective_provider == "offline"
    assert gateway.default_model == "offline-deterministic"
    assert gateway.has_remote is False


def test_qwen_gateway_builds_remote_and_returns_success(monkeypatch):
    from miniso_studio.infrastructure.llm import qwen

    calls = []

    class SuccessfulQwenClient:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))

        def chat(self, *args, **kwargs):
            calls.append(("chat", args, kwargs))
            return LLMResponse(
                text="remote answer",
                model="qwen3.7-plus",
                provider="qwen",
            )

    monkeypatch.setattr(qwen, "QwenClient", SuccessfulQwenClient)
    cfg = Settings(
        llm_provider="qwen",
        qwen_api_key="test-key",
        qwen_enable_thinking=False,
    )

    gateway = LLMGateway.from_settings(cfg)
    response = gateway.complete("system", "prompt", temperature=0.3)

    assert calls[0] == (
        "init",
        {
            "api_key": "test-key",
            "base_url": "https://coding.dashscope.aliyuncs.com/v1",
            "model": "qwen3.7-plus",
            "enable_thinking": False,
        },
    )
    assert calls[1][0] == "chat"
    assert response.text == "remote answer"
    assert response.provider == "qwen"
    assert gateway.configured_provider == "qwen"
    assert gateway.effective_provider == "qwen"
    assert gateway.default_model == "qwen3.7-plus"
    assert gateway.has_remote is True


def test_first_qwen_failure_opens_circuit_and_stays_offline():
    class FailingRemote:
        def __init__(self):
            self.calls = 0

        def chat(self, *_args, **_kwargs):
            self.calls += 1
            raise RuntimeError("Qwen transport_error request_id=unavailable")

    remote = FailingRemote()
    gateway = LLMGateway(
        provider="qwen",
        remote_client=remote,
        configured_provider="qwen",
        default_model="qwen3.7-plus",
    )

    response = gateway.complete("system", "offline fallback text")
    narration = gateway.narrate("default narration", "polish")

    assert response.provider == "offline"
    assert narration == "default narration"
    assert remote.calls == 1
    assert gateway.effective_provider == "offline"
    assert gateway.default_model == "offline-deterministic"
    assert gateway.has_remote is False


def test_legacy_minimax_client_injection_remains_supported():
    class MiniMaxRemote:
        def chat(self, *_args, **_kwargs):
            return LLMResponse(text="legacy remote", provider="minimax")

    gateway = LLMGateway(
        provider="minimax",
        minimax_client=MiniMaxRemote(),
        configured_provider="minimax",
    )

    assert gateway.complete("system", "prompt").text == "legacy remote"
    assert gateway.effective_provider == "minimax"
    assert gateway.has_remote is True
