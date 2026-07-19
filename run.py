#!/usr/bin/env python3
"""生产入口：启动 Trend2SKU FastAPI 服务。

默认监听 127.0.0.1:8767，可通过 MINISO_HOST / MINISO_PORT 配置。
本地直接运行也可：`python run.py`。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 把 backend 加入 import 路径（无需设置 PYTHONPATH）
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))


def main() -> None:
    import uvicorn
    from miniso_studio.common.config import settings

    cfg = settings()
    uvicorn.run(
        "miniso_studio.starter.api:app",
        host=cfg.host,
        port=cfg.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
