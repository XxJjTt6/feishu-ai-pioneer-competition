"""结构化决策输入在 API、SSE、视图和报告中的契约测试。"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from miniso_studio.common.config import settings
from miniso_studio.starter import api


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("MINISO_LLM_PROVIDER", "offline")
    monkeypatch.setenv("MINISO_TRACE_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("MINISO_HITL", "false")
    settings.cache_clear()
    api._reset_runtime_state()
    yield
    api._reset_runtime_state()
    settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(api.app)


def _result_event(response) -> dict:
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    return next(event for event in events if event["type"] == "result")


def test_sync_api_echoes_normalized_decision_input(client):
    payload = {
        "brief": "  设计开学礼赠  ",
        "product_category": "stationery",
        "custom_category": "会被规范化清空",
        "target_segment": "student",
        "target_market": "china",
        "price_band": "entry",
        "ip_strategy": "original",
        "objectives": ["social", "margin", "social"],
        "constraints": "  单件包装，四周交付  ",
    }

    response = client.post("/api/run", json=payload)

    assert response.status_code == 200
    assert response.json()["decision_input"] == {
        "brief": "设计开学礼赠",
        "product_category": "stationery",
        "custom_category": "",
        "target_segment": "student",
        "target_market": "china",
        "price_band": "entry",
        "ip_strategy": "original",
        "objectives": ["social", "margin"],
        "constraints": "单件包装，四周交付",
    }


def test_two_api_inputs_change_candidates_validation_risks_and_reports(client):
    plush = client.post(
        "/api/run",
        json={
            "brief": "为亲子家庭做节日陪伴礼物",
            "product_category": "plush",
            "target_segment": "family",
            "target_market": "china",
            "price_band": "mid",
            "ip_strategy": "licensed",
            "objectives": ["emotional", "supply_chain"],
            "constraints": "可拆洗，避免细小部件",
        },
    )
    stationery = client.post(
        "/api/run",
        json={
            "brief": "为学生做开学季社交文具",
            "product_category": "stationery",
            "target_segment": "student",
            "target_market": "southeast_asia",
            "price_band": "entry",
            "ip_strategy": "original",
            "objectives": ["social", "localization"],
            "constraints": "适配潮湿气候和校园渠道",
        },
    )

    assert plush.status_code == stationery.status_code == 200
    plush_view = plush.json()
    stationery_view = stationery.json()
    assert [item["id"] for item in plush_view["candidate_skus"]] == [
        "C-VOC",
        "C-TREND",
        "C-WHITESPACE",
    ]
    assert [item["id"] for item in stationery_view["candidate_skus"]] == [
        "C-VOC",
        "C-TREND",
        "C-WHITESPACE",
    ]
    assert {item["name"] for item in plush_view["candidate_skus"]} != {
        item["name"] for item in stationery_view["candidate_skus"]
    }
    assert {
        tuple(item["key_features"]) for item in plush_view["candidate_skus"]
    } != {
        tuple(item["key_features"]) for item in stationery_view["candidate_skus"]
    }
    assert (
        plush_view["launch_validation"]["by_candidate"]["C-VOC"]["interviews"]
        != stationery_view["launch_validation"]["by_candidate"]["C-VOC"]["interviews"]
    )
    assert (
        plush_view["quality_audit"]["by_candidate"]["C-VOC"]
        != stationery_view["quality_audit"]["by_candidate"]["C-VOC"]
    )

    plush_report = client.get(
        "/api/report", params={"run_id": plush_view["run_id"], "kind": "full"}
    ).json()["markdown"]
    stationery_report = client.get(
        "/api/report", params={"run_id": stationery_view["run_id"], "kind": "opening"}
    ).json()["markdown"]
    assert "本轮决策输入" in plush_report
    assert "亲子家庭" in plush_report
    assert "毛绒" in plush_report
    assert "学生" in stationery_report
    assert "文创文具" in stationery_report
    assert plush_report != stationery_report


def test_sse_propagates_every_decision_field(client):
    params = [
        ("brief", "设计香氛配饰"),
        ("product_category", "fragrance_accessory"),
        ("target_segment", "young_professional"),
        ("target_market", "global"),
        ("price_band", "premium"),
        ("ip_strategy", "evaluate"),
        ("objectives", "emotional"),
        ("objectives", "margin"),
        ("constraints", "礼盒可回收"),
        ("thread_id", "dynamic-sse-contract"),
        ("hitl", "false"),
    ]

    response = client.get("/api/stream", params=params)

    assert response.status_code == 200
    view = _result_event(response)["view"]
    assert view["thread_id"] == "dynamic-sse-contract"
    assert view["decision_input"] == {
        "brief": "设计香氛配饰",
        "product_category": "fragrance_accessory",
        "custom_category": "",
        "target_segment": "young_professional",
        "target_market": "global",
        "price_band": "premium",
        "ip_strategy": "evaluate",
        "objectives": ["emotional", "margin"],
        "constraints": "礼盒可回收",
    }


def test_sse_ticket_keeps_free_text_out_of_url_and_is_one_use(client):
    payload = {
        "brief": "未公开新品决策简报",
        "product_category": "other",
        "custom_category": "旅行收纳配件",
        "target_segment": "young_professional",
        "target_market": "global",
        "price_band": "mid",
        "ip_strategy": "original",
        "objectives": ["margin", "localization"],
        "constraints": "六周内交付并控制首单成本",
        "thread_id": "ticket-sse-contract",
        "hitl": False,
    }
    ticket_response = client.post("/api/stream/ticket", json=payload)

    assert ticket_response.status_code == 200
    ticket = ticket_response.json()
    assert ticket["thread_id"] == payload["thread_id"]
    assert ticket["stream_url"].startswith("api/stream?ticket=")
    assert all(
        value not in ticket["stream_url"]
        for value in (payload["brief"], payload["custom_category"], payload["constraints"])
    )

    response = client.get("/" + ticket["stream_url"])
    assert response.status_code == 200
    assert _result_event(response)["view"]["decision_input"] == {
        key: value for key, value in payload.items() if key not in {"thread_id", "hitl"}
    }
    assert client.get("/" + ticket["stream_url"]).status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"brief": "设计新品", "product_category": "unknown"},
        {
            "brief": "设计新品",
            "product_category": "other",
            "custom_category": "   ",
        },
        {"brief": "设计新品", "objectives": []},
        {
            "brief": "设计新品",
            "objectives": [
                "emotional",
                "social",
                "margin",
                "supply_chain",
                "localization",
            ],
        },
        {"brief": "设计新品", "constraints": "约" * 301},
    ],
)
def test_sync_api_rejects_invalid_structured_input(client, payload):
    assert client.post("/api/run", json=payload).status_code == 422


def test_sse_rejects_missing_custom_category_and_unknown_enum(client):
    missing_custom = client.get(
        "/api/stream",
        params={"brief": "设计新品", "product_category": "other"},
    )
    unknown_market = client.get(
        "/api/stream",
        params={"brief": "设计新品", "target_market": "moon"},
    )

    assert missing_custom.status_code == 422
    assert unknown_market.status_code == 422
