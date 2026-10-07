from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import schedules as schedule_service

router = APIRouter(prefix="/api/schedules", tags=["schedules"])

TriggerMode = Literal["interval", "on_task_succeeded"]


class ScheduleCreate(BaseModel):
    name: str = "自动化"
    prompt: str = Field(min_length=1, max_length=8000)
    model_id: str | None = Field(default=None, min_length=1, max_length=80)
    token_budget: int | None = Field(default=None, ge=1024, le=1000000)
    urls: list[str] = Field(default_factory=list, max_length=3)
    workspace_paths: list[str] = Field(default_factory=list, max_length=3)
    material_mode: Literal["snapshot", "latest"] = "snapshot"
    include_upstream_result: bool = False
    interval_minutes: int = Field(default=60, ge=1, le=10080)
    skill_id: str | None = None
    expert_id: str | None = None
    enabled: bool = True
    trigger_mode: TriggerMode = "interval"
    listen_schedule_id: str | None = None
    feishu_notify: bool = False
    feishu_notify_chat_id: str | None = None


class SchedulePatch(BaseModel):
    token_budget: int | None = Field(default=None, ge=1024, le=1000000)
    urls: list[str] | None = Field(default=None, max_length=3)
    workspace_paths: list[str] | None = Field(default=None, max_length=3)
    material_mode: Literal["snapshot", "latest"] | None = None
    include_upstream_result: bool | None = None
    model_id: str | None = Field(default=None, min_length=1, max_length=80)
    name: str | None = None
    prompt: str | None = None
    interval_minutes: int | None = Field(default=None, ge=1, le=10080)
    skill_id: str | None = None
    expert_id: str | None = None
    enabled: bool | None = None
    trigger_mode: TriggerMode | None = None
    listen_schedule_id: str | None = None
    feishu_notify: bool | None = None
    feishu_notify_chat_id: str | None = None


@router.get("")
def list_schedules(db: Session = Depends(get_db)) -> dict[str, Any]:
    items = [schedule_service.serialize_schedule(s) for s in schedule_service.list_schedules(db)]
    return {"items": items}


@router.post("")
def create_schedule(body: ScheduleCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = schedule_service.create_schedule(
        db,
        name=body.name,
        prompt=body.prompt,
        model_id=body.model_id,
        token_budget=body.token_budget,
        urls=body.urls,
        workspace_paths=body.workspace_paths,
        material_mode=body.material_mode,
        include_upstream_result=body.include_upstream_result,
        interval_minutes=body.interval_minutes,
        skill_id=body.skill_id,
        expert_id=body.expert_id,
        enabled=body.enabled,
        trigger_mode=body.trigger_mode,
        listen_schedule_id=body.listen_schedule_id,
        feishu_notify=body.feishu_notify,
        feishu_notify_chat_id=body.feishu_notify_chat_id,
    )
    return schedule_service.serialize_schedule(row)



@router.get("/notices")
def list_result_notices(
    limit: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None, description="可选：success|failed"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """自动化跑次结果站内通知列表（不做邮件/外发）。"""
    if status is not None and status not in ("success", "failed"):
        from app.core.errors import AppError

        raise AppError("VALIDATION_ERROR", "status 仅支持 success 或 failed", status_code=400)
    items = schedule_service.list_result_notices(db, limit=limit, status=status)
    return {"items": items, "limit": limit}


@router.patch("/{schedule_id}")
def patch_schedule(
    schedule_id: str, body: SchedulePatch, db: Session = Depends(get_db)
) -> dict[str, Any]:
    row = schedule_service.update_schedule(
        db, schedule_id, **body.model_dump(exclude_unset=True)
    )
    return schedule_service.serialize_schedule(row)


@router.delete("/{schedule_id}")
def delete_schedule(schedule_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    schedule_service.delete_schedule(db, schedule_id)
    return {"status": "deleted"}


@router.get("/{schedule_id}/runs")
def list_schedule_runs(
    schedule_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    items = [
        {**schedule_service.serialize_run(r), "usage": schedule_service.run_usage(db, r.id)}
        for r in schedule_service.list_schedule_runs(db, schedule_id, limit=limit)
    ]
    return {"items": items, "limit": limit}


@router.post("/{schedule_id}/run-now")
async def run_now(schedule_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = await schedule_service.trigger_schedule(db, schedule_id, trigger="manual")
    return schedule_service.serialize_schedule(row)


def _extract_hook_token(
    *,
    request: Request,
    token: str | None,
    x_hook_token: str | None,
) -> str | None:
    """优先 Header X-Hook-Token，其次 Authorization Bearer，再次 ?token=。"""
    if x_hook_token and str(x_hook_token).strip():
        return str(x_hook_token).strip()
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth:
        parts = auth.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
            return parts[1].strip()
    if token and str(token).strip():
        return str(token).strip()
    return None


@router.post("/{schedule_id}/hook")
async def inbound_hook(
    schedule_id: str,
    request: Request,
    db: Session = Depends(get_db),
    token: str | None = Query(default=None, description="Webhook 密钥（也可放 Header）"),
    x_hook_token: str | None = Header(default=None, alias="X-Hook-Token"),
) -> dict[str, Any]:
    """带密钥入站 Webhook：鉴权通过则以 trigger=webhook 跑一次。"""
    provided = _extract_hook_token(request=request, token=token, x_hook_token=x_hook_token)
    row = await schedule_service.trigger_webhook(
        db, schedule_id, provided_token=provided
    )
    return schedule_service.serialize_schedule(row)


@router.post("/{schedule_id}/rotate-hook-token")
def rotate_hook_token(schedule_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """生成或轮换 Webhook 密钥；明文仅本次响应返回。"""
    row, plain = schedule_service.rotate_hook_token(db, schedule_id)
    return schedule_service.serialize_hook_rotate(row, plain)
