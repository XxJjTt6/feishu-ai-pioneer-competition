"""Qwen 公网工作台在 SSE 断线后的结果恢复与部署契约。"""
from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
APP_FILE = ROOT / "backend/miniso_studio/starter/live_app_resilient.py"
HTML_FILE = ROOT / "frontend/index-qwen-resilient.html"
SCRIPT_FILE = ROOT / "frontend/app-qwen-resilient.js"
RUNNER_FILE = ROOT / "run_qwen_resilient.py"
BUILDER_FILE = ROOT / "scripts/build_qwen_resilient_pages.py"
WORKFLOW_FILE = ROOT / ".github/workflows/deploy-qwen-resilient-pages.yml"


def _node(script: str) -> dict:
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def _resilient_modules():
    assert APP_FILE.exists(), "缺少断线恢复后端新版"
    module = importlib.import_module("miniso_studio.starter.live_app_resilient")
    base_api = importlib.import_module("miniso_studio.starter.api")
    return module, base_api


def test_resilient_deployment_is_a_separate_version() -> None:
    for path in (APP_FILE, HTML_FILE, SCRIPT_FILE, RUNNER_FILE, BUILDER_FILE, WORKFLOW_FILE):
        assert path.exists(), f"缺少独立新版文件：{path.name}"

    assert 'src="static/app-qwen-resilient.js"' in HTML_FILE.read_text(encoding="utf-8")
    workflow = WORKFLOW_FILE.read_text(encoding="utf-8")
    assert "build_qwen_resilient_pages.py" in workflow
    assert "deploy-pages@v4" in workflow


def test_result_polling_endpoint_returns_pending_then_saved_view_without_rerun(
    monkeypatch,
) -> None:
    module, base_api = _resilient_modules()
    monkeypatch.delenv("TREND2SKU_ACCESS_TOKEN", raising=False)
    base_api._reset_runtime_state()
    calls = 0

    def forbidden_run(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("结果轮询不得重新调用工作流")

    monkeypatch.setattr(base_api, "run_studio", forbidden_run)
    monkeypatch.setattr(
        base_api,
        "to_view",
        lambda artifacts: {
            "run_id": artifacts.run_id,
            "thread_id": artifacts.thread_id,
            "status": "complete",
        },
    )
    client = TestClient(module.app)

    pending = client.get("/api/result", params={"thread_id": "recover-thread"})
    assert pending.status_code == 202
    assert pending.json() == {"status": "pending", "thread_id": "recover-thread"}
    assert pending.headers["retry-after"] == "2"

    base_api._RUNS.save(
        SimpleNamespace(run_id="run-recovered", thread_id="recover-thread")
    )
    completed = client.get("/api/result", params={"thread_id": "recover-thread"})

    assert completed.status_code == 200
    assert completed.json() == {
        "run_id": "run-recovered",
        "thread_id": "recover-thread",
        "status": "complete",
    }
    assert calls == 0
    base_api._reset_runtime_state()


def test_result_polling_endpoint_is_access_token_protected(monkeypatch) -> None:
    module, base_api = _resilient_modules()
    monkeypatch.setenv("TREND2SKU_ACCESS_TOKEN", "unit-test-result-token")
    base_api._reset_runtime_state()
    client = TestClient(module.app)

    denied = client.get("/api/result", params={"thread_id": "protected-thread"})
    allowed = client.get(
        "/api/result",
        params={"thread_id": "protected-thread"},
        headers={"X-Trend2SKU-Access": "unit-test-result-token"},
    )

    assert denied.status_code == 401
    assert allowed.status_code == 202


def test_frontend_polling_recovers_saved_result_without_reissuing_ticket() -> None:
    assert SCRIPT_FILE.exists(), "缺少断线恢复前端新版"
    result = _node(
        """
const app = require('./frontend/app-qwen-resilient.js');
const responses = [
  { status: 202, ok: true, json: async () => ({ status: 'pending' }) },
  { status: 200, ok: true, json: async () => ({
      run_id: 'run-recovered', thread_id: 'thread-recovered', status: 'complete'
  }) },
];
const requests = [];
async function fakeFetch(url, options) {
  requests.push({ url, options });
  return responses.shift();
}
(async () => {
  const view = await app.pollRunResult('thread-recovered', fakeFetch, {
    maxAttempts: 3,
    intervalMs: 0,
    sleepImpl: async () => {},
    accessToken: 'browser-access-token',
  });
  console.log(JSON.stringify({
    view,
    calls: requests.length,
    urls: requests.map((request) => request.url),
    headers: requests.map((request) => request.options.headers),
  }));
})().catch((error) => { console.error(error); process.exit(1); });
"""
    )

    assert result["view"] == {
        "run_id": "run-recovered",
        "thread_id": "thread-recovered",
        "status": "complete",
    }
    assert result["calls"] == 2
    assert result["urls"] == [
        "api/result?thread_id=thread-recovered",
        "api/result?thread_id=thread-recovered",
    ]
    assert result["headers"] == [
        {
            "Accept": "application/json",
            "X-Trend2SKU-Access": "browser-access-token",
        },
        {
            "Accept": "application/json",
            "X-Trend2SKU-Access": "browser-access-token",
        },
    ]

    source = SCRIPT_FILE.read_text(encoding="utf-8")
    onerror = source.split("source.onerror =", maxsplit=1)[1]
    assert "pollRunResult(requestedThreadId" in onerror
    assert "createStreamTicket(" not in onerror
    assert "请重新发起决策" not in onerror


def test_frontend_polling_has_bounded_timeout() -> None:
    assert SCRIPT_FILE.exists(), "缺少断线恢复前端新版"
    result = _node(
        """
const app = require('./frontend/app-qwen-resilient.js');
let calls = 0;
async function pendingFetch() {
  calls += 1;
  return { status: 202, ok: true, json: async () => ({ status: 'pending' }) };
}
(async () => {
  let error = '';
  try {
    await app.pollRunResult('thread-timeout', pendingFetch, {
      maxAttempts: 2,
      intervalMs: 0,
      sleepImpl: async () => {},
    });
  } catch (caught) {
    error = caught.message;
  }
  console.log(JSON.stringify({ calls, error }));
})();
"""
    )

    assert result == {"calls": 2, "error": "result_poll_timeout"}


def test_resilient_pages_builder_injects_api_base_and_new_script(tmp_path: Path) -> None:
    assert BUILDER_FILE.exists(), "缺少断线恢复 Pages 构建器新版"
    module = importlib.import_module("scripts.build_qwen_resilient_pages")
    output = tmp_path / "site"

    module.build_site(output, "https://example-tunnel.invalid/")

    html = (output / "index.html").read_text(encoding="utf-8")
    assert 'content="https://example-tunnel.invalid"' in html
    assert 'src="static/app-qwen-resilient.js"' in html
    assert (output / "static/app-qwen-resilient.js").exists()
    assert (output / "static/styles-qwen-live.css").exists()
