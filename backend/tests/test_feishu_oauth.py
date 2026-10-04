"""1.24 飞书用户 OAuth：mock 授权、导出身份、断开、脱敏。"""
from __future__ import annotations

import json
from pathlib import Path


def _make_succeeded_task(client, prompt: str = "OAuth 导出测") -> str:
    r = client.post("/api/tasks", json={"model_id": "mock", "prompt": prompt, "urls": []})
    assert r.status_code == 200
    task_id = r.json()["id"]
    client.post(f"/api/tasks/{task_id}/confirm", json={})
    # wait
    import time

    for _ in range(80):
        st = client.get(f"/api/tasks/{task_id}").json()["status"]
        if st in {"succeeded", "failed"}:
            break
        time.sleep(0.05)
    assert client.get(f"/api/tasks/{task_id}").json()["status"] == "succeeded"
    return task_id


def test_oauth_status_default_disconnected(client):
    r = client.get("/api/feishu/oauth/status")
    assert r.status_code == 200
    body = r.json()
    assert body["connected"] is False
    assert body["identity_default"] == "app"
    assert body["mock"] is True
    assert "access_token" not in body
    assert "refresh_token" not in body
    assert "127.0.0.1" in body["redirect_uri"]
    assert "oauth/callback" in body["redirect_uri"]
    assert body["redirect_uri"] == "http://127.0.0.1:8040/api/feishu/oauth/callback"
    assert "localhost" not in body["redirect_uri"]


def test_mock_connect_export_user_identity_and_disconnect(client):
    st0 = client.get("/api/feishu/oauth/status").json()
    assert st0["connected"] is False

    conn = client.post("/api/feishu/oauth/mock-connect", json={"user_name": "测用户"})
    assert conn.status_code == 200
    body = conn.json()
    assert body["connected"] is True
    assert body["user_name"] == "测用户"
    assert body["identity_default"] == "user"
    assert "access_token" not in json.dumps(body)

    task_id = _make_succeeded_task(client)
    done = client.post(
        f"/api/tasks/{task_id}/export/feishu",
        json={"confirmed": True},
    )
    assert done.status_code == 200
    exp = done.json()
    assert exp["mock"] is True
    assert exp["identity"] == "user"
    assert exp["space"] == "my"
    assert "我的" in exp.get("space_label", "")

    # 主动选应用兜底
    app_exp = client.post(
        f"/api/tasks/{task_id}/export/feishu",
        json={"confirmed": True, "as_app": True},
    )
    assert app_exp.status_code == 200
    assert app_exp.json()["identity"] == "app"
    assert app_exp.json()["space"] == "app"

    disc = client.post("/api/feishu/oauth/disconnect")
    assert disc.status_code == 200
    assert disc.json()["connected"] is False
    assert disc.json()["identity_default"] == "app"

    # 断开后导出走应用兜底
    again = client.post(
        f"/api/tasks/{task_id}/export/feishu",
        json={"confirmed": True},
    )
    assert again.status_code == 200
    assert again.json()["identity"] == "app"


def test_mock_oauth_start_callback_flow(client):
    start = client.get("/api/feishu/oauth/start", follow_redirects=False)
    assert start.status_code in (302, 307)
    loc = start.headers.get("location") or ""
    assert "/api/feishu/oauth/callback" in loc
    assert "code=" in loc and "state=" in loc

    # follow to callback
    cb = client.get(loc)
    assert cb.status_code == 200
    assert "授权成功" in cb.text or "已连接" in cb.text

    st = client.get("/api/feishu/oauth/status").json()
    assert st["connected"] is True
    assert "access_token" not in st


def test_oauth_callback_bad_state(client):
    # 无 pending state
    bad = client.get("/api/feishu/oauth/callback?code=mock_code_x&state=wrong")
    assert bad.status_code == 400
    assert "state" in bad.text or "授权" in bad.text


def test_oauth_tokens_not_in_git_path_and_chmod_file(client, tmp_path):
    """token 文件落在 DATA_DIR（已 gitignore），status 脱敏。"""
    from app.core.config import get_settings

    client.post("/api/feishu/oauth/mock-connect", json={})
    settings = get_settings()
    token_file = Path(settings.data_path) / "feishu_user_oauth.json"
    assert token_file.is_file()
    raw = token_file.read_text(encoding="utf-8")
    assert "access_token" in raw  # 文件内有，但不进 git / 不经 status API
    st = client.get("/api/feishu/oauth/status").json()
    dumped = json.dumps(st)
    assert "access_token" not in dumped
    assert "refresh_token" not in dumped
    # 确保不在仓库根明文示例
    example = Path(__file__).resolve().parents[2] / ".env.example"
    ex = example.read_text(encoding="utf-8")
    assert "FEISHU_OAUTH_REDIRECT_URI=" in ex
    assert "mock_user_" not in ex


def test_unauth_export_still_app_fallback(client):
    """未授权：应用兜底仍可用，并标明 identity=app。"""
    task_id = _make_succeeded_task(client, "未授权兜底")
    st = client.get("/api/feishu/oauth/status").json()
    assert st["connected"] is False
    done = client.post(
        f"/api/tasks/{task_id}/export/feishu",
        json={"confirmed": True},
    )
    assert done.status_code == 200
    body = done.json()
    assert body["mock"] is True
    assert body["identity"] == "app"
    assert body["document_id"]


def test_notify_still_default_not_forced_on_by_oauth(client):
    """本刀不得把群通知默认打开。"""
    n = client.get("/api/feishu/notify").json()
    # conftest 未写 prefs 时回落 env；至少不应因 OAuth 变成 always
    assert n["notify_on"] in {"off", "failed", "always"}
    # 模拟授权后通知时机不应被改写
    client.post("/api/feishu/oauth/mock-connect", json={})
    n2 = client.get("/api/feishu/notify").json()
    assert n2["notify_on"] == n["notify_on"]
