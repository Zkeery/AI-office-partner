from __future__ import annotations

import json
import time

from app.db import session as db_session
from app.services import tasks

from test_table_analysis import sales_workbook


def wait(client, task_id):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        value = client.get(f"/api/tasks/{task_id}").json()
        if value["status"] in {"succeeded", "failed"}:
            return value
        time.sleep(0.03)
    raise AssertionError("task did not finish")


def test_unsupported_step_fails_instead_of_being_marked_done(client):
    task_id = client.post("/api/tasks", json={"model_id": "mock", "prompt": "整理调研报告"}).json()["id"]
    with db_session.SessionLocal() as db:
        task = tasks.get_task(db, task_id)
        detail = json.loads(task.steps[0].detail_json)
        detail["tool_hint"] = "send_email"
        task.steps[0].detail_json = json.dumps(detail)
        db.commit()
    client.post(f"/api/tasks/{task_id}/confirm", json={})
    result = wait(client, task_id)
    assert result["status"] == "failed"
    assert result["error_code"] == "TOOL_UNSUPPORTED"
    assert result["steps"][0]["status"] == "failed"
    assert "暂不支持" in result["steps"][0]["detail"]["evidence"]
    assert not result["has_report"]


def test_optional_missing_material_is_skipped_and_analysis_has_real_output(client):
    task_id = client.post("/api/tasks", json={"model_id": "mock", "prompt": "根据这些要点写周报：完成方案评审", "skill_id": "weekly_report"}).json()["id"]
    client.post(f"/api/tasks/{task_id}/confirm", json={})
    result = wait(client, task_id)
    assert result["status"] == "succeeded"
    assert result["steps"][0]["status"] == "skipped"
    assert result["steps"][1]["status"] == "done"
    assert result["steps"][1]["detail"]["summary"]
    assert all(step["detail"].get("evidence") for step in result["steps"])


def test_complete_workbook_reaches_report_and_analysis_api(client):
    task_id = client.post("/api/tasks", json={"model_id": "mock", "prompt": "分析销售额并生成图表", "skill_id": "table_analysis"}).json()["id"]
    response = client.post(f"/api/tasks/{task_id}/uploads", files={"file": ("销售.xlsx", sales_workbook(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert response.status_code == 200
    client.post(f"/api/tasks/{task_id}/confirm", json={})
    result = wait(client, task_id)
    assert result["status"] == "succeeded"
    analysis = client.get(f"/api/tasks/{task_id}/analysis").json()["analysis"]
    assert analysis["row_count"] == 102
    assert analysis["sheet_count"] == 2
    assert "102 行" in result["steps"][1]["detail"]["evidence"]
    assert client.get(f"/api/tasks/{task_id}/report.xlsx").status_code == 200
    assert client.get(f"/api/tasks/{task_id}/report.pptx").status_code == 200


def test_empty_model_report_cannot_succeed(client, monkeypatch):
    task_id = client.post("/api/tasks", json={"model_id": "mock", "prompt": "整理资料"}).json()["id"]
    async def empty(*_):
        return ""
    monkeypatch.setattr(tasks, "_write_report", empty)
    client.post(f"/api/tasks/{task_id}/confirm", json={})
    result = wait(client, task_id)
    assert result["status"] == "failed"
    assert result["error_code"] == "EMPTY_REPORT"
    assert result["steps"][-1]["status"] == "failed"


def test_same_named_uploads_remain_separate_inputs(client):
    task_id = client.post("/api/tasks", json={"model_id": "mock", "prompt": "汇总金额", "skill_id": "table_analysis"}).json()["id"]
    for value in (10, 20):
        assert client.post(f"/api/tasks/{task_id}/uploads", files={"file": ("相同.csv", f"金额\n{value}\n".encode(), "text/csv")}).status_code == 200
    client.post(f"/api/tasks/{task_id}/confirm", json={})
    assert wait(client, task_id)["status"] == "succeeded"
    summary = client.get(f"/api/tasks/{task_id}/analysis").json()["analysis"]
    assert [table["metrics"][0]["sum"] for table in summary["tables"]] == [10, 20]


def test_resuming_reuses_persisted_tool_context(client, monkeypatch):
    task_id = client.post("/api/tasks", json={"model_id": "mock", "prompt": "整理资料"}).json()["id"]
    with db_session.SessionLocal() as db:
        task = tasks.get_task(db, task_id)
        for step in task.steps[:-1]:
            step.status = "done"
            step.detail_json = json.dumps({"tool_hint": "fetch_url", "context": "已读来源 UNIQUE_PERSISTED_EVIDENCE", "evidence": "已读取参考链接"})
        task.status = "paused"
        db.commit()
    observed = []
    async def report(_settings, _task, search_bits):
        observed.extend(search_bits)
        return "# 来源\n\nUNIQUE_PERSISTED_EVIDENCE"
    monkeypatch.setattr(tasks, "_write_report", report)
    client.post(f"/api/tasks/{task_id}/resume")
    assert wait(client, task_id)["status"] == "succeeded"
    assert any("UNIQUE_PERSISTED_EVIDENCE" in value for value in observed)
