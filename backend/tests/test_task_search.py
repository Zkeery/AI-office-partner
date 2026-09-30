from __future__ import annotations

import json
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


def _archive(tid: str) -> None:
    db = db_session.SessionLocal()
    try:
        task = db.get(Task, tid)
        assert task is not None
        task.status = "archived"
        task.updated_at = utcnow() - timedelta(days=3)
        db.commit()
    finally:
        db.close()


def test_task_search_archived_matches_prompt_not_generic_title(client, monkeypatch):
    monkeypatch.setenv("TASK_KEEP_RECENT", "50")
    monkeypatch.setenv("TASK_ARCHIVE_AFTER_DAYS", "3650")
    get_settings.cache_clear()

    want = client.post(
        "/api/tasks", json={"prompt": "独一无二的青柠周报搜索词", "urls": []}
    ).json()["id"]
    noise = client.post(
        "/api/tasks", json={"prompt": "最新归档干扰项芒果计划", "urls": []}
    ).json()["id"]
    client.post(f"/api/tasks/{want}/confirm", json={})
    client.post(f"/api/tasks/{noise}/confirm", json={})
    assert _wait_status(client, want, {"succeeded", "failed"}) == "succeeded"
    assert _wait_status(client, noise, {"succeeded", "failed"}) == "succeeded"

    # Force generic plan-like titles that used to false-hit on 「规划/撰写」.
    db = db_session.SessionLocal()
    try:
        w = db.get(Task, want)
        n = db.get(Task, noise)
        assert w and n
        w.title = "周报撰写规划"
        n.title = "周报撰写规划"
        db.commit()
    finally:
        db.close()

    _archive(want)
    _archive(noise)

    by_prompt = client.get("/api/tasks", params={"q": "青柠周报"}).json()["items"]
    ids = {t["id"] for t in by_prompt}
    assert want in ids
    assert noise not in ids

    # Generic title token must NOT pull archived rows that only match via title.
    by_title_token = client.get("/api/tasks", params={"q": "撰写规划"}).json()["items"]
    archived_ids = {t["id"] for t in by_title_token if t["status"] == "archived"}
    assert want not in archived_ids
    assert noise not in archived_ids

    get_settings.cache_clear()


def test_task_search_ignores_merge_note_titles(client, monkeypatch):
    """Primary must not hit on titles listed under 【已合并任务】."""
    monkeypatch.setenv("TASK_KEEP_RECENT", "50")
    monkeypatch.setenv("TASK_ARCHIVE_AFTER_DAYS", "3650")
    get_settings.cache_clear()

    primary = client.post(
        "/api/tasks", json={"prompt": "飞书导出验收主任务", "urls": []}
    ).json()["id"]
    child = client.post(
        "/api/tasks", json={"prompt": "普通能力说明一下", "urls": []}
    ).json()["id"]
    for tid in (primary, child):
        client.post(f"/api/tasks/{tid}/confirm", json={})
        assert _wait_status(client, tid, {"succeeded", "failed"}) == "succeeded"

    marker = "青柠冒烟标记词"
    db = db_session.SessionLocal()
    try:
        p = db.get(Task, primary)
        c = db.get(Task, child)
        assert p and c
        c.title = f"新Key{marker}与能力说明"
        c.user_prompt = "普通能力说明一下"
        c.status = "merged"
        meta = {}
        try:
            meta = json.loads(c.plan_json or "{}")
        except Exception:
            meta = {}
        meta["merged_into_id"] = primary
        c.plan_json = json.dumps(meta, ensure_ascii=False)
        p.user_prompt = (
            "飞书导出验收主任务\n\n"
            f"【已合并任务】\n- {c.title}（{c.id}）"
        )
        p_meta = {}
        try:
            p_meta = json.loads(p.plan_json or "{}")
        except Exception:
            p_meta = {}
        p_meta["merged_from_ids"] = [child]
        p.plan_json = json.dumps(p_meta, ensure_ascii=False)
        db.commit()
    finally:
        db.close()

    hitch = client.get(
        "/api/tasks", params={"q": marker, "include_merged": "true"}
    ).json()["items"]
    hitch_ids = {t["id"] for t in hitch}
    assert child in hitch_ids
    assert primary not in hitch_ids

    by_primary = client.get("/api/tasks", params={"q": "飞书导出验收"}).json()["items"]
    assert any(t["id"] == primary for t in by_primary)

    get_settings.cache_clear()


def test_task_search_matches_report_body(client, monkeypatch, tmp_path):
    """Keyword only in report.md still finds the task (including archived)."""
    monkeypatch.setenv("TASK_KEEP_RECENT", "50")
    monkeypatch.setenv("TASK_ARCHIVE_AFTER_DAYS", "3650")
    get_settings.cache_clear()

    tid = client.post(
        "/api/tasks", json={"prompt": "写一份普通周报提纲", "urls": []}
    ).json()["id"]
    noise = client.post(
        "/api/tasks", json={"prompt": "另一份完全无关芒果纪要", "urls": []}
    ).json()["id"]
    for x in (tid, noise):
        client.post(f"/api/tasks/{x}/confirm", json={})
        assert _wait_status(client, x, {"succeeded", "failed"}) == "succeeded"

    marker = "紫薇报告独有词"
    db = db_session.SessionLocal()
    try:
        task = db.get(Task, tid)
        other = db.get(Task, noise)
        assert task and other
        task.title = "周报撰写规划"
        other.title = "周报撰写规划"
        report_dir = tmp_path / tid
        report_dir.mkdir(parents=True)
        report_path = report_dir / "report.md"
        report_path.write_text(
            f"# 周报\n\n本周完成了{marker}相关事项。\n", encoding="utf-8"
        )
        task.report_path = str(report_path)
        db.commit()
    finally:
        db.close()

    hits = client.get("/api/tasks", params={"q": marker}).json()["items"]
    ids = {t["id"] for t in hits}
    assert tid in ids
    assert noise not in ids
    hit = next(t for t in hits if t["id"] == tid)
    assert hit.get("search_snippet")
    assert marker[:4] in (hit.get("search_snippet") or "")

    _archive(tid)
    archived_hits = client.get("/api/tasks", params={"q": marker}).json()["items"]
    assert any(t["id"] == tid for t in archived_hits)

    get_settings.cache_clear()
