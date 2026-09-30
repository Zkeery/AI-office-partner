from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.errors import AppError
from app.services import feishu_notify as feishu_notify_service
from app.services import feishu_oauth as feishu_oauth_service

router = APIRouter(prefix="/api/feishu", tags=["feishu"])


class NotifySettingsPatch(BaseModel):
    notify_on: str | None = None
    chat_id: str | None = Field(default=None, max_length=128)


class MockConnectBody(BaseModel):
    user_name: str | None = Field(default="Mock 用户", max_length=80)


@router.get("/notify")
def get_notify_settings() -> dict[str, Any]:
    """飞书群通知配置与最近发送记录（不含密钥）。"""
    return feishu_notify_service.serialize_notify_settings(get_settings())


@router.put("/notify")
def put_notify_settings(body: NotifySettingsPatch) -> dict[str, Any]:
    """更新通知时机与目标群；不接收也不返回 App Secret。"""
    payload = body.model_dump(exclude_unset=True)
    if payload:
        feishu_notify_service.save_notify_prefs(
            notify_on=payload.get("notify_on"),
            chat_id=payload.get("chat_id") if "chat_id" in payload else None,
            settings=get_settings(),
        )
    return feishu_notify_service.serialize_notify_settings(get_settings())


@router.get("/notify/log")
def get_notify_log(limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
    items = feishu_notify_service.list_notify_log(get_settings(), limit=limit)
    return {"items": items, "limit": limit}


# ---------- 1.24 用户 OAuth（写「我的」云文档；非登录本应用） ----------


@router.get("/oauth/status")
def oauth_status() -> dict[str, Any]:
    return feishu_oauth_service.serialize_oauth_status(get_settings())


@router.get("/oauth/start")
def oauth_start() -> RedirectResponse:
    """302 到飞书授权页；FEISHU_MOCK=1 时直接跳本机 callback 模拟同意。"""
    url = feishu_oauth_service.build_authorize_url(get_settings())
    return RedirectResponse(url=url, status_code=302)


@router.get("/oauth/callback")
async def oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> HTMLResponse:
    settings = get_settings()
    origin = settings.frontend_origin or "http://127.0.0.1:3040"
    if error:
        msg = error_description or error or "用户拒绝或授权失败"
        html = feishu_oauth_service.callback_html(
            ok=False,
            message=f"授权未完成：{msg}。可回到应用后重试「连接飞书账号」。",
            frontend_origin=origin,
        )
        return HTMLResponse(content=html, status_code=400)

    try:
        await feishu_oauth_service.exchange_code_for_token(
            code=code or "",
            state=state,
            settings=settings,
        )
        html = feishu_oauth_service.callback_html(
            ok=True,
            message="已连接飞书账号。关闭本页后回到应用，导出将优先写到「我的」云文档。",
            frontend_origin=origin,
        )
        return HTMLResponse(content=html, status_code=200)
    except AppError as exc:
        html = feishu_oauth_service.callback_html(
            ok=False,
            message=exc.message,
            frontend_origin=origin,
        )
        return HTMLResponse(content=html, status_code=exc.status_code)


@router.post("/oauth/disconnect")
def oauth_disconnect() -> dict[str, Any]:
    feishu_oauth_service.clear_tokens(get_settings())
    return feishu_oauth_service.serialize_oauth_status(get_settings())


@router.post("/oauth/mock-connect")
def oauth_mock_connect(body: MockConnectBody | None = None) -> dict[str, Any]:
    """仅 mock：一键模拟已授权（供 pytest / 本地无浏览器测通）。"""
    name = (body.user_name if body else None) or "Mock 用户"
    return feishu_oauth_service.mock_connect(get_settings(), user_name=name)
