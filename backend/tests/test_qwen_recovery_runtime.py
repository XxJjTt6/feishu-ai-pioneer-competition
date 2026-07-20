"""公网断线恢复后的运行阶段状态契约。"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_recovered_result_closes_every_successful_pipeline_stage() -> None:
    completed = subprocess.run(
        [
            "node",
            "-e",
            """
const app = require('./frontend/app-qwen-resilient.js');
let runtime = app.reduceRuntime(app.createRuntimeSnapshot(), { type: 'run_started' });
runtime = app.reduceRuntime(runtime, { type: 'trace', event: { node: 'insight', kind: 'end' } });
runtime = app.reduceRuntime(runtime, { type: 'result_received' });
console.log(JSON.stringify({
  phase: runtime.phase,
  terminal: runtime.terminal,
  stages: runtime.stages,
}));
""",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert result["phase"] == "complete"
    assert result["terminal"] is True
    assert set(result["stages"].values()) == {"done"}
