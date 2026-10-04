from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest
from sqlalchemy import create_engine, text

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.services import llm, models, tasks


def isolated_settings(**updates):
    return Settings(_env_file=None, llm_api_key="", llm_mock=False,
                    deepseek_api_key="", openai_api_key="", qwen_api_key="", doubao_api_key="").model_copy(update=updates)


def wait(client, task_id):
    for _ in range(80):
        value = client.get(f"/api/tasks/{task_id}").json()
        if value["status"] in {"succeeded", "failed"}:
            return value
        time.sleep(0.025)
    raise AssertionError("task did not finish")


def test_catalog_lists_four_providers_without_exposing_credentials(client):
    settings = get_settings()
    settings.openai_api_key = "secret-openai-sentinel"
    result = client.get("/api/models")
    assert result.status_code == 200
    items = {item["id"]: item for item in result.json()["items"]}
    assert {"deepseek", "openai", "qwen", "doubao"} <= items.keys()
    assert items["openai"]["available"] is True
    assert items["doubao"]["available"] is False
    assert "secret-openai-sentinel" not in result.text
    assert "api_key" not in result.text and "base_url" not in result.text


@pytest.mark.parametrize("endpoint", ["/api/tasks", "/api/schedules"])
@pytest.mark.parametrize("selection", [{}, {"model_id": ""}, {"model_id": "unknown"}, {"model_id": "doubao"}])
def test_new_work_requires_a_valid_configured_selection(client, endpoint, selection):
    response = client.post(endpoint, json={"prompt": "模型选择验收", **selection})
    assert response.status_code == 422
    assert client.get(endpoint).json()["items"] == []


def test_legacy_key_only_belongs_to_its_provider_and_mock_is_explicit():
    settings = isolated_settings(llm_api_key="legacy-deepseek", llm_base_url="https://api.deepseek.com/v1", llm_model="deepseek-chat")
    public = {m["id"]: m for m in models.list_models(settings)}
    assert public["deepseek"]["available"]
    assert not public["openai"]["available"]
    assert "mock" not in public
    with pytest.raises(AppError) as error:
        models.resolve_model(settings, "openai")
    assert error.value.code == "MODEL_NOT_CONFIGURED"
    settings.llm_mock = True
    assert models.resolve_model(settings, "mock").llm_mock
    assert not next(m for m in models.list_models(settings) if m["id"] == "deepseek")["available"]


@pytest.mark.parametrize("provider", ["deepseek", "openai", "qwen", "doubao"])
def test_provider_selection_reaches_actual_http_request(monkeypatch, provider):
    settings = isolated_settings(**{f"{provider}_api_key": f"key-{provider}", f"{provider}_model": f"model-{provider}"})
    selected = models.resolve_model(settings, provider)
    captured = []

    def handler(request):
        captured.append((str(request.url), request.headers["Authorization"], json.loads(request.content)))
        return httpx.Response(200, json={"choices": [{"message": {"content": "provider reply"}}]})

    client_class = httpx.AsyncClient
    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **kw: client_class(transport=httpx.MockTransport(handler), **kw))
    assert asyncio.run(llm.chat_completion(selected, "system", "user")) == "provider reply"
    url, authorization, payload = captured[0]
    assert url == getattr(settings, f"{provider}_base_url") + "/chat/completions"
    assert authorization == f"Bearer key-{provider}"
    assert payload["model"] == f"model-{provider}"
    assert settings.llm_api_key == ""  # Global configuration was not mutated.


def test_missing_key_and_upstream_errors_do_not_fall_back_to_mock(monkeypatch):
    with pytest.raises(AppError):
        asyncio.run(llm.chat_completion(isolated_settings(), "system", "user"))
    client_class = httpx.AsyncClient
    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **kw: client_class(
        transport=httpx.MockTransport(lambda req: httpx.Response(401, json={"error": "invalid key"})), **kw))
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(llm.chat_completion(isolated_settings(llm_api_key="invalid"), "system", "user"))


def test_tasks_keep_model_through_replan_execution_and_rewrite(client, monkeypatch):
    settings = get_settings()
    settings.openai_api_key, settings.openai_model = "key-openai", "gpt-test-original"
    settings.qwen_api_key, settings.qwen_model = "key-qwen", "qwen-test-original"
    calls = []

    async def capture(config, system, user):
        calls.append((config.llm_model, config.llm_api_key, config.llm_mock))
        return llm._mock_reply(system, user)

    monkeypatch.setattr(tasks, "chat_completion", capture)
    first = client.post("/api/tasks", json={"prompt": "整理周报", "skill_id": "weekly_report", "model_id": "openai"}).json()
    second = client.post("/api/tasks", json={"prompt": "整理周报", "skill_id": "weekly_report", "model_id": "qwen"}).json()
    assert first["model_id"] == "openai" and second["model_id"] == "qwen"
    # Later config changes must not silently change an existing task's concrete model.
    settings.openai_model, settings.qwen_model = "gpt-new", "qwen-new"
    assert client.post(f"/api/tasks/{first['id']}/replan", json={}).json()["model_name"] == "gpt-test-original"
    for item in (first, second):
        calls.clear()
        assert client.post(f"/api/tasks/{item['id']}/confirm", json={}).status_code == 200
        assert wait(client, item["id"])["status"] == "succeeded"
        assert client.post(f"/api/tasks/{item['id']}/rewrite", json={"instruction": "压缩正文"}).status_code == 200
        assert len(calls) >= 2
        assert all(model == item["model_name"] and key == f"key-{item['model_id']}" and not mock for model, key, mock in calls)
        assert client.get(f"/api/tasks/{item['id']}").json()["model_name"] == item["model_name"]


def test_schedule_pins_model_and_forwards_it_to_every_run(client, monkeypatch):
    settings = get_settings()
    settings.qwen_api_key, settings.qwen_model = "schedule-key", "qwen-pinned"
    seen = []

    async def capture(config, system, user):
        seen.append(config.llm_model)
        return llm._mock_reply(system, user)

    monkeypatch.setattr(tasks, "chat_completion", capture)
    scheduled = client.post("/api/schedules", json={"name": "模型继承", "prompt": "周报", "skill_id": "weekly_report", "model_id": "qwen", "enabled": False}).json()
    settings.qwen_model = "qwen-new"
    assert scheduled["model_name"] == "qwen-pinned"
    result = client.post(f"/api/schedules/{scheduled['id']}/run-now")
    assert result.status_code == 200
    assert seen and set(seen) == {"qwen-pinned"}
    assert client.get("/api/tasks").json()["items"][0]["model_id"] == "qwen"
    assert client.patch(f"/api/schedules/{scheduled['id']}", json={"model_id": None}).status_code == 422


def test_schedule_migration_preserves_existing_rows(monkeypatch):
    from app.db import session
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE schedules (id VARCHAR(36) PRIMARY KEY, name TEXT)"))
        conn.execute(text("INSERT INTO schedules VALUES ('old', 'keep me')"))
    monkeypatch.setattr(session, "engine", engine)
    session._ensure_schedule_columns()
    session._ensure_schedule_columns()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT name, model_id, model_name FROM schedules")).one() == ("keep me", None, None)
