from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import ModelCall, Schedule, ScheduleRun, Task, utcnow
from app.services import tasks as task_service
from app.services.models import selection_metadata
from app.services.catalog import resolve_creation_capabilities
from app.services.schedule_inputs import attach_run_inputs, configure_inputs, read_config
from app.services.usage import run_usage

TRIGGER_INTERVAL = "interval"
TRIGGER_ON_TASK_SUCCEEDED = "on_task_succeeded"
VALID_TRIGGER_MODES = frozenset({TRIGGER_INTERVAL, TRIGGER_ON_TASK_SUCCEEDED})
DEFAULT_SCHEDULE_TOKEN_BUDGET = 50_000


def serialize_schedule(row: Schedule) -> dict[str, Any]:
    token = getattr(row, "hook_token", None) or None
    inputs = read_config(row)
    return {
        "id": row.id,
        "name": row.name,
        "prompt": row.prompt,
        "model_id": row.model_id,
        "model_name": row.model_name,
        "token_budget": row.token_budget or DEFAULT_SCHEDULE_TOKEN_BUDGET,
        "active_run_id": row.active_run_id,
        "setup_required": not row.model_id,
        "urls": inputs.get("urls", []),
        "workspace_paths": [item["path"] for item in inputs.get("bindings", [])],
        "material_mode": inputs.get("material_mode", "snapshot"),
        "include_upstream_result": inputs.get("include_upstream_result", False),
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
        "finished_at": row.finished_at.isoformat() if row.finished_at and row.status != "running" else None,
        "status": row.status,
        "error": row.error,
        "trigger": row.trigger,
        "input_manifest": json.loads(row.input_manifest_json or "{}"),
        "token_budget": row.token_budget,
        "budget_used_tokens": row.budget_used_tokens,
        "upstream_run_id": row.upstream_run_id,
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
    model_id: str | None = None,
    token_budget: int | None = None,
    urls: list[str] | None = None,
    workspace_paths: list[str] | None = None,
    material_mode: str = "snapshot",
    include_upstream_result: bool = False,
) -> Schedule:
    settings = get_settings()
    chosen = selection_metadata(settings, model_id)
    skill, expert = resolve_creation_capabilities(prompt, skill_id, expert_id)
    if token_budget is None:
        token_budget = DEFAULT_SCHEDULE_TOKEN_BUDGET
    if not isinstance(token_budget, int) or isinstance(token_budget, bool) or not 1024 <= token_budget <= 1000000:
        raise AppError("BUDGET_REQUIRED", "自动化执行上限配置无效，请联系管理员。", status_code=422)
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
        model_id=chosen.get("model_id"),
        model_name=chosen.get("model_name"),
        token_budget=token_budget,
        skill_id=skill["id"] if skill else None,
        expert_id=expert["id"] if expert else None,
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
    if include_upstream_result and mode != TRIGGER_ON_TASK_SUCCEEDED:
        raise AppError("VALIDATION_ERROR", "只有上游成功触发的自动化可以读取上游报告")
    config = configure_inputs(settings, row.id, urls=urls or [], workspace_paths=workspace_paths or [], material_mode=material_mode, include_upstream_result=include_upstream_result)
    row.input_config_json = json.dumps(config, ensure_ascii=False)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_schedule(db: Session, schedule_id: str, **fields: Any) -> Schedule:
    fields = {key: value for key, value in fields.items()
              if value is not None or key not in {"urls", "workspace_paths", "material_mode", "include_upstream_result"}}
    row = get_schedule(db, schedule_id)
    if row.active_run_id:
        raise AppError("SCHEDULE_BUSY", "自动化正在运行，请等待本次结束后再修改", status_code=409)
    guarded = db.execute(update(Schedule).where(Schedule.id == schedule_id, Schedule.active_run_id.is_(None)).values(updated_at=utcnow()))
    if guarded.rowcount != 1:
        db.rollback()
        raise AppError("SCHEDULE_BUSY", "自动化已开始运行，请等待本次结束", status_code=409)
    if "token_budget" in fields:
        budget = fields["token_budget"]
        if budget is None:
            budget = DEFAULT_SCHEDULE_TOKEN_BUDGET
        if not isinstance(budget, int) or isinstance(budget, bool) or not 1024 <= budget <= 1000000:
            raise AppError("BUDGET_REQUIRED", "自动化执行上限配置无效，请联系管理员。", status_code=422)
        row.token_budget = budget
    elif not row.token_budget:
        row.token_budget = DEFAULT_SCHEDULE_TOKEN_BUDGET
    if "model_id" in fields and fields["model_id"] is None:
        raise AppError("MODEL_REQUIRED", "不能清空自动化使用的模型。", status_code=422)
    if "model_id" in fields and (fields["model_id"] != row.model_id or not row.model_name):
        chosen = selection_metadata(get_settings(), fields["model_id"])
        row.model_id, row.model_name = chosen["model_id"], chosen["model_name"]
    elif "model_id" not in fields and not row.model_id:
        chosen = selection_metadata(get_settings())
        row.model_id, row.model_name = chosen["model_id"], chosen["model_name"]
    if "name" in fields and fields["name"] is not None:
        row.name = str(fields["name"]).strip()[:200]
    if "prompt" in fields and fields["prompt"] is not None:
        if not str(fields["prompt"]).strip():
            raise AppError("VALIDATION_ERROR", "请填写任务内容")
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
    if not row.skill_id and not row.expert_id and not any(key in fields for key in ("skill_id", "expert_id")):
        skill, expert = resolve_creation_capabilities(row.prompt, None, None)
        row.skill_id = skill["id"] if skill else None
        row.expert_id = expert["id"] if expert else None
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

    if any(key in fields for key in ("urls", "workspace_paths", "material_mode", "include_upstream_result")):
        old = read_config(row)
        use_upstream = fields.get("include_upstream_result", old.get("include_upstream_result", False))
        if use_upstream and mode != TRIGGER_ON_TASK_SUCCEEDED:
            raise AppError("VALIDATION_ERROR", "只有上游成功触发的自动化可以读取上游报告")
        row.input_config_json = json.dumps(configure_inputs(
            get_settings(), row.id, urls=fields.get("urls", old.get("urls", [])),
            workspace_paths=fields.get("workspace_paths", [item["path"] for item in old.get("bindings", [])]),
            material_mode=fields.get("material_mode", old.get("material_mode", "snapshot")),
            include_upstream_result=use_upstream,
        ), ensure_ascii=False)
    elif mode != TRIGGER_ON_TASK_SUCCEEDED and read_config(row).get("include_upstream_result"):
        raise AppError("VALIDATION_ERROR", "切换为定时时请同时关闭读取上游报告")

    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


def delete_schedule(db: Session, schedule_id: str) -> None:
    row = get_schedule(db, schedule_id)
    if row.active_run_id:
        raise AppError("SCHEDULE_BUSY", "自动化正在运行，请等待本次结束后再删除", status_code=409)
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
            .where(ScheduleRun.schedule_id == schedule_id, ScheduleRun.status != "running")
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
        .where(ScheduleRun.status != "running")
        .order_by(ScheduleRun.finished_at.desc(), ScheduleRun.id.desc())
    )
    if status:
        stmt = stmt.where(ScheduleRun.status == status)
    rows = list(db.execute(stmt.limit(lim)).all())
    return [serialize_notice(run, name or "") for run, name in rows]


async def dispatch_on_schedule_succeeded(
    db: Session, source_schedule_id: str, *, chain_depth: int, upstream_run_id: str | None = None
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
                upstream_run_id=upstream_run_id,
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
    upstream_run_id: str | None = None,
    due_before: datetime | None = None,
) -> Schedule:
    """Claim and persist a run before any network call; only succeeded means success."""
    settings = get_settings()
    row = get_schedule(db, schedule_id)
    if not row.model_id:
        raise AppError("SCHEDULE_SETUP_REQUIRED", "请重新保存自动化设置后再运行", status_code=409)
    token_budget = row.token_budget or DEFAULT_SCHEDULE_TOKEN_BUDGET
    run_id, task_id = str(uuid.uuid4()), str(uuid.uuid4())
    started_at = utcnow()
    conditions = [Schedule.id == schedule_id, Schedule.active_run_id.is_(None)]
    if due_before is not None:
        conditions += [Schedule.enabled.is_(True), Schedule.trigger_mode == TRIGGER_INTERVAL,
                       Schedule.next_run_at <= due_before]
    claimed = db.execute(update(Schedule).where(*conditions).execution_options(synchronize_session=False).values(
        active_run_id=run_id, last_run_at=started_at,
        next_run_at=started_at + timedelta(minutes=row.interval_minutes),
        updated_at=started_at, token_budget=token_budget,
    ))
    if claimed.rowcount != 1:
        db.rollback()
        raise AppError("SCHEDULE_BUSY", "自动化已在执行或本次已被领取", status_code=409)
    run_row = ScheduleRun(id=run_id, schedule_id=schedule_id, task_id=task_id,
                          started_at=started_at, finished_at=started_at,
                          status="running", trigger=trigger, token_budget=token_budget,
                          budget_used_tokens=0, upstream_run_id=upstream_run_id)
    db.add(run_row)
    db.commit()
    db.refresh(row)
    config = read_config(row)
    failure: Exception | None = None
    cancelled = False
    status, error = "failed", None
    try:
        task = await task_service.create_task(
            db, row.prompt, config.get("urls", []),
            settings=settings,
            skill_id=row.skill_id,
            expert_id=row.expert_id,
            source_schedule_id=row.id,
            model_id=row.model_id,
            model_name=row.model_name,
            task_id=task_id,
            defer_plan=True,
        )
        meta = json.loads(task.plan_json)
        meta.update(schedule_run_id=run_id, upstream_run_id=upstream_run_id)
        task.plan_json = json.dumps(meta, ensure_ascii=False)
        db.commit()
        await attach_run_inputs(db, task, run_row, config, settings)
        await task_service.generate_plan(db, task.id, settings=settings)
        await task_service.confirm_and_run(
            db, task.id, confirm_cost=True, settings=settings
        )
        task = task_service.get_task(db, task.id)
        if task.status == "succeeded":
            status = "success"
            from app.services import reports
            revision = reports.current(db, task)
            manifest = json.loads(run_row.input_manifest_json or "{}")
            manifest["result"] = {"version": revision.version, "sha256": hashlib.sha256(revision.markdown.encode("utf-8")).hexdigest()}
            run_row.input_manifest_json = json.dumps(manifest, ensure_ascii=False)
            db.commit()
        else:
            status = "paused" if task.status == "paused" else "failed"
            error = f"{task.error_code or 'RUN_' + status.upper()}: {task.error_message or '任务未完成'}"
    except asyncio.CancelledError:
        cancelled = True
        status, error = "interrupted", "RUN_INTERRUPTED: 服务停止或执行被取消"
    except AppError as exc:
        failure, error = exc, f"{exc.code}: {exc.message}"
    except Exception:
        failure = AppError("RUN_FAILED", "自动化执行异常，请查看任务记录后重试", status_code=500)
        error = "RUN_FAILED: 自动化执行异常"
    db.rollback()
    now = utcnow()
    run_row = db.get(ScheduleRun, run_id)
    already_closed = run_row.status != "running"
    if already_closed:
        status, error = run_row.status, run_row.error
    run_row.status, run_row.error, run_row.finished_at = status, error, now
    actual_task = db.get(Task, task_id)
    if actual_task is None:
        run_row.task_id = None
    elif not already_closed and status in {"failed", "interrupted"} and actual_task.status in {"draft", "planning", "running"}:
        actual_task.status = "failed" if status == "failed" else "paused"
        actual_task.operation_token = str(uuid.uuid4())
        actual_task.error_code = error.split(":", 1)[0] if error else "RUN_FAILED"
        actual_task.error_message = error
    db.execute(update(Schedule).where(Schedule.id == schedule_id, Schedule.active_run_id == run_id).values(
        active_run_id=None, last_task_id=run_row.task_id, last_error=error,
        next_run_at=now + timedelta(minutes=row.interval_minutes), updated_at=now))
    db.commit()
    _prune_runs(db, schedule_id)
    db.commit()
    db.refresh(row)
    if cancelled:
        raise asyncio.CancelledError
    await _maybe_feishu_after_run(row=row, status=status, error=error, task_id=run_row.task_id, run=run_row)
    if failure:
        raise failure
    if status == "success" and chain_depth == 0:
        await dispatch_on_schedule_succeeded(db, row.id, chain_depth=1, upstream_run_id=run_id)
        db.refresh(row)
    return row


def recover_schedule_runs(db: Session) -> int:
    """Called only while holding the exclusive service lock."""
    interrupted = list(db.scalars(select(ScheduleRun).where(ScheduleRun.status == "running")))
    for run in interrupted:
        run.status, run.finished_at = "interrupted", utcnow()
        run.error = "RUN_INTERRUPTED: 上次服务退出，未确认完成；请检查任务后手动重跑"
        row = db.get(Schedule, run.schedule_id)
        if row:
            row.last_error = run.error
            row.next_run_at = utcnow() + timedelta(minutes=row.interval_minutes)
    db.execute(update(Schedule).where(Schedule.active_run_id.is_not(None)).values(active_run_id=None))
    db.execute(update(ModelCall).where(ModelCall.status == "pending").values(status="interrupted", error_code="RUN_INTERRUPTED"))
    db.commit()
    return len(interrupted)


async def tick_due_schedules(db: Session) -> int:
    """只扫 trigger_mode=interval，避免纯事件型被 30s tick 误跑。"""
    now = utcnow()
    due = list(
        db.scalars(
            select(Schedule).where(
                Schedule.enabled.is_(True),
                Schedule.next_run_at <= now,
                Schedule.trigger_mode == TRIGGER_INTERVAL,
                Schedule.model_id.is_not(None),
            )
        )
    )
    # 兼容极旧行：若 trigger_mode 列刚补上前有脏空，上面等值已够；默认 interval
    count = 0
    for row in due:
        try:
            await trigger_schedule(db, row.id, trigger="interval", chain_depth=0, due_before=now)
            count += 1
        except Exception:
            # error already recorded on row when AppError; swallow to keep loop alive
            continue
    return count
