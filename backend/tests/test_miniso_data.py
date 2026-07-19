"""名创优品兴趣消费数据与公开趋势信号回归测试。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from miniso_studio.infrastructure.data import loader
from miniso_studio.infrastructure.data.connectors import fetch_trends
from miniso_studio.infrastructure.data.loader import load_evidence, split_by_brand
from miniso_studio.infrastructure.data.retail_reviews import normalize_public_review


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_BRANDS = {"MINISO", "POP MART", "DAISO", "MUJI", "Flying Tiger"}


def _sample_rows() -> list[dict]:
    rows: list[dict] = []
    for path in sorted((PROJECT_ROOT / "data" / "sample").glob("*.jsonl")):
        rows.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
    return rows


def test_interest_goods_dataset_has_target_and_four_competitors():
    evidences = load_evidence("interest_goods")
    split = split_by_brand(evidences)

    assert len(evidences) >= 360
    assert len(split["target"]) >= 120
    assert {item.brand for item in split["target"]} == {"MINISO"}
    assert set(split["competitors"]) == EXPECTED_BRANDS - {"MINISO"}
    assert all(split["competitors"].values())
    assert not split["other"]


def test_sample_rows_are_labeled_stable_and_explicitly_demo_only():
    rows = _sample_rows()

    assert len(rows) >= 360
    assert {row["brand"] for row in rows} == EXPECTED_BRANDS
    assert {row["category"] for row in rows} == {"interest_goods"}
    assert len({row["source_id"] for row in rows}) == len(rows)
    assert all(row["source_id"].startswith("demo-") for row in rows)
    assert all(row["url"].startswith("demo://synthetic/") for row in rows)


def test_loader_filters_category_and_matches_brand_case_insensitively(tmp_path, monkeypatch):
    sample = tmp_path / "sample"
    sample.mkdir()
    rows = [
        {
            "source_id": "demo-miniso-interest",
            "brand": "miniso",
            "category": "INTEREST_GOODS",
            "text": "设计很可爱",
        },
        {
            "source_id": "demo-popmart-interest",
            "brand": "pop mart",
            "category": "interest_goods",
            "text": "系列值得收藏",
        },
        {
            "source_id": "demo-miniso-audio",
            "brand": "MINISO",
            "category": "audio",
            "text": "声音清晰",
        },
    ]
    path = sample / "mixed.jsonl"
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    monkeypatch.setattr(loader, "_data_root", lambda: tmp_path)

    evidences = load_evidence("interest_goods")
    split = split_by_brand(evidences)

    assert [item.source_id for item in evidences] == [
        "demo-miniso-interest",
        "demo-popmart-interest",
    ]
    assert [item.brand for item in split["target"]] == ["MINISO"]
    assert [item.brand for item in split["competitors"]["POP MART"]] == ["POP MART"]


def test_loader_rejects_duplicate_review_source_ids(tmp_path, monkeypatch):
    sample = tmp_path / "sample"
    sample.mkdir()
    duplicate_id = "duplicated-review-id"
    rows = [
        {
            "source_id": duplicate_id,
            "brand": "MINISO",
            "category": "interest_goods",
            "text": "第一条样本",
        },
        {
            "source_id": duplicate_id,
            "brand": "DAISO",
            "category": "interest_goods",
            "text": "内容不同的第二条样本",
        },
    ]
    (sample / "duplicates.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    monkeypatch.setattr(loader, "_data_root", lambda: tmp_path)

    with pytest.raises(RuntimeError, match=duplicate_id):
        load_evidence("interest_goods")


def test_offline_trends_are_traceable_to_dated_official_sources():
    trends, evidence = fetch_trends(["IP联名", "情绪价值", "社交传播", "全球本地化"])
    evidence_by_id = {item.source_id: item for item in evidence}
    trend_names = {item.name for item in trends}

    assert {"IP联名", "情绪价值", "社交传播", "全球本地化"} <= trend_names
    assert all(item.evidence_ids for item in trends)
    assert all(source_id in evidence_by_id for item in trends for source_id in item.evidence_ids)
    assert all(evidence_by_id[source_id].url for item in trends for source_id in item.evidence_ids)

    official_text = " ".join(item.text for item in evidence)
    official_urls = " ".join(item.url or "" for item in evidence)
    assert "2026-05-26" in official_text
    assert "2026-04-24" in official_text
    assert "42.0%" in official_text
    assert "March-Quarter-2026" in official_urls
    assert "Annual+Report+2025" in official_urls


def test_public_review_normalizer_produces_loader_schema_without_enterprise_claims():
    normalized = normalize_public_review(
        {
            "id": "public-42",
            "title": "Character storage box",
            "content": "Cute and practical.",
            "score": "4",
            "created_at": "2026-01-03",
            "helpful": "7",
        },
        brand="miniso",
        source_url="https://example.org/open-reviews.jsonl",
    )

    assert normalized["source_id"].startswith("public-review-public-42-")
    assert {key: value for key, value in normalized.items() if key != "source_id"} == {
        "source_type": "review",
        "brand": "MINISO",
        "product": "Character storage box",
        "category": "interest_goods",
        "rating": 4.0,
        "text": "Cute and practical.",
        "date": "2026-01-03",
        "helpful_votes": 7,
        "url": "https://example.org/open-reviews.jsonl",
    }


def test_external_review_ids_are_stable_and_unique_across_sources_and_brands():
    row = {"id": "shared-42", "content": "Cute storage box."}
    miniso_a = normalize_public_review(
        row,
        brand="MINISO",
        source_url="https://source-a.example/reviews.jsonl",
    )["source_id"]
    miniso_a_repeat = normalize_public_review(
        row,
        brand="miniso",
        source_url="https://source-a.example/reviews.jsonl",
    )["source_id"]
    miniso_b = normalize_public_review(
        row,
        brand="MINISO",
        source_url="https://source-b.example/reviews.jsonl",
    )["source_id"]
    competitor_a = normalize_public_review(
        row,
        brand="DAISO",
        source_url="https://source-a.example/reviews.jsonl",
    )["source_id"]

    assert miniso_a == miniso_a_repeat
    assert len({miniso_a, miniso_b, competitor_a}) == 3
    assert all(source_id.startswith("public-review-shared-42-") for source_id in {
        miniso_a,
        miniso_b,
        competitor_a,
    })


def test_non_ascii_external_review_id_has_stable_safe_fallback():
    kwargs = {
        "brand": "MINISO",
        "source_url": "https://example.org/chinese-reviews.jsonl",
    }
    first = normalize_public_review({"id": "评论一号", "content": "包装精美"}, **kwargs)[
        "source_id"
    ]
    repeat = normalize_public_review({"id": "评论一号", "content": "内容不同"}, **kwargs)[
        "source_id"
    ]
    other = normalize_public_review({"id": "评论二号", "content": "包装精美"}, **kwargs)[
        "source_id"
    ]

    assert first == repeat
    assert first.startswith("public-review-id-")
    assert first != other
