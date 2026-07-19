"""跨层共享的不可降级领域错误。"""
from __future__ import annotations


class FatalPipelineError(RuntimeError):
    """继续执行会破坏领域数据完整性的错误。"""
