from __future__ import annotations

import time
from datetime import timedelta

from app.core.config import get_settings
from app.db import session as db_session
from app.db.models import Task, utcnow


def _wait_status(client, task_id: str, want: set[str], timeout: float = 8.0) -> str:
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        last = client.get(f"/api/tasks/{task_id}").json().get("status") or ""
        if last in want:
            return last
        time.sleep(0.1)
    return last


def test_auto_archive_by_count(client, monkeypatch):
    monkeypatch.setenv("TASK_KEEP_RECENT", "3")
    monkeypatch.setenv("TASK_ARCHIVE_AFTER_DAYS", "3650")
    get_settings.cache_clear()

    ids = []
    for i in range(5):
        r = client.post("/api/tasks", json={"model_id": "mock", "prompt": f"归档条数测试 {i}", "urls": []})
        tid = r.json()["id"]
        ids.append(tid)
        client.post(f"/api/tasks/{tid}/confirm", json={})
        assert _wait_status(client, tid, {"succeeded", "failed"}) == "succeeded"

    listed = client.get("/api/tasks").json()["items"]
    active_ids = {t["id"] for t in listed if t["status"] != "archived"}
    assert len(active_ids) <= 3

    archived = client.get("/api/tasks?include_archived=true").json()["items"]
    archived_rows = [t for t in archived if t["status"] == "archived"]
    assert len(archived_rows) >= 2

    target = archived_rows[0]["id"]
    restored = client.post(f"/api/tasks/{target}/unarchive")
    assert restored.status_code == 200
    assert restored.json()["status"] != "archived"

    get_settings.cache_clear()


def test_auto_archive_by_age(client, monkeypatch):
    monkeypatch.setenv("TASK_KEEP_RECENT", "50")
    monkeypatch.setenv("TASK_ARCHIVE_AFTER_DAYS", "1")
    get_settings.cache_clear()

    r = client.post("/api/tasks", json={"model_id": "mock", "prompt": "归档天数测试", "urls": []})
    tid = r.json()["id"]
    client.post(f"/api/tasks/{tid}/confirm", json={})
    assert _wait_status(client, tid, {"succeeded", "failed"}) == "succeeded"

    db = db_session.SessionLocal()
    try:
        task = db.get(Task, tid)
        assert task is not None
        task.updated_at = utcnow() - timedelta(days=10)
        db.commit()
    finally:
        db.close()

    listed = client.get("/api/tasks").json()["items"]
    assert tid not in {t["id"] for t in listed}

    with_arch = client.get("/api/tasks?include_archived=true").json()["items"]
    row = next(t for t in with_arch if t["id"] == tid)
    assert row["status"] == "archived"

    get_settings.cache_clear()
