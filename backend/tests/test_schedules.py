from __future__ import annotations

from app.core.errors import AppError


def test_schedule_create_run_disable(client):
    r = client.post(
        "/api/schedules",
        json={"model_id": "mock",
            "name": "每小时速览",
            "prompt": "定时行业速览测试",
            "interval_minutes": 60,
            "skill_id": "industry_brief",
            "enabled": True,
        },
    )
    assert r.status_code == 200
    sid = r.json()["id"]
    assert r.json()["enabled"] is True

    run = client.post(f"/api/schedules/{sid}/run-now")
    assert run.status_code == 200
    body = run.json()
    assert body["last_task_id"]
    assert body["last_run_at"]
    assert body["last_error"] is None
    task_id = body["last_task_id"]
    task = client.get(f"/api/tasks/{task_id}").json()
    assert task["status"] == "succeeded"
    assert task["skill_id"] == "industry_brief"

    listed = client.get("/api/schedules").json()["items"]
    match = next(i for i in listed if i["id"] == sid)
    assert match["last_run_at"]
    assert match["last_task_id"] == task_id
    assert match["last_error"] is None

    off = client.patch(f"/api/schedules/{sid}", json={"enabled": False})
    assert off.status_code == 200
    assert off.json()["enabled"] is False

    listed = client.get("/api/schedules").json()["items"]
    assert any(i["id"] == sid for i in listed)

    deleted = client.delete(f"/api/schedules/{sid}")
    assert deleted.status_code == 200
    assert client.get("/api/schedules").json()["items"] == []


def test_schedule_apperror_sets_last_error_and_last_run_at(client, monkeypatch):
    r = client.post(
        "/api/schedules",
        json={"model_id": "mock",
            "name": "失败自动化",
            "prompt": "触发 AppError",
            "interval_minutes": 30,
            "enabled": True,
        },
    )
    assert r.status_code == 200
    sid = r.json()["id"]

    async def boom_create(*_args, **_kwargs):
        raise AppError("PLAN_FAILED", "计划生成失败，请重试", status_code=500)

    monkeypatch.setattr("app.services.schedules.task_service.create_task", boom_create)

    run = client.post(f"/api/schedules/{sid}/run-now")
    assert run.status_code == 500

    listed = client.get("/api/schedules").json()["items"]
    match = next(i for i in listed if i["id"] == sid)
    assert match["last_error"]
    assert "PLAN_FAILED" in match["last_error"]
    assert match["last_run_at"]


def test_schedule_task_failed_keeps_last_task_and_error(client, monkeypatch):
    r = client.post(
        "/api/schedules",
        json={"model_id": "mock",
            "name": "执行失败自动化",
            "prompt": "任务跑挂后仍可跟",
            "interval_minutes": 60,
            "skill_id": "industry_brief",
            "enabled": True,
        },
    )
    assert r.status_code == 200
    sid = r.json()["id"]

    async def boom_execute(*_args, **_kwargs):
        raise AppError("RUN_FAILED", "模拟执行失败", status_code=500)

    monkeypatch.setattr("app.services.tasks._execute_agent", boom_execute)

    run = client.post(f"/api/schedules/{sid}/run-now")
    assert run.status_code == 200
    body = run.json()
    assert body["last_task_id"]
    assert body["last_run_at"]
    assert body["last_error"]
    assert "RUN_FAILED" in body["last_error"] or "模拟执行失败" in body["last_error"]

    task_id = body["last_task_id"]
    task = client.get(f"/api/tasks/{task_id}").json()
    assert task["status"] == "failed"

    listed = client.get("/api/schedules").json()["items"]
    match = next(i for i in listed if i["id"] == sid)
    assert match["last_error"]
    assert match["last_task_id"] == task_id
    assert match["last_run_at"]


def test_schedule_run_history_success_and_fail(client, monkeypatch):
    r = client.post(
        "/api/schedules",
        json={"model_id": "mock",
            "name": "跑次历史",
            "prompt": "连续跑两次看历史",
            "interval_minutes": 60,
            "skill_id": "industry_brief",
            "enabled": True,
        },
    )
    assert r.status_code == 200
    sid = r.json()["id"]

    ok = client.post(f"/api/schedules/{sid}/run-now")
    assert ok.status_code == 200
    ok_task = ok.json()["last_task_id"]
    assert ok.json()["last_error"] is None

    async def boom_execute(*_args, **_kwargs):
        raise AppError("RUN_FAILED", "第二次失败", status_code=500)

    monkeypatch.setattr("app.services.tasks._execute_agent", boom_execute)

    bad = client.post(f"/api/schedules/{sid}/run-now")
    assert bad.status_code == 200
    bad_task = bad.json()["last_task_id"]
    assert bad.json()["last_error"]
    assert "第二次失败" in bad.json()["last_error"] or "RUN_FAILED" in bad.json()["last_error"]

    hist = client.get(f"/api/schedules/{sid}/runs?limit=20")
    assert hist.status_code == 200
    items = hist.json()["items"]
    assert len(items) >= 2
    # newest first
    assert items[0]["status"] == "failed"
    assert items[0]["task_id"] == bad_task
    assert items[0]["error"]
    assert items[1]["status"] == "success"
    assert items[1]["task_id"] == ok_task
    assert items[1]["error"] is None
    finished = [i["finished_at"] for i in items[:2]]
    assert finished[0] >= finished[1]

    # last_* still matches newest
    listed = client.get("/api/schedules").json()["items"]
    match = next(i for i in listed if i["id"] == sid)
    assert match["last_task_id"] == bad_task
    assert match["last_error"]
    assert match["last_run_at"]


def test_schedule_run_history_apperror_and_prune(client, monkeypatch):
    r = client.post(
        "/api/schedules",
        json={"model_id": "mock",
            "name": "裁剪历史",
            "prompt": "超过 N 条淘汰",
            "interval_minutes": 30,
            "enabled": True,
        },
    )
    assert r.status_code == 200
    sid = r.json()["id"]

    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("SCHEDULE_RUN_KEEP", "3")
    get_settings.cache_clear()

    async def boom_create(*_args, **_kwargs):
        raise AppError("PLAN_FAILED", "计划失败", status_code=500)

    monkeypatch.setattr("app.services.schedules.task_service.create_task", boom_create)

    for _ in range(5):
        run = client.post(f"/api/schedules/{sid}/run-now")
        assert run.status_code == 500

    hist = client.get(f"/api/schedules/{sid}/runs?limit=20")
    assert hist.status_code == 200
    items = hist.json()["items"]
    assert len(items) == 3
    assert all(i["status"] == "failed" for i in items)
    assert all("PLAN_FAILED" in (i["error"] or "") for i in items)
    # still newest first
    for a, b in zip(items, items[1:]):
        assert (a["finished_at"] or "") >= (b["finished_at"] or "")

    listed = client.get("/api/schedules").json()["items"]
    match = next(i for i in listed if i["id"] == sid)
    assert match["last_error"]
    assert match["last_run_at"]

    missing = client.get("/api/schedules/does-not-exist/runs")
    assert missing.status_code == 404


def test_unread_notices_filters_acked():
    from app.services.schedules import unread_notices

    notices = [
        {"run_id": "r1", "status": "failed"},
        {"run_id": "r2", "status": "success"},
        {"run_id": "r3", "status": "failed"},
    ]
    assert unread_notices(notices, acked_run_ids=set()) == notices
    assert unread_notices(notices, acked_run_ids={"r1"}) == notices[1:]
    assert unread_notices(notices, acked_run_ids=["r1", "r2", "r3"]) == []
    assert unread_notices(notices, acked_run_ids={"r9"}) == notices


def test_schedule_result_notices_success_and_fail(client, monkeypatch):
    r = client.post(
        "/api/schedules",
        json={"model_id": "mock",
            "name": "结果通知自动化",
            "prompt": "跑出成功和失败各一次",
            "interval_minutes": 60,
            "skill_id": "industry_brief",
            "enabled": True,
        },
    )
    assert r.status_code == 200
    sid = r.json()["id"]

    ok = client.post(f"/api/schedules/{sid}/run-now")
    assert ok.status_code == 200
    ok_task = ok.json()["last_task_id"]

    async def boom_execute(*_args, **_kwargs):
        raise AppError("RUN_FAILED", "通知测失败", status_code=500)

    monkeypatch.setattr("app.services.tasks._execute_agent", boom_execute)

    bad = client.post(f"/api/schedules/{sid}/run-now")
    assert bad.status_code == 200
    bad_task = bad.json()["last_task_id"]

    all_n = client.get("/api/schedules/notices?limit=20")
    assert all_n.status_code == 200
    items = all_n.json()["items"]
    assert len(items) >= 2
    assert items[0]["status"] == "failed"
    assert items[0]["schedule_id"] == sid
    assert items[0]["schedule_name"] == "结果通知自动化"
    assert items[0]["task_id"] == bad_task
    assert items[0]["run_id"]
    assert items[0]["error"]
    assert "通知测失败" in (items[0]["error"] or "") or "RUN_FAILED" in (items[0]["error"] or "")
    assert items[1]["status"] == "success"
    assert items[1]["task_id"] == ok_task
    assert items[1]["error"] is None

    fails = client.get("/api/schedules/notices?status=failed&limit=10")
    assert fails.status_code == 200
    fail_items = fails.json()["items"]
    assert fail_items
    assert all(i["status"] == "failed" for i in fail_items)
    assert fail_items[0]["run_id"] == items[0]["run_id"]

    oks = client.get("/api/schedules/notices?status=success&limit=10")
    assert oks.status_code == 200
    assert any(i["run_id"] == items[1]["run_id"] for i in oks.json()["items"])

    bad_status = client.get("/api/schedules/notices?status=weird")
    assert bad_status.status_code == 400

    empty_client_notices = client.get("/api/schedules/notices?limit=1")
    assert empty_client_notices.status_code == 200
    assert len(empty_client_notices.json()["items"]) == 1


def test_on_task_succeeded_triggers_listener_once(client):
    """刀1：A 立即跑成功 → B 自动出现 trigger=task_done 跑次。"""
    a = client.post(
        "/api/schedules",
        json={"model_id": "mock",
            "name": "自动化A",
            "prompt": "上游任务 A",
            "interval_minutes": 60,
            "skill_id": "industry_brief",
            "trigger_mode": "interval",
            "enabled": True,
        },
    )
    assert a.status_code == 200
    aid = a.json()["id"]

    b = client.post(
        "/api/schedules",
        json={"model_id": "mock",
            "name": "自动化B",
            "prompt": "下游任务 B，听 A 成功",
            "interval_minutes": 60,
            "skill_id": "industry_brief",
            "trigger_mode": "on_task_succeeded",
            "listen_schedule_id": aid,
            "enabled": True,
        },
    )
    assert b.status_code == 200, b.text
    bid = b.json()["id"]
    assert b.json()["trigger_mode"] == "on_task_succeeded"
    assert b.json()["listen_schedule_id"] == aid

    run_a = client.post(f"/api/schedules/{aid}/run-now")
    assert run_a.status_code == 200
    assert run_a.json()["last_error"] is None
    assert run_a.json()["last_task_id"]

    hist_b = client.get(f"/api/schedules/{bid}/runs?limit=10")
    assert hist_b.status_code == 200
    items_b = hist_b.json()["items"]
    assert len(items_b) == 1
    assert items_b[0]["status"] == "success"
    assert items_b[0]["trigger"] == "task_done"
    assert items_b[0]["task_id"]

    listed = client.get("/api/schedules").json()["items"]
    match_b = next(i for i in listed if i["id"] == bid)
    assert match_b["last_task_id"] == items_b[0]["task_id"]
    assert match_b["last_run_at"]
    assert match_b["last_error"] is None

    notices = client.get("/api/schedules/notices?limit=20").json()["items"]
    assert any(n["schedule_id"] == bid and n["trigger"] == "task_done" for n in notices)


def test_on_task_succeeded_no_self_and_depth_one(client):
    """防环：不能监听自己；A→B 后 B 成功不再链式触发 C（depth≤1）。"""
    a = client.post(
        "/api/schedules",
        json={"model_id": "mock",
            "name": "链A",
            "prompt": "A",
            "interval_minutes": 60,
            "skill_id": "industry_brief",
            "enabled": True,
        },
    )
    assert a.status_code == 200
    aid = a.json()["id"]

    b = client.post(
        "/api/schedules",
        json={"model_id": "mock",
            "name": "链B",
            "prompt": "B",
            "interval_minutes": 60,
            "skill_id": "industry_brief",
            "trigger_mode": "on_task_succeeded",
            "listen_schedule_id": aid,
            "enabled": True,
        },
    )
    assert b.status_code == 200
    bid = b.json()["id"]

    self_patch = client.patch(
        f"/api/schedules/{bid}",
        json={"listen_schedule_id": bid},
    )
    assert self_patch.status_code == 400

    c = client.post(
        "/api/schedules",
        json={"model_id": "mock",
            "name": "链C",
            "prompt": "C 不应被 B 链式触发",
            "interval_minutes": 60,
            "skill_id": "industry_brief",
            "trigger_mode": "on_task_succeeded",
            "listen_schedule_id": bid,
            "enabled": True,
        },
    )
    assert c.status_code == 200
    cid = c.json()["id"]

    run_a = client.post(f"/api/schedules/{aid}/run-now")
    assert run_a.status_code == 200

    hist_b = client.get(f"/api/schedules/{bid}/runs").json()["items"]
    assert len(hist_b) == 1
    assert hist_b[0]["trigger"] == "task_done"

    hist_c = client.get(f"/api/schedules/{cid}/runs").json()["items"]
    assert hist_c == []  # depth≤1：B 成功不继续触发 C

    missing = client.post(
        "/api/schedules",
        json={"model_id": "mock",
            "name": "缺监听",
            "prompt": "x",
            "trigger_mode": "on_task_succeeded",
            "enabled": True,
        },
    )
    assert missing.status_code == 400

    ghost = client.post(
        "/api/schedules",
        json={"model_id": "mock",
            "name": "幽灵",
            "prompt": "x",
            "trigger_mode": "on_task_succeeded",
            "listen_schedule_id": "00000000-0000-0000-0000-000000000000",
            "enabled": True,
        },
    )
    assert ghost.status_code == 400


def test_event_schedule_not_ticked_as_interval(client):
    """纯事件型不被 tick 误跑；旧 interval 仍可被 tick。"""
    import asyncio
    from datetime import timedelta

    from app.db import session as db_session
    from app.db.models import utcnow
    from app.services import schedules as schedule_service

    a = client.post(
        "/api/schedules",
        json={"model_id": "mock",
            "name": "间隔旧自动化",
            "prompt": "interval 回归",
            "interval_minutes": 60,
            "skill_id": "industry_brief",
            "trigger_mode": "interval",
            "enabled": True,
        },
    )
    assert a.status_code == 200
    aid = a.json()["id"]

    # 上游占位：B 监听它，但故意不把它标为到期，避免 A→B 链式干扰「非 tick」断言
    upstream = client.post(
        "/api/schedules",
        json={"model_id": "mock",
            "name": "未到期上游",
            "prompt": "不会在本测 tick",
            "interval_minutes": 60,
            "skill_id": "industry_brief",
            "trigger_mode": "interval",
            "enabled": True,
        },
    )
    assert upstream.status_code == 200
    uid = upstream.json()["id"]

    b = client.post(
        "/api/schedules",
        json={"model_id": "mock",
            "name": "纯事件",
            "prompt": "不应被 tick",
            "interval_minutes": 60,
            "skill_id": "industry_brief",
            "trigger_mode": "on_task_succeeded",
            "listen_schedule_id": uid,
            "enabled": True,
        },
    )
    assert b.status_code == 200
    bid = b.json()["id"]

    db = db_session.SessionLocal()
    try:
        past = utcnow() - timedelta(minutes=5)
        future = utcnow() + timedelta(hours=2)
        row_a = schedule_service.get_schedule(db, aid)
        row_b = schedule_service.get_schedule(db, bid)
        row_u = schedule_service.get_schedule(db, uid)
        row_a.next_run_at = past
        row_b.next_run_at = past  # 即便「到期」，事件型也不该被 tick 扫到
        row_u.next_run_at = future
        db.commit()
        n = asyncio.run(schedule_service.tick_due_schedules(db))
    finally:
        db.close()

    assert n == 1  # 只跑 interval 的 A

    hist_a = client.get(f"/api/schedules/{aid}/runs").json()["items"]
    assert len(hist_a) == 1
    assert hist_a[0]["trigger"] == "interval"

    hist_b = client.get(f"/api/schedules/{bid}/runs").json()["items"]
    assert hist_b == []

    hist_u = client.get(f"/api/schedules/{uid}/runs").json()["items"]
    assert hist_u == []


def test_webhook_auth_success_triggers_once(client):
    """刀2：有效密钥 POST hook → 跑次 trigger=webhook；last_* / notices 复用。"""
    created = client.post(
        "/api/schedules",
        json={"model_id": "mock",
            "name": "Webhook 目标",
            "prompt": "被 webhook 触发的任务",
            "interval_minutes": 60,
            "skill_id": "industry_brief",
            "trigger_mode": "interval",
            "enabled": True,
        },
    )
    assert created.status_code == 200
    sid = created.json()["id"]
    assert created.json().get("hook_configured") is False
    assert created.json().get("webhook_path") == f"/api/schedules/{sid}/hook"

    rotated = client.post(f"/api/schedules/{sid}/rotate-hook-token")
    assert rotated.status_code == 200, rotated.text
    body = rotated.json()
    assert body["hook_configured"] is True
    token = body["hook_token"]
    assert token and len(token) >= 20
    assert body["webhook_url"].endswith(f"/api/schedules/{sid}/hook")
    assert "X-Hook-Token" in body["usage_hint"]

    # 列表不回说明文密钥
    listed = client.get("/api/schedules").json()["items"]
    match = next(i for i in listed if i["id"] == sid)
    assert match["hook_configured"] is True
    assert "hook_token" not in match or match.get("hook_token") in (None, "")

    hit = client.post(
        f"/api/schedules/{sid}/hook",
        headers={"X-Hook-Token": token},
    )
    assert hit.status_code == 200, hit.text
    assert hit.json()["last_task_id"]
    assert hit.json()["last_error"] is None

    hist = client.get(f"/api/schedules/{sid}/runs?limit=10").json()["items"]
    assert len(hist) == 1
    assert hist[0]["status"] == "success"
    assert hist[0]["trigger"] == "webhook"
    assert hist[0]["task_id"] == hit.json()["last_task_id"]

    notices = client.get("/api/schedules/notices?limit=20").json()["items"]
    assert any(n["schedule_id"] == sid and n["trigger"] == "webhook" for n in notices)

    # ?token= 亦可
    hit2 = client.post(f"/api/schedules/{sid}/hook?token={token}")
    assert hit2.status_code == 200
    hist2 = client.get(f"/api/schedules/{sid}/runs?limit=10").json()["items"]
    assert len(hist2) == 2
    assert hist2[0]["trigger"] == "webhook"


def test_webhook_auth_failure_and_rotate_invalidates(client):
    """刀2：缺密钥/错密钥/旧密钥 → 401，不创建跑次；轮换后新密钥可用。"""
    created = client.post(
        "/api/schedules",
        json={"model_id": "mock",
            "name": "鉴权拒",
            "prompt": "不应被错误密钥触发",
            "interval_minutes": 60,
            "skill_id": "industry_brief",
            "enabled": True,
        },
    )
    assert created.status_code == 200
    sid = created.json()["id"]

    # 尚未生成密钥
    bare = client.post(f"/api/schedules/{sid}/hook")
    assert bare.status_code == 401
    assert client.get(f"/api/schedules/{sid}/runs").json()["items"] == []

    r1 = client.post(f"/api/schedules/{sid}/rotate-hook-token")
    assert r1.status_code == 200
    old_token = r1.json()["hook_token"]

    missing = client.post(f"/api/schedules/{sid}/hook")
    assert missing.status_code == 401

    wrong = client.post(
        f"/api/schedules/{sid}/hook",
        headers={"X-Hook-Token": "definitely-not-the-real-token-value!!"},
    )
    assert wrong.status_code == 401

    assert client.get(f"/api/schedules/{sid}/runs").json()["items"] == []
    listed = client.get("/api/schedules").json()["items"]
    match = next(i for i in listed if i["id"] == sid)
    assert match["last_task_id"] is None
    assert match["last_run_at"] is None

    r2 = client.post(f"/api/schedules/{sid}/rotate-hook-token")
    assert r2.status_code == 200
    new_token = r2.json()["hook_token"]
    assert new_token != old_token

    stale = client.post(
        f"/api/schedules/{sid}/hook",
        headers={"X-Hook-Token": old_token},
    )
    assert stale.status_code == 401
    assert client.get(f"/api/schedules/{sid}/runs").json()["items"] == []

    ok = client.post(
        f"/api/schedules/{sid}/hook",
        headers={"X-Hook-Token": new_token},
    )
    assert ok.status_code == 200
    hist = client.get(f"/api/schedules/{sid}/runs").json()["items"]
    assert len(hist) == 1
    assert hist[0]["trigger"] == "webhook"

    # 与 interval / run-now 并存：立即跑仍可用，trigger=manual
    manual = client.post(f"/api/schedules/{sid}/run-now")
    assert manual.status_code == 200
    hist2 = client.get(f"/api/schedules/{sid}/runs").json()["items"]
    assert len(hist2) == 2
    triggers = {h["trigger"] for h in hist2}
    assert "webhook" in triggers and "manual" in triggers
