from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import Schedule, ScheduleRun, utcnow
from app.services import tasks as task_service

TRIGGER_INTERVAL = "interval"
TRIGGER_ON_TASK_SUCCEEDED = "on_task_succeeded"
VALID_TRIGGER_MODES = frozenset({TRIGGER_INTERVAL, TRIGGER_ON_TASK_SUCCEEDED})


def serialize_schedule(row: Schedule) -> dict[str, Any]:
    token = getattr(row, "hook_token", None) or None
    return {
        "id": row.id,
        "name": row.name,
        "prompt": row.prompt,
        "skill_id": row.skill_id,
        "expert_id": row.expert_id,
        "interval_minutes": row.interval_minutes,
        "trigger_mode": getattr(row, "trigger_mode", None) or TRIGGER_INTERVAL,
        "listen_schedule_id": getattr(row, "listen_schedule_id", None),
        "hook_configured": bool(token),
        "webhook_path": f"/api/schedules/{row.id}/hook",
        "feishu_notify": bool(getattr(row, "feishu_notify", False)),
        "feishu_notify_chat_id": getattr(row, "feishu_notify_chat_id", None) or None,
        "enabled": row.enabled,
        "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "last_task_id": row.last_task_id,
        "last_error": row.last_error,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def serialize_run(row: ScheduleRun) -> dict[str, Any]:
    return {
        "id": row.id,
        "schedule_id": row.schedule_id,
        "task_id": row.task_id,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "status": row.status,
        "error": row.error,
        "trigger": row.trigger,
    }


def list_schedules(db: Session) -> list[Schedule]:
    return list(db.scalars(select(Schedule).order_by(Schedule.created_at.desc())))


def get_schedule(db: Session, schedule_id: str) -> Schedule:
    row = db.get(Schedule, schedule_id)
    if not row:
        raise AppError("SCHEDULE_NOT_FOUND", "自动化不存在", status_code=404)
    return row


def _normalize_trigger_mode(raw: Any) -> str:
    mode = (str(raw).strip() if raw is not None else TRIGGER_INTERVAL) or TRIGGER_INTERVAL
    if mode not in VALID_TRIGGER_MODES:
        raise AppError(
            "VALIDATION_ERROR",
            "触发方式仅支持「到点重复」或「某条成功后」",
            status_code=400,
        )
    return mode


def _validate_listen_target(
    db: Session,
    *,
    trigger_mode: str,
    listen_schedule_id: str | None,
    self_id: str | None = None,
) -> str | None:
    if trigger_mode != TRIGGER_ON_TASK_SUCCEEDED:
        return None
    lid = (listen_schedule_id or "").strip() or None
    if not lid:
        raise AppError(
            "VALIDATION_ERROR",
            "请选择要监听的自动化（某条成功后再跑本条）",
            status_code=400,
        )
    if self_id and lid == self_id:
        raise AppError(
            "VALIDATION_ERROR",
            "不能监听自己（禁止自触发）",
            status_code=400,
        )
    target = db.get(Schedule, lid)
    if not target:
        raise AppError("VALIDATION_ERROR", "监听的自动化不存在", status_code=400)
    return lid


def create_schedule(
    db: Session,
    *,
    name: str,
    prompt: str,
    interval_minutes: int = 60,
    skill_id: str | None = None,
    expert_id: str | None = None,
    enabled: bool = True,
    trigger_mode: str = TRIGGER_INTERVAL,
    listen_schedule_id: str | None = None,
    feishu_notify: bool = False,
    feishu_notify_chat_id: str | None = None,
) -> Schedule:
    mode = _normalize_trigger_mode(trigger_mode)
    if interval_minutes < 1:
        raise AppError("VALIDATION_ERROR", "间隔至少 1 分钟")
    if not prompt.strip():
        raise AppError("VALIDATION_ERROR", "请填写任务内容")
    listen_id = _validate_listen_target(
        db, trigger_mode=mode, listen_schedule_id=listen_schedule_id, self_id=None
    )
    now = utcnow()
    row = Schedule(
        id=str(uuid.uuid4()),
        name=(name or "自动化").strip()[:200],
        prompt=prompt.strip(),
        skill_id=skill_id or None,
        expert_id=expert_id or None,
        interval_minutes=interval_minutes,
        trigger_mode=mode,
        listen_schedule_id=listen_id,
        feishu_notify=bool(feishu_notify),
        feishu_notify_chat_id=(str(feishu_notify_chat_id).strip() if feishu_notify_chat_id else None)
        or None,
        enabled=enabled,
        # 事件型不参与到期扫；仍写 next_run_at 占位，避免空值
        next_run_at=now + timedelta(minutes=interval_minutes),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_schedule(db: Session, schedule_id: str, **fields: Any) -> Schedule:
    row = get_schedule(db, schedule_id)
    if "name" in fields and fields["name"] is not None:
        row.name = str(fields["name"]).strip()[:200]
    if "prompt" in fields and fields["prompt"] is not None:
        row.prompt = str(fields["prompt"]).strip()
    if "interval_minutes" in fields and fields["interval_minutes"] is not None:
        mins = int(fields["interval_minutes"])
        if mins < 1:
            raise AppError("VALIDATION_ERROR", "间隔至少 1 分钟")
        row.interval_minutes = mins
    if "enabled" in fields and fields["enabled"] is not None:
        row.enabled = bool(fields["enabled"])
    if "skill_id" in fields:
        row.skill_id = fields["skill_id"] or None
    if "expert_id" in fields:
        row.expert_id = fields["expert_id"] or None
    if "feishu_notify" in fields and fields["feishu_notify"] is not None:
        row.feishu_notify = bool(fields["feishu_notify"])
    if "feishu_notify_chat_id" in fields:
        raw_chat = fields["feishu_notify_chat_id"]
        row.feishu_notify_chat_id = (
            str(raw_chat).strip() if raw_chat else None
        ) or None

    mode = getattr(row, "trigger_mode", None) or TRIGGER_INTERVAL
    listen_id = getattr(row, "listen_schedule_id", None)
    if "trigger_mode" in fields and fields["trigger_mode"] is not None:
        mode = _normalize_trigger_mode(fields["trigger_mode"])
    if "listen_schedule_id" in fields:
        listen_id = fields["listen_schedule_id"] or None
    listen_id = _validate_listen_target(
        db, trigger_mode=mode, listen_schedule_id=listen_id, self_id=row.id
    )
    row.trigger_mode = mode
    row.listen_schedule_id = listen_id

    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


def delete_schedule(db: Session, schedule_id: str) -> None:
    row = get_schedule(db, schedule_id)
    # 其他自动化若监听本条：置空 listen，避免悬空
    dependents = list(
        db.scalars(
            select(Schedule).where(Schedule.listen_schedule_id == schedule_id)
        )
    )
    for dep in dependents:
        dep.listen_schedule_id = None
        if (getattr(dep, "trigger_mode", None) or "") == TRIGGER_ON_TASK_SUCCEEDED:
            dep.enabled = False
        dep.updated_at = utcnow()
    db.delete(row)
    db.commit()


def _run_keep_limit() -> int:
    keep = int(get_settings().schedule_run_keep or 20)
    return max(1, keep)


def _append_run(
    db: Session,
    schedule_id: str,
    *,
    task_id: str | None,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    error: str | None,
    trigger: str,
) -> ScheduleRun:
    run = ScheduleRun(
        id=str(uuid.uuid4()),
        schedule_id=schedule_id,
        task_id=task_id,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        error=error,
        trigger=trigger or "manual",
    )
    db.add(run)
    db.flush()
    _prune_runs(db, schedule_id)
    return run


def _prune_runs(db: Session, schedule_id: str) -> None:
    keep = _run_keep_limit()
    rows = list(
        db.scalars(
            select(ScheduleRun)
            .where(ScheduleRun.schedule_id == schedule_id)
            .order_by(ScheduleRun.finished_at.desc(), ScheduleRun.id.desc())
        )
    )
    for old in rows[keep:]:
        db.delete(old)


def list_schedule_runs(
    db: Session, schedule_id: str, *, limit: int | None = None
) -> list[ScheduleRun]:
    get_schedule(db, schedule_id)
    keep = _run_keep_limit()
    lim = keep if limit is None else int(limit)
    lim = max(1, min(lim, max(keep, 100)))
    return list(
        db.scalars(
            select(ScheduleRun)
            .where(ScheduleRun.schedule_id == schedule_id)
            .order_by(ScheduleRun.finished_at.desc(), ScheduleRun.id.desc())
            .limit(lim)
        )
    )


def serialize_notice(run: ScheduleRun, schedule_name: str) -> dict[str, Any]:
    """站内结果通知条目（可点进任务）。"""
    return {
        "run_id": run.id,
        "schedule_id": run.schedule_id,
        "schedule_name": schedule_name or "",
        "task_id": run.task_id,
        "status": run.status,
        "error": run.error,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "trigger": run.trigger,
    }


def unread_notices(
    notices: list[dict[str, Any]], *, acked_run_ids: set[str] | list[str]
) -> list[dict[str, Any]]:
    """按已读 run_id 水位过滤未读通知（前端 localStorage / 单测共用）。"""
    acked = set(acked_run_ids or [])
    return [n for n in notices if n.get("run_id") not in acked]


def list_result_notices(
    db: Session, *, limit: int = 20, status: str | None = None
) -> list[dict[str, Any]]:
    """跨自动化汇总最近跑次，供站内提示（成功/失败均可；默认全要）。"""
    keep = _run_keep_limit()
    lim = max(1, min(int(limit), max(keep * 5, 100)))
    stmt = (
        select(ScheduleRun, Schedule.name)
        .join(Schedule, Schedule.id == ScheduleRun.schedule_id)
        .order_by(ScheduleRun.finished_at.desc(), ScheduleRun.id.desc())
    )
    if status:
        stmt = stmt.where(ScheduleRun.status == status)
    rows = list(db.execute(stmt.limit(lim)).all())
    return [serialize_notice(run, name or "") for run, name in rows]


async def dispatch_on_schedule_succeeded(
    db: Session, source_schedule_id: str, *, chain_depth: int
) -> int:
    """A 成功后触发监听它的 B；chain_depth 已计入本次将要触发的层级（≥1 不再继续链式）。"""
    if chain_depth > 1:
        return 0
    listeners = list(
        db.scalars(
            select(Schedule).where(
                Schedule.enabled.is_(True),
                Schedule.trigger_mode == TRIGGER_ON_TASK_SUCCEEDED,
                Schedule.listen_schedule_id == source_schedule_id,
            )
        )
    )
    count = 0
    for listener in listeners:
        if listener.id == source_schedule_id:
            # 禁自触发（配置层已拦；此处双保险）
            continue
        try:
            await trigger_schedule(
                db,
                listener.id,
                trigger="task_done",
                chain_depth=chain_depth,
            )
            count += 1
        except Exception:
            # B 的 last_error / run 已由 trigger_schedule 写入；不向外抛以免打断 A
            continue
    return count



def _tokens_match(stored: str | None, provided: str | None) -> bool:
    if not stored or not provided:
        return False
    a = str(stored)
    b = str(provided)
    if len(a) != len(b):
        return False
    return secrets.compare_digest(a, b)


def rotate_hook_token(db: Session, schedule_id: str) -> tuple[Schedule, str]:
    """生成/轮换入站 Webhook 密钥；明文仅返回一次，不进列表序列化。"""
    row = get_schedule(db, schedule_id)
    plain = secrets.token_urlsafe(32)
    row.hook_token = plain
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row, plain


def webhook_public_url(schedule_id: str) -> str:
    settings = get_settings()
    host = (settings.app_host or "127.0.0.1").strip() or "127.0.0.1"
    port = int(settings.app_port or 8040)
    return f"http://{host}:{port}/api/schedules/{schedule_id}/hook"


def serialize_hook_rotate(row: Schedule, plain_token: str) -> dict[str, Any]:
    base = serialize_schedule(row)
    url = webhook_public_url(row.id)
    return {
        **base,
        "hook_token": plain_token,
        "webhook_url": url,
        "usage_hint": (
            "用 POST 调用下方 URL。鉴权二选一："
            "Header「X-Hook-Token: <密钥>」，或查询参数「?token=<密钥>」。"
            "密钥只在生成/轮换时展示一次，请立即复制保存；轮换后旧密钥立即失效。"
            "仅本机/局域网可用，勿把密钥发到公网。"
        ),
    }



async def _maybe_feishu_after_run(
    *,
    row: Schedule,
    status: str,
    error: str | None,
    task_id: str | None,
    run: ScheduleRun | None,
) -> None:
    """出站飞书通知：失败也不影响自动化主流程。"""
    try:
        from app.services import feishu_notify as feishu_notify_service

        await feishu_notify_service.maybe_notify_schedule_run(
            schedule_name=row.name or "",
            schedule_feishu_notify=bool(getattr(row, "feishu_notify", False)),
            status=status,
            error=error,
            task_id=task_id,
            run_id=run.id if run else None,
            schedule_id=row.id,
            schedule_chat_id=getattr(row, "feishu_notify_chat_id", None),
        )
    except Exception:
        # 双保险：通知模块内部已吞错，这里再兜底
        return


async def trigger_webhook(
    db: Session, schedule_id: str, *, provided_token: str | None
) -> Schedule:
    """鉴权通过后以 trigger=webhook 跑一次；失败不写跑次。"""
    row = get_schedule(db, schedule_id)
    stored = getattr(row, "hook_token", None) or None
    if not stored:
        raise AppError(
            "HOOK_NOT_CONFIGURED",
            "尚未生成 Webhook 密钥，请先在自动化页生成",
            status_code=401,
        )
    if not _tokens_match(stored, (provided_token or "").strip() or None):
        raise AppError(
            "HOOK_UNAUTHORIZED",
            "Webhook 密钥无效或已失效",
            status_code=401,
        )
    return await trigger_schedule(db, schedule_id, trigger="webhook", chain_depth=0)


async def trigger_schedule(
    db: Session,
    schedule_id: str,
    *,
    trigger: str = "manual",
    chain_depth: int = 0,
) -> Schedule:
    """Create and run one research task for this schedule.

    Align schedule last_* with the actual task outcome:
    - always stamp last_run_at when a run was attempted
    - on task failed (run_agent_job swallows AppError): keep last_task_id and set last_error
    - on schedule-level AppError: set last_error; keep last_task_id if we already have one
    - always append a schedule_runs row (then prune to schedule_run_keep)
    - on success and chain_depth==0: dispatch on_task_succeeded listeners (A→B only)
    """
    settings = get_settings()
    row = get_schedule(db, schedule_id)
    task_id: str | None = None
    started_at = utcnow()
    task_succeeded = False
    try:
        task = await task_service.create_task(
            db,
            row.prompt,
            [],
            settings=settings,
            skill_id=row.skill_id,
            expert_id=row.expert_id,
            source_schedule_id=row.id,
        )
        task_id = task.id
        await task_service.confirm_and_run(
            db, task.id, confirm_cost=True, settings=settings
        )
        task = task_service.get_task(db, task.id)
        now = utcnow()
        row.last_task_id = task.id
        row.last_run_at = now
        row.next_run_at = now + timedelta(minutes=row.interval_minutes)
        row.updated_at = now
        notify_status = "success"
        notify_error: str | None = None
        run_row: ScheduleRun | None = None
        if task.status == "failed":
            code = task.error_code or "RUN_FAILED"
            msg = task.error_message or "任务执行失败"
            err = f"{code}: {msg}"
            row.last_error = err
            run_row = _append_run(
                db,
                row.id,
                task_id=task.id,
                started_at=started_at,
                finished_at=now,
                status="failed",
                error=err,
                trigger=trigger,
            )
            notify_status = "failed"
            notify_error = err
        else:
            row.last_error = None
            run_row = _append_run(
                db,
                row.id,
                task_id=task.id,
                started_at=started_at,
                finished_at=now,
                status="success",
                error=None,
                trigger=trigger,
            )
            task_succeeded = task.status == "succeeded"
            notify_status = "success"
            notify_error = None
        db.commit()
        db.refresh(row)
        await _maybe_feishu_after_run(
            row=row,
            status=notify_status,
            error=notify_error,
            task_id=task.id,
            run=run_row,
        )
    except AppError as exc:
        now = utcnow()
        err = f"{exc.code}: {exc.message}"
        row.last_error = err
        row.last_run_at = now
        row.next_run_at = now + timedelta(minutes=row.interval_minutes)
        row.updated_at = now
        if task_id:
            row.last_task_id = task_id
        run_row = _append_run(
            db,
            row.id,
            task_id=task_id,
            started_at=started_at,
            finished_at=now,
            status="failed",
            error=err,
            trigger=trigger,
        )
        db.commit()
        db.refresh(row)
        await _maybe_feishu_after_run(
            row=row,
            status="failed",
            error=err,
            task_id=task_id,
            run=run_row,
        )
        raise

    # 成功落库后再分发：仅 depth=0 的 A 可触发 B（depth≤1）
    if task_succeeded and chain_depth == 0:
        await dispatch_on_schedule_succeeded(db, row.id, chain_depth=1)
        db.refresh(row)
    return row


async def tick_due_schedules(db: Session) -> int:
    """只扫 trigger_mode=interval，避免纯事件型被 30s tick 误跑。"""
    now = utcnow()
    due = list(
        db.scalars(
            select(Schedule).where(
                Schedule.enabled.is_(True),
                Schedule.next_run_at <= now,
                Schedule.trigger_mode == TRIGGER_INTERVAL,
            )
        )
    )
    # 兼容极旧行：若 trigger_mode 列刚补上前有脏空，上面等值已够；默认 interval
    count = 0
    for row in due:
        try:
            await trigger_schedule(db, row.id, trigger="interval", chain_depth=0)
            count += 1
        except Exception:
            # error already recorded on row when AppError; swallow to keep loop alive
            continue
    return count
