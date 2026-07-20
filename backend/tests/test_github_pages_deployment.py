"""GitHub Pages 离线交互演示与 Deployment 契约测试。"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
PYTHON = Path(sys.executable)
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
WORKFLOW = ROOT / ".github/workflows/deploy-pages.yml"
ADAPTER = ROOT / "frontend/pages-demo.js"
BUILDER = ROOT / "scripts/build_github_pages.py"


def _node(script: str) -> dict:
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def _chrome_dump_url(url: str, tmp_path: Path, width: int, height: int) -> tuple[str, str]:
    stdout_path = tmp_path / f"chrome-{width}x{height}.html"
    stderr_path = tmp_path / f"chrome-{width}x{height}.log"
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
                f"--user-data-dir={tmp_path / f'chrome-profile-{width}x{height}'}",
                f"--window-size={width},{height}",
                "--virtual-time-budget=1800",
                "--dump-dom",
                url,
            ],
            stdout=stdout,
            stderr=stderr,
            text=True,
        )
        deadline = time.monotonic() + 25
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
        if not probe_ready and process.returncode not in (0, -15):
            raise subprocess.CalledProcessError(process.returncode, process.args)
    return stdout_path.read_text(encoding="utf-8"), stderr_path.read_text(encoding="utf-8")


def test_pages_workflow_uses_official_deployment_contract() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)

    assert re.search(r"(?m)^on:\s*$", text)
    assert re.search(r"(?m)^\s+workflow_dispatch:\s*$", text)
    assert re.search(r"(?m)^\s+branches:\s*\[main\]\s*$", text)
    assert workflow["permissions"] == {
        "contents": "read",
        "pages": "write",
        "id-token": "write",
    }

    build = workflow["jobs"]["build"]
    deploy = workflow["jobs"]["deploy"]
    assert build["runs-on"] == "ubuntu-latest"
    assert deploy["needs"] == "build"
    assert deploy["environment"] == {
        "name": "github-pages",
        "url": "${{ steps.deployment.outputs.page_url }}",
    }

    build_steps = build["steps"]
    assert any(step.get("uses") == "actions/checkout@v6" for step in build_steps)
    assert any(step.get("uses") == "actions/configure-pages@v5" for step in build_steps)
    assert any(
        step.get("run") == "python3 scripts/build_github_pages.py --output _site"
        for step in build_steps
    )
    upload = next(
        step for step in build_steps if step.get("uses") == "actions/upload-pages-artifact@v4"
    )
    assert upload["with"]["path"] == "_site"

    deployment = next(
        step for step in deploy["steps"] if step.get("uses") == "actions/deploy-pages@v4"
    )
    assert deployment["id"] == "deployment"


def test_pages_build_artifact_is_minimal_and_loads_adapter_before_app(tmp_path: Path) -> None:
    output = tmp_path / "site"
    subprocess.run(
        [str(PYTHON), str(BUILDER), "--output", str(output)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    index = (output / "index.html").read_text(encoding="utf-8")
    assert index.index('src="static/pages-demo.js"') < index.index('src="static/app.js"')
    assert (output / ".nojekyll").is_file()
    assert (output / "static/pages-demo.js").is_file()
    assert (output / "static/app.js").is_file()
    assert (output / "static/styles.css").is_file()
    assert (output / "static/assets/miniso-v1/mood-charm-v1.png").is_file()
    assert not (output / ".env").exists()
    assert not (output / "backend").exists()
    assert not (output / "runs").exists()
    assert not any(path.is_symlink() for path in output.rglob("*"))

    text_files = [
        path
        for path in output.rglob("*")
        if path.is_file() and path.suffix in {".html", ".css", ".js", ".json", ".md"}
    ]
    published_text = "\n".join(path.read_text(encoding="utf-8") for path in text_files)
    assert "/Users/" not in published_text
    assert "sk-sp-" not in published_text
    assert "DASHSCOPE_API_KEY" not in published_text


def test_pages_adapter_builds_input_driven_linked_contract() -> None:
    script = r"""
const pages = require('./frontend/pages-demo.js');
const app = require('./frontend/app.js');

const base = {
  brief: '面向都市年轻人的情绪价值礼赠新品',
  product_category: 'fragrance_accessory',
  custom_category: '',
  target_segment: 'young_professional',
  target_market: 'global',
  price_band: 'mid',
  ip_strategy: 'original',
  objectives: ['emotional', 'social'],
  constraints: '六周内完成小批量验证',
};
const structuredChange = {
  ...base,
  product_category: 'stationery',
  target_segment: 'student',
  target_market: 'china',
  price_band: 'entry',
  objectives: ['margin', 'supply_chain'],
};
const briefOnlyChange = { ...base, brief: '完全不同的自由文本，不应获得额外分数' };

const first = pages.buildDemoView(base, 'thread-pages-first', 'run-pages-first');
const second = pages.buildDemoView(structuredChange, 'thread-pages-second', 'run-pages-second');
const briefOnly = pages.buildDemoView(briefOnlyChange, 'thread-pages-third', 'run-pages-third');
const evaluated = pages.buildDemoView(
  { ...base, ip_strategy: 'evaluate' },
  'thread-pages-risk',
  'run-pages-risk',
);
app.validateViewContract(first, { runId: first.run_id, threadId: first.thread_id });
app.validateViewContract(second, { runId: second.run_id, threadId: second.thread_id });

const ids = first.candidate_skus.map((item) => item.id);
const scores = (view) => view.scorecards.map((item) => item.total_score);
const linked = ids.every((id) =>
  Object.hasOwn(first.launch_validation.by_candidate, id) &&
  Object.hasOwn(first.quality_audit.by_candidate, id)
);
const blocking = evaluated.scorecards.every((card) =>
  card.blocking_risks.some((risk) => risk.severity === 'high')
) && Object.values(evaluated.quality_audit.by_candidate).every((item) =>
  item.risks.some((risk) => risk.severity === 'high')
);

console.log(JSON.stringify({
  ids,
  secondIds: second.candidate_skus.map((item) => item.id),
  dimensions: first.scorecards.map((item) => item.dimensions.length),
  weights: first.scorecards.map((item) => item.dimensions.reduce((sum, row) => sum + row.weight, 0)),
  linked,
  structuredNamesChanged: JSON.stringify(first.candidate_skus.map((item) => item.name)) !==
    JSON.stringify(second.candidate_skus.map((item) => item.name)),
  structuredScoresChanged: JSON.stringify(scores(first)) !== JSON.stringify(scores(second)),
  freeTextScoresStable: JSON.stringify(scores(first)) === JSON.stringify(scores(briefOnly)),
  blocking,
  riskVerdict: evaluated.portfolio_decision.verdict,
  provider: first.provider,
  configuredProvider: first.configured_provider,
  effectiveProvider: first.effective_provider,
  model: first.model,
  disclaimer: first.data_provenance.disclaimer,
}));
"""

    result = _node(script)

    assert result["ids"] == ["C-VOC", "C-TREND", "C-WHITESPACE"]
    assert result["secondIds"] == result["ids"]
    assert result["dimensions"] == [8, 8, 8]
    assert result["weights"] == pytest.approx([1, 1, 1])
    assert result["linked"] is True
    assert result["structuredNamesChanged"] is True
    assert result["structuredScoresChanged"] is True
    assert result["freeTextScoresStable"] is True
    assert result["blocking"] is True
    assert result["riskVerdict"] == "NO_GO"
    assert result["provider"] == "offline-pages"
    assert result["configuredProvider"] == "offline-pages"
    assert result["effectiveProvider"] == "offline-pages"
    assert result["model"] == "offline-pages-deterministic"
    assert "未调用远程模型" in result["disclaimer"]
    assert "销量" in result["disclaimer"]
    assert "ROI" in result["disclaimer"]
    assert "用户研究" in result["disclaimer"]


def test_pages_adapter_issues_one_time_ticket_and_orders_stream_events() -> None:
    script = r"""
const pages = require('./frontend/pages-demo.js');
const input = {
  brief: '测试一次性票据',
  product_category: 'plush',
  custom_category: '',
  target_segment: 'gift',
  target_market: 'china',
  price_band: 'mid',
  ip_strategy: 'none',
  objectives: ['emotional'],
  constraints: '',
};
const engine = pages.createDemoEngine();
const ticket = engine.issueTicket(input, 'thread-ticket-pages');
const stream = engine.consumeTicket(ticket.stream_url);
let rejectedReuse = false;
try { engine.consumeTicket(ticket.stream_url); } catch (_error) { rejectedReuse = true; }
const report = engine.report(stream.view.run_id, 'full');

console.log(JSON.stringify({
  threadId: ticket.thread_id,
  streamUrl: ticket.stream_url,
  types: stream.events.map((event) => event.type),
  sameEnvelope: stream.events.every((event) =>
    event.run_id === stream.view.run_id && event.thread_id === stream.view.thread_id
  ),
  resultBeforeDone: stream.events.findIndex((event) => event.type === 'result') <
    stream.events.findIndex((event) => event.type === 'done'),
  rejectedReuse,
  reportHasRun: report.includes(stream.view.run_id),
  reportHasBoundary: report.includes('未调用远程模型'),
}));
"""

    result = _node(script)

    assert result["threadId"] == "thread-ticket-pages"
    assert re.fullmatch(r"api/stream\?ticket=[a-f0-9]{32}", result["streamUrl"])
    assert result["types"][0] == "trace"
    assert result["types"][-2:] == ["result", "done"]
    assert result["sameEnvelope"] is True
    assert result["resultBeforeDone"] is True
    assert result["rejectedReuse"] is True
    assert result["reportHasRun"] is True
    assert result["reportHasBoundary"] is True


@pytest.mark.skipif(not CHROME.exists(), reason="本机未安装 Google Chrome")
@pytest.mark.parametrize(
    ("width", "height"),
    [(390, 844), (375, 812), (1121, 800), (1440, 900)],
)
def test_pages_mode_real_browser_runs_switches_reports_downloads_and_fits(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    site = tmp_path / "site"
    subprocess.run(
        [str(PYTHON), str(BUILDER), "--output", str(site)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    html_path = site / "index.html"
    html = html_path.read_text(encoding="utf-8")
    probe = r"""
<script>
window.__downloads = [];
URL.createObjectURL = () => 'blob:trend2sku-pages-test';
URL.revokeObjectURL = () => {};
HTMLAnchorElement.prototype.click = function click() {
  if (this.download) window.__downloads.push(this.download);
};
window.addEventListener('load', () => {
  const brief = document.getElementById('brief');
  brief.value = '学生开学季高复购文具组合';
  document.getElementById('productCategory').value = 'stationery';
  document.getElementById('targetSegment').value = 'student';
  document.querySelector('[name="ip_strategy"][value="evaluate"]').checked = true;
  brief.dispatchEvent(new Event('input', { bubbles: true }));
  document.getElementById('runBtn').click();

  window.setTimeout(() => {
    const target = document.querySelector('[data-candidate-id="C-WHITESPACE"]');
    target?.click();
    document.getElementById('fullReportLink').dispatchEvent(
      new MouseEvent('click', { bubbles: true, cancelable: true })
    );
    window.setTimeout(() => {
      document.getElementById('reportDownloadBtn').click();
      document.getElementById('jsonDownloadBtn').click();
      const selected = document.querySelector('[role="tab"][aria-selected="true"]');
      const detail = document.getElementById('candidateDetail');
      const report = document.getElementById('reportMarkdown');
      document.body.dataset.phaseResult = document.body.dataset.phase || '';
      document.body.dataset.service = document.getElementById('serviceBadge').textContent;
      document.body.dataset.candidates = document.getElementById('candidateCount').textContent;
      document.body.dataset.selected = selected?.dataset.candidateId || '';
      document.body.dataset.detail = detail?.textContent || '';
      document.body.dataset.highRisk = String(Boolean(document.querySelector('[data-severity="high"]')));
      document.body.dataset.report = report?.textContent || '';
      document.body.dataset.downloads = window.__downloads.join('|');
      document.body.dataset.overflow = String(document.documentElement.scrollWidth > window.innerWidth);
      document.body.dataset.overflowNodes = Array.from(document.querySelectorAll('body *'))
        .filter((node) => {
          const rect = node.getBoundingClientRect();
          return rect.right > window.innerWidth + 1 || rect.left < -1;
        })
        .slice(0, 8)
        .map((node) => `${node.tagName.toLowerCase()}.${node.className || node.id}`)
        .join('|');
      document.body.dataset.probe = 'ready';
    }, 220);
  }, 280);
});
</script>
"""
    html_path.write_text(html.replace("</body>", probe + "</body>"), encoding="utf-8")

    stdout, stderr = _chrome_dump_url(
        html_path.as_uri() + "?pages_demo=1", tmp_path, width, height
    )

    body = re.search(r"<body\b([^>]*)>", stdout)
    assert body, stderr
    attrs = body.group(1)
    assert 'data-probe="ready"' in attrs
    assert 'data-phase-result="complete"' in attrs
    assert "offline-pages · 就绪" in attrs
    assert 'data-candidates="3 个候选"' in attrs
    assert 'data-selected="C-WHITESPACE"' in attrs
    assert "学生" in attrs and "文具" in attrs
    assert 'data-high-risk="true"' in attrs
    assert "GitHub Pages 离线交互演示" in attrs
    assert "未调用远程模型" in attrs
    assert ".md" in attrs and "-result.json" in attrs
    assert 'data-overflow="false"' in attrs, attrs
    assert 'data-overflow-nodes=""' in attrs, attrs
