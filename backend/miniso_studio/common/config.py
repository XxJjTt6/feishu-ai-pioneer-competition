"""Trend2SKU 集中配置。从环境变量或 ``.env`` 读取，全程只读。"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CATEGORY = "interest_goods"
DEFAULT_TARGET_BRAND = "MINISO"
DEFAULT_BRIEF = (
    "为 MINISO 生成可全球本地化的兴趣消费候选 SKU 组合，"
    "从趋势感知、产品创意到上市前验证形成可审计决策。"
)


def _load_dotenv() -> None:
    """尽力加载 .env（缺少 python-dotenv 也不报错）。"""
    try:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env")
    except Exception:  # noqa: BLE001 - 配置加载失败不应中断程序
        pass


class Settings(BaseModel):
    """运行配置。"""

    # LLM
    llm_provider: Literal["offline", "minimax", "qwen"] = Field(
        default="offline",
        description="offline | minimax | qwen",
    )
    minimax_api_key: str = Field(default="")
    minimax_base_url: str = Field(default="https://api.minimax.io/v1")
    minimax_model: str = Field(default="MiniMax-M3")
    qwen_api_key: str = Field(default="")
    qwen_base_url: str = Field(
        default="https://coding.dashscope.aliyuncs.com/v1"
    )
    qwen_model: str = Field(default="qwen3.7-plus")
    qwen_enable_thinking: bool = Field(default=False)

    # 媒体
    enable_media: bool = Field(default=False)

    # 运行
    max_retrieval_iters: int = Field(default=3)
    hitl: bool = Field(default=False, description="决策闸是否人工确认")
    trace_dir: str = Field(default="runs")
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8767, ge=1, le=65535)
    category: str = Field(default=DEFAULT_CATEGORY)
    target_brand: str = Field(default=DEFAULT_TARGET_BRAND)
    default_brief: str = Field(default=DEFAULT_BRIEF)

    # 路径
    project_root: str = Field(default=str(PROJECT_ROOT))
    data_dir: str = Field(default=str(PROJECT_ROOT / "data"))

    @property
    def trace_path(self) -> Path:
        configured = Path(self.trace_dir).expanduser()
        p = configured if configured.is_absolute() else Path(self.project_root) / configured
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache(maxsize=1)
def settings() -> Settings:
    _load_dotenv()

    def _bool(name: str, default: bool) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        normalized = raw.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return default

    return Settings(
        llm_provider=os.getenv("MINISO_LLM_PROVIDER", "offline").strip().lower(),
        minimax_api_key=os.getenv("MINIMAX_API_KEY", "").strip(),
        minimax_base_url=os.getenv("MINIMAX_BASE_URL", "https://api.minimax.io/v1").strip(),
        minimax_model=os.getenv("MINIMAX_MODEL", "MiniMax-M3").strip(),
        qwen_api_key=os.getenv("QWEN_API_KEY", "").strip(),
        qwen_base_url=os.getenv(
            "QWEN_BASE_URL",
            "https://coding.dashscope.aliyuncs.com/v1",
        ).strip(),
        qwen_model=os.getenv("QWEN_MODEL", "qwen3.7-plus").strip(),
        qwen_enable_thinking=_bool("QWEN_ENABLE_THINKING", False),
        enable_media=_bool("MINISO_ENABLE_MEDIA", False),
        max_retrieval_iters=int(os.getenv("MINISO_MAX_RETRIEVAL_ITERS", "3")),
        hitl=_bool("MINISO_HITL", False),
        trace_dir=os.getenv("MINISO_TRACE_DIR", "runs").strip(),
        host=os.getenv("MINISO_HOST", "127.0.0.1").strip(),
        port=int(os.getenv("MINISO_PORT", "8767")),
        category=DEFAULT_CATEGORY,
        target_brand=DEFAULT_TARGET_BRAND,
        default_brief=DEFAULT_BRIEF,
    )
