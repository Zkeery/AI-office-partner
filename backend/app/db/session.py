from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Base, make_engine, make_session_factory

_settings = get_settings()
_settings.data_path.mkdir(parents=True, exist_ok=True)
_settings.uploads_path.mkdir(parents=True, exist_ok=True)
_settings.artifacts_path.mkdir(parents=True, exist_ok=True)

engine = make_engine(f"sqlite:///{_settings.db_path}")
SessionLocal = make_session_factory(engine)


def _ensure_schedule_columns() -> None:
    """SQLite create_all 不补已有表列；为 1.22 事件触发补列。"""
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(schedules)")).fetchall()
        if not rows:
            return
        cols = {r[1] for r in rows}
        for name, kind in (("model_id", "VARCHAR(80)"), ("model_name", "VARCHAR(200)")):
            if name not in cols:
                conn.execute(text(f"ALTER TABLE schedules ADD COLUMN {name} {kind}"))
        for name, kind in (("input_config_json", "TEXT NOT NULL DEFAULT '{}'"), ("token_budget", "INTEGER"), ("active_run_id", "VARCHAR(36)")):
            if name not in cols:
                conn.execute(text(f"ALTER TABLE schedules ADD COLUMN {name} {kind}"))
        if "trigger_mode" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE schedules ADD COLUMN trigger_mode VARCHAR(40) "
                    "NOT NULL DEFAULT 'interval'"
                )
            )
        if "listen_schedule_id" not in cols:
            conn.execute(
                text("ALTER TABLE schedules ADD COLUMN listen_schedule_id VARCHAR(36)")
            )
        if "hook_token" not in cols:
            conn.execute(
                text("ALTER TABLE schedules ADD COLUMN hook_token VARCHAR(128)")
            )
        if "feishu_notify" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE schedules ADD COLUMN feishu_notify BOOLEAN "
                    "NOT NULL DEFAULT 0"
                )
            )
        if "feishu_notify_chat_id" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE schedules ADD COLUMN feishu_notify_chat_id VARCHAR(128)"
                )
            )


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_schedule_columns()
    with engine.begin() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(tasks)"))}
        if "operation_token" not in cols:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN operation_token VARCHAR(36) NOT NULL DEFAULT ''"))
        run_cols = {r[1] for r in conn.execute(text("PRAGMA table_info(schedule_runs)"))}
        for name, kind in (("input_manifest_json", "TEXT NOT NULL DEFAULT '{}'"), ("token_budget", "INTEGER"), ("budget_used_tokens", "INTEGER NOT NULL DEFAULT 0"), ("upstream_run_id", "VARCHAR(36)")):
            if name not in run_cols:
                conn.execute(text(f"ALTER TABLE schedule_runs ADD COLUMN {name} {kind}"))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
