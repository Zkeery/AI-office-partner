from __future__ import annotations

import asyncio

import pytest

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db import session as db_session
from app.db.models import Schedule
from app.services import catalog, llm, models, schedules, tasks
from app.services.schedules import DEFAULT_SCHEDULE_TOKEN_BUDGET
from app.services.tasks import utcnow


def isolated_settings(**updates):
    return Settings(
        _env_file=None, llm_api_key="", llm_mock=False,
        deepseek_api_key="", openai_api_key="", qwen_api_key="", doubao_api_key="",
    ).model_copy(update=updates)


@pytest.mark.parametrize("provider,base", [
    ("deepseek", "https://api.deepseek.com/v1"),
    ("openai", "https://api.openai.com/v1"),
    ("qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    ("doubao", "https://ark.cn-beijing.volces.com/api/v3"),
])
def test_default_model_uses_global_provider_and_pins_model(provider, base):
    settings = isolated_settings(llm_api_key="test-default-key", llm_base_url=base, llm_model="default-pinned")
    meta = models.selection_metadata(settings)
    assert meta["model_id"] == provider and meta["model_name"] == "default-pinned"
    settings.llm_model = "later-default"
    assert models.task_settings(settings, meta).llm_model == "default-pinned"


@pytest.mark.parametrize("updates", [
    {},
    {"openai_api_key": "configured-profile"},
    {"llm_api_key": "test-key", "llm_base_url": "https://unknown.example/v1"},
    {"llm_api_key": "test-key", "llm_model": ""},
])
def test_missing_default_does_not_choose_an_available_profile_or_mock(updates):
    with pytest.raises(AppError) as error:
        models.selection_metadata(isolated_settings(**updates))
    assert error.value.code == "DEFAULT_MODEL_NOT_CONFIGURED"
    assert "管理员" in error.value.message


@pytest.mark.parametrize("configured", [True, False])
def test_health_reports_safe_internal_defaults_when_configured_or_missing(client, monkeypatch, configured):
    settings = get_settings()
    for field, value in {
        "llm_mock": False,
        "llm_api_key": "health-test-secret" if configured else "",
        "llm_base_url": "https://api.deepseek.com/v1", "llm_model": "health-default",
        "deepseek_api_key": "",
    }.items():
        monkeypatch.setattr(settings, field, value)
    response = client.get("/health")
    assert response.status_code == 200
    value = response.json()
    assert value["default_model_id"] == ("deepseek" if configured else None)
    assert value["default_schedule_token_budget"] == DEFAULT_SCHEDULE_TOKEN_BUDGET
    assert "health-test-secret" not in response.text and "api_key" not in response.text


@pytest.mark.parametrize("endpoint", ["/api/tasks", "/api/schedules"])
def test_new_work_without_technical_fields_uses_server_defaults(client, endpoint):
    response = client.post(endpoint, json={"prompt": "整理本周工作周报", "enabled": False})
    assert response.status_code == 200
    value = response.json()
    assert value["model_id"] == "mock" and value["model_name"] == "mock"
    assert value["skill_id"] == "weekly_report" and value["expert_id"] == "ops_writer"
    if endpoint == "/api/schedules":
        assert value["token_budget"] == DEFAULT_SCHEDULE_TOKEN_BUDGET
        assert value["setup_required"] is False


@pytest.mark.parametrize("endpoint", ["/api/tasks", "/api/schedules"])
def test_default_configuration_error_creates_no_work(client, monkeypatch, endpoint):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_mock", False)
    monkeypatch.setattr(settings, "llm_api_key", "")
    response = client.post(endpoint, json={"prompt": "整理本周工作周报", "enabled": False})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "DEFAULT_MODEL_NOT_CONFIGURED"
    assert client.get(endpoint).json()["items"] == []


@pytest.mark.parametrize("endpoint", ["/api/tasks", "/api/schedules"])
def test_real_default_is_persisted_without_requiring_user_selection(client, monkeypatch, endpoint):
    settings = get_settings()
    for field, value in {
        "llm_mock": False, "llm_api_key": "test-default-key",
        "llm_base_url": "https://api.deepseek.com/v1", "llm_model": "default-original",
        "deepseek_api_key": "",
    }.items():
        monkeypatch.setattr(settings, field, value)
    seen = []

    async def capture(config, system, user):
        seen.append((config.llm_model, config.llm_mock))
        return llm._mock_reply(system, user)

    monkeypatch.setattr(tasks, "chat_completion", capture)
    response = client.post(endpoint, json={"prompt": "整理本周工作周报", "enabled": False})
    assert response.status_code == 200
    value = response.json()
    assert value["model_id"] == "deepseek" and value["model_name"] == "default-original"
    monkeypatch.setattr(settings, "llm_model", "default-changed")
    if endpoint == "/api/tasks":
        response = client.post(f"/api/tasks/{value['id']}/replan", json={})
        assert response.status_code == 200 and response.json()["model_name"] == "default-original"
        assert seen and all(item == ("default-original", False) for item in seen)
    else:
        response = client.patch(f"/api/schedules/{value['id']}", json={"name": "renamed"})
        assert response.status_code == 200 and response.json()["model_name"] == "default-original"
        assert seen == []


@pytest.mark.parametrize("endpoint", ["/api/tasks", "/api/schedules"])
def test_explicit_legacy_choices_override_capability_detection(client, endpoint):
    response = client.post(endpoint, json={
        "prompt": "整理本周工作周报", "model_id": "mock", "enabled": False,
        "skill_id": "email_draft", "expert_id": "biz_writer", "token_budget": 100000,
    })
    assert response.status_code == 200
    value = response.json()
    assert value["skill_id"] == "email_draft" and value["expert_id"] == "biz_writer"
    if endpoint == "/api/schedules":
        assert value["token_budget"] == 100000
        patched = client.patch(f"/api/schedules/{value['id']}", json={"name": "renamed"}).json()
        assert patched["token_budget"] == 100000


def test_capability_detection_keeps_generic_requests_generic():
    assert catalog.resolve_creation_capabilities("请整理这些事实", None, None) == (None, None)
    skill, expert = catalog.resolve_creation_capabilities("分析CSV表格", None, None)
    assert skill["id"] == "table_analysis" and expert["id"] == "data_analyst"
    skill, expert = catalog.resolve_creation_capabilities("整理周报", None, "biz_writer")
    assert skill["id"] == "email_draft" and expert["id"] == "biz_writer"


def make_legacy_rule(client, *, missing_model: bool, enabled: bool = False):
    value = client.post("/api/schedules", json={"prompt": "整理周报", "enabled": enabled}).json()
    with db_session.SessionLocal() as db:
        row = db.get(Schedule, value["id"])
        row.token_budget = None
        if missing_model:
            row.model_id = row.model_name = None
        row.next_run_at = utcnow()
        db.commit()
    return value["id"]


@pytest.mark.parametrize("trigger", ["manual", "interval"])
def test_legacy_missing_budget_runs_with_internal_default(client, trigger):
    sid = make_legacy_rule(client, missing_model=False, enabled=trigger == "interval")
    value = client.get("/api/schedules").json()["items"][0]
    assert not value["setup_required"] and value["token_budget"] == DEFAULT_SCHEDULE_TOKEN_BUDGET
    if trigger == "manual":
        assert client.post(f"/api/schedules/{sid}/run-now").status_code == 200
    else:
        with db_session.SessionLocal() as db:
            assert asyncio.run(schedules.tick_due_schedules(db)) == 1
    run = client.get(f"/api/schedules/{sid}/runs").json()["items"][0]
    assert run["status"] == "success" and run["token_budget"] == DEFAULT_SCHEDULE_TOKEN_BUDGET
    with db_session.SessionLocal() as db:
        assert db.get(Schedule, sid).token_budget == DEFAULT_SCHEDULE_TOKEN_BUDGET


def test_legacy_missing_model_stays_blocked_until_user_saves(client):
    sid = make_legacy_rule(client, missing_model=True)
    with db_session.SessionLocal() as db:
        row = db.get(Schedule, sid)
        assert schedules.serialize_schedule(row)["setup_required"] is True
        assert asyncio.run(schedules.tick_due_schedules(db)) == 0
        db.refresh(row)
        assert row.model_id is None and row.enabled is False
    rejected = client.post(f"/api/schedules/{sid}/run-now")
    assert rejected.status_code == 409
    assert rejected.json()["error"]["message"] == "请重新保存自动化设置后再运行"
    assert client.get(f"/api/schedules/{sid}/runs").json()["items"] == []
    saved = client.patch(f"/api/schedules/{sid}", json={"name": "用户主动保存"})
    assert saved.status_code == 200
    value = saved.json()
    assert value["model_id"] == "mock" and value["model_name"] == "mock"
    assert value["token_budget"] == DEFAULT_SCHEDULE_TOKEN_BUDGET
    assert value["setup_required"] is False and value["enabled"] is False
    assert client.get(f"/api/schedules/{sid}/runs").json()["items"] == []


def test_legacy_save_without_default_keeps_old_rule_unchanged(client, monkeypatch):
    sid = make_legacy_rule(client, missing_model=True)
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_mock", False)
    monkeypatch.setattr(settings, "llm_api_key", "")
    response = client.patch(f"/api/schedules/{sid}", json={"name": "不应保存"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "DEFAULT_MODEL_NOT_CONFIGURED"
    with db_session.SessionLocal() as db:
        row = db.get(Schedule, sid)
        assert row.model_id is None and row.token_budget is None and row.enabled is False
    assert client.get(f"/api/schedules/{sid}/runs").json()["items"] == []


def test_old_run_usage_is_not_backfilled_when_rule_is_saved(client):
    value = client.post("/api/schedules", json={"prompt": "整理周报", "enabled": False, "token_budget": 100000}).json()
    sid = value["id"]
    assert client.post(f"/api/schedules/{sid}/run-now").status_code == 200
    before = client.get(f"/api/schedules/{sid}/runs").json()["items"]
    assert client.patch(f"/api/schedules/{sid}", json={"token_budget": None}).status_code == 200
    assert client.get(f"/api/schedules/{sid}/runs").json()["items"] == before
