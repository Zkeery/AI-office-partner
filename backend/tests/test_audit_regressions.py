"""Executable regressions for the 2026-10-04 chain audit (F01–F09, F12)."""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db import session as db_session
from app.db.models import ModelCall, Schedule, ScheduleRun, Task, utcnow
from app.services import files, llm, schedules, tasks
from app.services.usage import CallContext, _context, usage_summary


def create_schedule(client, **extra):
    response = client.post("/api/schedules", json={"name": "回归规则", "prompt": "整理周报",
        "model_id": "mock", "skill_id": "weekly_report", "token_budget": 100000, **extra})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def workspace(client, tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    assert client.put("/api/workspace", json={"root": str(root)}).status_code == 200
    return root


def test_only_explicit_files_reach_execution_context(client, tmp_path, monkeypatch):
    root = workspace(client, tmp_path)
    (root / "selected.txt").write_text("SELECTED_7e8aa", encoding="utf-8")
    (root / "private.txt").write_text("DO_NOT_READ_f9219", encoding="utf-8")
    task_id = client.post("/api/tasks", json={"prompt": "整理上传材料", "model_id": "mock", "skill_id": "weekly_report"}).json()["id"]
    assert client.post(f"/api/tasks/{task_id}/workspace-refs", json={"paths": ["selected.txt"]}).status_code == 200
    (root / "selected.txt").write_text("LATER_CHANGE_38f44", encoding="utf-8")
    captured = []
    async def capture(settings, system, user):
        captured.append(user)
        return llm._mock_reply(system, user)
    monkeypatch.setattr(tasks, "chat_completion", capture)
    with db_session.SessionLocal() as db:
        task = db.get(Task, task_id)
        detail = json.loads(task.steps[0].detail_json)
        detail["tool_hint"] = "read_workspace"
        task.steps[0].detail_json = json.dumps(detail)
        db.commit()
        asyncio.run(tasks.confirm_and_run(db, task_id, confirm_cost=True))
    joined = "\n".join(captured)
    assert "SELECTED_7e8aa" in joined
    assert "DO_NOT_READ_f9219" not in joined and "LATER_CHANGE_38f44" not in joined


def test_long_documents_tables_and_full_context_or_explicit_error(tmp_path):
    from docx import Document
    doc = Document()
    doc.add_paragraph("BEGIN_MARKER" + "长" * 20000)
    table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "TABLE_MARKER"
    nested = table.cell(0, 0).add_table(rows=1, cols=1)
    nested.cell(0, 0).text = "NESTED_MARKER"
    doc.add_paragraph("END_MARKER")
    path = tmp_path / "long.docx"
    doc.save(path)
    result = files.extract_text(path, ".docx")
    assert result.index("BEGIN_MARKER") < result.index("TABLE_MARKER") < result.index("NESTED_MARKER") < result.index("END_MARKER")
    context = files.task_document_context([SimpleNamespace(filename=path.name, stored_path=str(path))])
    assert "END_MARKER" in context and len(context) > 20000
    assert "BEGIN_MARKER" in files.join_context([context, "analysis", context])
    too_big = tmp_path / "oversize.txt"
    too_big.write_text("x" * (files.MAX_DOCUMENT_CHARS + 1), encoding="utf-8")
    with pytest.raises(AppError, match="超过") as error:
        files.extract_text(too_big, ".txt")
    assert error.value.code == "DOCUMENT_TOO_LARGE"


def test_workspace_attachment_failure_is_atomic(client, tmp_path):
    root = workspace(client, tmp_path)
    (root / "ok.txt").write_text("usable", encoding="utf-8")
    task_id = client.post("/api/tasks", json={"prompt": "整理", "model_id": "mock"}).json()["id"]
    response = client.post(f"/api/tasks/{task_id}/workspace-refs", json={"paths": ["ok.txt", "missing.txt"]})
    assert response.status_code == 404
    assert client.get(f"/api/tasks/{task_id}").json()["uploads"] == []
    assert list((get_settings().uploads_path / task_id).glob("*")) == []


def test_three_identical_filenames_never_overwrite(client, tmp_path):
    root = workspace(client, tmp_path)
    names = []
    for value in [11, 22, 33, 44]:
        result = client.post("/api/workspace/upload", files={"file": ("data.csv", f"a,b\n1,{value}\n".encode(), "text/csv")})
        assert result.status_code == 200
        names.append(result.json()["rel"])
    assert len(set(names)) == 4
    assert [int((root / name).read_text().splitlines()[1].split(",")[1]) for name in names] == [11, 22, 33, 44]


def test_startup_recovers_planning_and_running(client):
    planned = client.post("/api/tasks", json={"prompt": "已有计划", "model_id": "mock"}).json()["id"]
    with db_session.SessionLocal() as db:
        db.add(Task(id="interrupted-plan", title="", user_prompt="未完成计划", status="planning", plan_json="{}"))
        task = db.get(Task, planned)
        task.status = "running"
        task.steps[0].status = "running"
        db.commit()
        assert tasks.recover_running_tasks(db) == 2
        assert db.get(Task, planned).status == "paused"
        assert db.get(Task, planned).steps[0].status == "pending"
        assert db.get(Task, "interrupted-plan").error_code == "PLANNING_INTERRUPTED"
    response = client.post("/api/tasks/interrupted-plan/replan", json={})
    assert response.status_code == 200 and response.json()["status"] == "plan_ready"


@pytest.mark.parametrize("route", ["plan", "replan"])
@pytest.mark.parametrize("state", ["running", "planning", "succeeded"])
def test_all_plan_routes_obey_state_guard(client, route, state):
    task_id = client.post("/api/tasks", json={"prompt": "原始需求", "model_id": "mock"}).json()["id"]
    with db_session.SessionLocal() as db:
        task = db.get(Task, task_id)
        task.status = state
        db.commit()
    response = client.post(f"/api/tasks/{task_id}/{route}", json={"prompt": "不得覆盖"})
    assert response.status_code in {400, 409}
    detail = client.get(f"/api/tasks/{task_id}").json()
    assert detail["status"] == state and detail["user_prompt"] == "原始需求"


def test_paused_schedule_is_not_success_and_manual_continuation_works(client, monkeypatch):
    sid = create_schedule(client)
    original = tasks._execute_agent
    async def pause(db, task_id, settings):
        tasks.pause_task(db, task_id)
    monkeypatch.setattr(tasks, "_execute_agent", pause)
    result = client.post(f"/api/schedules/{sid}/run-now")
    assert result.status_code == 200
    run = client.get(f"/api/schedules/{sid}/runs").json()["items"][0]
    assert run["status"] == "paused" and "RUN_PAUSED" in run["error"]
    monkeypatch.setattr(tasks, "_execute_agent", original)
    with db_session.SessionLocal() as db:
        asyncio.run(tasks.resume_task(db, run["task_id"]))
        assert db.get(Task, run["task_id"]).status == "succeeded"
        asyncio.run(tasks.rewrite_report(db, run["task_id"], "精简表述"))
        manual_calls = list(db.scalars(select(ModelCall).where(ModelCall.task_id == run["task_id"], ModelCall.schedule_run_id.is_(None))))
        assert manual_calls


def test_concurrent_claim_and_crash_recovery(client, monkeypatch):
    sid = create_schedule(client)
    original = tasks.create_task
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def delayed(*args, **kwargs):
            entered.set()
            await release.wait()
            return await original(*args, **kwargs)
        monkeypatch.setattr(tasks, "create_task", delayed)
        with db_session.SessionLocal() as first, db_session.SessionLocal() as second:
            running = asyncio.create_task(schedules.trigger_schedule(first, sid))
            await entered.wait()
            run = second.scalar(select(ScheduleRun).where(ScheduleRun.schedule_id == sid))
            assert run.status == "running" and run.task_id
            with pytest.raises(AppError) as error:
                await schedules.trigger_schedule(second, sid)
            assert error.value.code == "SCHEDULE_BUSY"
            running.cancel()
            with pytest.raises(asyncio.CancelledError):
                await running
            second.expire_all()
            assert second.get(ScheduleRun, run.id).status == "interrupted"
            assert second.get(Schedule, sid).active_run_id is None
            # Reproduce an ungraceful process exit after its durable claim.
            run = second.get(ScheduleRun, run.id)
            run.status = "running"
            second.get(Schedule, sid).active_run_id = run.id
            second.commit()
            assert schedules.recover_schedule_runs(second) == 1
            assert run.status == "interrupted"
            assert second.get(Schedule, sid).active_run_id is None
    asyncio.run(scenario())


def test_process_lock_prevents_second_startup_recovery(tmp_path):
    from app.core.process_lock import data_lock
    with data_lock(tmp_path):
        with pytest.raises(RuntimeError, match="正在使用"):
            with data_lock(tmp_path):
                pytest.fail("second owner acquired data")
    with data_lock(tmp_path):
        pass


@pytest.mark.parametrize("mode,expected", [("snapshot", "original"), ("latest", "updated")])
def test_schedule_material_versions_and_manifest(client, tmp_path, mode, expected):
    root = workspace(client, tmp_path)
    (root / "brief.txt").write_text("original", encoding="utf-8")
    sid = create_schedule(client, workspace_paths=["brief.txt"], material_mode=mode, urls=["https://example.com"])
    (root / "brief.txt").write_text("updated", encoding="utf-8")
    result = client.post(f"/api/schedules/{sid}/run-now")
    assert result.status_code == 200, result.text
    task = client.get(f"/api/tasks/{result.json()['last_task_id']}").json()
    assert task["uploads"][0]["text_excerpt"] == expected
    run = client.get(f"/api/schedules/{sid}/runs").json()["items"][0]
    assert run["input_manifest"]["files"][0]["sha256"] == hashlib.sha256(expected.encode()).hexdigest()
    assert run["input_manifest"]["urls"] == ["https://example.com"]
    assert run["usage"]["simulated_calls"] > 0 and run["usage"]["total_tokens"] == 0


def test_upstream_run_result_is_attached_and_versioned(client):
    source = create_schedule(client)
    target = create_schedule(client, trigger_mode="on_task_succeeded", listen_schedule_id=source, include_upstream_result=True)
    assert client.post(f"/api/schedules/{source}/run-now").status_code == 200
    upstream = client.get(f"/api/schedules/{source}/runs").json()["items"][0]
    downstream = client.get(f"/api/schedules/{target}/runs").json()["items"][0]
    assert downstream["status"] == "success"
    assert downstream["input_manifest"]["upstream"]["run_id"] == upstream["id"]
    assert downstream["input_manifest"]["upstream"]["sha256"] == upstream["input_manifest"]["result"]["sha256"]


def test_budget_stops_before_model_request_and_records_failure(client, monkeypatch):
    sid = create_schedule(client, token_budget=1024)
    calls = []
    monkeypatch.setattr(llm, "_mock_reply", lambda *args: calls.append(args) or "should not run")
    response = client.post(f"/api/schedules/{sid}/run-now")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "BUDGET_EXCEEDED"
    assert calls == []
    run = client.get(f"/api/schedules/{sid}/runs").json()["items"][0]
    assert run["status"] == "failed" and run["budget_used_tokens"] == 0
    assert run["task_id"] is not None


def test_legacy_rules_require_explicit_setup(client):
    sid = create_schedule(client)
    with db_session.SessionLocal() as db:
        row = db.get(Schedule, sid)
        row.model_id = row.model_name = row.token_budget = None
        row.next_run_at = utcnow()
        db.commit()
        assert schedules.serialize_schedule(row)["setup_required"] is True
        assert asyncio.run(schedules.tick_due_schedules(db)) == 0
    assert client.post(f"/api/schedules/{sid}/run-now").json()["error"]["code"] == "SCHEDULE_SETUP_REQUIRED"


@pytest.mark.parametrize("status,body,expected,count", [
    (401, {"error": {}}, "LLM_AUTH_FAILED", 1),
    (429, {"error": {"code": "insufficient_quota"}}, "LLM_QUOTA_EXCEEDED", 1),
    (429, {"error": {}}, "LLM_RATE_LIMITED", 3),
    (503, {"error": {}}, "LLM_UNAVAILABLE", 3),
    (400, {"error": {}}, "LLM_REQUEST_REJECTED", 1),
    (200, [], "LLM_INVALID_RESPONSE", 1),
    (200, {"choices": [{"finish_reason": "length", "message": {"content": "partial"}}]}, "LLM_OUTPUT_TRUNCATED", 1),
])
def test_model_retry_classification(monkeypatch, status, body, expected, count):
    called = []
    def handler(req):
        called.append(json.loads(req.content))
        return httpx.Response(status, json=body)
    original = httpx.AsyncClient
    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    settings = Settings(_env_file=None, llm_mock=False, llm_api_key="test", llm_retry_base_seconds=0)
    with pytest.raises(AppError) as error:
        asyncio.run(llm.chat_completion(settings, "system", "user"))
    assert error.value.code == expected
    assert len(called) == count and all(item["max_tokens"] == 4096 for item in called)


def test_model_retries_and_persists_actual_vs_unknown_usage(client, monkeypatch):
    task_id = client.post("/api/tasks", json={"prompt": "usage", "model_id": "mock"}).json()["id"]
    responses = iter([httpx.Response(429, json={"error": {}}), httpx.Response(200, json={
        "choices": [{"message": {"content": "answer"}}],
        "usage": {"prompt_tokens": 30, "completion_tokens": 10, "total_tokens": 40}})])
    original = httpx.AsyncClient
    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(lambda req: next(responses)), **kw))
    settings = Settings(_env_file=None, llm_mock=False, llm_api_key="test", llm_retry_base_seconds=0)
    with db_session.SessionLocal() as db:
        db.get(Task, task_id).status = "planning"
        db.commit()
        async def call():
            token = _context.set(CallContext(db, task_id, None, "planning"))
            try:
                assert await llm.chat_completion(settings, "system", "user") == "answer"
            finally:
                _context.reset(token)
        asyncio.run(call())
        rows = list(db.scalars(select(ModelCall).where(ModelCall.task_id == task_id, ModelCall.status != "mock")))
        summary = usage_summary(rows)
        assert summary["calls"] == 2 and summary["unknown_calls"] == 1
        assert summary["total_tokens"] == 40 and summary["prompt_tokens"] == 30


def test_old_execution_failure_cannot_overwrite_a_new_plan(client, monkeypatch):
    task_id = client.post("/api/tasks", json={"prompt": "原计划", "model_id": "mock"}).json()["id"]
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def delayed_failure(*args):
            entered.set()
            await release.wait()
            raise AppError("LLM_TIMEOUT", "old failure")
        monkeypatch.setattr(tasks, "_execute_agent", delayed_failure)
        with db_session.SessionLocal() as first, db_session.SessionLocal() as second:
            running = asyncio.create_task(tasks.confirm_and_run(first, task_id, confirm_cost=True))
            await entered.wait()
            tasks.pause_task(second, task_id)
            await tasks.replan_task(second, task_id, prompt="新的计划")
            release.set()
            await running
            second.expire_all()
            task = tasks.get_task(second, task_id)
            assert task.status == "plan_ready" and task.user_prompt == "新的计划"
            assert task.error_code is None
    asyncio.run(scenario())


@pytest.mark.parametrize("kind,expected", [(httpx.ReadTimeout, "LLM_TIMEOUT"), (httpx.ConnectError, "LLM_NETWORK_ERROR")])
def test_network_failures_have_bounded_retries(monkeypatch, kind, expected):
    calls = []
    def handler(req):
        calls.append(req)
        raise kind("offline", request=req)
    original = httpx.AsyncClient
    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    settings = Settings(_env_file=None, llm_mock=False, llm_api_key="test", llm_retry_base_seconds=0, llm_max_attempts=50)
    with pytest.raises(AppError) as error:
        asyncio.run(llm.chat_completion(settings, "system", "user"))
    assert error.value.code == expected and len(calls) == 3


def test_unknown_usage_keeps_reservation_and_blocks_over_budget_retry(client, monkeypatch):
    sid = create_schedule(client)
    task_id = client.post("/api/tasks", json={"prompt": "budget retry", "model_id": "mock"}).json()["id"]
    called = []
    def handler(req):
        called.append(req)
        return httpx.Response(429, json={"error": {}})
    original = httpx.AsyncClient
    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    settings = Settings(_env_file=None, llm_mock=False, llm_api_key="test", llm_retry_base_seconds=0)
    with db_session.SessionLocal() as db:
        db.get(Task, task_id).status = "planning"
        run = ScheduleRun(id="budget-retry", schedule_id=sid, task_id=task_id, status="running", token_budget=6000, budget_used_tokens=0)
        db.add(run)
        db.commit()
        async def call():
            token = _context.set(CallContext(db, task_id, run.id, "planning"))
            try:
                await llm.chat_completion(settings, "system", "user")
            finally:
                _context.reset(token)
        with pytest.raises(AppError) as error:
            asyncio.run(call())
        assert error.value.code == "BUDGET_EXCEEDED" and len(called) == 1
        db.refresh(run)
        assert 5000 < run.budget_used_tokens <= 6000
        assert schedules.run_usage(db, run.id)["unknown_calls"] == 1
