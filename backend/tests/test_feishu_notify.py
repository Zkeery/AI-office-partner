"""1.23 飞书群通知：mock 发送、时机开关、未配置跳过、不打断自动化。"""
from __future__ import annotations

from app.core.errors import AppError


def test_should_notify_matrix():
    from app.services.feishu_notify import should_notify

    assert should_notify(notify_on="off", status="failed", schedule_enabled=True) is False
    assert should_notify(notify_on="failed", status="failed", schedule_enabled=True) is True
    assert should_notify(notify_on="failed", status="success", schedule_enabled=True) is False
    assert should_notify(notify_on="always", status="success", schedule_enabled=True) is True
    assert should_notify(notify_on="always", status="failed", schedule_enabled=True) is True
    assert should_notify(notify_on="always", status="failed", schedule_enabled=False) is False


def test_build_notify_text_hides_secretish_errors():
    from app.services.feishu_notify import build_notify_text

    text = build_notify_text(
        schedule_name="周报",
        status="failed",
        error="boom APP_SECRET=abc tenant_access_token=xyz",
        task_id="t1",
        frontend_origin="http://127.0.0.1:3040",
    )
    assert "周报" in text and "失败" in text
    assert "APP_SECRET" not in text
    assert "tenant_access_token" not in text
    assert "t1" in text


def test_notify_prefs_api_and_mock_send_on_failed_run(client, monkeypatch):
    # 默认 mock；配置全局时机与目标群
    put = client.put(
        "/api/feishu/notify",
        json={"notify_on": "failed", "chat_id": "oc_test_chat"},
    )
    assert put.status_code == 200
    body = put.json()
    assert body["notify_on"] == "failed"
    assert body["chat_id"] == "oc_test_chat"
    assert body["feishu_mock"] is True
    assert "hint" in body

    get = client.get("/api/feishu/notify")
    assert get.status_code == 200
    assert get.json()["chat_id_configured"] is True

    # 创建并打开「发飞书」
    r = client.post(
        "/api/schedules",
        json={"model_id": "mock",
            "name": "飞书通知自动化",
            "prompt": "测失败通知",
            "interval_minutes": 60,
            "skill_id": "industry_brief",
            "enabled": True,
            "feishu_notify": True,
        },
    )
    assert r.status_code == 200
    sid = r.json()["id"]
    assert r.json()["feishu_notify"] is True

    async def boom_execute(*_args, **_kwargs):
        raise AppError("RUN_FAILED", "飞书通知测失败", status_code=500)

    monkeypatch.setattr("app.services.tasks._execute_agent", boom_execute)

    bad = client.post(f"/api/schedules/{sid}/run-now")
    assert bad.status_code == 200  # 通知失败也不打断跑次落库
    assert bad.json()["last_error"]

    log = client.get("/api/feishu/notify/log?limit=10")
    assert log.status_code == 200
    items = log.json()["items"]
    assert items, "mock 下应有本地发送记录"
    latest = items[0]
    assert latest["status"] == "mocked"
    assert latest["mock"] is True
    assert latest["schedule_id"] == sid
    assert latest["run_status"] == "failed"
    assert "已模拟发送" in (latest.get("message") or "")

    # 站内 notices 仍在
    notices = client.get("/api/schedules/notices?status=failed&limit=5")
    assert notices.status_code == 200
    assert any(n["schedule_id"] == sid for n in notices.json()["items"])


def test_notify_off_and_schedule_flag_skip(client, monkeypatch):
    client.put("/api/feishu/notify", json={"notify_on": "off", "chat_id": "oc_x"})

    r = client.post(
        "/api/schedules",
        json={"model_id": "mock",
            "name": "关闭全局",
            "prompt": "不应发飞书",
            "interval_minutes": 30,
            "skill_id": "industry_brief",
            "feishu_notify": True,
        },
    )
    sid = r.json()["id"]

    async def boom(*_a, **_k):
        raise AppError("RUN_FAILED", "仍失败但不发飞书", status_code=500)

    monkeypatch.setattr("app.services.tasks._execute_agent", boom)
    assert client.post(f"/api/schedules/{sid}/run-now").status_code == 200
    assert client.get("/api/feishu/notify/log").json()["items"] == []

    # 打开全局，但单条未开「发飞书」
    client.put("/api/feishu/notify", json={"notify_on": "always"})
    r2 = client.post(
        "/api/schedules",
        json={"model_id": "mock",
            "name": "未开单条",
            "prompt": "成功也不发",
            "interval_minutes": 30,
            "skill_id": "industry_brief",
            "feishu_notify": False,
        },
    )
    sid2 = r2.json()["id"]
    ok = client.post(f"/api/schedules/{sid2}/run-now")
    assert ok.status_code == 200
    assert client.get("/api/feishu/notify/log").json()["items"] == []


def test_notify_always_sends_on_success_mock(client):
    client.put(
        "/api/feishu/notify",
        json={"notify_on": "always", "chat_id": "oc_ok"},
    )
    r = client.post(
        "/api/schedules",
        json={"model_id": "mock",
            "name": "成功也推",
            "prompt": "成功路径",
            "interval_minutes": 60,
            "skill_id": "industry_brief",
            "feishu_notify": True,
        },
    )
    sid = r.json()["id"]
    ok = client.post(f"/api/schedules/{sid}/run-now")
    assert ok.status_code == 200
    items = client.get("/api/feishu/notify/log").json()["items"]
    assert items
    assert items[0]["run_status"] == "success"
    assert items[0]["status"] == "mocked"


def test_notify_real_mode_without_credentials_skips(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("FEISHU_MOCK", "0")
    monkeypatch.setenv("FEISHU_APP_ID", "")
    monkeypatch.setenv("FEISHU_APP_SECRET", "")
    get_settings.cache_clear()

    client.put(
        "/api/feishu/notify",
        json={"notify_on": "failed", "chat_id": "oc_need_creds"},
    )
    r = client.post(
        "/api/schedules",
        json={"model_id": "mock",
            "name": "无凭证",
            "prompt": "应跳过",
            "interval_minutes": 60,
            "skill_id": "industry_brief",
            "feishu_notify": True,
        },
    )
    sid = r.json()["id"]

    async def boom(*_a, **_k):
        raise AppError("RUN_FAILED", "无凭证测", status_code=500)

    monkeypatch.setattr("app.services.tasks._execute_agent", boom)
    assert client.post(f"/api/schedules/{sid}/run-now").status_code == 200

    items = client.get("/api/feishu/notify/log").json()["items"]
    assert items
    assert items[0]["status"] == "skipped"
    assert items[0]["code"] == "FEISHU_NOT_CONFIGURED"
    # 恢复 cache，避免污染同进程后续用例
    monkeypatch.setenv("FEISHU_MOCK", "1")
    get_settings.cache_clear()


def test_notify_prefs_validation(client):
    bad = client.put("/api/feishu/notify", json={"notify_on": "sometimes"})
    assert bad.status_code == 400


def test_schedule_patch_feishu_notify_fields(client):
    r = client.post(
        "/api/schedules",
        json={"model_id": "mock",
            "name": "补丁飞书字段",
            "prompt": "x",
            "interval_minutes": 60,
            "skill_id": "industry_brief",
        },
    )
    sid = r.json()["id"]
    assert r.json().get("feishu_notify") is False

    patched = client.patch(
        f"/api/schedules/{sid}",
        json={"feishu_notify": True, "feishu_notify_chat_id": "oc_override"},
    )
    assert patched.status_code == 200
    assert patched.json()["feishu_notify"] is True
    assert patched.json()["feishu_notify_chat_id"] == "oc_override"
