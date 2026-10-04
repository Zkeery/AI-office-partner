from __future__ import annotations

import asyncio
import json
import re
import shutil
import uuid
from datetime import timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db.models import Task, TaskEvent, TaskStep, Upload, utcnow
from app.schemas.tasks import PlanOut, StepOut, TaskOut, UploadOut
from app.services.costing import estimate_cost_cny
from app.services.files import (
    MAX_BYTES,
    MAX_FILES,
    assert_allowed,
    atomic_write_text,
    extract_text,
    read_upload_bytes,
    safe_filename,
)
from app.services.llm import chat_completion
from app.services.models import selection_metadata, task_settings
from app.services.office_speed import accelerate_plan, is_write_skill
from app.services.search import fetch_url_text, web_search
from app.services import reports, table_analysis

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"

_ARCHIVEABLE = frozenset({"succeeded", "failed", "paused", "plan_ready"})
_HIDDEN_STATUSES = frozenset({"merged", "archived"})


def _load_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def _parse_plan(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    data = json.loads(text)
    plan = PlanOut.model_validate(data)
    if not (3 <= len(plan.steps) <= 8):
        raise ValueError("steps length")
    if not any(step.tool_hint == "write_report" for step in plan.steps):
        raise ValueError("a report-producing step is required")
    return plan.model_dump()


def _plan_meta(task: Task) -> dict[str, Any]:
    if not task.plan_json:
        return {}
    try:
        raw = json.loads(task.plan_json)
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _save_plan_meta(task: Task, meta: dict[str, Any]) -> None:
    task.plan_json = json.dumps(meta, ensure_ascii=False)


def serialize_task(task: Task, *, search_query: str | None = None) -> TaskOut:
    plan = None
    skill_id = None
    expert_id = None
    merged_into_id = None
    merged_from_ids: list[str] = []
    raw = _plan_meta(task)
    if raw:
        skill_id = raw.get("skill_id")
        expert_id = raw.get("expert_id")
        merged_into_id = raw.get("merged_into_id")
        from_ids = raw.get("merged_from_ids") or []
        if isinstance(from_ids, list):
            merged_from_ids = [str(x) for x in from_ids]
        try:
            plan = PlanOut.model_validate(raw)
        except Exception:
            plan = None
    steps = []
    for s in task.steps:
        try:
            detail = json.loads(s.detail_json or "{}")
        except Exception:
            detail = {}
        steps.append(StepOut(seq=s.seq, name=s.name, status=s.status, detail=detail))
    uploads = [
        UploadOut(
            id=u.id,
            filename=u.filename,
            size_bytes=u.size_bytes,
            text_excerpt=(u.text_excerpt or "")[:500],
        )
        for u in task.uploads
    ]
    snippet = None
    q = (search_query or "").strip()
    if q:
        snippet = _search_snippet_for_query(task, q)
    return TaskOut(
        id=task.id,
        title=task.title or "",
        user_prompt=task.user_prompt,
        status=task.status,
        cost_estimate_cny=task.cost_estimate_cny,
        cost_confirmed=task.cost_confirmed,
        model_id=raw.get("model_id"),
        model_name=raw.get("model_name"),
        model_label=raw.get("model_label"),
        skill_id=skill_id,
        expert_id=expert_id,
        plan=plan,
        steps=steps,
        uploads=uploads,
        report_path=task.report_path,
        has_report=bool(task.report_path and (Path(task.report_path).exists() or task.report_versions)),
        merged_into_id=merged_into_id,
        merged_from_ids=merged_from_ids,
        search_snippet=snippet,
        error_code=task.error_code,
        error_message=task.error_message,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def get_task(db: Session, task_id: str) -> Task:
    task = db.scalar(
        select(Task)
        .where(Task.id == task_id)
        .options(
            selectinload(Task.steps),
            selectinload(Task.uploads),
            selectinload(Task.events),
        )
    )
    if not task:
        raise AppError("TASK_NOT_FOUND", "任务不存在", status_code=404)
    return task


# Appended when tasks are merged; must not participate in keyword search.
_MERGE_NOTE_MARK = "【已合并任务】"
_REPORT_SEARCH_MAX_CHARS = 200_000


def _searchable_prompt_text(prompt: str | None) -> str:
    """User-typed body only — strip the merge appendix that lists other titles."""
    text = prompt or ""
    idx = text.find(_MERGE_NOTE_MARK)
    if idx >= 0:
        text = text[:idx]
    return text.rstrip()


def _read_report_text(task: Task) -> str:
    if not task.report_path:
        return ""
    path = Path(task.report_path)
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:_REPORT_SEARCH_MAX_CHARS]
    except OSError:
        return ""


def _task_matches_query(task: Task, query: str) -> bool:
    needle = query.lower()
    prompt = _searchable_prompt_text(task.user_prompt).lower()
    if task.status == "archived":
        # Archived: original prompt or report — not auto plan titles.
        return needle in prompt or needle in _read_report_text(task).lower()
    title = (task.title or "").lower()
    if needle in title or needle in prompt:
        return True
    return needle in _read_report_text(task).lower()


def _search_snippet_for_query(task: Task, query: str) -> str | None:
    """When only the report matched, return a short excerpt for the side rail."""
    needle = query.lower()
    title = (task.title or "").lower()
    prompt = _searchable_prompt_text(task.user_prompt).lower()
    if task.status != "archived" and needle in title:
        return None
    if needle in prompt:
        return None
    report = _read_report_text(task)
    lower = report.lower()
    idx = lower.find(needle)
    if idx < 0:
        return None
    start = max(0, idx - 4)
    snip = re.sub(r"\s+", " ", report[start : start + 32]).strip()
    if not snip:
        return None
    suffix = "…" if start + 32 < len(report) else ""
    prefix = "…" if start > 0 else ""
    return f"{prefix}{snip}{suffix}"


def list_tasks(
    db: Session,
    *,
    include_merged: bool = False,
    include_archived: bool = False,
    q: str | None = None,
    settings: Settings | None = None,
) -> list[Task]:
    auto_archive_tasks(db, settings=settings)
    query = (q or "").strip()
    stmt = (
        select(Task)
        .options(selectinload(Task.steps), selectinload(Task.uploads))
        .order_by(Task.created_at.desc())
    )
    if not include_merged:
        stmt = stmt.where(Task.status != "merged")
    # Searching may surface archived / report hits; otherwise hide archived by default.
    if not query and not include_archived:
        stmt = stmt.where(Task.status != "archived")
    tasks = list(db.scalars(stmt))
    if not query:
        return tasks
    return [t for t in tasks if _task_matches_query(t, query)]


def _mark_archived(db: Session, task: Task) -> None:
    meta = _plan_meta(task)
    meta["archived_from_status"] = task.status
    _save_plan_meta(task, meta)
    task.status = "archived"
    task.updated_at = utcnow()
    append_event(db, task, "progress", {"message": "已自动归档（列表过长或过旧）"})


def _as_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def auto_archive_tasks(db: Session, settings: Settings | None = None) -> int:
    """Archive old / excess idle tasks. Returns number newly archived."""
    settings = settings or get_settings()
    keep = max(1, int(settings.task_keep_recent or 8))
    days = max(1, int(settings.task_archive_after_days or 7))
    cutoff = utcnow() - timedelta(days=days)
    changed = 0

    active = list(
        db.scalars(
            select(Task)
            .where(Task.status.notin_(list(_HIDDEN_STATUSES)))
            .order_by(Task.updated_at.asc())
        )
    )
    for task in active:
        if task.status not in _ARCHIVEABLE:
            continue
        stamp = _as_utc(task.updated_at or task.created_at)
        if stamp and stamp < cutoff:
            _mark_archived(db, task)
            changed += 1

    active = list(
        db.scalars(
            select(Task)
            .where(Task.status.notin_(list(_HIDDEN_STATUSES)))
            .order_by(Task.updated_at.asc())
        )
    )
    if len(active) > keep:
        need = len(active) - keep
        candidates = [t for t in active if t.status in _ARCHIVEABLE]
        candidates.sort(key=lambda t: _as_utc(t.updated_at or t.created_at) or utcnow())
        for task in candidates[:need]:
            if task.status == "archived":
                continue
            _mark_archived(db, task)
            changed += 1

    if changed:
        db.commit()
    return changed


def unarchive_task(db: Session, task_id: str) -> Task:
    task = get_task(db, task_id)
    if task.status != "archived":
        raise AppError("INVALID_STATE", "仅已归档任务可恢复")
    meta = _plan_meta(task)
    prev = meta.pop("archived_from_status", None)
    if prev in _ARCHIVEABLE:
        task.status = str(prev)
    elif _task_has_report(task):
        task.status = "succeeded"
    else:
        task.status = "plan_ready"
    _save_plan_meta(task, meta)
    task.updated_at = utcnow()
    append_event(db, task, "progress", {"message": "已从归档恢复"})
    db.commit()
    return get_task(db, task_id)


def _task_has_report(task: Task) -> bool:
    return bool(task.report_path and Path(task.report_path).exists())


def _pick_merge_primary(tasks: list[Task]) -> Task:
    with_report = [t for t in tasks if _task_has_report(t)]
    if with_report:
        return max(with_report, key=lambda t: t.updated_at or t.created_at)
    succeeded = [t for t in tasks if t.status == "succeeded"]
    if succeeded:
        return max(succeeded, key=lambda t: t.updated_at or t.created_at)
    return max(tasks, key=lambda t: t.created_at)


def _invalidate_export_caches(task_id: str, settings: Settings) -> None:
    art = settings.artifacts_path / task_id
    for name in ("report.docx", "report.xlsx", "report.pptx"):
        p = art / name
        if p.exists():
            p.unlink()


def merge_tasks(
    db: Session,
    task_ids: list[str],
    settings: Settings | None = None,
) -> Task:
    """Merge multiple tasks into one primary; mark others as merged."""
    settings = settings or get_settings()
    ids = []
    seen: set[str] = set()
    for tid in task_ids:
        tid = (tid or "").strip()
        if not tid or tid in seen:
            continue
        seen.add(tid)
        ids.append(tid)
    if len(ids) < 2:
        raise AppError("VALIDATION_ERROR", "请至少选择 2 条任务合并")

    tasks = [get_task(db, tid) for tid in ids]
    blocked = {"running", "planning", "merged", "archived"}
    for t in tasks:
        if t.status in blocked:
            raise AppError(
                "INVALID_STATE",
                f"任务「{t.title or t.id[:8]}」状态为 {t.status}，不可合并",
            )

    primary = _pick_merge_primary(tasks)
    others = [t for t in tasks if t.id != primary.id]
    primary_revision = reports.current(db, primary) if _task_has_report(primary) else None

    sections: list[str] = []
    if _task_has_report(primary):
        sections.append(Path(primary.report_path).read_text(encoding="utf-8").strip())
    for t in others:
        if not _task_has_report(t):
            continue
        body = Path(t.report_path).read_text(encoding="utf-8").strip()
        if not body:
            continue
        label = t.title or t.id[:8]
        sections.append(f"## 附录：来自「{label}」\n\n{body}")

    if sections:
        art_dir = settings.artifacts_path / primary.id
        art_dir.mkdir(parents=True, exist_ok=True)
        report_path = art_dir / "report.md"
        primary.report_path = str(report_path)
        reports.save(
            db, primary, "\n\n---\n\n".join(sections) + "\n", reason="merge",
            instruction=f"合并 {len(others)} 个任务",
            analysis_id=primary_revision.analysis_id if primary_revision else None,
            expected_version=primary_revision.version if primary_revision else 0,
        )
        _invalidate_export_caches(primary.id, settings)

    note_lines = [f"- {t.title or '未命名'}（{t.id}）" for t in others]
    merge_note = "【已合并任务】\n" + "\n".join(note_lines)
    if "【已合并任务】" not in (primary.user_prompt or ""):
        primary.user_prompt = (primary.user_prompt or "").rstrip() + "\n\n" + merge_note

    primary_meta = _plan_meta(primary)
    prev = primary_meta.get("merged_from_ids") or []
    if not isinstance(prev, list):
        prev = []
    merged_from = list(dict.fromkeys([*prev, *[t.id for t in others]]))
    primary_meta["merged_from_ids"] = merged_from
    _save_plan_meta(primary, primary_meta)
    primary.updated_at = utcnow()

    for t in others:
        meta = _plan_meta(t)
        meta["merged_into_id"] = primary.id
        _save_plan_meta(t, meta)
        t.status = "merged"
        t.updated_at = utcnow()
        append_event(
            db,
            t,
            "progress",
            {"message": f"已合并到任务 {primary.id}", "merged_into_id": primary.id},
        )

    append_event(
        db,
        primary,
        "progress",
        {
            "message": f"已并入 {len(others)} 条任务",
            "merged_from_ids": [t.id for t in others],
        },
    )
    db.commit()
    return get_task(db, primary.id)


def append_event(db: Session, task: Task, event_type: str, payload: dict[str, Any]) -> None:
    db.add(
        TaskEvent(
            task_id=task.id,
            event_type=event_type,
            payload_json=json.dumps(payload, ensure_ascii=False),
        )
    )


def recover_running_tasks(db: Session) -> int:
    tasks = list(db.scalars(select(Task).where(Task.status == "running")))
    for task in tasks:
        task.status = "paused"
        task.updated_at = utcnow()
        append_event(db, task, "progress", {"message": "服务重启，任务已暂停，可点继续"})
    if tasks:
        db.commit()
    return len(tasks)


async def create_task(
    db: Session,
    prompt: str,
    urls: list[str],
    settings: Settings | None = None,
    skill_id: str | None = None,
    expert_id: str | None = None,
    source_schedule_id: str | None = None,
    model_id: str | None = None,
    model_name: str | None = None,
) -> Task:
    from app.services.catalog import resolve_skill_and_expert

    settings = settings or get_settings()
    skill, expert = resolve_skill_and_expert(skill_id, expert_id)
    meta = {
        "urls": urls,
        "skill_id": skill["id"] if skill else None,
        "expert_id": expert["id"] if expert else None,
    }
    if source_schedule_id:
        meta["source_schedule_id"] = source_schedule_id
    if model_id is not None:
        meta.update(selection_metadata(settings, model_id, model_name))
    task = Task(
        id=str(uuid.uuid4()),
        title="",
        user_prompt=prompt.strip(),
        status="planning",
        plan_json=json.dumps(meta, ensure_ascii=False),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    await generate_plan(db, task.id, urls=urls, settings=settings)
    return get_task(db, task.id)


async def generate_plan(
    db: Session,
    task_id: str,
    urls: list[str] | None = None,
    settings: Settings | None = None,
) -> Task:
    from app.services.catalog import resolve_skill_and_expert

    settings = settings or get_settings()
    task = get_task(db, task_id)
    settings = task_settings(settings, _plan_meta(task))
    task.status = "planning"
    task.error_code = None
    task.error_message = None
    db.commit()

    existing = {}
    try:
        existing = json.loads(task.plan_json or "{}")
    except Exception:
        existing = {}
    url_list = urls if urls is not None else existing.get("urls") or []
    skill, expert = resolve_skill_and_expert(existing.get("skill_id"), existing.get("expert_id"))
    upload_summary = "\n".join(
        f"- {u.filename}: {(u.text_excerpt or '')[:300]}" for u in task.uploads
    ) or "（无）"

    system = _load_prompt("plan.md")
    if skill:
        system += f"\n\n【技能：{skill['name']}】\n{skill['plan_hint']}\n"
    if expert:
        system += f"\n\n【专家人设：{expert['name']}】\n{expert['persona']}\n"
    user = (
        f"用户需求：\n{task.user_prompt}\n\n"
        f"参考链接：{url_list}\n\n"
        f"上传材料摘要：\n{upload_summary}\n"
    )
    if skill:
        user += f"\n请按技能「{skill['name']}」组织步骤。skill_id={skill['id']}\n"

    plan_dict = None
    skill_id = skill["id"] if skill else None
    for _ in range(3):
        try:
            raw = await chat_completion(settings, system, user)
            plan_dict = _parse_plan(raw)
            plan_dict = accelerate_plan(plan_dict, skill_id)
            break
        except Exception:
            plan_dict = None
    if plan_dict is None:
        task.status = "failed"
        task.error_code = "PLAN_FAILED"
        task.error_message = "计划生成失败，请重试"
        append_event(db, task, "error", {"code": "PLAN_FAILED", "message": task.error_message})
        db.commit()
        raise AppError("PLAN_FAILED", "计划生成失败，请重试", status_code=500)

    cost = estimate_cost_cny(settings, plan_dict)
    task.title = plan_dict.get("title") or "调研任务"
    plan_payload = {
        **plan_dict,
        "urls": url_list,
        "skill_id": skill_id,
        "expert_id": expert["id"] if expert else None,
    }
    for key in ("model_id", "model_name", "model_label"):
        if key in existing:
            plan_payload[key] = existing[key]
    # 保留自动化来源，供 1.22 A→B 事件触发关联
    if existing.get("source_schedule_id"):
        plan_payload["source_schedule_id"] = existing["source_schedule_id"]
    task.plan_json = json.dumps(plan_payload, ensure_ascii=False)
    task.cost_estimate_cny = cost
    task.cost_confirmed = False
    task.status = "plan_ready"

    for s in list(task.steps):
        db.delete(s)
    db.flush()
    for i, step in enumerate(plan_dict.get("steps") or [], start=1):
        db.add(
            TaskStep(
                task_id=task.id,
                seq=i,
                name=step.get("name") or f"步骤{i}",
                status="pending",
                detail_json=json.dumps(step, ensure_ascii=False),
            )
        )
    append_event(
        db,
        task,
        "progress",
        {"message": "计划已就绪，请确认后执行", "cost_estimate_cny": cost},
    )
    db.commit()
    return get_task(db, task.id)


async def replan_task(
    db: Session,
    task_id: str,
    *,
    prompt: str | None = None,
    urls: list[str] | None = None,
    settings: Settings | None = None,
) -> Task:
    """Regenerate plan for plan_ready / paused / failed tasks."""
    settings = settings or get_settings()
    task = get_task(db, task_id)
    if task.status not in {"plan_ready", "paused", "failed"}:
        raise AppError("INVALID_STATE", f"当前状态不可改计划：{task.status}")
    if prompt is not None:
        text = prompt.strip()
        if not text:
            raise AppError("VALIDATION_ERROR", "请填写任务内容")
        task.user_prompt = text
    task.report_path = None
    task.error_code = None
    task.error_message = None
    db.commit()
    append_event(db, task, "progress", {"message": "正在按新需求重新生成计划"})
    db.commit()
    return await generate_plan(db, task_id, urls=urls, settings=settings)


async def confirm_and_run(
    db: Session,
    task_id: str,
    confirm_cost: bool = False,
    settings: Settings | None = None,
) -> Task:
    """Sync helper for tests: confirm gates then run agent inline."""
    settings = settings or get_settings()
    task = get_task(db, task_id)
    if task.status not in {"plan_ready", "paused", "failed"}:
        raise AppError("INVALID_STATE", f"当前状态不可确认执行：{task.status}")

    if task.status == "plan_ready":
        if task.cost_estimate_cny > settings.cost_soft_limit_cny and not (
            confirm_cost or task.cost_confirmed
        ):
            raise AppError(
                "COST_CONFIRM_REQUIRED",
                f"预估费用约 ¥{task.cost_estimate_cny:.2f}，超过软上限 ¥{settings.cost_soft_limit_cny:.0f}，请确认后继续",
            )
        if confirm_cost:
            task.cost_confirmed = True

    task.status = "running"
    task.error_code = None
    task.error_message = None
    append_event(db, task, "progress", {"message": "开始执行"})
    db.commit()
    await run_agent_job(db, task_id, settings)
    return get_task(db, task_id)


async def run_agent_job(db: Session, task_id: str, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    try:
        settings = task_settings(settings, _plan_meta(get_task(db, task_id)))
        await _execute_agent(db, task_id, settings)
    except AppError as exc:
        if exc.code == "TASK_NOT_FOUND":
            return
        task = get_task(db, task_id)
        if task.status != "paused":
            _mark_step_failed(task, exc.code, exc.message)
            task.status = "failed"
            task.error_code = exc.code
            task.error_message = exc.message
            append_event(
                db, task, "error", {"code": task.error_code, "message": task.error_message}
            )
            db.commit()
    except Exception:
        try:
            task = get_task(db, task_id)
        except AppError:
            return
        if task.status != "paused":
            _mark_step_failed(task, "RUN_FAILED", "本步骤执行失败，请重试")
            task.status = "failed"
            task.error_code = "RUN_FAILED"
            task.error_message = "执行失败，请改计划或重试"
            append_event(
                db, task, "error", {"code": task.error_code, "message": task.error_message}
            )
            db.commit()


def _mark_step_failed(task: Task, code: str, message: str) -> None:
    for step in task.steps:
        if step.status == "running":
            detail = json.loads(step.detail_json or "{}")
            detail.update(error_code=code, evidence=message)
            step.detail_json = json.dumps(detail, ensure_ascii=False)
            step.status = "failed"


async def _ensure_table_analysis(db: Session, task: Task, settings: Settings) -> dict[str, Any] | None:
    meta = _plan_meta(task)
    uploads = [
        {"filename": upload.filename, "stored_path": upload.stored_path}
        for upload in task.uploads if Path(upload.filename).suffix.lower() in {".csv", ".xlsx"}
    ]
    if not uploads:
        if meta.get("skill_id") == "table_analysis":
            raise AppError("TABLE_REQUIRED", "请先上传 CSV / Excel，或从资料库选择表格，再开始分析")
        return None
    analysis_id = meta.get("analysis_id")
    if not analysis_id:
        append_event(db, task, "progress", {"message": "正在完整读取各工作表并计算指标"})
        db.commit()
        analysis_id = await asyncio.to_thread(
            table_analysis.build_snapshot, uploads, settings.artifacts_path / task.id, task.user_prompt
        )
        meta["analysis_id"] = analysis_id
        _save_plan_meta(task, meta)
        append_event(db, task, "artifact", {"kind": "table_analysis", "analysis_id": analysis_id})
        db.commit()
    return table_analysis.load_snapshot(settings.artifacts_path / task.id, analysis_id)["summary"]


async def _execute_agent(db: Session, task_id: str, settings: Settings) -> None:
    from app.services.workspace import collect_workspace_excerpts

    task = get_task(db, task_id)
    plan = json.loads(task.plan_json or "{}")
    urls = plan.get("urls") or []
    skill_id = plan.get("skill_id")
    write_fast = is_write_skill(skill_id)
    search_bits: list[str] = []
    # Table previews are never used as a substitute for full-data calculations.
    ref_texts = [
        (u.text_excerpt or "").strip()
        for u in task.uploads
        if (u.text_excerpt or "").strip() and Path(u.filename).suffix.lower() not in {".csv", ".xlsx"}
    ]
    if ref_texts:
        joined = "\n---\n".join(ref_texts)[:12000]
        search_bits.append("用户添加的参考材料：\n" + joined)
        append_event(db, task, "progress", {"message": "已读取用户添加的参考材料"})
        db.commit()
    steps = list(task.steps)
    if not steps or len(steps) > settings.agent_max_steps:
        raise AppError("STEP_LIMIT_EXCEEDED", "计划步骤超出执行范围，请重新生成较短计划")
    max_steps = len(steps)
    if not any(json.loads(step.detail_json or "{}").get("tool_hint") == "write_report" for step in steps):
        raise AppError("REPORT_STEP_REQUIRED", "计划缺少成品生成步骤，请重新生成计划")

    for idx, step in enumerate(steps, start=1):
        db.refresh(task)
        task = get_task(db, task_id)
        if task.status == "paused":
            append_event(db, task, "progress", {"message": "已暂停"})
            db.commit()
            return

        if step.status in {"done", "skipped"}:
            try:
                detail = json.loads(step.detail_json or "{}")
            except Exception:
                detail = {}
            if detail.get("context"):
                search_bits.append(detail["context"])
            elif detail.get("results"):
                search_bits.append(json.dumps(detail["results"], ensure_ascii=False))
            continue

        detail = json.loads(step.detail_json or "{}")
        detail.pop("error_code", None)
        step.status = "running"
        append_event(
            db, task, "step", {"seq": step.seq, "name": step.name, "status": "running"}
        )
        db.commit()

        hint = (detail.get("tool_hint") or "").strip().lower()
        hint = {"none": "analyze", "": "analyze", "read_local": "read_workspace"}.get(hint, hint)
        outcome = "done"
        context = ""
        if hint == "web_search":
            if write_fast:
                outcome = "skipped"
                detail["evidence"] = "此写作任务使用用户材料，未执行联网检索"
            else:
                query = (detail.get("goal") or task.user_prompt)[:300]
                results = await web_search(settings, query)
                context = json.dumps(results, ensure_ascii=False)
                detail["results"] = results
                detail["evidence"] = f"已检索并取得 {len(results)} 条结果" if results else "已执行检索，未找到公开来源；报告须标待核实"
                if not results:
                    context = "检索未找到公开来源，请明确标注待核实。"
        elif hint == "fetch_url":
            if not urls:
                outcome = "skipped"
                detail["evidence"] = "没有提供参考链接，未执行网页读取"
            else:
                parts = []
                for url in urls:
                    text = await fetch_url_text(url)
                    if not text.strip():
                        raise AppError("EMPTY_SOURCE", "参考网页没有可读取正文，请更换链接")
                    parts.append(f"来源：{url}\n{text}")
                context = "\n---\n".join(parts)
                detail["evidence"] = f"已读取 {len(parts)} 个链接，共 {sum(len(p) for p in parts)} 字符"
        elif hint in {"read_uploads", "read_workspace", "analyze_tables"}:
            analysis = await _ensure_table_analysis(db, task, settings)
            if hint == "analyze_tables" and analysis is None:
                raise AppError("TABLE_REQUIRED", "请添加 CSV 或 XLSX 数据后再执行表格计算")
            texts = [u.text_excerpt or "" for u in task.uploads if Path(u.filename).suffix.lower() not in {".csv", ".xlsx"}]
            context = "\n".join(texts)[:12000]
            detail["evidence"] = f"已读取 {len(task.uploads)} 份参考材料"
            if analysis:
                detail["analysis_id"] = analysis["id"]
                detail["evidence"] = f"已完整计算 {analysis['source_count']} 个文件、{analysis['sheet_count']} 个工作表、{analysis['row_count']} 行数据"
            if hint == "read_workspace":
                extra = collect_workspace_excerpts(settings)
                if extra:
                    context += "\n" + extra
                    detail["workspace_chars"] = len(extra)
                    detail["evidence"] = f"已读取授权目录摘录 {len(extra)} 字符；该步骤不是全目录数据分析"
            if not context.strip() and analysis is None:
                outcome = "skipped"
                detail["evidence"] = "没有可读取的参考材料，本次仅依据用户描述起草"
        elif hint == "analyze":
            analysis = await _ensure_table_analysis(db, task, settings)
            material = table_analysis.prompt_summary(analysis) if analysis else "\n---\n".join(search_bits)[-24000:]
            raw = await chat_completion(
                settings,
                "[EXECUTION_ANALYSIS] 根据已提供的需求和材料完成当前分析/结构组织步骤。输出严格 JSON："
                '{"summary":"非空的分析结论","findings":["要点"]}。不能声称使用了其他工具；缺少来源就写待核实。',
                f"需求：{task.user_prompt}\n步骤：{step.name}\n目标：{detail.get('goal', '')}\n材料：{material}",
            )
            try:
                clean = raw.strip().removeprefix(chr(96) * 3 + "json").removeprefix(chr(96) * 3).removesuffix(chr(96) * 3).strip()
                parsed = json.loads(clean)
                if not isinstance(parsed, dict) or not isinstance(parsed.get("summary"), str) or not parsed["summary"].strip():
                    raise ValueError("missing summary")
                if not isinstance(parsed.get("findings"), list) or not all(isinstance(item, str) for item in parsed["findings"]):
                    raise ValueError("invalid findings")
                context = (parsed["summary"] + "\n" + "\n".join(parsed["findings"]))[:12000]
            except (ValueError, TypeError, KeyError) as exc:
                raise AppError("ANALYSIS_INVALID", "本步骤未返回有效分析结果，请重试") from exc
            detail["evidence"] = "已生成可查看的分析结论与要点"
            detail["summary"] = parsed["summary"][:500]
        elif hint == "write_report":
            analysis = await _ensure_table_analysis(db, task, settings)
            report = await _write_report(settings, task, search_bits)
            reports.validate_markdown(report)
            art_dir = settings.artifacts_path / task.id
            report_path = art_dir / "report.md"
            task.report_path = str(report_path)
            revision = reports.save(db, task, report, reason="generated", analysis_id=analysis["id"] if analysis else None)
            detail["report_path"] = str(report_path)
            detail["evidence"] = f"已保存报告 v{revision.version}，正文 {len(report)} 字符"
            append_event(
                db, task, "artifact", {"kind": "report", "path": str(report_path)}
            )
        else:
            raise AppError("TOOL_UNSUPPORTED", f"步骤「{step.name}」要求的操作暂不支持，请改计划后重试")

        if context:
            search_bits.append(context)
            detail["context"] = context
        step.detail_json = json.dumps(detail, ensure_ascii=False)
        step.status = outcome
        append_event(db, task, "step", {"seq": step.seq, "name": step.name, "status": outcome, "evidence": detail["evidence"]})
        append_event(
            db,
            task,
            "progress",
            {"message": f"{'已完成' if outcome == 'done' else '已跳过'}：{step.name} · {detail['evidence']}", "percent": int(idx / max_steps * 100)},
        )
        db.commit()
        await asyncio.sleep(0.05)

    task = get_task(db, task_id)
    if task.status == "paused":
        return

    if not task.report_path or not Path(task.report_path).is_file():
        raise AppError("REPORT_NOT_READY", "步骤结束但没有生成报告，请重试")
    reports.validate_markdown(reports.current(db, task).markdown)
    if any(step.status not in {"done", "skipped"} for step in task.steps):
        raise AppError("STEPS_INCOMPLETE", "仍有步骤未完成，任务不能标记成功")

    task.status = "succeeded"
    append_event(db, task, "done", {"task_id": task.id, "status": "succeeded"})
    db.commit()


async def _write_report(settings: Settings, task: Task, search_bits: list[str]) -> str:
    from app.services.catalog import resolve_skill_and_expert

    system = _load_prompt("report.md")
    try:
        meta = json.loads(task.plan_json or "{}")
    except Exception:
        meta = {}
    skill, expert = resolve_skill_and_expert(meta.get("skill_id"), meta.get("expert_id"))
    if expert:
        system += f"\n\n【专家人设：{expert['name']}】\n{expert['persona']}\n"
    if skill:
        system += f"\n\n【技能成稿要求：{skill['name']}】\n{skill['report_hint']}\n"
    user = (
        f"用户需求：\n{task.user_prompt}\n\n"
        f"计划：\n{task.plan_json}\n\n"
        f"已收集摘录：\n" + "\n---\n".join(search_bits)[-40000:]
    )
    if meta.get("analysis_id"):
        analysis = table_analysis.load_snapshot(settings.artifacts_path / task.id, meta["analysis_id"])["summary"]
        system += "\n表格结论必须依据程序已计算的结果；不要把材料预览当全部数据，不自行猜测未计算的数字。指出缺失值、非数字与基期缺失；不要编造已经生成的图表路径。"
        user += "\n\n" + table_analysis.prompt_summary(analysis)
    return await chat_completion(settings, system, user)


async def rewrite_report(
    db: Session,
    task_id: str,
    instruction: str,
    settings: Settings | None = None,
    *,
    scope: str = "full",
    section_id: str | None = None,
    expected_version: int | None = None,
) -> Task:
    """Rewrite an existing succeeded report using a user instruction."""
    settings = settings or get_settings()
    task = get_task(db, task_id)
    settings = task_settings(settings, _plan_meta(task))
    if task.status != "succeeded":
        raise AppError("INVALID_STATE", "仅已成功完成的任务可重写报告")
    text = (instruction or "").strip()
    if not text:
        raise AppError("VALIDATION_ERROR", "请填写改写指令")

    revision = reports.current(db, task)
    base_version = revision.version
    if expected_version is not None and expected_version != base_version:
        raise AppError("REPORT_CONFLICT", "报告已更新，请刷新后再修改", status_code=409)
    old = revision.markdown
    selected_text = old
    selected_part = None
    if scope == "section":
        selected_part = next((part for part in reports.sections(old) if part["id"] == section_id), None)
        if selected_part is None:
            raise AppError("SECTION_NOT_FOUND", "请选择要修改的章节", status_code=422)
        selected_text = old[selected_part["body_start"]:selected_part["end"]]
    elif scope != "full":
        raise AppError("VALIDATION_ERROR", "改写范围无效", status_code=422)
    if len(selected_text) > 60000:
        raise AppError("REWRITE_TOO_LARGE", "本次正文过长，请选择一个较短章节修改")
    system = _load_prompt("report.md")
    if selected_part:
        system += (
            "\n[SECTION_REWRITE] 只按指令改写选中章节的正文。只返回这一节的新正文，"
            "不要返回章节标题、文档标题或其他章节，不要用代码围栏包装。保留来源与事实口径。"
        )
    else:
        system += "\n你正在按用户指令改写已有 Markdown 报告。输出完整正文，保留事实与来源。"
    user = (
        f"用户原始需求：\n{task.user_prompt}\n\n"
        f"【改写指令】\n{text}\n\n"
        f"【当前报告】\n{selected_text}\n"
    )
    if selected_part:
        user += f"\n选中章节：{selected_part['title']}\n"
    analysis_id = revision.analysis_id
    if analysis_id:
        analysis = table_analysis.load_snapshot(settings.artifacts_path / task.id, analysis_id)["summary"]
        user += "\n" + table_analysis.prompt_summary(analysis)
    changed = await chat_completion(settings, system, user)
    new_md = reports.replace_section(old, section_id, changed) if selected_part else reports.validate_markdown(changed)
    # End the read transaction after the model call, then compare against the current head.
    db.rollback()
    task = get_task(db, task_id)
    if task.status != "succeeded":
        raise AppError("INVALID_STATE", "任务状态已改变，未保存改写")
    saved = reports.save(
        db, task, new_md, reason="section_rewrite" if selected_part else "rewrite",
        instruction=(f"【{selected_part['title']}】" if selected_part else "") + text,
        analysis_id=analysis_id, expected_version=base_version,
    )
    _invalidate_export_caches(task_id, settings)
    append_event(db, task, "artifact", {"kind": "report_rewrite", "version": saved.version, "instruction": text[:200]})
    db.commit()
    return get_task(db, task_id)


def restore_report(
    db: Session, task_id: str, version: int, expected_version: int,
    settings: Settings | None = None,
) -> Task:
    settings = settings or get_settings()
    task = get_task(db, task_id)
    if task.status != "succeeded":
        raise AppError("INVALID_STATE", "仅已完成的任务可恢复报告版本")
    reports.current(db, task)
    target = reports.get_version(db, task, version)
    saved = reports.save(
        db, task, target.markdown, reason="restore", instruction=f"恢复 v{version}",
        analysis_id=target.analysis_id, expected_version=expected_version,
    )
    _invalidate_export_caches(task_id, settings)
    append_event(db, task, "artifact", {"kind": "report_restore", "version": saved.version, "restored_from": version})
    db.commit()
    return get_task(db, task_id)


def get_analysis(db: Session, task_id: str, settings: Settings | None = None) -> dict[str, Any] | None:
    settings = settings or get_settings()
    task = get_task(db, task_id)
    if task.report_path:
        analysis_id = reports.current(db, task).analysis_id
    else:
        analysis_id = _plan_meta(task).get("analysis_id")
    if not analysis_id:
        return None
    return table_analysis.load_snapshot(settings.artifacts_path / task.id, analysis_id)["summary"]


def pause_task(db: Session, task_id: str) -> Task:
    task = get_task(db, task_id)
    if task.status != "running":
        raise AppError("INVALID_STATE", "仅运行中的任务可暂停")
    task.status = "paused"
    append_event(db, task, "progress", {"message": "用户暂停"})
    db.commit()
    return get_task(db, task_id)


async def resume_task(db: Session, task_id: str, settings: Settings | None = None) -> Task:
    settings = settings or get_settings()
    task = get_task(db, task_id)
    if task.status != "paused":
        raise AppError("INVALID_STATE", "仅暂停中的任务可继续")
    return await confirm_and_run(db, task_id, confirm_cost=True, settings=settings)


def delete_task(db: Session, task_id: str, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    task = get_task(db, task_id)
    upload_dir = settings.uploads_path / task.id
    art_dir = settings.artifacts_path / task.id
    db.delete(task)
    db.commit()
    if upload_dir.exists():
        shutil.rmtree(upload_dir, ignore_errors=True)
    if art_dir.exists():
        shutil.rmtree(art_dir, ignore_errors=True)


async def add_upload(db: Session, task_id: str, upload_file, settings: Settings | None = None) -> Upload:
    settings = settings or get_settings()
    task = get_task(db, task_id)
    if len(task.uploads) >= MAX_FILES:
        raise AppError("UPLOAD_LIMIT", "最多上传 3 个参考文件")
    if task.status not in {"plan_ready", "paused", "failed"}:
        raise AppError("INVALID_STATE", "请在任务开始前添加材料")
    if any(step.status in {"done", "skipped"} for step in task.steps):
        raise AppError("MATERIAL_CHANGE_REQUIRES_REPLAN", "部分步骤已执行，请先改计划，再添加新材料")

    filename = safe_filename(upload_file.filename or "upload.bin")
    ext = assert_allowed(filename)
    data = await read_upload_bytes(upload_file)
    dest_dir = settings.uploads_path / task.id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{uuid.uuid4().hex}_{filename}"
    dest.write_bytes(data)
    try:
        excerpt = extract_text(dest, ext)
    except Exception:
        dest.unlink(missing_ok=True)
        raise AppError("UPLOAD_INVALID", "文件内容无法读取，请检查格式或是否已加密")
    row = Upload(
        task_id=task.id,
        filename=filename,
        stored_path=str(dest),
        mime=upload_file.content_type or "application/octet-stream",
        size_bytes=len(data),
        text_excerpt=excerpt,
    )
    db.add(row)
    append_event(db, task, "progress", {"message": f"已上传 {filename}"})
    db.commit()
    db.refresh(row)
    return row


def add_workspace_refs(
    db: Session,
    task_id: str,
    paths: list[str],
    settings: Settings | None = None,
) -> Task:
    """Attach files from the authorized workspace as task reference uploads."""
    from app.services import workspace as ws

    settings = settings or get_settings()
    task = get_task(db, task_id)
    if task.status not in {"plan_ready", "paused", "failed"}:
        raise AppError("INVALID_STATE", "当前状态不可再添加参考材料")
    if any(step.status in {"done", "skipped"} for step in task.steps):
        raise AppError("MATERIAL_CHANGE_REQUIRES_REPLAN", "部分步骤已执行，请先改计划，再添加新材料")
    if not paths:
        raise AppError("VALIDATION_ERROR", "请选择至少一个资料库文件")

    root = ws.require_root(settings)
    dest_dir = settings.uploads_path / task.id
    dest_dir.mkdir(parents=True, exist_ok=True)
    used = len(task.uploads)

    for rel in paths:
        if used >= MAX_FILES:
            raise AppError("UPLOAD_LIMIT", "最多上传 3 个参考文件")
        src = ws.safe_resolve(root, rel)
        if not src.is_file():
            raise AppError("FILE_NOT_FOUND", f"资料库文件不存在：{rel}", status_code=404)
        filename = safe_filename(src.name)
        ext = assert_allowed(filename)
        size = src.stat().st_size
        if size > MAX_BYTES:
            raise AppError("UPLOAD_TOO_LARGE", f"{filename} 超过 20MB")
        dest = dest_dir / f"{uuid.uuid4().hex}_{filename}"
        dest.write_bytes(src.read_bytes())
        excerpt = extract_text(dest, ext)
        row = Upload(
            task_id=task.id,
            filename=filename,
            stored_path=str(dest),
            mime="application/octet-stream",
            size_bytes=size,
            text_excerpt=excerpt,
        )
        db.add(row)
        used += 1
        append_event(db, task, "progress", {"message": f"已从资料库添加 {filename}"})

    db.commit()
    return get_task(db, task_id)


def read_report(db: Session, task_id: str) -> str:
    task = get_task(db, task_id)
    return reports.current(db, task).markdown


def report_download_stem(task: Task) -> str:
    """Safe basename (no extension) for report downloads."""
    raw = (task.title or "").strip() or "report"
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ._")
    if not cleaned:
        cleaned = "report"
    return cleaned[:80]

def ensure_docx(db: Session, task_id: str, settings: Settings | None = None) -> Path:
    from app.services.docx_export import markdown_to_docx

    settings = settings or get_settings()
    task = get_task(db, task_id)
    revision = reports.current(db, task)
    docx_path = settings.artifacts_path / task.id / f"report-v{revision.version}.docx"
    if docx_path.exists() and docx_path.stat().st_size > 0:
        return docx_path
    return markdown_to_docx(revision.markdown, docx_path)


def ensure_xlsx(db: Session, task_id: str, settings: Settings | None = None) -> Path:
    from app.services.xlsx_export import markdown_to_xlsx, analysis_to_xlsx

    settings = settings or get_settings()
    task = get_task(db, task_id)
    revision = reports.current(db, task)
    xlsx_path = settings.artifacts_path / task.id / f"report-v{revision.version}.xlsx"
    if xlsx_path.exists() and xlsx_path.stat().st_size > 0:
        return xlsx_path
    if revision.analysis_id:
        snapshot = table_analysis.load_snapshot(settings.artifacts_path / task.id, revision.analysis_id)
        return analysis_to_xlsx(snapshot, revision.markdown, xlsx_path)
    return markdown_to_xlsx(revision.markdown, xlsx_path)


def ensure_pptx(db: Session, task_id: str, settings: Settings | None = None) -> Path:
    from app.services.pptx_export import markdown_to_pptx

    settings = settings or get_settings()
    task = get_task(db, task_id)
    revision = reports.current(db, task)
    pptx_path = settings.artifacts_path / task.id / f"report-v{revision.version}.pptx"
    if pptx_path.exists() and pptx_path.stat().st_size > 0:
        return pptx_path
    analysis = table_analysis.load_snapshot(settings.artifacts_path / task.id, revision.analysis_id)["summary"] if revision.analysis_id else None
    return markdown_to_pptx(revision.markdown, pptx_path, analysis=analysis)


async def export_report_to_feishu(
    db: Session,
    task_id: str,
    *,
    confirmed: bool,
    as_app: bool = False,
    settings: Settings | None = None,
) -> dict:
    from app.services.feishu_export import export_markdown_to_feishu

    if not confirmed:
        raise AppError(
            "CONFIRM_REQUIRED",
            "导出到飞书将在云端创建文档，请确认后继续",
            status_code=400,
        )

    settings = settings or get_settings()
    task = get_task(db, task_id)
    markdown = read_report(db, task_id)
    if task.status != "succeeded":
        raise AppError("INVALID_STATE", "仅已完成的任务可导出到飞书", status_code=400)
    title = (task.title or "调研报告").strip() or "调研报告"
    artifact_dir = settings.artifacts_path / task.id
    result = await export_markdown_to_feishu(
        markdown=markdown,
        title=title,
        artifact_dir=artifact_dir,
        settings=settings,
        as_app=bool(as_app),
    )
    append_event(
        db,
        task,
        "artifact",
        {
            "kind": "feishu_export",
            "document_id": result.get("document_id"),
            "mock": bool(result.get("mock")),
            "identity": result.get("identity"),
            "space": result.get("space"),
        },
    )
    db.commit()
    return result
