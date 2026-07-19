"""兴趣消费评论数据加载（Infrastructure 层）。

优先加载 ``data/processed`` 中明确标注品类的公开数据；没有处理后文件时，
回退到仓库内可复现的合成演示样本。加载器统一品牌大小写并真正按 category 过滤。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from miniso_studio.common.config import settings
from miniso_studio.common.errors import FatalPipelineError
from miniso_studio.common.logging import log
from miniso_studio.common.models import Evidence, SourceType

TARGET_BRAND = "MINISO"
COMPETITOR_BRANDS = ["POP MART", "DAISO", "MUJI", "Flying Tiger"]
_CANONICAL_BRANDS = {
    brand.casefold(): brand for brand in [TARGET_BRAND, *COMPETITOR_BRANDS]
}


class EvidenceIdConflictError(FatalPipelineError):
    """同一 ``source_id`` 指向重复或互相矛盾的证据。"""


def index_evidence_by_source_id(
    evidences: Iterable[Evidence],
    *,
    context: str,
    allow_identical_duplicates: bool = False,
) -> Dict[str, Evidence]:
    """建立不会静默覆盖的证据索引。"""
    indexed: Dict[str, Evidence] = {}
    for evidence in evidences:
        existing = indexed.get(evidence.source_id)
        if existing is None:
            indexed[evidence.source_id] = evidence
            continue
        identical = existing.model_dump(mode="json") == evidence.model_dump(mode="json")
        if allow_identical_duplicates and identical:
            continue
        raise EvidenceIdConflictError(
            f"{context}存在重复 source_id={evidence.source_id}，拒绝覆盖证据"
        )
    return indexed


def _data_root() -> Path:
    return Path(settings().data_dir)


def canonical_brand(value: object) -> str:
    """将已配置品牌做忽略大小写的规范化，未知品牌保留原值。"""
    brand = str(value or "unknown").strip()
    return _CANONICAL_BRANDS.get(brand.casefold(), brand)


def _read_jsonl(path: Path) -> List[dict]:
    rows: List[dict] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                log.bind(node="data").warning(f"跳过坏行 {path.name}: {exc}")
    return rows


def _row_to_evidence(row: dict, default_provenance: str = "unspecified") -> Evidence:
    brand = canonical_brand(row.get("brand") or row.get("store"))
    source_type = row.get("source_type")
    if source_type not in {item.value for item in SourceType}:
        source_type = (
            SourceType.REVIEW.value
            if brand.casefold() == TARGET_BRAND.casefold()
            else SourceType.COMPETITOR.value
        )
    return Evidence(
        source_id=str(row.get("source_id") or row.get("id") or row.get("asin") or id(row)),
        source_type=SourceType(source_type),
        brand=brand,
        product=str(row.get("product") or row.get("title") or ""),
        rating=row.get("rating"),
        text=str(row.get("text") or row.get("review") or ""),
        date=row.get("date") or row.get("timestamp"),
        url=row.get("url"),
        helpful_votes=int(row.get("helpful_votes") or row.get("helpful_vote") or 0),
        data_provenance=str(row.get("data_provenance") or default_provenance),
    )


def _jsonl_files(directory: Path) -> List[Path]:
    return sorted(
        path
        for path in directory.glob("*.jsonl")
        if not path.name.startswith(".")
    )


def load_evidence(category: str = "interest_goods") -> List[Evidence]:
    """加载与 ``category`` 精确匹配的 Evidence（忽略大小写和首尾空白）。"""
    root = _data_root()
    processed = root / "processed"
    sample = root / "sample"
    files = _jsonl_files(processed) if processed.exists() else []
    source_label = "processed(公开数据)"
    if not files:
        files = _jsonl_files(sample) if sample.exists() else []
        source_label = "sample(合成演示)"
    default_provenance = "public" if source_label.startswith("processed") else "synthetic_demo"

    requested_category = category.strip().casefold()
    evidences: List[Evidence] = []
    for path in files:
        for row in _read_jsonl(path):
            row_category = str(row.get("category") or "").strip().casefold()
            if row_category != requested_category:
                continue
            evidence = _row_to_evidence(row, default_provenance=default_provenance)
            if evidence.text:
                evidences.append(evidence)

    index_evidence_by_source_id(
        evidences,
        context=f"{category} 评论集合",
    )

    log.bind(node="data").info(
        f"加载 {len(evidences)} 条 Evidence（来源={source_label}，category={category}）"
    )
    return evidences


def split_by_brand(evidences: List[Evidence]) -> Dict[str, object]:
    """切分目标品牌、四个竞品和未配置品牌。"""
    target: List[Evidence] = []
    competitors: Dict[str, List[Evidence]] = {brand: [] for brand in COMPETITOR_BRANDS}
    other: List[Evidence] = []
    for evidence in evidences:
        brand = canonical_brand(evidence.brand)
        if brand == TARGET_BRAND:
            target.append(evidence)
        elif brand in competitors:
            competitors[brand].append(evidence)
        else:
            other.append(evidence)
    return {"target": target, "competitors": competitors, "other": other}


def filter_evidence(evidences: List[Evidence], brand: Optional[str] = None) -> List[Evidence]:
    if brand is None:
        return evidences
    requested_brand = canonical_brand(brand).casefold()
    return [item for item in evidences if canonical_brand(item.brand).casefold() == requested_brand]
