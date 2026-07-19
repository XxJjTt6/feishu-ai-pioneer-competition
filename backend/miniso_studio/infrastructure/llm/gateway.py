"""统一 LLM 网关（Infrastructure 层）。

设计要点：
- 确定性核心由各分析模块产出结构化数值；网关主要负责"叙述/归纳/角色扮演/批判"。
- 三种 provider：
    offline —— 不联网，确定性：narrate() 直接返回传入文本，complete() 做抽取式摘要。
    minimax —— 调用 MiniMax M3 增强。
    qwen —— 调用 Qwen3.7 Plus 增强。
- 任何远程失败都自动降级到 offline，不中断流程（错误即信息）。
"""
from __future__ import annotations

import re
import time
from typing import Optional

from miniso_studio.common.config import Settings
from miniso_studio.common.logging import log
from miniso_studio.common.models import LLMResponse
from miniso_studio.infrastructure.observability.trace import Tracer


class LLMGateway:
    def __init__(
        self,
        provider: str = "offline",
        minimax_client=None,
        default_model: str = "offline-deterministic",
        configured_provider: Optional[str] = None,
        tracer: Optional[Tracer] = None,
        remote_client=None,
    ):
        self.configured_provider = configured_provider or provider
        self.effective_provider = provider
        self._remote = remote_client if remote_client is not None else minimax_client
        self.default_model = default_model
        self.tracer = tracer

    @property
    def provider(self) -> str:
        """兼容旧调用方；始终返回实际执行 provider。"""
        return self.effective_provider

    @staticmethod
    def provider_status(settings: Settings) -> tuple[str, str]:
        configured = settings.llm_provider
        if configured == "minimax" and bool(settings.minimax_api_key.strip()):
            effective = "minimax"
        elif configured == "qwen" and bool(settings.qwen_api_key.strip()):
            effective = "qwen"
        else:
            effective = "offline"
        return configured, effective

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        tracer: Optional[Tracer] = None,
    ) -> "LLMGateway":
        configured, effective = cls.provider_status(settings)
        if effective != "offline":
            if effective == "qwen":
                from miniso_studio.infrastructure.llm.qwen import QwenClient

                client = QwenClient(
                    api_key=settings.qwen_api_key,
                    base_url=settings.qwen_base_url,
                    model=settings.qwen_model,
                    enable_thinking=settings.qwen_enable_thinking,
                )
                default_model = settings.qwen_model
            else:
                from miniso_studio.infrastructure.llm.minimax import MiniMaxClient

                client = MiniMaxClient(
                    api_key=settings.minimax_api_key,
                    base_url=settings.minimax_base_url,
                    model=settings.minimax_model,
                )
                default_model = settings.minimax_model
            log.bind(node="llm").info(
                f"LLM configured={configured} effective={effective} model={default_model}"
            )
            return cls(
                provider=effective,
                remote_client=client,
                default_model=default_model,
                configured_provider=configured,
                tracer=tracer,
            )
        gateway = cls(
            provider="offline",
            configured_provider=configured,
            tracer=tracer,
        )
        if configured in {"minimax", "qwen"}:
            gateway._emit_provider_fallback(
                operation="configuration",
                reason="missing_api_key",
            )
        log.bind(node="llm").info(
            f"LLM configured={configured} effective=offline（确定性模式，无网络）"
        )
        return gateway

    @property
    def has_remote(self) -> bool:
        return (
            self.effective_provider in {"minimax", "qwen"}
            and self._remote is not None
        )

    def _emit_provider_fallback(self, *, operation: str, reason: str) -> None:
        if self.tracer is not None:
            self.tracer.emit(
                "llm",
                "provider_fallback",
                configured_provider=self.configured_provider,
                effective_provider=self.effective_provider,
                operation=operation,
                reason=reason,
            )

    def _fallback_to_offline(
        self,
        *,
        operation: str,
        reason: str = "remote_error",
        exc: Optional[Exception] = None,
    ) -> None:
        if self.effective_provider == "offline":
            return
        failed_provider = self.effective_provider
        self.effective_provider = "offline"
        self._remote = None
        self.default_model = "offline-deterministic"
        error_category = (
            str(getattr(exc, "category", "") or type(exc).__name__)
            if exc is not None
            else ""
        )
        request_id = str(getattr(exc, "request_id", "unavailable") or "unavailable")
        status = getattr(exc, "status", None)
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", error_category) is None:
            error_category = type(exc).__name__ if exc is not None else ""
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", request_id) is None:
            request_id = "unavailable"
        if not isinstance(status, int) or isinstance(status, bool) or not 100 <= status <= 599:
            status = None
        detail = f" error_category={error_category}" if error_category else ""
        log.bind(node="llm").warning(
            f"{failed_provider} {operation} 返回不可用结果，"
            f"effective provider 降级 offline{detail}"
        )
        self._emit_provider_fallback(operation=operation, reason=reason)
        if self.tracer is not None and exc is not None:
            self.tracer.emit_internal(
                "llm",
                "provider_fallback_detail",
                operation=operation,
                error_category=error_category,
                request_id=request_id,
                status=status,
            )

    # ── 主接口 ──────────────────────────────────────────────
    def complete(
        self,
        system: str,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.6,
        task: str = "",
    ) -> LLMResponse:
        if self.has_remote:
            try:
                response = self._remote.chat(
                    system,
                    prompt,
                    model,
                    max_tokens,
                    temperature,
                )
                if response.text.strip():
                    return response
                self._fallback_to_offline(
                    operation="complete",
                    reason="empty_response",
                )
            except Exception as exc:  # noqa: BLE001 - 远程失败降级
                self._fallback_to_offline(operation="complete", exc=exc)
        return self._offline_complete(system, prompt, task)

    def narrate(self, default_text: str, instruction: str, context: str = "", task: str = "") -> str:
        """把确定性结果包装成更顺畅的叙述。

        offline：直接返回 default_text（已是可读的确定性文本）。
        远程 provider：在 default_text 基础上做润色/扩写，但不得引入新事实。
        """
        if not self.has_remote:
            return default_text
        system = (
            "你是 MINISO 兴趣消费商品决策团队的资深产品负责人。只能基于给定事实进行润色与归纳，"
            "禁止引入任何未提供的新数据或新事实。输出简洁、专业、中文。"
        )
        prompt = (
            f"任务：{instruction}\n\n"
            f"事实与上下文（不得超出）：\n{context}\n\n"
            f"待润色的草稿：\n{default_text}\n\n请输出润色后的版本："
        )
        try:
            resp = self._remote.chat(
                system,
                prompt,
                max_tokens=900,
                temperature=0.5,
            )
            text = resp.text.strip()
            if text:
                return text
            self._fallback_to_offline(
                operation="narrate",
                reason="empty_response",
            )
            return default_text
        except Exception as exc:  # noqa: BLE001
            self._fallback_to_offline(operation="narrate", exc=exc)
            return default_text

    # ── offline 确定性实现 ────────────────────────────────────
    @staticmethod
    def _offline_complete(system: str, prompt: str, task: str) -> LLMResponse:
        start = time.time()
        # 抽取式摘要：取 prompt 的前若干句作为"回答"，保证零网络可运行且可复现。
        text = prompt.strip()
        sentences = [s.strip() for s in text.replace("\n", " ").split("。") if s.strip()]
        summary = "。".join(sentences[:3])
        out = summary or text[:400]
        return LLMResponse(
            text=out,
            model="offline-deterministic",
            provider="offline",
            tokens_in=len(prompt),
            tokens_out=len(out),
            latency_ms=round((time.time() - start) * 1000, 2),
        )
