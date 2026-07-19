"""可选媒体请求适配器测试。"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from miniso_studio.infrastructure.assets import media


def _digest(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_disabled_media_is_a_noop(monkeypatch, tmp_path):
    monkeypatch.setattr(
        media,
        "settings",
        lambda: SimpleNamespace(enable_media=False, project_root=str(tmp_path)),
    )

    assert media.generate_concept_image("concept") is None
    assert media.synthesize_narration("narration") is None
    assert not (tmp_path / "assets").exists()


def test_enabled_media_records_distinct_requests_without_fake_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(
        media,
        "settings",
        lambda: SimpleNamespace(enable_media=True, project_root=str(tmp_path)),
    )
    prompts = ["第一个概念", "第二个概念"]
    narration = "产品旁白"

    assert media.generate_concept_image(prompts[0]) is None
    assert media.generate_concept_image(prompts[1]) is None
    assert media.synthesize_narration(narration) is None

    request_dir = tmp_path / "assets" / "requests"
    expected = {
        f"concept-image-{_digest(prompts[0])}.txt": prompts[0],
        f"concept-image-{_digest(prompts[1])}.txt": prompts[1],
        f"narration-{_digest(narration)}.txt": narration,
    }
    files = {
        path.name: path.read_text(encoding="utf-8")
        for path in request_dir.glob("*.txt")
    }

    assert files == expected
