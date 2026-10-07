"""Database claims shared by HTTP and inline execution paths."""
from __future__ import annotations

import uuid

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import Task, utcnow


def claim_task(db: Session, task: Task, *, allowed: set[str], state: str) -> str:
    token = str(uuid.uuid4())
    result = db.execute(
        update(Task).where(Task.id == task.id, Task.status.in_(allowed)).values(
            status=state, operation_token=token, error_code=None, error_message=None, updated_at=utcnow()
        ), execution_options={"synchronize_session": False},
    )
    if result.rowcount != 1:
        db.rollback()
        raise AppError("INVALID_STATE", "任务状态已改变，当前不可执行此操作，请刷新", status_code=409)
    db.commit()
    db.refresh(task)
    return token


def assert_owner(db: Session, task: Task, token: str, *, state: str = "running") -> None:
    db.refresh(task)
    if task.operation_token != token or task.status != state:
        raise AppError("TASK_SUPERSEDED", "任务已暂停或开始了新的操作，本次旧结果不会保存", status_code=409)
