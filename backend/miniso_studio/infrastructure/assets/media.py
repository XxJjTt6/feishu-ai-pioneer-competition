"""离线可选媒体适配器。"""
from __future__ import annotations

import hashlib
from pathlib import Path

from miniso_studio.common.config import settings


def _write_request(kind: str, payload: str) -> None:
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    output = (
        Path(settings().project_root) / "assets" / "requests" / f"{kind}-{digest}.txt"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload, encoding="utf-8")


def generate_concept_image(prompt: str) -> None:
    if settings().enable_media:
        _write_request("concept-image", prompt)


def synthesize_narration(text: str) -> None:
    if settings().enable_media:
        _write_request("narration", text)
