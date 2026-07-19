"""可选的公开零售评论下载与标准化接口。

调用方必须确认来源允许下载和研究使用。本模块只处理调用方明确提供的公开 JSON 或
JSONL URL；仓库自带样本是另行生成的合成演示数据，不是 MINISO 或竞品企业数据。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable, List, Mapping
from urllib.request import Request, urlopen

from miniso_studio.common.config import settings
from miniso_studio.common.logging import log
from miniso_studio.infrastructure.data.loader import TARGET_BRAND, canonical_brand


def _first(row: Mapping[str, object], *keys: str, default: object = "") -> object:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return default


def _number(value: object, *, integer: bool = False) -> float | int | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0 if integer else None
    return int(number) if integer else number


def _stable_source_id(
    row: Mapping[str, object], brand: str, source_url: str, index: int
) -> str:
    external_id = str(_first(row, "source_id", "review_id", "id", "uuid")).strip()
    if external_id:
        safe_id = re.sub(r"[^a-zA-Z0-9._-]+", "-", external_id).strip("-")[:48]
        identity = f"{brand}|{source_url}|{external_id}"
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        return f"public-review-{safe_id or 'id'}-{digest}"
    identity = "|".join(
        [
            brand,
            source_url,
            str(_first(row, "product", "product_name", "title", "item_name")),
            str(_first(row, "text", "content", "review", "body")),
            str(_first(row, "date", "created_at", "timestamp")),
            str(index),
        ]
    )
    return f"public-review-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:20]}"


def normalize_public_review(
    row: Mapping[str, object],
    *,
    brand: str,
    source_url: str,
    index: int = 0,
    category: str = "interest_goods",
) -> dict:
    """把常见公开评论字段标准化为 loader 可读取的 JSONL schema。"""
    normalized_brand = canonical_brand(brand)
    return {
        "source_id": _stable_source_id(row, normalized_brand, source_url, index),
        "source_type": "review" if normalized_brand == TARGET_BRAND else "competitor",
        "brand": normalized_brand,
        "product": str(_first(row, "product", "product_name", "title", "item_name")),
        "category": category,
        "rating": _number(_first(row, "rating", "score", "stars")),
        "text": str(_first(row, "text", "content", "review", "body")),
        "date": str(_first(row, "date", "created_at", "timestamp")),
        "helpful_votes": _number(
            _first(row, "helpful_votes", "helpful_vote", "helpful", default=0), integer=True
        ),
        "url": str(_first(row, "url", "review_url", default=source_url)),
    }


def _rows_from_payload(payload: str) -> Iterable[Mapping[str, object]]:
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        for line in payload.splitlines():
            if line.strip():
                row = json.loads(line)
                if isinstance(row, dict):
                    yield row
        return

    if isinstance(decoded, list):
        candidates = decoded
    elif isinstance(decoded, dict):
        candidates = next(
            (decoded[key] for key in ("reviews", "items", "data") if isinstance(decoded.get(key), list)),
            [decoded],
        )
    else:
        candidates = []
    yield from (row for row in candidates if isinstance(row, dict))


def download_public_reviews(
    source_url: str,
    *,
    brand: str,
    max_reviews: int = 800,
    timeout: float = 30.0,
) -> List[dict]:
    """下载公开 JSON/JSONL 并返回标准化记录，不自动声称其代表企业全量用户。"""
    request = Request(source_url, headers={"User-Agent": "miniso-studio-public-research/1.0"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL 由调用方明确提供
        payload = response.read().decode("utf-8")
    rows = list(_rows_from_payload(payload))[:max_reviews]
    return [
        normalize_public_review(row, brand=brand, source_url=source_url, index=index)
        for index, row in enumerate(rows)
    ]


def download_and_write(
    source_url: str,
    *,
    brand: str,
    max_reviews: int = 800,
) -> Path:
    """下载并写入 ``data/processed``，返回目标路径。"""
    rows = download_public_reviews(source_url, brand=brand, max_reviews=max_reviews)
    out_dir = Path(settings().data_dir) / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = re.sub(r"[^a-zA-Z0-9]+", "_", canonical_brand(brand)).strip("_")
    path = out_dir / f"{filename}.jsonl"
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(
                json.dumps({**row, "data_provenance": "public"}, ensure_ascii=False)
                + "\n"
            )
    log.bind(node="data").info(f"写出 {len(rows)} 条公开来源评论 -> {path}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="下载调用方指定的公开零售评论 JSON/JSONL")
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--brand", required=True)
    parser.add_argument("--max-reviews", type=int, default=800)
    args = parser.parse_args()
    download_and_write(args.source_url, brand=args.brand, max_reviews=args.max_reviews)


if __name__ == "__main__":
    main()
