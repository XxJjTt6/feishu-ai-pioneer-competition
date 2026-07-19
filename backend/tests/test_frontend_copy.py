from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from PIL import Image, ImageChops


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_FILES = (
    ROOT / "frontend/index.html",
    ROOT / "frontend/app.js",
    ROOT / "frontend/styles.css",
    ROOT / "web/landing/index.html",
)
STALE_TERMS = (
    "Anker",
    "安克",
    "soundcore",
    "TWS",
    "JML",
    "BEES",
    "AMI",
    "AIME",
    "eufy",
)
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def _frontend_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in FRONTEND_FILES)


def _node(script: str) -> dict:
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def _chrome_dump(page: Path, tmp_path: Path, width: int, height: int) -> tuple[str, str]:
    stdout_path = tmp_path / "chrome-dom.html"
    stderr_path = tmp_path / "chrome-stderr.log"
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr:
        process = subprocess.Popen(
            [
                str(CHROME),
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-background-networking",
                "--disable-component-update",
                "--no-first-run",
                "--allow-file-access-from-files",
                f"--user-data-dir={tmp_path / 'chrome-profile'}",
                f"--window-size={width},{height}",
                "--virtual-time-budget=1500",
                "--dump-dom",
                page.as_uri(),
            ],
            stdout=stdout,
            stderr=stderr,
            text=True,
        )
        deadline = time.monotonic() + 20
        probe_ready = False
        while time.monotonic() < deadline:
            stdout.flush()
            if stdout_path.exists() and 'data-probe="ready"' in stdout_path.read_text(
                encoding="utf-8", errors="ignore"
            ):
                probe_ready = True
                break
            if process.poll() is not None:
                break
            time.sleep(0.05)
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if not probe_ready and process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, process.args)
    return stdout_path.read_text(encoding="utf-8"), stderr_path.read_text(encoding="utf-8")


def _mock_view() -> dict:
    malicious = "恶意'><img src=x onerror=window.__pwned=1>" + "超长词" * 700
    dimensions = [
        ("trend_fit", "趋势匹配", 82, 0.20),
        ("demand_strength", "需求强度", 80, 0.20),
        ("differentiation", "差异化", 78, 0.15),
        ("social_virality", "社交传播", 76, 0.15),
        ("margin_potential", "成本与毛利", 74, 0.10),
        ("supply_feasibility", "供应链可行性", 72, 0.10),
        ("ip_compliance", "IP/合规", 90, 0.05),
        ("localization_fit", "全球本地化", 88, 0.05),
    ]

    def scorecard(concept_id: str, total: float) -> dict:
        return {
            "concept_id": concept_id,
            "dimensions": [
                {
                    "key": key,
                    "label": label,
                    "score": score,
                    "weight": weight,
                    "rationale": malicious if key == "trend_fit" else f"{label}评分依据",
                    "evidence_ids": ["demo-1"],
                }
                for key, label, score, weight in dimensions
            ],
            "total_score": total,
            "recommendation": "GO" if total >= 75 else "CONDITIONAL_GO",
            "evidence_ids": ["demo-1"],
            "blocking_risks": [],
        }

    candidates = [
        {
            "id": "C-1",
            "name": "榜首香氛挂件",
            "path": "trend_driven",
            "one_liner": "榜首摘要必须保持稳定",
            "target_segment": "年轻兴趣消费用户",
            "value_proposition": "城市故事与日常情绪价值",
            "key_features": ["可替换香芯", "区域限定色"],
            "differentiators": [{"statement": "全球结构、本地内容", "evidence_ids": ["demo-1"]}],
            "tech_enablers": ["柔性排产"],
        },
        {
            "id": "C-2",
            "name": malicious,
            "path": "voc_driven",
            "one_liner": "用户机会驱动候选",
            "target_segment": "轻礼赠用户",
            "value_proposition": "多场景使用",
            "key_features": [malicious],
            "differentiators": [],
            "tech_enablers": [],
        },
        {
            "id": "C-3",
            "name": "共创贴片套装",
            "path": "whitespace_driven",
            "one_liner": "白空间候选",
            "target_segment": "创意用户",
            "value_proposition": "低门槛共创",
            "key_features": ["模块贴片"],
            "differentiators": [],
            "tech_enablers": [],
        },
    ]
    cards = [scorecard("C-1", 82.0), scorecard("C-2", 71.0), scorecard("C-3", 65.0)]
    interviews = {
        concept["id"]: {
            "concept_id": concept["id"],
            "interviews": [
                {
                    "persona_name": "用户镜像",
                    "segment": "测试客群",
                    "verdict": "would_buy",
                    "acceptance": 0.8,
                    "objections": [malicious],
                    "must_fixes": [],
                    "evidence_ids": ["demo-1"],
                }
            ],
            "nps": {"score": 5, "rationale": "离线预测", "evidence_ids": ["demo-1"]},
            "average_acceptance": 0.8,
            "mode": "offline_demo",
        }
        for concept in candidates
    }
    feasibility = {
        concept["id"]: {
            "concept_id": concept["id"],
            "overall": "yellow",
            "gross_margin_score": 72,
            "supply_feasibility_score": 75,
            "ip_compliance_score": 88,
            "localization_score": 84,
            "gross_margin": "模拟毛利需校准",
            "supply_chain": "供应链可行",
            "ip_authorization": "优先原创资产",
            "localization": "区域内容替换",
            "risks": [
                {
                    "area": "supply_chain",
                    "description": malicious,
                    "severity": "medium",
                    "mitigation": "小批量验证",
                }
            ],
            "evidence_ids": ["demo-1"],
        }
        for concept in candidates
    }
    return {
        "schema_version": "1.0",
        "product": "Trend2SKU",
        "run_id": "run-browser-test",
        "thread_id": "thread-browser-test",
        "status": "completed",
        "awaiting_human": False,
        "elapsed_seconds": 0.5,
        "provider": "offline",
        "target_brand": "MINISO",
        "data_provenance": {
            "review_scope": "synthetic_demo",
            "review_count": 400,
            "disclaimer": "离线演示，不代表企业真实收益。",
            "official_trend_cutoff": "2026-05-26",
        },
        "candidate_skus": candidates,
        "scorecards": cards,
        "winner_scorecard": cards[0],
        "portfolio_decision": {
            "winner_id": "C-1",
            "winner_name": "榜首香氛挂件",
            "verdict": "GO",
            "confidence": 0.88,
            "rationale": "组合第一",
            "conditions": [],
            "evidence_ids": ["demo-1"],
            "prfaq": {
                "headline": "榜首提案",
                "subheading": "小批量验证",
                "summary": malicious,
                "call_to_action": "启动样件验证",
                "external_faq": [],
                "internal_faq": [],
            },
        },
        "trend_signals": [
            {"name": "情绪价值", "direction": "up", "summary": malicious, "evidence_ids": ["demo-1"]}
        ],
        "consumer_insights": {
            "review_count": 400,
            "opportunities": [
                {
                    "id": "OPP-1",
                    "aspect": "礼赠性",
                    "statement": malicious,
                    "opportunity_score": 12,
                    "impact_score": 8,
                    "rationale": "机会依据",
                    "evidence_ids": ["demo-1"],
                }
            ],
            "white_space": [],
        },
        "launch_validation": {
            "by_candidate": interviews,
            "winner_id": "C-1",
            "winner": interviews["C-1"],
            "disclaimer": "离线模拟访谈。",
        },
        "quality_audit": {
            "by_candidate": feasibility,
            "winner_assessment": feasibility["C-1"],
            "rubric": {
                "groundedness": 1,
                "faithfulness": 0.8,
                "citation_hit_rate": 1,
                "opportunity_coverage": 0.7,
                "persona_fidelity": 1,
                "explainability": 1,
                "overall": 0.9,
            },
            "evidence_count": 1,
            "claim_count": 2,
            "mode": "offline_demo",
        },
        "evidence_index": {
            "demo-1": {
                "source_id": "demo-1",
                "source_type": "review",
                "brand": "MINISO",
                "product": "概念示意",
                "rating": 4,
                "text": malicious,
                "date": "2026",
                "url": "demo://synthetic/1",
                "data_provenance": "synthetic_demo",
                "is_demo": True,
            }
        },
        "audit": {
            "tool_calls": [{"tool_name": "get_retail_trends", "status": "success", "used_fallback": False}],
            "trace": [],
            "experience_baseline": {
                "arm_a": {"opportunity_coverage": 0.2, "evidence_citations": 0, "nps_prediction": -20},
                "arm_b": {"opportunity_coverage": 0.7, "evidence_citations": 10, "nps_prediction": 5},
                "deltas": {"opportunity_coverage": 0.5, "evidence_citations": 10, "nps_prediction": 25},
                "narrative": malicious,
            },
        },
    }


def test_frontend_is_trend2sku_workspace_without_legacy_copy() -> None:
    text = _frontend_text()

    assert "Trend2SKU" in text
    assert "候选 SKU" in text
    assert "名创优品" in text
    assert all(term not in text for term in STALE_TERMS)
    assert "linear-gradient" not in (ROOT / "frontend/styles.css").read_text(encoding="utf-8")
    assert "radial-gradient" not in (ROOT / "frontend/styles.css").read_text(encoding="utf-8")


def test_frontend_contract_exposes_accessible_control_and_all_stages() -> None:
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend/app.js").read_text(encoding="utf-8")

    assert re.search(r"<label[^>]+for=[\"']brief[\"']", html)
    assert 'maxlength="500"' in html
    assert 'aria-live="polite"' in html
    assert 'role="status"' in html
    for stage in (
        "insight",
        "trend_radar",
        "ideation",
        "user_mirror",
        "merchandise_expert",
        "hit_judge",
        "proposal",
    ):
        assert stage in html + js
    for api_path in ("api/health", "api/stream", "api/report?run_id="):
        assert api_path in js
    assert "validateViewContract" in js
    assert "bindSseEnvelope" in js
    assert "hitl=false" in js
    assert 'role="tabpanel"' in html
    assert "aria-controls" in js


def test_frontend_uses_dom_text_and_safe_urls_for_untrusted_data() -> None:
    js = (ROOT / "frontend/app.js").read_text(encoding="utf-8")

    assert "escapeHtml" in js
    assert ".innerHTML" not in js
    assert "textContent" in js
    assert "safeHttpUrl" in js
    assert "demo://" in js


def test_frontend_pure_behavior_handles_selection_security_and_terminal_states() -> None:
    view = json.dumps(_mock_view(), ensure_ascii=False)
    script = f"""
const app = require('./frontend/app.js');
const raw = {view};
const view = app.normalizeView(raw);
const validated = app.validateViewContract(raw, {{ runId: raw.run_id, threadId: raw.thread_id }});
const selected = app.selectCandidateModel(view, 'C-2');
let runtime = app.createRuntimeSnapshot();
runtime = app.reduceRuntime(runtime, {{ type: 'run_started' }});
runtime = app.reduceRuntime(runtime, {{ type: 'trace', event: {{ node: 'insight', kind: 'end' }} }});
runtime = app.reduceRuntime(runtime, {{ type: 'trace', event: {{ node: 'ideation', kind: 'end' }} }});
runtime = app.reduceRuntime(runtime, {{ type: 'trace', event: {{ node: 'user_mirror', kind: 'end' }} }});
runtime = app.reduceRuntime(runtime, {{ type: 'trace', event: {{ node: 'ideation', kind: 'start' }} }});
const resetWorked = runtime.stages.user_mirror === 'pending' && runtime.stages.merchandise_expert === 'pending';
runtime = app.reduceRuntime(runtime, {{ type: 'trace', event: {{ node: 'decision_review', kind: 'interrupt' }} }});
const reviewMapped = runtime.stages.hit_judge === 'waiting';
runtime = app.reduceRuntime(runtime, {{ type: 'trace', event: {{ node: 'proposal', kind: 'node_error' }} }});
runtime = app.reduceRuntime(runtime, {{ type: 'trace', event: {{ node: 'proposal', kind: 'end' }} }});
const nodeErrorStayedSticky = runtime.stages.proposal === 'error';
runtime = app.reduceRuntime(runtime, {{ type: 'tool_warning', message: 'tool failed' }});
const warningStayedPartial = runtime.phase === 'partial' && runtime.warnings.length === 1;
runtime = app.reduceRuntime(runtime, {{ type: 'result_received' }});
runtime = app.reduceRuntime(runtime, {{ type: 'done' }});
runtime = app.reduceRuntime(runtime, {{ type: 'disconnected' }});
runtime = app.reduceRuntime(runtime, {{ type: 'trace', event: {{ node: 'proposal', kind: 'error' }} }});
const terminalStayedStable = runtime.phase === 'complete' && runtime.stages.proposal === 'error';
let doneOnly = app.reduceRuntime(app.reduceRuntime(null, {{ type: 'run_started' }}), {{ type: 'done' }});
const doneOnlyFailedClosed = doneOnly.phase === 'error' && doneOnly.terminal;
const restarted = app.reduceRuntime(runtime, {{ type: 'run_started' }});
const nextRunIsFresh = restarted.phase === 'running' && restarted.terminal === false &&
  restarted.iteration === 1 && restarted.warnings.length === 0 &&
  Object.values(restarted.stages).every((status) => status === 'pending');
console.log(JSON.stringify({{
  escaped: app.escapeHtml(`&<>"'`),
  demoUrl: app.safeHttpUrl('demo://synthetic/1'),
  scriptUrl: app.safeHttpUrl('javascript:alert(1)'),
  httpUrl: app.safeHttpUrl('https://example.com/a'),
  selectedId: selected.candidate.id,
  winnerId: selected.winnerCandidate.id,
  selectedScoreId: selected.scorecard.concept_id,
  validatedWinnerId: validated.winner_id,
  resetWorked,
  reviewMapped,
  nodeErrorStayedSticky,
  warningStayedPartial,
  terminalStayedStable,
  doneOnlyFailedClosed,
  nextRunIsFresh,
  finalPhase: runtime.phase,
  terminal: runtime.terminal,
  bounded: app.safeText('x'.repeat(5000), 120).length <= 121,
}}));
"""

    result = _node(script)

    assert result == {
        "escaped": "&amp;&lt;&gt;&quot;&#39;",
        "demoUrl": None,
        "scriptUrl": None,
        "httpUrl": "https://example.com/a",
        "selectedId": "C-2",
        "winnerId": "C-1",
        "selectedScoreId": "C-2",
        "validatedWinnerId": "C-1",
        "resetWorked": True,
        "reviewMapped": True,
        "nodeErrorStayedSticky": True,
        "warningStayedPartial": True,
        "terminalStayedStable": True,
        "doneOnlyFailedClosed": True,
        "nextRunIsFresh": True,
        "finalPhase": "complete",
        "terminal": True,
        "bounded": True,
    }


def test_frontend_strict_view_and_sse_contract_rejects_cross_run_or_hitl_results() -> None:
    view = json.dumps(_mock_view(), ensure_ascii=False)
    script = f"""
const app = require('./frontend/app.js');
const valid = {view};
const first = app.bindSseEnvelope({{ runId: null, threadId: valid.thread_id }}, {{
  type: 'heartbeat', run_id: valid.run_id, thread_id: valid.thread_id,
}});

function rejected(fn) {{
  try {{ fn(); return false; }} catch (_error) {{ return true; }}
}}

const missingScorecard = JSON.parse(JSON.stringify(valid));
missingScorecard.scorecards.pop();
const awaitingHuman = JSON.parse(JSON.stringify(valid));
awaitingHuman.status = 'awaiting_human';
awaitingHuman.awaiting_human = true;

console.log(JSON.stringify({{
  first,
  validWinner: app.validateViewContract(valid, first).winner_id,
  rejectsMissingScorecard: rejected(() => app.validateViewContract(missingScorecard, first)),
  rejectsAwaitingHuman: rejected(() => app.validateViewContract(awaitingHuman, first)),
  rejectsWrongRun: rejected(() => app.validateViewContract(valid, {{ ...first, runId: 'run-other' }})),
  rejectsEnvelopeRunSwitch: rejected(() => app.bindSseEnvelope(first, {{
    type: 'trace', run_id: 'run-other', thread_id: valid.thread_id, event: {{}},
  }})),
  rejectsEnvelopeThreadSwitch: rejected(() => app.bindSseEnvelope(first, {{
    type: 'done', run_id: valid.run_id, thread_id: 'thread-other',
  }})),
  rejectsUnknownType: rejected(() => app.bindSseEnvelope(first, {{
    type: 'mystery', run_id: valid.run_id, thread_id: valid.thread_id,
  }})),
}}));
"""

    result = _node(script)

    assert result == {
        "first": {"runId": "run-browser-test", "threadId": "thread-browser-test"},
        "validWinner": "C-1",
        "rejectsMissingScorecard": True,
        "rejectsAwaitingHuman": True,
        "rejectsWrongRun": True,
        "rejectsEnvelopeRunSwitch": True,
        "rejectsEnvelopeThreadSwitch": True,
        "rejectsUnknownType": True,
    }


def test_concept_assets_are_original_versioned_nonblank_pngs() -> None:
    asset_dir = ROOT / "frontend/assets/miniso-v1"
    expected = {
        "mood-charm-v1.png",
        "city-scent-charm-v1.png",
        "cocreate-patch-kit-v1.png",
    }

    assert {path.name for path in asset_dir.glob("*.png")} == expected
    for path in asset_dir.glob("*.png"):
        with Image.open(path) as image:
            assert image.format == "PNG"
            assert image.size == (1200, 900)
            assert ImageChops.difference(image, Image.new(image.mode, image.size, image.getpixel((0, 0)))).getbbox()


@pytest.mark.skipif(not CHROME.exists(), reason="本机未安装 Google Chrome")
@pytest.mark.parametrize(
    ("width", "height"),
    [(390, 844), (375, 812), (1121, 800), (1440, 900)],
)
def test_real_browser_candidate_switch_escapes_malicious_text_and_has_no_page_overflow(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    site = tmp_path / "site"
    static = site / "static"
    shutil.copytree(ROOT / "frontend", static)
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    payload = json.dumps(_mock_view(), ensure_ascii=False).replace("</", "<\\/")
    probe = f"""
<script>
window.__pwned = 0;
window.addEventListener('load', () => {{
  window.Trend2SKUApp.renderViewForTest({payload});
  window.Trend2SKUApp.selectCandidate('C-2');
  window.setTimeout(() => {{
    const selected = document.querySelector('[role="tab"][aria-selected="true"]');
    document.body.dataset.selected = selected ? selected.dataset.candidateId : '';
    document.body.dataset.winner = document.querySelector('[data-testid="winner-name"]')?.textContent || '';
    document.body.dataset.pwned = String(window.__pwned);
    document.body.dataset.injectedImages = String(document.querySelectorAll('img[src="x"]').length);
    document.body.dataset.overflow = String(document.documentElement.scrollWidth > window.innerWidth);
    document.body.dataset.overflowNodes = Array.from(document.querySelectorAll('body *'))
      .filter((node) => {{
        const rect = node.getBoundingClientRect();
        return rect.right > window.innerWidth + 1 || rect.left < -1;
      }})
      .slice(0, 8)
      .map((node) => `${{node.tagName.toLowerCase()}}.${{node.className || node.id}}`)
      .join('|');
    document.body.dataset.ariaControls = selected?.getAttribute('aria-controls') || '';
    document.body.dataset.panelLabelledby = document.getElementById('candidateDetail')?.getAttribute('aria-labelledby') || '';
    const stageState = document.querySelector('.stage-state');
    document.body.dataset.stageStateVisible = String(stageState && getComputedStyle(stageState).display !== 'none');
    document.body.dataset.stageStateText = stageState?.textContent || '';
    const runButtonRect = document.getElementById('runBtn')?.getBoundingClientRect();
    document.body.dataset.runButtonVisible = String(Boolean(
      runButtonRect && runButtonRect.left >= 0 && runButtonRect.right <= window.innerWidth,
    ));
    document.body.dataset.probe = 'ready';
  }}, 60);
}});
</script>
"""
    (site / "index.html").write_text(html.replace("</body>", probe + "</body>"), encoding="utf-8")

    stdout, stderr = _chrome_dump(site / "index.html", tmp_path, width, height)

    body = re.search(r"<body\b([^>]*)>", stdout)
    assert body, stderr
    attrs = body.group(1)
    assert 'data-probe="ready"' in attrs
    assert 'data-selected="C-2"' in attrs
    assert 'data-winner="榜首香氛挂件"' in attrs
    assert 'data-pwned="0"' in attrs
    assert 'data-injected-images="0"' in attrs
    assert 'data-overflow="false"' in attrs
    assert 'data-aria-controls="candidateDetail"' in attrs
    assert 'data-panel-labelledby="candidate-tab-C-2"' in attrs
    assert 'data-stage-state-visible="true"' in attrs
    assert 'data-stage-state-text="待处理"' in attrs
    assert 'data-run-button-visible="true"' in attrs


@pytest.mark.skipif(not CHROME.exists(), reason="本机未安装 Google Chrome")
def test_real_browser_second_run_resets_workspace_ignores_stale_stream_and_links_own_report(
    tmp_path: Path,
) -> None:
    site = tmp_path / "site"
    static = site / "static"
    shutil.copytree(ROOT / "frontend", static)
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    first_payload = json.dumps(_mock_view(), ensure_ascii=False).replace("</", "<\\/")
    prelude = """
<script>
window.__streams = [];
window.fetch = async () => ({
  ok: true,
  json: async () => ({ effective_provider: 'offline' }),
});
window.EventSource = class FakeEventSource {
  constructor(url) {
    this.url = url;
    this.closed = false;
    this.threadId = new URL(url, location.href).searchParams.get('thread_id');
    window.__streams.push(this);
  }
  close() { this.closed = true; }
  emit(message) {
    const runId = message.run_id || message.view?.run_id || `run-stream-${window.__streams.indexOf(this) + 1}`;
    const normalized = { ...message, run_id: runId, thread_id: this.threadId };
    if (normalized.view) normalized.view = {
      ...normalized.view,
      run_id: runId,
      thread_id: this.threadId,
      status: 'completed',
      awaiting_human: false,
    };
    this.onmessage?.({ data: JSON.stringify(normalized) });
  }
};
</script>
"""
    probe = f"""
<script>
window.addEventListener('load', () => {{
  const firstView = {first_payload};
  const secondView = JSON.parse(JSON.stringify(firstView));
  secondView.run_id = 'run-second';
  secondView.candidate_skus[0].name = '第二轮榜首';
  secondView.portfolio_decision.winner_name = '第二轮榜首';

  const form = document.getElementById('runForm');
  const brief = document.getElementById('brief');
  brief.value = '第一轮';
  form.dispatchEvent(new Event('submit', {{ bubbles: true, cancelable: true }}));
  const first = window.__streams[0];
  first.emit({{ type: 'result', view: firstView }});

  brief.value = '第二轮';
  form.dispatchEvent(new Event('submit', {{ bubbles: true, cancelable: true }}));
  const resetWorked =
    document.body.dataset.phase === 'running' &&
    document.getElementById('candidateCount').textContent === '0 个候选' &&
    document.getElementById('fullReportLink').getAttribute('aria-disabled') === 'true' &&
    !document.getElementById('fullReportLink').hasAttribute('href');

  const second = window.__streams[1];
  first.emit({{ type: 'result', view: firstView }});
  second.emit({{ type: 'result', view: secondView }});
  second.emit({{ type: 'done' }});

  window.setTimeout(() => {{
    document.body.dataset.sources = String(window.__streams.length);
    document.body.dataset.firstClosed = String(first.closed);
    document.body.dataset.explicitHitl = String(second.url.includes('hitl=false'));
    document.body.dataset.boundThread = String(Boolean(second.threadId));
    document.body.dataset.reset = String(resetWorked);
    document.body.dataset.finalWinner = document.querySelector('[data-testid="winner-name"]')?.textContent || '';
    document.body.dataset.report = document.getElementById('fullReportLink').getAttribute('href') || '';
    document.body.dataset.buttonEnabled = String(!document.getElementById('runBtn').disabled);
    document.body.dataset.probe = 'ready';
  }}, 60);
}});
</script>
"""
    html = html.replace('<script src="static/app.js" defer></script>', prelude + '<script src="static/app.js" defer></script>')
    (site / "index.html").write_text(html.replace("</body>", probe + "</body>"), encoding="utf-8")

    stdout, stderr = _chrome_dump(site / "index.html", tmp_path, 390, 844)

    body = re.search(r"<body\b([^>]*)>", stdout)
    assert body, stderr
    attrs = body.group(1)
    assert 'data-probe="ready"' in attrs
    assert 'data-sources="2"' in attrs
    assert 'data-first-closed="true"' in attrs
    assert 'data-explicit-hitl="true"' in attrs
    assert 'data-bound-thread="true"' in attrs
    assert 'data-reset="true"' in attrs
    assert 'data-final-winner="第二轮榜首"' in attrs
    assert 'data-report="api/report?run_id=run-second&amp;kind=full"' in attrs
    assert 'data-button-enabled="true"' in attrs
