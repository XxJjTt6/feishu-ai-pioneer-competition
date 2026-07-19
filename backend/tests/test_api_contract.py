"""Trend2SKU 服务契约、HITL 生命周期与报告边界测试。"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from miniso_studio.application.graph.checkpoint import JsonCheckpointer
from miniso_studio.application.reporting import build_data_provenance, to_view
from miniso_studio.application.runner import run_studio
from miniso_studio.common.config import settings
from miniso_studio.common.models import Evidence, LLMResponse, SourceType
from miniso_studio.infrastructure.data.loader import load_evidence
from miniso_studio.infrastructure.llm.gateway import LLMGateway
from miniso_studio.infrastructure.observability.trace import Tracer
from miniso_studio.starter import api


EXPECTED_VIEW_KEYS = {
    "schema_version",
    "product",
    "run_id",
    "thread_id",
    "status",
    "awaiting_human",
    "elapsed_seconds",
    "provider",
    "configured_provider",
    "effective_provider",
    "category",
    "target_brand",
    "data_provenance",
    "candidate_skus",
    "scorecards",
    "winner_scorecard",
    "portfolio_decision",
    "trend_signals",
    "consumer_insights",
    "launch_validation",
    "quality_audit",
    "evidence_index",
    "audit",
}
EXPECTED_DIMENSIONS = [
    "trend_fit",
    "demand_strength",
    "differentiation",
    "social_virality",
    "margin_potential",
    "supply_feasibility",
    "ip_compliance",
    "localization_fit",
]
STALE_RUNTIME_TERMS = (
    "Anker",
    "安克",
    "soundcore",
    "TWS",
    "Thus",
    "JML",
    "BEES",
    "AMI",
    "AIME",
    "eufy",
    "Amazon",
    "真实评论",
    "真实证据",
)


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


def _assert_uuid_level_id(value: str, prefix: str) -> None:
    assert value.startswith(prefix)
    UUID(value.removeprefix(prefix))


def _sse_events(response) -> list[dict]:
    events = []
    for line in response.text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line.removeprefix("data: ")))
    return events


def _referenced_evidence_ids(value) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "evidence_ids" and isinstance(nested, list):
                found.update(item for item in nested if isinstance(item, str))
            else:
                found.update(_referenced_evidence_ids(nested))
    elif isinstance(value, list):
        for nested in value:
            found.update(_referenced_evidence_ids(nested))
    return found


def test_health_identifies_product_schema_and_provider(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "product": "Trend2SKU",
        "schema_version": "1.0",
        "provider": "offline",
        "configured_provider": "offline",
        "effective_provider": "offline",
    }


def test_sync_run_returns_complete_ranked_decision_view(client):
    response = client.post(
        "/api/run",
        json={"brief": "为全球门店设计可验证的本地限定兴趣消费组合", "category": "interest_goods"},
    )

    assert response.status_code == 200
    view = response.json()
    assert EXPECTED_VIEW_KEYS <= view.keys()
    assert view["schema_version"] == "1.0"
    assert view["product"] == "Trend2SKU"
    assert view["status"] == "completed"
    assert view["awaiting_human"] is False
    assert view["category"] == "interest_goods"
    assert view["target_brand"] == "MINISO"
    assert view["provider"] == "offline"
    assert view["configured_provider"] == "offline"
    assert view["effective_provider"] == "offline"
    _assert_uuid_level_id(view["run_id"], "run-")
    _assert_uuid_level_id(view["thread_id"], "thread-")

    assert len(view["candidate_skus"]) == len(view["scorecards"]) >= 3
    assert view["scorecards"] == sorted(
        view["scorecards"], key=lambda card: (-card["total_score"], card["concept_id"])
    )
    assert all(
        [dimension["key"] for dimension in card["dimensions"]] == EXPECTED_DIMENSIONS
        for card in view["scorecards"]
    )
    winner = view["winner_scorecard"]
    decision = view["portfolio_decision"]
    assert winner == view["scorecards"][0]
    assert winner["concept_id"] == decision["winner_id"]
    assert winner["recommendation"] == decision["verdict"]
    assert decision["winner_id"] in {item["id"] for item in view["candidate_skus"]}
    assert decision["prfaq"]["headline"]

    by_candidate = view["launch_validation"]["by_candidate"]
    quality_by_candidate = view["quality_audit"]["by_candidate"]
    candidate_ids = {item["id"] for item in view["candidate_skus"]}
    assert set(by_candidate) == candidate_ids
    assert set(quality_by_candidate) == candidate_ids
    assert all({"interviews", "nps", "average_acceptance"} <= item.keys() for item in by_candidate.values())
    assert view["launch_validation"]["winner"]["concept_id"] == decision["winner_id"]
    assert view["quality_audit"]["winner_assessment"]["concept_id"] == decision["winner_id"]


@pytest.mark.parametrize(
    "payload",
    [
        {"brief": ""},
        {"brief": "   "},
        {"brief": "x" * 501},
        {"category": "audio"},
        {"thread_id": "../escape"},
        {"thread_id": "含中文"},
    ],
)
def test_run_rejects_invalid_request_contract(client, payload):
    assert client.post("/api/run", json=payload).status_code == 422


def test_evidence_index_resolves_all_visible_references_and_marks_demo_data(client):
    view = client.post("/api/run", json={}).json()
    referenced = _referenced_evidence_ids(
        {
            "candidate_skus": view["candidate_skus"],
            "scorecards": view["scorecards"],
            "portfolio_decision": view["portfolio_decision"],
            "trend_signals": view["trend_signals"],
            "consumer_insights": view["consumer_insights"],
            "launch_validation": view["launch_validation"],
            "quality_audit": view["quality_audit"],
        }
    )
    index = view["evidence_index"]

    assert referenced
    assert referenced <= set(index)
    assert all(item["source_id"] == source_id for source_id, item in index.items())
    assert all(
        {"source_type", "brand", "product", "rating", "text", "date", "url", "helpful_votes", "is_demo"}
        <= item.keys()
        for item in index.values()
    )
    assert any(item["is_demo"] for item in index.values())
    assert all(item["url"] is None for item in index.values() if item["is_demo"])


def test_data_provenance_is_explicit_and_uses_latest_official_cutoff(client):
    view = client.post("/api/run", json={}).json()
    provenance = view["data_provenance"]

    assert provenance["review_scope"] == "synthetic_demo"
    assert provenance["review_count"] == 400
    assert provenance["official_trend_cutoff"] == "2026-05-26"
    assert provenance["disclaimer"] == (
        "400 条固定种子合成离线演示，不是企业内部数据或真实用户评论，不代表爆款概率/销售/ROI"
    )
    assert {source["date"] for source in provenance["official_trend_sources"]} == {
        "2026-04-24",
        "2026-05-26",
    }
    assert all(source["url"].startswith("https://ir.miniso.com/") for source in provenance["official_trend_sources"])
    hypotheses = {
        item["name"]: item["summary"]
        for item in view["trend_signals"]
        if item["name"] in {"情绪价值", "社交传播"}
    }
    assert set(hypotheses) == {"情绪价值", "社交传播"}
    assert all("研究假设" in summary for summary in hypotheses.values())


def test_loader_preserves_source_provenance():
    evidences = load_evidence("interest_goods")

    assert len(evidences) == 400
    assert {item.data_provenance for item in evidences} == {"synthetic_demo"}


def test_missing_target_evidence_fails_without_relabeling_competitors(client, monkeypatch):
    from miniso_studio.application import runner

    only_daiso = [
        Evidence(
            source_id="daiso-only",
            source_type=SourceType.COMPETITOR,
            brand="DAISO",
            text="包装实用但设计普通",
            data_provenance="public",
        )
    ]
    monkeypatch.setattr(runner, "load_evidence", lambda _category: only_daiso)

    with pytest.raises(RuntimeError, match="MINISO.*目标样本"):
        run_studio(thread_id="missing-target-direct")

    response = client.post(
        "/api/run",
        json={"thread_id": "missing-target-api"},
    )
    assert response.status_code == 422
    assert "MINISO" in response.json()["detail"]
    assert only_daiso[0].brand == "DAISO"
    assert only_daiso[0].source_type == SourceType.COMPETITOR


def test_target_and_competitor_sets_never_overlap_and_provenance_deduplicates_identical_evidence():
    artifacts = run_studio(thread_id="disjoint-review-sets")
    target_ids = {item.source_id for item in artifacts.state.target_evidences}
    competitor_ids = {
        item.source_id
        for values in artifacts.state.competitor_evidences.values()
        for item in values
    }
    expected_count = len(target_ids | competitor_ids)

    assert target_ids
    assert target_ids.isdisjoint(competitor_ids)
    assert build_data_provenance(artifacts)["review_count"] == expected_count

    artifacts.state.target_evidences.append(artifacts.state.target_evidences[0])
    assert build_data_provenance(artifacts)["review_count"] == expected_count
    assert to_view(artifacts)["data_provenance"]["review_count"] == expected_count


def test_official_trend_id_cannot_be_overwritten_by_competitor_evidence(monkeypatch):
    from miniso_studio.application import runner

    malicious_id = "trend-miniso-q1-2026-ip"
    evidences = load_evidence("interest_goods")
    evidences.append(
        Evidence(
            source_id=malicious_id,
            source_type=SourceType.COMPETITOR,
            brand="DAISO",
            text="伪装成官方趋势的竞品样本",
            data_provenance="public",
        )
    )
    monkeypatch.setattr(runner, "load_evidence", lambda _category: evidences)

    with pytest.raises(RuntimeError, match=malicious_id):
        run_studio(thread_id="malicious-official-id")


def test_view_rejects_different_evidence_with_same_global_source_id():
    artifacts = run_studio(thread_id="defensive-evidence-index")
    official = next(
        item
        for item in artifacts.state.trend_evidences
        if item.source_id == "trend-miniso-q1-2026-ip"
    )
    artifacts.state.competitor_evidences["DAISO"].append(
        Evidence(
            source_id=official.source_id,
            source_type=SourceType.COMPETITOR,
            brand="DAISO",
            text="不同内容不得覆盖官方证据",
            data_provenance="public",
        )
    )

    with pytest.raises(RuntimeError, match=official.source_id):
        to_view(artifacts)


def test_reports_are_addressable_by_run_id_and_do_not_cross_runs(client):
    first = client.post("/api/run", json={"brief": "独立方案甲：城市通勤礼赠"}).json()
    second = client.post("/api/run", json={"brief": "独立方案乙：旅行限定礼赠"}).json()

    first_report = client.get("/api/report", params={"run_id": first["run_id"], "kind": "full"})
    second_report = client.get("/api/report", params={"run_id": second["run_id"], "kind": "opening"})

    assert first_report.status_code == second_report.status_code == 200
    assert first_report.json()["run_id"] == first["run_id"]
    assert first_report.json()["kind"] == "full"
    assert "独立方案甲" in first_report.json()["markdown"]
    assert "独立方案乙" not in first_report.json()["markdown"]
    assert second_report.json()["run_id"] == second["run_id"]
    assert second_report.json()["kind"] == "opening"
    assert "独立方案乙" in second_report.json()["markdown"]
    assert second_report.json()["data_provenance"] == second["data_provenance"]
    assert client.get("/api/report").status_code == 422
    assert client.get("/api/report", params={"run_id": "run-missing", "kind": "full"}).status_code == 404
    assert client.get("/api/report", params={"run_id": first["run_id"], "kind": "other"}).status_code == 422


def test_concurrent_runs_get_unique_identifiers_and_isolated_reports():
    def execute(label: str) -> dict:
        with TestClient(api.app) as local_client:
            response = local_client.post("/api/run", json={"brief": f"并发方案{label}"})
            assert response.status_code == 200
            return response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(execute, ["甲", "乙"]))

    assert first["run_id"] != second["run_id"]
    assert first["thread_id"] != second["thread_id"]
    with TestClient(api.app) as local_client:
        report_a = local_client.get("/api/report", params={"run_id": first["run_id"]}).json()["markdown"]
        report_b = local_client.get("/api/report", params={"run_id": second["run_id"]}).json()["markdown"]
    assert "并发方案甲" in report_a and "并发方案乙" not in report_a
    assert "并发方案乙" in report_b and "并发方案甲" not in report_b


def test_sse_has_cache_headers_unique_context_and_single_terminal_pair(client):
    response = client.get("/api/stream", params={"brief": "流式候选验证"})
    events = _sse_events(response)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert len([event for event in events if event["type"] == "result"]) == 1
    assert len([event for event in events if event["type"] == "done"]) == 1
    assert not [event for event in events if event["type"] == "error"]
    assert events[-1]["type"] == "done"
    contexts = {(event["run_id"], event["thread_id"]) for event in events}
    assert len(contexts) == 1
    run_id, thread_id = contexts.pop()
    _assert_uuid_level_id(run_id, "run-")
    _assert_uuid_level_id(thread_id, "thread-")
    result = next(event for event in events if event["type"] == "result")
    assert result["view"]["run_id"] == run_id
    assert result["view"]["thread_id"] == thread_id


def test_sse_error_is_sanitized_and_still_terminates(client, monkeypatch):
    def explode(**kwargs):
        kwargs["tracer"].emit(
            "unsafe_node",
            "node_error",
            error="private-api-key=SHOULD_NOT_LEAK",
        )
        raise RuntimeError("private-api-key=SHOULD_NOT_LEAK")

    monkeypatch.setattr(api, "run_studio", explode)
    response = client.get("/api/stream", params={"brief": "触发异常"})
    events = _sse_events(response)

    assert [event["type"] for event in events][-2:] == ["error", "done"]
    error = next(event for event in events if event["type"] == "error")
    assert error["message"] == "运行失败，请稍后重试"
    assert "SHOULD_NOT_LEAK" not in response.text


def test_sse_hitl_returns_awaiting_human_result(client):
    response = client.get("/api/stream", params={"hitl": "true"})
    result = next(event for event in _sse_events(response) if event["type"] == "result")

    assert result["view"]["status"] == "awaiting_human"
    assert result["view"]["awaiting_human"] is True


def test_sse_rejects_fifth_worker_before_creating_another_thread(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(api, "_SSE_WORKERS", threading.BoundedSemaphore(value=4))
    original_thread = threading.Thread
    worker_threads = []

    def tracked_thread(*args, **kwargs):
        worker = original_thread(*args, **kwargs)
        worker_threads.append(worker)
        return worker

    monkeypatch.setattr(api.threading, "Thread", tracked_thread)
    release_workers = threading.Event()
    condition = threading.Condition()
    started = 0
    finished = 0

    def block_worker(**_kwargs):
        nonlocal started, finished
        with condition:
            started += 1
            condition.notify_all()
        release_workers.wait(timeout=5)
        with condition:
            finished += 1
            condition.notify_all()
        raise RuntimeError("capacity test completed")

    monkeypatch.setattr(api, "run_studio", block_worker)
    responses = []
    try:
        for index in range(4):
            responses.append(
                api.stream(
                    brief="SSE 固定容量测试",
                    hitl=None,
                    thread_id=f"capacity-{index}",
                )
            )
        with condition:
            assert condition.wait_for(lambda: started == 4, timeout=3)

        before = time.perf_counter()
        with pytest.raises(HTTPException) as exc_info:
            api.stream(
                brief="第五个请求应立即拒绝",
                hitl=None,
                thread_id="capacity-overflow",
            )
        assert exc_info.value.status_code == 503
        assert time.perf_counter() - before < 0.5
        assert started == 4
    finally:
        release_workers.set()
        for worker in worker_threads:
            worker.join(timeout=5)

    assert len(responses) == 4
    assert len(worker_threads) == 4
    assert all(not worker.is_alive() for worker in worker_threads)


def test_resume_preserves_run_id_handles_second_pause_and_is_single_use(client, monkeypatch):
    from miniso_studio.application.agents.decision_officer import DecisionOfficerAgent
    from miniso_studio.common.models import DecisionVerdict

    original_run = DecisionOfficerAgent.run

    def require_second_iteration(self, state):
        state = original_run(self, state)
        if state.pm_iteration == 1 and state.decision is not None:
            state.decision.verdict = DecisionVerdict.CONDITIONAL_GO
            winner = state.concept_scorecards[0]
            winner.recommendation = DecisionVerdict.CONDITIONAL_GO
        return state

    monkeypatch.setattr(DecisionOfficerAgent, "run", require_second_iteration)
    first = client.post("/api/run", json={"hitl": True, "thread_id": "resume-life"})
    assert first.status_code == 200
    initial = first.json()
    assert initial["status"] == "awaiting_human"

    second = client.post("/api/resume", json={"thread_id": "resume-life", "action": "approve"})
    assert second.status_code == 200
    assert second.json()["status"] == "awaiting_human"
    assert second.json()["run_id"] == initial["run_id"]

    third = client.post("/api/resume", json={"thread_id": "resume-life", "action": "approve"})
    assert third.status_code == 200
    assert third.json()["status"] == "completed"
    assert third.json()["run_id"] == initial["run_id"]
    assert third.json()["thread_id"] == "resume-life"
    assert third.json()["portfolio_decision"]["reviewer"] == "human"
    approval_events = [
        event
        for event in third.json()["audit"]["trace"]
        if event.get("kind") == "human_approval"
    ]
    assert len(approval_events) == 2
    assert [event["iteration"] for event in approval_events] == [1, 2]
    assert {event["action"] for event in approval_events} == {"approve"}
    assert len({event["checkpoint_id"] for event in approval_events}) == 2
    assert all(datetime.fromisoformat(event["approved_at"]) for event in approval_events)
    assert any(
        event.get("tool_name") == "get_retail_trends"
        for event in third.json()["audit"]["tool_calls"]
    )
    assert client.post(
        "/api/resume", json={"thread_id": "resume-life", "action": "approve"}
    ).status_code == 409
    assert client.post(
        "/api/resume", json={"thread_id": "unknown-thread", "action": "approve"}
    ).status_code == 404
    assert client.post(
        "/api/resume", json={"thread_id": "resume-life", "action": "reject"}
    ).status_code == 422
    assert client.post(
        "/api/resume",
        json={"thread_id": "resume-life", "action": "approve", "approval_note": "ignored"},
    ).status_code == 422


def test_checkpoint_rejects_traversal_writes_atomically_and_deletes(tmp_path):
    checkpointer = JsonCheckpointer(str(tmp_path / "checkpoints"))
    state = run_studio(thread_id="checkpoint-source").state

    with pytest.raises(ValueError):
        checkpointer.save("../escape", state, "hit_judge")
    with pytest.raises(ValueError):
        checkpointer.load("a/b")

    checkpointer.save("safe_Thread-1", state, "hit_judge")
    assert checkpointer.load("safe_Thread-1")[1] == "hit_judge"
    assert not list((tmp_path / "checkpoints").glob("*.tmp*"))
    assert checkpointer.delete("safe_Thread-1") is True
    assert checkpointer.load("safe_Thread-1") is None
    assert checkpointer.delete("safe_Thread-1") is False


def test_pending_checkpoint_survives_memory_reset_and_blocks_same_thread_run(client):
    first = client.post(
        "/api/run",
        json={"hitl": True, "thread_id": "restart-pending"},
    )
    assert first.status_code == 200
    initial = first.json()
    assert initial["status"] == "awaiting_human"
    checkpointer = JsonCheckpointer()
    before, next_node = checkpointer.load("restart-pending")

    api._reset_runtime_state()
    blocked = client.post(
        "/api/run",
        json={"hitl": False, "thread_id": "restart-pending"},
    )

    assert blocked.status_code == 409
    after, after_next_node = checkpointer.load("restart-pending")
    assert after.trace_run_id == before.trace_run_id == initial["run_id"]
    assert after_next_node == next_node
    stream_blocked = client.get(
        "/api/stream",
        params={"thread_id": "restart-pending"},
    )
    assert stream_blocked.status_code == 409
    resumed = client.post(
        "/api/resume",
        json={"thread_id": "restart-pending", "action": "approve"},
    )
    assert resumed.status_code == 200
    assert resumed.json()["run_id"] == initial["run_id"]
    assert resumed.json()["status"] == "completed"


def test_persistent_thread_reservation_is_exclusive_and_reusable(tmp_path):
    from miniso_studio.application.graph.checkpoint import ReservationConflictError

    first_checkpointer = JsonCheckpointer(str(tmp_path / "checkpoints"))
    second_checkpointer = JsonCheckpointer(str(tmp_path / "checkpoints"))
    first = first_checkpointer.reserve_for_run("exclusive-thread")
    try:
        with pytest.raises(ReservationConflictError):
            second_checkpointer.reserve_for_run("exclusive-thread")
    finally:
        first.release()

    second = second_checkpointer.reserve_for_run("exclusive-thread")
    second.release()


def test_thread_reservation_is_exclusive_across_processes(tmp_path):
    checkpointer = JsonCheckpointer(str(tmp_path / "checkpoints"))
    reservation = checkpointer.reserve_for_run("cross-process")
    backend_dir = str(Path(__file__).resolve().parents[1])
    script = """
import sys
sys.path.insert(0, sys.argv[1])
from miniso_studio.application.graph.checkpoint import JsonCheckpointer, ReservationConflictError
checkpointer = JsonCheckpointer(sys.argv[2])
try:
    reservation = checkpointer.reserve_for_run('cross-process')
except ReservationConflictError:
    raise SystemExit(23)
reservation.release()
"""
    try:
        blocked = subprocess.run(
            [sys.executable, "-c", script, backend_dir, str(tmp_path / "checkpoints")],
            check=False,
            capture_output=True,
            text=True,
        )
        assert blocked.returncode == 23, blocked.stderr
    finally:
        reservation.release()

    available = subprocess.run(
        [sys.executable, "-c", script, backend_dir, str(tmp_path / "checkpoints")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert available.returncode == 0, available.stderr


def test_process_exit_releases_thread_reservation(tmp_path):
    backend_dir = str(Path(__file__).resolve().parents[1])
    checkpoint_dir = str(tmp_path / "checkpoints")
    script = """
import sys, time
sys.path.insert(0, sys.argv[1])
from miniso_studio.application.graph.checkpoint import JsonCheckpointer
reservation = JsonCheckpointer(sys.argv[2]).reserve_for_run('crash-release')
print('ready', flush=True)
time.sleep(30)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, backend_dir, checkpoint_dir],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "ready"
        from miniso_studio.application.graph.checkpoint import ReservationConflictError

        with pytest.raises(ReservationConflictError):
            JsonCheckpointer(checkpoint_dir).reserve_for_run("crash-release")
    finally:
        process.kill()
        process.wait(timeout=5)

    reservation = JsonCheckpointer(checkpoint_dir).reserve_for_run("crash-release")
    reservation.release()


def test_conditional_checkpoint_delete_cannot_remove_new_generation(tmp_path):
    from miniso_studio.application.graph.checkpoint import (
        CheckpointGenerationConflictError,
    )

    state = run_studio(thread_id="generation-state").state
    checkpointer = JsonCheckpointer(str(tmp_path / "checkpoints"))
    first_id = checkpointer.save("generation-thread", state, "decision_review")
    reservation = checkpointer.reserve_for_resume("generation-thread")
    try:
        second_id = checkpointer.save("generation-thread", state, "decision_review")
        with pytest.raises(CheckpointGenerationConflictError):
            checkpointer.delete_if_checkpoint_id(reservation, first_id)
        assert checkpointer.load_snapshot("generation-thread").checkpoint_id == second_id
    finally:
        reservation.release()


def test_runner_failure_releases_its_persistent_reservation(monkeypatch):
    from miniso_studio.application import runner

    def fail_loading(_category):
        raise RuntimeError("load failed")

    monkeypatch.setattr(runner, "load_evidence", fail_loading)
    with pytest.raises(RuntimeError, match="load failed"):
        runner.run_studio(thread_id="failure-release")

    reservation = JsonCheckpointer().reserve_for_run("failure-release")
    reservation.release()


def test_resume_failure_preserves_checkpoint_and_releases_reservation(monkeypatch):
    from miniso_studio.application import runner

    initial = runner.run_studio(hitl=True, thread_id="resume-failure")
    assert initial.awaiting_human
    checkpointer = JsonCheckpointer()
    checkpoint_path = checkpointer.dir / "resume-failure.json"
    before = checkpoint_path.read_bytes()

    def fail_graph(*_args, **_kwargs):
        raise RuntimeError("graph build failed")

    monkeypatch.setattr(runner, "build_studio_graph", fail_graph)
    with pytest.raises(RuntimeError, match="graph build failed"):
        runner.resume_studio(thread_id="resume-failure")

    assert checkpoint_path.read_bytes() == before
    reservation = checkpointer.reserve_for_resume("resume-failure")
    reservation.release()


def test_tracer_default_run_ids_are_uuid_unique():
    first = Tracer()
    second = Tracer()

    assert first.run_id != second.run_id
    _assert_uuid_level_id(first.run_id, "run-")
    _assert_uuid_level_id(second.run_id, "run-")
    assert first.path != second.path
    with pytest.raises(ValueError):
        Tracer(run_id="../trace-escape")


def test_miniso_environment_configuration_takes_effect(monkeypatch, tmp_path):
    monkeypatch.setenv("MINISO_LLM_PROVIDER", "minimax")
    monkeypatch.setenv("MINISO_ENABLE_MEDIA", "true")
    monkeypatch.setenv("MINISO_MAX_RETRIEVAL_ITERS", "7")
    monkeypatch.setenv("MINISO_HITL", "true")
    monkeypatch.setenv("MINISO_TRACE_DIR", str(tmp_path / "trace"))
    monkeypatch.setenv("MINISO_HOST", "0.0.0.0")
    monkeypatch.setenv("MINISO_PORT", "9876")
    settings.cache_clear()

    cfg = settings()
    assert cfg.llm_provider == "minimax"
    assert cfg.enable_media is True
    assert cfg.max_retrieval_iters == 7
    assert cfg.hitl is True
    assert cfg.trace_path == tmp_path / "trace"
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 9876
    assert cfg.category == "interest_goods"
    assert cfg.target_brand == "MINISO"
    assert "全球本地化" in cfg.default_brief


def test_health_and_run_report_configured_minimax_without_key_as_effective_offline(
    client,
    monkeypatch,
):
    monkeypatch.setenv("MINISO_LLM_PROVIDER", "minimax")
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    settings.cache_clear()

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["configured_provider"] == "minimax"
    assert health.json()["effective_provider"] == "offline"
    assert health.json()["provider"] == "offline"

    view = client.post(
        "/api/run",
        json={"thread_id": "configured-without-key"},
    ).json()
    assert view["configured_provider"] == "minimax"
    assert view["effective_provider"] == "offline"
    assert view["provider"] == "offline"
    fallback = [
        event
        for event in view["audit"]["trace"]
        if event.get("kind") == "provider_fallback"
    ]
    assert fallback
    assert fallback[0]["reason"] == "missing_api_key"


def test_remote_narrate_failure_switches_effective_provider_and_is_visible_everywhere(
    client,
    monkeypatch,
):
    from miniso_studio.infrastructure.llm import minimax

    class FailingMiniMaxClient:
        def __init__(self, **_kwargs):
            pass

        def chat(self, *_args, **_kwargs):
            raise RuntimeError("simulated remote outage")

    monkeypatch.setenv("MINISO_LLM_PROVIDER", "minimax")
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr(minimax, "MiniMaxClient", FailingMiniMaxClient)
    settings.cache_clear()

    view = client.post(
        "/api/run",
        json={"thread_id": "remote-provider-fallback"},
    ).json()

    assert view["configured_provider"] == "minimax"
    assert view["effective_provider"] == "offline"
    assert view["provider"] == "offline"
    fallback = [
        event
        for event in view["audit"]["trace"]
        if event.get("kind") == "provider_fallback"
    ]
    assert len(fallback) == 1
    assert fallback[0]["operation"] == "narrate"
    assert fallback[0]["effective_provider"] == "offline"

    report = client.get(
        "/api/report",
        params={"run_id": view["run_id"], "kind": "full"},
    ).json()["markdown"]
    assert "Configured Provider：minimax" in report
    assert "Effective Provider：offline" in report


@pytest.mark.parametrize("remote_text", ["", "  \n\t"], ids=["empty", "whitespace"])
def test_remote_narrate_empty_response_switches_to_offline(remote_text):
    class EmptyResponseClient:
        def chat(self, *_args, **_kwargs):
            return LLMResponse(text=remote_text, provider="minimax")

    tracer = Tracer(run_id=f"narrate-empty-{len(remote_text)}")
    gateway = LLMGateway(
        provider="minimax",
        minimax_client=EmptyResponseClient(),
        configured_provider="minimax",
        tracer=tracer,
    )

    assert gateway.narrate("离线默认文本", "润色") == "离线默认文本"
    assert gateway.effective_provider == "offline"
    fallback = [event for event in tracer.events if event.get("kind") == "provider_fallback"]
    assert len(fallback) == 1
    assert fallback[0]["operation"] == "narrate"
    assert fallback[0]["reason"] == "empty_response"


@pytest.mark.parametrize("remote_text", ["", "  \n\t"], ids=["empty", "whitespace"])
def test_remote_complete_empty_response_switches_to_offline(remote_text):
    class EmptyResponseClient:
        def chat(self, *_args, **_kwargs):
            return LLMResponse(text=remote_text, provider="minimax")

    tracer = Tracer(run_id=f"complete-empty-{len(remote_text)}")
    gateway = LLMGateway(
        provider="minimax",
        minimax_client=EmptyResponseClient(),
        configured_provider="minimax",
        tracer=tracer,
    )

    response = gateway.complete("system", "离线回退内容。第二句。")
    assert response.provider == "offline"
    assert response.text == "离线回退内容。第二句"
    assert gateway.effective_provider == "offline"
    fallback = [event for event in tracer.events if event.get("kind") == "provider_fallback"]
    assert len(fallback) == 1
    assert fallback[0]["operation"] == "complete"
    assert fallback[0]["reason"] == "empty_response"


def test_generic_port_environment_variable_is_ignored(monkeypatch):
    monkeypatch.delenv("MINISO_PORT", raising=False)
    monkeypatch.setenv("PORT", "9999")
    settings.cache_clear()

    assert settings().port == 8767


@pytest.mark.parametrize(
    ("provenance_values", "expected_scope"),
    [
        (["synthetic_demo"], "synthetic_demo"),
        (["public"], "public"),
        (["unspecified"], "unknown"),
        (["public", "unspecified"], "mixed"),
        (["synthetic_demo", "public"], "mixed"),
        (["synthetic_demo", "unspecified"], "mixed"),
    ],
)
def test_review_scope_classification_is_conservative(provenance_values, expected_scope):
    artifacts = run_studio(thread_id=f"scope-{expected_scope}-{'-'.join(provenance_values)}")
    reviews = list(artifacts.state.target_evidences)
    for values in artifacts.state.competitor_evidences.values():
        reviews.extend(values)
    for index, evidence in enumerate(reviews):
        evidence.data_provenance = provenance_values[index % len(provenance_values)]

    provenance = build_data_provenance(artifacts)

    assert provenance["review_scope"] == expected_scope
    if "unspecified" in provenance_values:
        assert "来源未确认" in provenance["disclaimer"]


def test_evidence_index_exposes_original_data_provenance():
    artifacts = run_studio(thread_id="evidence-provenance-field")
    initial_view = to_view(artifacts)
    source_id = next(iter(initial_view["evidence_index"]))
    evidence = next(item for item in artifacts.state.all_evidences() if item.source_id == source_id)
    evidence.data_provenance = "unspecified"

    evidence_view = to_view(artifacts)["evidence_index"][source_id]

    assert evidence_view["data_provenance"] == "unspecified"


def test_full_and_opening_reports_cover_business_chain_and_data_boundary():
    art = run_studio(brief="报告契约：从趋势感知到上市验证", thread_id="report-contract")
    full = api.render_full_report(art)
    opening = api.render_opening_report(art)

    for report in (full, opening):
        assert "Trend2SKU" in report
        assert "MINISO" in report
        assert "报告契约" in report
        assert "2026-05-26" in report
        assert "2026-04-24" in report
        assert "未经审计" in report
        assert "1,600" in report
        assert "研究假设" in report
        assert "离线演示" in report
        assert all(term not in report for term in STALE_RUNTIME_TERMS)

    assert all(concept.name in full for concept in art.state.concepts)
    assert all(dimension.label in full for dimension in art.state.concept_scorecards[0].dimensions)
    assert "工具调用" in full
    assert "上市验证" in full
    assert "数据边界" in full


def test_runtime_api_payload_has_no_stale_business_copy(client):
    payload = json.dumps(client.post("/api/run", json={}).json(), ensure_ascii=False)

    assert all(term not in payload for term in STALE_RUNTIME_TERMS)


def test_cli_writes_new_miniso_reports_without_overwriting_legacy_files(tmp_path, monkeypatch):
    from miniso_studio.starter import cli

    generated = tmp_path / "docs" / "generated"
    generated.mkdir(parents=True)
    legacy_full = generated / "运行报告.md"
    legacy_opening = generated / "开题报告_自动生成.md"
    legacy_full.write_text("legacy-full", encoding="utf-8")
    legacy_opening.write_text("legacy-opening", encoding="utf-8")
    artifacts = run_studio(thread_id="cli-report-contract")
    monkeypatch.setattr(cli, "settings", lambda: type("Cfg", (), {"project_root": str(tmp_path)})())

    paths = cli._write_reports(artifacts)

    assert legacy_full.read_text(encoding="utf-8") == "legacy-full"
    assert legacy_opening.read_text(encoding="utf-8") == "legacy-opening"
    assert {path.name for path in paths} == {
        "运行报告_名创优品_v1.md",
        "开题报告_名创优品_v1.md",
    }
    assert all(path.exists() for path in paths)


def test_cli_run_defaults_to_interest_goods_and_defers_hitl_to_config(monkeypatch):
    from miniso_studio.starter import cli

    captured = {}

    def fake_run_studio(**kwargs):
        captured.update(kwargs)
        return type("Artifacts", (), {"awaiting_human": True})()

    monkeypatch.setattr(cli, "run_studio", fake_run_studio)
    monkeypatch.setattr(sys, "argv", ["trend2sku", "run"])

    assert cli.main() == 0
    assert captured["category"] == "interest_goods"
    assert captured["hitl"] is None


def test_cli_returns_nonzero_and_explains_missing_target_evidence(
    monkeypatch,
    capsys,
):
    from miniso_studio.application import runner
    from miniso_studio.starter import cli

    monkeypatch.setattr(
        runner,
        "load_evidence",
        lambda _category: [
            Evidence(
                source_id="cli-daiso-only",
                source_type=SourceType.COMPETITOR,
                brand="DAISO",
                text="只有竞品样本",
                data_provenance="public",
            )
        ],
    )
    monkeypatch.setattr(cli, "_write_reports", lambda _artifacts: [])
    monkeypatch.setattr(sys, "argv", ["trend2sku", "run", "--thread", "cli-no-target"])

    assert cli.main() == 2
    captured = capsys.readouterr()
    assert "MINISO" in captured.err
    assert "目标样本" in captured.err


def test_entire_runtime_package_has_no_stale_business_copy():
    project_root = Path(__file__).resolve().parents[2]
    runtime_files = sorted((project_root / "backend/miniso_studio").rglob("*.py"))
    runtime_files.extend([project_root / ".env.example", project_root / "run.py"])
    forbidden = (*STALE_RUNTIME_TERMS, "ANKER_", "耳机", "降噪", "音质")
    ascii_term_patterns = {
        term: re.compile(
            rf"(?<![a-z0-9]){re.escape(term.casefold().rstrip('_'))}(?![a-z0-9])"
        )
        for term in forbidden
        if term.isascii()
    }
    violations = {}
    for path in runtime_files:
        relative_path = str(path.relative_to(project_root))
        searchable = "\n".join(
            (relative_path.casefold(), path.read_text(encoding="utf-8").casefold())
        )
        matched = []
        for term in forbidden:
            folded = term.casefold()
            pattern = ascii_term_patterns.get(term)
            if (pattern and pattern.search(searchable)) or (
                pattern is None and folded in searchable
            ):
                matched.append(term)
        if matched:
            violations[relative_path] = matched

    assert not violations, violations
    source = "\n".join(path.read_text(encoding="utf-8") for path in runtime_files)
    assert "MINISO_HOST" in source
    assert "MINISO_PORT" in source


def test_interest_goods_opportunity_weights_and_solution_templates_cover_all_aspects():
    from miniso_studio.application.methodology.odi import STRATEGIC_WEIGHT
    from miniso_studio.application.methodology.ost import SOLUTION_TEMPLATES
    from miniso_studio.infrastructure.nlp.lexicons import ASPECT_LEXICON

    expected_aspects = set(ASPECT_LEXICON)
    assert set(STRATEGIC_WEIGHT) == expected_aspects
    assert set(SOLUTION_TEMPLATES) == expected_aspects
    assert all(0 < STRATEGIC_WEIGHT[aspect] <= 1 for aspect in expected_aspects)
    assert all(SOLUTION_TEMPLATES[aspect] for aspect in expected_aspects)
    template_copy = " ".join(
        template
        for templates in SOLUTION_TEMPLATES.values()
        for template in templates
    )
    for business_term in ("IP", "品质", "价格", "礼赠", "收藏", "包装", "门店", "本地化"):
        assert business_term in template_copy
