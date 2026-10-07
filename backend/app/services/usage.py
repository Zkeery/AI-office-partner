"""Per-attempt usage and conservative pre-request automation token reservations."""
from __future__ import annotations

import json
import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import ModelCall, ScheduleRun, Task


@dataclass
class CallContext:
    db: Session
    task_id: str
    run_id: str | None
    phase: str
    token: str | None = None


_context: ContextVar[CallContext | None] = ContextVar("model_call_context", default=None)


def track_calls(phase: str):
    def decorate(fn):
        @wraps(fn)
        async def wrapped(db: Session, task_id: str, *args, **kwargs):
            task = db.get(Task, task_id)
            meta = json.loads(task.plan_json or "{}") if task else {}
            run_id = meta.get("schedule_run_id")
            run = db.get(ScheduleRun, run_id) if run_id else None
            # A manual continuation or rewrite after a closed run is a user action.
            # Its usage belongs to the task, not to the already-finished automation.
            if phase == "rewrite" or not run or run.status != "running":
                run_id = None
            token = _context.set(CallContext(db, task_id, run_id, phase))
            try:
                return await fn(db, task_id, *args, **kwargs)
            finally:
                _context.reset(token)
        return wrapped
    return decorate


def reserve_attempt(settings, system: str, user: str, attempt: int) -> ModelCall | None:
    ctx = _context.get()
    if ctx is None:
        return None
    db = ctx.db
    task = db.get(Task, ctx.task_id, populate_existing=True)
    state = {"planning": "planning", "execution": "running", "rewrite": "succeeded"}[ctx.phase]
    if not task or task.status != state or (ctx.token is not None and task.operation_token != ctx.token):
        raise AppError("TASK_SUPERSEDED", "任务状态已改变，停止本次模型调用", status_code=409)
    ctx.token = task.operation_token
    # UTF-8 bytes plus message overhead is deliberately conservative. Unknown usage
    # keeps this reservation; it is never presented as a provider's bill.
    reserve = len((system + user).encode("utf-8")) + 1024 + max(1, min(settings.llm_max_output_tokens, 16384))
    if ctx.run_id:
        result = db.execute(
            update(ScheduleRun).where(
                ScheduleRun.id == ctx.run_id, ScheduleRun.status == "running",
                ScheduleRun.token_budget.is_not(None),
                ScheduleRun.budget_used_tokens + reserve <= ScheduleRun.token_budget,
            ).values(budget_used_tokens=ScheduleRun.budget_used_tokens + reserve),
            execution_options={"synchronize_session": False},
        )
        if result.rowcount != 1:
            db.rollback()
            raise AppError("BUDGET_EXCEEDED", "本次自动化达到单次处理上限，已在调用模型前停止；请减少材料或拆分任务", status_code=409)
    call = ModelCall(
        id=str(uuid.uuid4()), task_id=ctx.task_id, schedule_run_id=ctx.run_id,
        model=settings.llm_model, phase=ctx.phase, attempt=attempt, reserved_tokens=reserve,
    )
    db.add(call)
    db.commit()
    return call


def finish_attempt(call: ModelCall | None, *, status: str, settings, usage: Any = None, error_code: str | None = None, simulated: bool = False) -> None:
    ctx = _context.get()
    if call is None or ctx is None:
        return
    call.status, call.error_code = status, error_code
    values = [usage.get(k) if isinstance(usage, dict) else None for k in ("prompt_tokens", "completion_tokens", "total_tokens")]
    if all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in values) and values[2] >= values[0] + values[1]:
        call.prompt_tokens, call.completion_tokens, call.total_tokens = values
        call.usage_source = "simulated" if simulated else "provider"
        call.estimated_cost_cny = round(values[2] / 1000 * settings.llm_price_per_1k_cny, 6)
        if ctx.run_id:
            ctx.db.execute(update(ScheduleRun).where(ScheduleRun.id == ctx.run_id).values(
                budget_used_tokens=ScheduleRun.budget_used_tokens - call.reserved_tokens + values[2]
            ), execution_options={"synchronize_session": False})
    ctx.db.commit()


def usage_summary(calls: list[ModelCall]) -> dict[str, Any]:
    actual = [call for call in calls if call.usage_source == "provider"]
    return {
        "calls": len(calls), "prompt_tokens": sum(call.prompt_tokens or 0 for call in actual),
        "completion_tokens": sum(call.completion_tokens or 0 for call in actual),
        "total_tokens": sum(call.total_tokens or 0 for call in actual),
        "unknown_calls": sum(call.usage_source == "unknown" for call in calls),
        "simulated_calls": sum(call.usage_source == "simulated" for call in calls),
        "estimated_cost_cny": round(sum(call.estimated_cost_cny or 0 for call in actual), 6),
    }


def run_usage(db: Session, run_id: str) -> dict[str, Any]:
    return usage_summary(list(db.scalars(select(ModelCall).where(ModelCall.schedule_run_id == run_id))))
