"""Qwen 动态前端的 GitHub Pages 构建与官方 Deployment 契约。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
PYTHON = Path(sys.executable)
BUILDER = ROOT / "scripts/build_qwen_pages.py"
WORKFLOW = ROOT / ".github/workflows/deploy-qwen-pages.yml"


def test_qwen_pages_has_distinct_builder_and_official_deployment_workflow() -> None:
    assert BUILDER.is_file()
    assert WORKFLOW.is_file()

    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert workflow["permissions"] == {
        "contents": "read",
        "pages": "write",
        "id-token": "write",
    }
    assert workflow["jobs"]["deploy"]["environment"] == {
        "name": "github-pages",
        "url": "${{ steps.deployment.outputs.page_url }}",
    }
    build_steps = workflow["jobs"]["build"]["steps"]
    command = next(step["run"] for step in build_steps if "build_qwen_pages.py" in step.get("run", ""))
    assert "vars.TREND2SKU_API_BASE" in command
    assert any(step.get("uses") == "actions/upload-pages-artifact@v4" for step in build_steps)
    assert any(step.get("uses") == "actions/deploy-pages@v4" for step in workflow["jobs"]["deploy"]["steps"])


def test_qwen_pages_builder_publishes_dynamic_frontend_without_secrets_or_offline_adapter(
    tmp_path: Path,
) -> None:
    output = tmp_path / "site"
    subprocess.run(
        [
            str(PYTHON),
            str(BUILDER),
            "--output",
            str(output),
            "--api-base",
            "https://api.example.test",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    index = (output / "index.html").read_text(encoding="utf-8")
    assert 'meta name="trend2sku-api-base" content="https://api.example.test"' in index
    assert 'src="static/app-qwen-live.js"' in index
    assert 'href="static/styles-qwen-live.css"' in index
    assert "offline-pages" not in index
    assert "pages-demo.js" not in index
    assert (output / ".nojekyll").is_file()
    assert (output / "static/app-qwen-live.js").is_file()
    assert (output / "static/styles-qwen-live.css").is_file()
    assert (output / "static/assets/miniso-v1/mood-charm-v1.png").is_file()
    assert not (output / ".env").exists()
    assert not (output / "backend").exists()
    assert not (output / "runs").exists()
    assert not any(path.is_symlink() for path in output.rglob("*"))

    published_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in output.rglob("*")
        if path.is_file() and path.suffix in {".html", ".css", ".js", ".json", ".md"}
    )
    assert "/Users/" not in published_text
    assert "sk-sp-" not in published_text
    assert "QWEN_API_KEY" not in published_text


@pytest.mark.parametrize("api_base", ["http://api.example.test", "javascript:alert(1)", "https://user:pass@example.test"])
def test_qwen_pages_builder_rejects_unsafe_api_base(tmp_path: Path, api_base: str) -> None:
    completed = subprocess.run(
        [
            str(PYTHON),
            str(BUILDER),
            "--output",
            str(tmp_path / "site"),
            "--api-base",
            api_base,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert api_base not in completed.stdout
    assert api_base not in completed.stderr
