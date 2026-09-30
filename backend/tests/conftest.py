from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("LLM_MOCK", "1")
os.environ.setdefault("SEARCH_MOCK", "1")
os.environ.setdefault("FEISHU_MOCK", "1")
os.environ.setdefault("COST_SOFT_LIMIT_CNY", "5")
os.environ.setdefault("LLM_PRICE_PER_1K_CNY", "0.02")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("LLM_MOCK", "1")
    monkeypatch.setenv("SEARCH_MOCK", "1")
    monkeypatch.setenv("FEISHU_MOCK", "1")
    monkeypatch.setenv("LLM_PRICE_PER_1K_CNY", "0.02")
    monkeypatch.setenv("COST_SOFT_LIMIT_CNY", "5")
    monkeypatch.delenv("LOCAL_WORKSPACE_ROOT", raising=False)
    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()

    from app.db import session as db_session
    from app.db.models import make_engine, make_session_factory
    from app.db.session import init_db
    from app.main import create_app

    db_session.engine = make_engine(f"sqlite:///{settings.db_path}")
    db_session.SessionLocal = make_session_factory(db_session.engine)
    init_db()
    app = create_app()
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()
