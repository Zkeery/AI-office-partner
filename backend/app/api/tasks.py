from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db import session as db_session
from app.db.models import TaskEvent
from app.db.session import get_db
from app.schemas.tasks import (
    TaskConfirm,
    TaskCreate,
    TaskListOut,
    TaskMerge,
    TaskOut,
    TaskReplan,
    TaskRewrite,
)
from app.services import tasks as task_service
from app.services import reports
from app.services.execution import claim_task
from app.schemas.reports import (
    AnalysisResponse,
    ReportDocument,
    ReportRestore,
    ReportVersionList,
    ReportVersionPreview,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

_running_jobs: dict[str, asyncio.Task] = {}


async def cancel_running_jobs() -> None:
    jobs = list(_running_jobs.values())
    for job in jobs:
        job.cancel()
    if jobs:
        await asyncio.gather(*jobs, return_exceptions=True)
    _running_jobs.clear()


def _to_out(task) -> TaskOut:
    return task_service.serialize_task(task)


@router.get("", response_model=TaskListOut)
def list_tasks(
    include_merged: bool = False,
    include_archived: bool = False,
    q: str = "",
    db: Session = Depends(get_db),
) -> TaskListOut:
    query = (q or "").strip() or None
    items = [
        task_service.serialize_task(t, search_query=query)
        for t in task_service.list_tasks(
            db,
            include_merged=include_merged,
            include_archived=include_archived,
            q=query,
        )
    ]
    return TaskListOut(items=items)


@router.post("", response_model=TaskOut)
async def create_task(body: TaskCreate, db: Session = Depends(get_db)) -> TaskOut:
    task = await task_service.create_task(
        db,
        body.prompt,
        body.urls,
        skill_id=body.skill_id,
        expert_id=body.expert_id,
        model_id=body.model_id,
    )
    return _to_out(task)


@router.post("/merge", response_model=TaskOut)
def merge_tasks(body: TaskMerge, db: Session = Depends(get_db)) -> TaskOut:
    return _to_out(task_service.merge_tasks(db, body.task_ids))


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: str, db: Session = Depends(get_db)) -> TaskOut:
    return _to_out(task_service.get_task(db, task_id))


@router.post("/{task_id}/plan", response_model=TaskOut)
async def rebuild_plan(task_id: str, db: Session = Depends(get_db)) -> TaskOut:
    task = await task_service.replan_task(db, task_id)
    return _to_out(task)


async def _run_job(task_id: str, operation_token: str) -> None:
    settings = get_settings()
    db = db_session.SessionLocal()
    try:
        await task_service.run_agent_job(db, task_id, settings, operation_token=operation_token)
    finally:
        db.close()
        if _running_jobs.get(task_id) is asyncio.current_task():
            _running_jobs.pop(task_id, None)


@router.post("/{task_id}/confirm", response_model=TaskOut)
async def confirm_task(
    task_id: str, body: TaskConfirm, db: Session = Depends(get_db)
) -> TaskOut:
    settings = get_settings()
    task = task_service.get_task(db, task_id)
    if task.status not in {"plan_ready", "paused", "failed"}:
        raise AppError("INVALID_STATE", f"当前状态不可确认执行：{task.status}")

    if task.status == "plan_ready":
        if task.cost_estimate_cny > settings.cost_soft_limit_cny and not (
            body.confirm_cost or task.cost_confirmed
        ):
            raise AppError(
                "COST_CONFIRM_REQUIRED",
                f"预估费用约 ¥{task.cost_estimate_cny:.2f}，超过软上限 "
                f"¥{settings.cost_soft_limit_cny:.0f}，请确认后继续",
            )
        if body.confirm_cost:
            task.cost_confirmed = True

    if not task.steps:
        raise AppError("PLAN_REQUIRED", "计划尚未完成，请先改计划后重试")
    token = claim_task(db, task, allowed={"plan_ready", "paused", "failed"}, state="running")
    task_service.append_event(db, task, "progress", {"message": "开始执行"})
    db.commit()

    previous = _running_jobs.get(task_id)
    if previous and not previous.done():
        previous.cancel()
    _running_jobs[task_id] = asyncio.create_task(_run_job(task_id, token))

    return _to_out(task_service.get_task(db, task_id))


@router.post("/{task_id}/pause", response_model=TaskOut)
def pause_task(task_id: str, db: Session = Depends(get_db)) -> TaskOut:
    task = task_service.pause_task(db, task_id)
    job = _running_jobs.get(task_id)
    if job and not job.done():
        job.cancel()
    return _to_out(task)


@router.post("/{task_id}/resume", response_model=TaskOut)
async def resume_task(task_id: str, db: Session = Depends(get_db)) -> TaskOut:
    task = task_service.get_task(db, task_id)
    if task.status != "paused":
        raise AppError("INVALID_STATE", "仅暂停中的任务可继续")
    return await confirm_task(task_id, TaskConfirm(confirm_cost=True), db)


@router.post("/{task_id}/replan", response_model=TaskOut)
async def replan_task(
    task_id: str, body: TaskReplan, db: Session = Depends(get_db)
) -> TaskOut:
    task = await task_service.replan_task(
        db,
        task_id,
        prompt=body.prompt,
        urls=body.urls,
    )
    return _to_out(task)


@router.post("/{task_id}/rewrite", response_model=TaskOut)
async def rewrite_task(
    task_id: str, body: TaskRewrite, db: Session = Depends(get_db)
) -> TaskOut:
    task = await task_service.rewrite_report(
        db, task_id, body.instruction, scope=body.scope,
        section_id=body.section_id, expected_version=body.expected_version,
    )
    return _to_out(task)


@router.delete("/{task_id}")
def delete_task(task_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    job = _running_jobs.get(task_id)
    if job and not job.done():
        job.cancel()
    task_service.delete_task(db, task_id)
    return {"status": "deleted"}


@router.post("/{task_id}/unarchive", response_model=TaskOut)
def unarchive_task(task_id: str, db: Session = Depends(get_db)) -> TaskOut:
    return _to_out(task_service.unarchive_task(db, task_id))


@router.post("/{task_id}/uploads")
async def upload_file(
    task_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = await task_service.add_upload(db, task_id, file)
    return {
        "id": row.id,
        "filename": row.filename,
        "size_bytes": row.size_bytes,
        "text_excerpt": (row.text_excerpt or "")[:500],
    }


class WorkspaceRefsBody(BaseModel):
    paths: list[str] = Field(default_factory=list, max_length=3)


@router.post("/{task_id}/workspace-refs")
def attach_workspace_refs(
    task_id: str,
    body: WorkspaceRefsBody,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    task = task_service.add_workspace_refs(db, task_id, body.paths)
    return task_service.serialize_task(task).model_dump(mode="json")


@router.get("/{task_id}/report", response_model=ReportDocument)
def get_report(task_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    task = task_service.get_task(db, task_id)
    revision = reports.current(db, task)
    return {"markdown": revision.markdown, "version": revision.version, "sections": reports.sections(revision.markdown)}


@router.get("/{task_id}/analysis", response_model=AnalysisResponse)
def get_analysis(task_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"analysis": task_service.get_analysis(db, task_id)}


@router.get("/{task_id}/report/versions", response_model=ReportVersionList)
def list_report_versions(task_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    return reports.list_versions(db, task_service.get_task(db, task_id))


@router.get("/{task_id}/report/versions/{version}", response_model=ReportVersionPreview)
def preview_report_version(task_id: str, version: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return reports.version_preview(db, task_service.get_task(db, task_id), version)


@router.post("/{task_id}/report/restore", response_model=TaskOut)
def restore_report(task_id: str, body: ReportRestore, db: Session = Depends(get_db)) -> TaskOut:
    return _to_out(task_service.restore_report(db, task_id, body.version, body.expected_version))


@router.get("/{task_id}/report.docx")
def get_report_docx(task_id: str, db: Session = Depends(get_db)) -> FileResponse:
    path = task_service.ensure_docx(db, task_id)
    task = task_service.get_task(db, task_id)
    stem = task_service.report_download_stem(task)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"{stem}.docx",
    )


@router.get("/{task_id}/report.xlsx")
def get_report_xlsx(task_id: str, db: Session = Depends(get_db)) -> FileResponse:
    path = task_service.ensure_xlsx(db, task_id)
    task = task_service.get_task(db, task_id)
    stem = task_service.report_download_stem(task)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{stem}.xlsx",
    )


@router.get("/{task_id}/report.pptx")
def get_report_pptx(task_id: str, db: Session = Depends(get_db)) -> FileResponse:
    path = task_service.ensure_pptx(db, task_id)
    task = task_service.get_task(db, task_id)
    stem = task_service.report_download_stem(task)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=f"{stem}.pptx",
    )


class FeishuExportBody(BaseModel):
    confirmed: bool = False
    # 1.24：主动选应用空间兜底（默认 False＝已授权则走用户身份）
    as_app: bool = False


@router.post("/{task_id}/export/feishu")
async def export_feishu(
    task_id: str,
    body: FeishuExportBody,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return await task_service.export_report_to_feishu(
        db, task_id, confirmed=body.confirmed, as_app=body.as_app
    )


@router.get("/{task_id}/events")
async def task_events(task_id: str) -> StreamingResponse:
    async def event_generator():
        db = db_session.SessionLocal()
        last_id = 0
        try:
            # ensure task exists
            task_service.get_task(db, task_id)
            terminal = False
            idle_rounds = 0
            while not terminal and idle_rounds < 300:
                rows = list(
                    db.scalars(
                        select(TaskEvent)
                        .where(TaskEvent.task_id == task_id, TaskEvent.id > last_id)
                        .order_by(TaskEvent.id.asc())
                    )
                )
                if not rows:
                    idle_rounds += 1
                    await asyncio.sleep(0.3)
                    # refresh task status
                    db.expire_all()
                    task = task_service.get_task(db, task_id)
                    if task.status in {"succeeded", "failed", "plan_ready", "paused"} and idle_rounds > 3:
                        # if already terminal and no new events, end
                        if task.status in {"succeeded", "failed"}:
                            yield f"event: done\ndata: {json.dumps({'task_id': task_id, 'status': task.status}, ensure_ascii=False)}\n\n"
                            terminal = True
                        continue
                    continue

                idle_rounds = 0
                for row in rows:
                    last_id = row.id
                    try:
                        payload = json.loads(row.payload_json or "{}")
                    except Exception:
                        payload = {}
                    et = row.event_type
                    yield f"event: {et}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    if et in {"done", "error"}:
                        terminal = True
                        break
                await asyncio.sleep(0.05)
            if not terminal:
                yield f"event: error\ndata: {json.dumps({'code': 'SSE_TIMEOUT', 'message': '事件流超时'}, ensure_ascii=False)}\n\n"
        finally:
            db.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")
