#!/usr/bin/env python3
"""启动不允许固定内容回退的 Qwen 严格动态决策工作台。"""
from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))


def main() -> None:
    import uvicorn

    from miniso_studio.application import runner as runner_module
    from miniso_studio.application.graph.pipeline_qwen_strict import (
        build_qwen_strict_graph,
    )
    from miniso_studio.application.reporting_qwen_strict import to_view_qwen_strict
    from miniso_studio.common.config import settings
    from miniso_studio.starter import api as base_api

    runner_module.build_studio_graph = build_qwen_strict_graph
    base_api.to_view = to_view_qwen_strict

    from miniso_studio.starter.live_app_qwen_strict import app

    cfg = settings()
    uvicorn.run(
        app,
        host=cfg.host,
        port=cfg.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
