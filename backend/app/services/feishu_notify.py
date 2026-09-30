"""飞书群/会话出站通知（1.23 第一刀）。

沿用应用凭证 tenant_access_token；不做用户 OAuth、不做飞书登录本应用。
FEISHU_MOCK=1 时只写本地发送记录，不调真实 IM。
发送失败不抛到自动化主流程，避免打断跑次。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.services.feishu_export import FEISHU_OPEN, _tenant_token

NotifyOn = Literal["off", "failed", "always"]
VALID_NOTIFY_ON = frozenset({"off", "failed", "always"})
PREFS_NAME = "feishu_notify_prefs.json"
LOG_NAME = "feishu_notify_log.json"
LOG_KEEP = 50


def _prefs_path(settings: Settings) -> Path:
    return settings.data_path / PREFS_NAME


def _log_path(settings: Settings) -> Path:
    return settings.data_path / LOG_NAME


def _normalize_notify_on(raw: Any) -> NotifyOn:
    val = (str(raw).strip().lower() if raw is not None else "") or ""
    if val in VALID_NOTIFY_ON:
        return val  # type: ignore[return-value]
    return "failed"


def load_notify_prefs(settings: Settings | None = None) -> dict[str, Any]:
    """UI/运行时可写偏好；缺省回落到 env。不包含任何 secret。"""
    settings = settings or get_settings()
    env_on = _normalize_notify_on(getattr(settings, "feishu_notify_on", None) or "failed")
    env_chat = (getattr(settings, "feishu_notify_chat_id", None) or "").strip()
    prefs: dict[str, Any] = {
        "notify_on": env_on,
        "chat_id": env_chat,
    }
    path = _prefs_path(settings)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                if "notify_on" in data:
                    prefs["notify_on"] = _normalize_notify_on(data.get("notify_on"))
                if "chat_id" in data and data.get("chat_id") is not None:
                    prefs["chat_id"] = str(data.get("chat_id") or "").strip()
        except Exception:
            pass
    return prefs


def save_notify_prefs(
    *,
    notify_on: str | None = None,
    chat_id: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    current = load_notify_prefs(settings)
    if notify_on is not None:
        on = _normalize_notify_on(notify_on)
        if str(notify_on).strip().lower() not in VALID_NOTIFY_ON:
            raise AppError(
                "VALIDATION_ERROR",
                "飞书通知时机仅支持 off / failed / always",
                status_code=400,
            )
        current["notify_on"] = on
    if chat_id is not None:
        current["chat_id"] = str(chat_id).strip()
    path = _prefs_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def list_notify_log(settings: Settings | None = None, *, limit: int = 20) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    path = _log_path(settings)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else data.get("items", [])
        if not isinstance(items, list):
            return []
        lim = max(1, min(int(limit), 100))
        return list(reversed(items[-lim:]))  # newest first
    except Exception:
        return []


def _append_log(settings: Settings, entry: dict[str, Any]) -> None:
    path = _log_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict) and isinstance(data.get("items"), list):
                items = list(data["items"])
        except Exception:
            items = []
    items.append(entry)
    items = items[-LOG_KEEP:]
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def should_notify(*, notify_on: str, status: str, schedule_enabled: bool) -> bool:
    if not schedule_enabled:
        return False
    on = _normalize_notify_on(notify_on)
    if on == "off":
        return False
    if status == "failed":
        return on in ("failed", "always")
    if status == "success":
        return on == "always"
    return False


def build_notify_text(
    *,
    schedule_name: str,
    status: str,
    error: str | None,
    task_id: str | None,
    frontend_origin: str,
    feishu_doc_url: str | None = None,
) -> str:
    title = (schedule_name or "自动化").strip() or "自动化"
    outcome = "成功" if status == "success" else "失败"
    lines = [f"【AI办公搭子】自动化「{title}」{outcome}"]
    if status == "failed" and error:
        # 绝不回写密钥；截断错误文案
        err = str(error).strip()
        for secret_key in ("APP_SECRET", "app_secret", "tenant_access_token"):
            if secret_key in err:
                err = "（错误详情已隐藏，可能含凭证相关信息）"
                break
        lines.append(f"原因：{err[:300]}")
    if task_id:
        lines.append(f"任务 ID：{task_id}")
    origin = (frontend_origin or "http://127.0.0.1:3040").rstrip("/")
    lines.append(f"本机查看：{origin} （打开应用 → 自动化 / 任务）")
    if feishu_doc_url:
        lines.append(f"云文档：{feishu_doc_url}")
    return "\n".join(lines)


def serialize_notify_settings(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    prefs = load_notify_prefs(settings)
    chat = prefs.get("chat_id") or ""
    return {
        "notify_on": prefs.get("notify_on") or "failed",
        "chat_id": chat,
        "chat_id_configured": bool(chat),
        "app_configured": bool(settings.feishu_app_id and settings.feishu_app_secret),
        "feishu_mock": bool(settings.feishu_mock),
        "hint": (
            "凭证写在本机 .env（FEISHU_APP_ID / FEISHU_APP_SECRET），勿提交仓库。"
            "目标群填 chat_id（机器人需已进群）。"
            "FEISHU_MOCK=1 时只记本地模拟发送，不调真实飞书。"
            "单条自动化还需打开「发飞书」才会推送；站内通知仍保留。"
        ),
        "recent": list_notify_log(settings, limit=10),
    }


async def _send_im_text(*, token: str, chat_id: str, text: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{FEISHU_OPEN}/im/v1/messages",
            params={"receive_id_type": "chat_id"},
            headers={"Authorization": f"Bearer {token}"},
            json={
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        )
        try:
            data = r.json()
        except Exception:
            data = {"http_status": r.status_code, "text": (r.text or "")[:200]}
        if data.get("code") != 0:
            msg = data.get("msg") or r.text[:200] or "飞书发消息失败"
            # 不把响应全文（可能含敏感）写进异常长文
            raise AppError("FEISHU_NOTIFY_FAILED", f"飞书发消息失败：{msg}", status_code=502)
        return data.get("data") or {}


async def send_notify_message(
    *,
    text: str,
    chat_id: str | None = None,
    settings: Settings | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """发送一条文本；mock 写本地日志。缺凭证/chat 时返回 skipped，不抛（调用方可选择抛）。"""
    settings = settings or get_settings()
    prefs = load_notify_prefs(settings)
    target = (chat_id or prefs.get("chat_id") or "").strip()
    now = datetime.now(timezone.utc).isoformat()
    base_meta = dict(meta or {})
    base_meta.update({"text_preview": text[:400], "sent_at": now})

    if settings.feishu_mock:
        use_chat = target or "mock_chat"
        entry = {
            **base_meta,
            "mock": True,
            "status": "mocked",
            "chat_id": use_chat,
            "message": "已模拟发送到飞书群（未调真实 IM）",
        }
        _append_log(settings, entry)
        return entry

    if not settings.feishu_app_id or not settings.feishu_app_secret:
        entry = {
            **base_meta,
            "mock": False,
            "status": "skipped",
            "code": "FEISHU_NOT_CONFIGURED",
            "chat_id": target or None,
            "message": "未配置飞书应用凭证。请在 .env 填写 FEISHU_APP_ID / FEISHU_APP_SECRET，或保持 FEISHU_MOCK=1",
        }
        _append_log(settings, entry)
        return entry

    if not target:
        entry = {
            **base_meta,
            "mock": False,
            "status": "skipped",
            "code": "FEISHU_CHAT_NOT_CONFIGURED",
            "chat_id": None,
            "message": "未配置目标群 chat_id。请在自动化页填写，或在 .env 设置 FEISHU_NOTIFY_CHAT_ID",
        }
        _append_log(settings, entry)
        return entry

    try:
        token = await _tenant_token(settings)
        data = await _send_im_text(token=token, chat_id=target, text=text)
        entry = {
            **base_meta,
            "mock": False,
            "status": "sent",
            "chat_id": target,
            "message_id": data.get("message_id"),
            "message": "已发送到飞书群",
        }
        _append_log(settings, entry)
        return entry
    except AppError as exc:
        entry = {
            **base_meta,
            "mock": False,
            "status": "failed",
            "code": exc.code,
            "chat_id": target,
            "message": exc.message,
        }
        _append_log(settings, entry)
        return entry
    except Exception as exc:  # noqa: BLE001 — 出站通知永不打断主流程
        entry = {
            **base_meta,
            "mock": False,
            "status": "failed",
            "code": "FEISHU_NOTIFY_FAILED",
            "chat_id": target,
            "message": f"飞书通知异常：{type(exc).__name__}",
        }
        _append_log(settings, entry)
        return entry


async def maybe_notify_schedule_run(
    *,
    schedule_name: str,
    schedule_feishu_notify: bool,
    status: str,
    error: str | None,
    task_id: str | None,
    run_id: str | None = None,
    schedule_id: str | None = None,
    schedule_chat_id: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """自动化跑次结束后的可选飞书通知；不该通知时返回 None。"""
    settings = settings or get_settings()
    prefs = load_notify_prefs(settings)
    if not should_notify(
        notify_on=str(prefs.get("notify_on") or "failed"),
        status=status,
        schedule_enabled=bool(schedule_feishu_notify),
    ):
        return None
    text = build_notify_text(
        schedule_name=schedule_name,
        status=status,
        error=error,
        task_id=task_id,
        frontend_origin=settings.frontend_origin,
    )
    chat = (schedule_chat_id or "").strip() or None
    return await send_notify_message(
        text=text,
        chat_id=chat,
        settings=settings,
        meta={
            "kind": "schedule_run",
            "schedule_id": schedule_id,
            "schedule_name": schedule_name,
            "run_id": run_id,
            "task_id": task_id,
            "run_status": status,
        },
    )
