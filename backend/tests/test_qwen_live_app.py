"""Qwen 在线工作台入口、健康状态和前端运行文案契约。"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.tests.test_frontend_copy import CHROME, _chrome_dump, _mock_view
from miniso_studio.application.reporting import SCHEMA_VERSION
from miniso_studio.common.config import settings
from miniso_studio.starter.live_app_dynamic import app


ROOT = Path(__file__).resolve().parents[2]
LIVE_HTML = ROOT / "frontend" / "index-qwen-live.html"
LIVE_SCRIPT = ROOT / "frontend" / "app-qwen-live.js"


def _node(script: str) -> dict:
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_live_root_uses_distinct_qwen_frontend_without_offline_pages_copy() -> None:
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert 'src="static/app-qwen-live.js"' in response.text
    assert "Qwen 3.7 Plus" in response.text
    assert "offline-pages" not in response.text
    assert "固定规则离线演示" not in response.text


def test_live_health_reports_configured_qwen_model(monkeypatch) -> None:
    monkeypatch.setenv("MINISO_LLM_PROVIDER", "qwen")
    monkeypatch.setenv("QWEN_API_KEY", "unit-test-secret")
    monkeypatch.setenv("QWEN_MODEL", "qwen3.7-plus")
    settings.cache_clear()
    try:
        health = TestClient(app).get("/api/health").json()
    finally:
        settings.cache_clear()

    assert health == {
        "status": "ok",
        "product": "Trend2SKU",
        "schema_version": SCHEMA_VERSION,
        "provider": "qwen",
        "configured_provider": "qwen",
        "effective_provider": "qwen",
        "model": "qwen3.7-plus",
        "decision_mode": "llm_dynamic_with_deterministic_guardrails",
    }


def test_live_app_optional_access_token_protects_public_api_without_leaking_token(
    monkeypatch,
) -> None:
    token = "unit-test-public-gateway-token"
    monkeypatch.setenv("TREND2SKU_ACCESS_TOKEN", token)
    client = TestClient(app)

    assert client.get("/").status_code == 200
    denied = client.get("/api/health")
    wrong = client.get("/api/health", headers={"X-Trend2SKU-Access": "wrong"})
    allowed = client.get("/api/health", headers={"X-Trend2SKU-Access": token})

    assert denied.status_code == 401
    assert wrong.status_code == 401
    assert allowed.status_code == 200
    assert token not in denied.text
    assert token not in wrong.text

    preflight = client.options(
        "/api/stream/ticket",
        headers={
            "Origin": "https://xxjjtt6.github.io",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-trend2sku-access",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "https://xxjjtt6.github.io"

    ticket = client.post(
        "/api/stream/ticket",
        headers={"X-Trend2SKU-Access": token},
        json={"brief": "访问令牌保护下的动态新品", "thread_id": "token-test"},
    )
    assert ticket.status_code == 200
    assert ticket.json()["stream_url"].startswith("api/stream?ticket=")


def test_live_script_routes_all_network_calls_through_configurable_api_base() -> None:
    script = LIVE_SCRIPT.read_text(encoding="utf-8")
    html = LIVE_HTML.read_text(encoding="utf-8")

    assert 'meta name="trend2sku-api-base"' in html
    assert "function apiUrl(" in script
    assert 'fetchImpl(apiUrl("api/stream/ticket")' in script
    assert "new EventSource(apiUrl(ticket.stream_url))" in script
    assert "fetch(apiUrl(url)" in script
    assert 'fetch(apiUrl("api/health")' in script
    assert "qwen3.7-plus" in script
    assert "Agent 正在调用 Qwen" in script
    assert "Agent 正在读取离线演示样本" not in script


def test_live_frontend_exposes_qwen_interviews_risk_narratives_and_proposal_quotes() -> None:
    script = LIVE_SCRIPT.read_text(encoding="utf-8")

    assert "interview.transcript" in script
    assert "interview.must_fixes" in script
    assert "assessment.technical" in script
    assert "assessment.supply_chain" in script
    assert "assessment.compliance" in script
    assert "prfaq.customer_quote" in script
    assert "prfaq.maker_quote" in script


def test_live_frontend_localizes_model_and_audit_enums_for_judges() -> None:
    result = _node(
        """
const app = require('./frontend/app-qwen-live.js');
console.log(JSON.stringify({
  buy: app.interviewVerdictLabel('would_buy'),
  maybe: app.interviewVerdictLabel('maybe'),
  quality: app.riskAreaLabel('quality'),
  ip: app.riskAreaLabel('ip_authorization'),
  yellow: app.assessmentLabel('yellow'),
  fidelity: app.metricLabel('persona_fidelity'),
  ideationStart: app.runtimeTraceMessage({ node: 'ideation', kind: 'start' }),
  strategyDone: app.runtimeTraceMessage({ node: 'Qwen strategy', kind: 'llm_call', task: 'strategy' }),
  auditNoise: app.runtimeTraceMessage({ node: 'runner', kind: 'audit' }),
  readyToRun: app.canRunDecision({ valid: true }, false, true),
  blockedWithoutQwen: app.canRunDecision({ valid: true }, false, false),
  blockedInvalid: app.canRunDecision({ valid: false }, false, true),
  protectedHeaders: app.accessHeaders('demo-token', { Accept: 'application/json' }),
  publicHeaders: app.accessHeaders('', { Accept: 'application/json' }),
}));
"""
    )

    assert result == {
        "buy": "愿意购买",
        "maybe": "考虑购买",
        "quality": "质量",
        "ip": "IP 授权",
        "yellow": "需验证",
        "fidelity": "用户镜像可追溯性",
        "ideationStart": "创意工坊 · 运行中",
        "strategyDone": "Qwen 已生成动态候选与合成验证",
        "auditNoise": "",
        "readyToRun": True,
        "blockedWithoutQwen": False,
        "blockedInvalid": False,
        "protectedHeaders": {
            "Accept": "application/json",
            "X-Trend2SKU-Access": "demo-token",
        },
        "publicHeaders": {"Accept": "application/json"},
    }


@pytest.mark.skipif(not CHROME.exists(), reason="本机未安装 Google Chrome")
@pytest.mark.parametrize(("width", "height"), [(375, 812), (390, 844), (1121, 800), (1440, 900)])
def test_live_frontend_real_browser_renders_dynamic_llm_details_without_page_overflow(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    site = tmp_path / "site"
    static = site / "static"
    shutil.copytree(ROOT / "frontend", static)
    html = LIVE_HTML.read_text(encoding="utf-8")
    view = _mock_view()
    view["configured_provider"] = "qwen"
    view["effective_provider"] = "qwen"
    view["model"] = "qwen3.7-plus"
    for validation in view["launch_validation"]["by_candidate"].values():
        interview = validation["interviews"][0]
        interview["objections"] = ["希望先看到样件"]
        interview["must_fixes"] = ["验证连续使用意愿"]
        interview["transcript"] = [
            {"question": "会在什么场景使用？", "answer": "课堂记录和社团分享。", "sentiment": "positive"},
            {"question": "主要顾虑是什么？", "answer": "先确认耐用度和价格。", "sentiment": "neutral"},
            {"question": "愿意推荐吗？", "answer": "样件达标后会考虑。", "sentiment": "positive"},
        ]
    for assessment in view["quality_audit"]["by_candidate"].values():
        assessment.update(
            {
                "technical": "常规工艺可完成首轮样件",
                "bom_cost": "按模块逐项核价",
                "compliance": "按目标市场完成材料与标签检查",
                "quality": "验证连接件寿命与跌落",
                "supplier_lead_time": "以打样排期为准",
                "regional_compliance": "进入各区域前分别核验",
            }
        )
        assessment["risks"] = [
            {
                "area": "quality",
                "description": "连接件寿命需要样件验证",
                "severity": "medium",
                "mitigation": "完成三轮耐久测试",
            }
        ]
    prfaq = view["portfolio_decision"]["prfaq"]
    prfaq["summary"] = "Qwen 根据本轮输入生成的动态提案。"
    prfaq["customer_quote"] = "我需要真正解决课堂和分享任务的用品。"
    prfaq["maker_quote"] = "先用样件关闭耐用度与成本假设。"

    payload = json.dumps(view, ensure_ascii=False).replace("</", "<\\/")
    probe = f"""
<script>
window.addEventListener('load', () => {{
  window.Trend2SKUApp.renderViewForTest({payload});
  window.setTimeout(() => {{
    const pageContainers = Array.from(document.querySelectorAll(
      '.header-inner, .workflow-inner, .workspace, .app-footer > p'
    ));
    document.body.dataset.overflow = String(
      document.documentElement.scrollWidth > document.documentElement.clientWidth
    );
    document.body.dataset.containerOverflow = String(pageContainers.some((node) => {{
      const rect = node.getBoundingClientRect();
      return rect.left < -1 || rect.right > document.documentElement.clientWidth + 1;
    }}));
    document.body.dataset.transcripts = String(document.querySelectorAll('.interview-transcript').length);
    document.body.dataset.narratives = String(document.querySelectorAll('.feasibility-narratives').length);
    document.body.dataset.quotes = String(document.querySelectorAll('.proposal-quotes blockquote').length);
    document.body.dataset.verdict = document.querySelector('.validation-verdict')?.textContent || '';
    document.body.dataset.risk = document.querySelector('.risk-item h4')?.textContent || '';
    document.body.dataset.pwned = String(window.__pwned || 0);
    document.body.dataset.probe = 'ready';
  }}, 80);
}});
</script>
"""
    (site / "index.html").write_text(
        html.replace("</body>", probe + "</body>"),
        encoding="utf-8",
    )

    stdout, stderr = _chrome_dump(site / "index.html", tmp_path, width, height)

    body = re.search(r"<body\b([^>]*)>", stdout)
    assert body, stderr
    attrs = body.group(1)
    assert 'data-probe="ready"' in attrs
    assert 'data-overflow="false"' in attrs
    assert 'data-container-overflow="false"' in attrs
    assert 'data-transcripts="1"' in attrs
    assert 'data-narratives="1"' in attrs
    assert 'data-quotes="2"' in attrs
    assert 'data-verdict="愿意购买"' in attrs
    assert 'data-risk="质量"' in attrs
    assert 'data-pwned="0"' in attrs
