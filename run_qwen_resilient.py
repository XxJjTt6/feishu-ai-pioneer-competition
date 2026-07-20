#!/usr/bin/env python3
"""启动支持公网断线恢复的 Qwen 动态决策工作台。"""
from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))


def main() -> None:
    import uvicorn

    from miniso_studio.application import runner as runner_module
    from miniso_studio.application.graph.pipeline_llm_dynamic import (
        build_llm_studio_graph_dynamic,
    )
    from miniso_studio.common.config import settings

    runner_module.build_studio_graph = build_llm_studio_graph_dynamic

    from miniso_studio.starter.live_app_resilient import app

    cfg = settings()
    uvicorn.run(
        app,
        host=cfg.host,
        port=cfg.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
