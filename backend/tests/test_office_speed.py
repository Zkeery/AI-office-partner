from __future__ import annotations

import asyncio

import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.services.office_speed import accelerate_plan, is_write_skill
from app.services.search import web_search


def test_accelerate_write_plan_drops_search_and_shortens():
    plan = {
        "title": "周报",
        "steps": [
            {"name": "整理进展", "goal": "a", "tool_hint": "read_uploads"},
            {"name": "联网检索", "goal": "b", "tool_hint": "web_search"},
            {"name": "归纳问题", "goal": "c", "tool_hint": "none"},
            {"name": "下周计划", "goal": "d", "tool_hint": "none"},
            {"name": "起草周报", "goal": "e", "tool_hint": "write_report"},
        ],
    }
    out = accelerate_plan(plan, "weekly_report")
    assert is_write_skill("weekly_report")
    assert len(out["steps"]) <= 4
    assert not any("search" in (s.get("tool_hint") or "") for s in out["steps"])
    assert not any("检索" in (s.get("name") or "") for s in out["steps"])
    assert any("write" in (s.get("tool_hint") or "") for s in out["steps"])


def test_accelerate_research_keeps_search():
    plan = {
        "title": "竞品",
        "steps": [
            {"name": "明确名单", "goal": "a", "tool_hint": "none"},
            {"name": "联网检索", "goal": "b", "tool_hint": "web_search"},
            {"name": "对比", "goal": "c", "tool_hint": "none"},
            {"name": "成稿", "goal": "d", "tool_hint": "write_report"},
        ],
    }
    out = accelerate_plan(plan, "competitor_research")
    assert any("web_search" in (s.get("tool_hint") or "") for s in out["steps"])


def test_search_requires_key_when_not_mock():
    settings = Settings(
        search_mock=False,
        tavily_api_key="",
        llm_mock=True,
    )
    with pytest.raises(AppError) as ei:
        asyncio.run(web_search(settings, "办公 AI"))
    assert ei.value.code == "SEARCH_NOT_CONFIGURED"


def test_health_exposes_runtime_flags(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "llm_mock" in body
    assert "search_mock" in body
    assert "search_configured" in body
    assert "llm_model" in body
