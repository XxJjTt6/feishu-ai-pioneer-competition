"""支持公网断线恢复的 Qwen 工作台；原 API 保持不变并挂载为后备路由。"""
from __future__ import annotations

import hmac
import os
import re
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from miniso_studio.application.reporting import (
    PRODUCT_NAME,
    SCHEMA_VERSION,
    build_data_provenance,
)
from miniso_studio.application.reporting_llm_dynamic import (
    render_full_report_llm_dynamic,
    render_opening_report_llm_dynamic,
)
from miniso_studio.common.config import settings
from miniso_studio.infrastructure.data.loader import EvidenceIdConflictError
from miniso_studio.infrastructure.llm.gateway import LLMGateway
from miniso_studio.starter import api as base_api


app = FastAPI(
    title="Trend2SKU Qwen 稳健公网爆款产品决策工作台",
    version=SCHEMA_VERSION,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8767",
        "http://localhost:8767",
        "https://xxjjtt6.github.io",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "X-Trend2SKU-Access"],
    allow_credentials=False,
)


def _access_token() -> str:
    return os.getenv("TREND2SKU_ACCESS_TOKEN", "").strip()


@app.middleware("http")
async def optional_access_guard(request: Request, call_next):
    token = _access_token()
    if not token or request.method == "OPTIONS":
        return await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static/") or path.startswith("/assets/"):
        return await call_next(request)
    if path == "/api/stream" and re.fullmatch(
        r"[a-f0-9]{32}",
        request.query_params.get("ticket", ""),
    ):
        return await call_next(request)
    provided = request.headers.get("X-Trend2SKU-Access", "")
    if not provided or not hmac.compare_digest(provided, token):
        return JSONResponse(status_code=401, content={"detail": "访问未授权"})
    return await call_next(request)


@app.get("/", include_in_schema=False)
def live_index() -> FileResponse:
    frontend = Path(settings().project_root) / "frontend" / "index-qwen-resilient.html"
    return FileResponse(str(frontend))


@app.get("/api/health")
def live_health() -> dict:
    cfg = settings()
    configured_provider, effective_provider = LLMGateway.provider_status(cfg)
    model = cfg.qwen_model if effective_provider == "qwen" else "offline-deterministic"
    return {
        "status": "ok",
        "product": PRODUCT_NAME,
        "schema_version": SCHEMA_VERSION,
        "provider": effective_provider,
        "configured_provider": configured_provider,
        "effective_provider": effective_provider,
        "model": model,
        "decision_mode": "llm_dynamic_with_deterministic_guardrails",
    }


@app.get("/api/result")
def live_result(
    thread_id: str = Query(..., pattern=base_api.THREAD_ID_PATTERN),
):
    """按 thread_id 取回已完成结果，供长连接中断后的前端轮询恢复。"""
    artifacts = base_api._RUNS.get_by_thread(thread_id)
    if artifacts is None:
        return JSONResponse(
            status_code=202,
            content={"status": "pending", "thread_id": thread_id},
            headers={"Retry-After": "2", "Cache-Control": "no-store"},
        )
    return base_api.to_view(artifacts)


@app.get("/api/report")
def live_report(
    run_id: str = Query(..., min_length=1),
    kind: Literal["full", "opening"] = Query(default="full"),
) -> dict:
    artifacts = base_api._RUNS.get(run_id)
    if artifacts is None:
        raise HTTPException(status_code=404, detail="未找到该 run_id 的运行结果")
    try:
        markdown = (
            render_opening_report_llm_dynamic(artifacts)
            if kind == "opening"
            else render_full_report_llm_dynamic(artifacts)
        )
    except EvidenceIdConflictError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "run_id": artifacts.run_id,
        "kind": kind,
        "markdown": markdown,
        "data_provenance": build_data_provenance(artifacts),
    }


app.mount("/", base_api.app)
