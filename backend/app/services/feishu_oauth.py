"""飞书用户 OAuth（1.24）：授权码 → user_access_token，供导出写进「我的」云文档。

不做飞书登录本应用；token 仅存本机 data 目录（已 gitignore），不进 .env。
FEISHU_MOCK=1 时可完整模拟授权/断开/导出身份，无需真实开放平台。
"""
from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.services.feishu_export import FEISHU_OPEN

TOKEN_NAME = "feishu_user_oauth.json"
PENDING_NAME = "feishu_oauth_pending.json"
AUTHORIZE_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
# 须与开放平台「安全设置 → 重定向 URL」逐字一致（含协议/主机/端口/路径，勿用 localhost）
DEFAULT_OAUTH_REDIRECT_URI = "http://127.0.0.1:8040/api/feishu/oauth/callback"
TOKEN_URL = f"{FEISHU_OPEN}/authen/v2/oauth/token"
DEFAULT_SCOPES = "offline_access docx:document drive:drive"
STATE_TTL_SEC = 600
REFRESH_SKEW_SEC = 300


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _token_path(settings: Settings) -> Path:
    return settings.data_path / TOKEN_NAME


def _pending_path(settings: Settings) -> Path:
    return settings.data_path / PENDING_NAME


def _chmod_private(path: Path) -> None:
    try:
        path.chmod(0o600)
    except Exception:
        pass


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _chmod_private(path)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def redirect_uri(settings: Settings | None = None) -> str:
    """本机 OAuth 回调。默认钉死 127.0.0.1:8040 规范地址，避免 localhost/0.0.0.0 漂移。

    开放平台登记必须与返回值完全一致，否则授权页 20029「redirect_uri 请求不合法」。
    """
    settings = settings or get_settings()
    custom = (getattr(settings, "feishu_oauth_redirect_uri", None) or "").strip()
    if custom:
        # 去掉末尾 /，与常见后台粘贴差异对齐；保留显式配置的主机/端口/路径
        return custom.rstrip("/") or DEFAULT_OAUTH_REDIRECT_URI
    host = (settings.app_host or "127.0.0.1").strip() or "127.0.0.1"
    if host in ("0.0.0.0", "::", "localhost"):
        # localhost 与 127.0.0.1 在飞书侧是不同登记项；统一成 127.0.0.1
        host = "127.0.0.1"
    port = int(settings.app_port or 8040)
    if host == "127.0.0.1" and port == 8040:
        return DEFAULT_OAUTH_REDIRECT_URI
    return f"http://{host}:{port}/api/feishu/oauth/callback"


def oauth_scopes(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    raw = (getattr(settings, "feishu_oauth_scopes", None) or "").strip()
    return raw or DEFAULT_SCOPES


def load_token_record(settings: Settings | None = None) -> dict[str, Any] | None:
    settings = settings or get_settings()
    data = _read_json(_token_path(settings))
    if not data:
        return None
    if not data.get("access_token") and not data.get("mock"):
        return None
    return data


def clear_tokens(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    path = _token_path(settings)
    if path.is_file():
        try:
            path.unlink()
        except Exception:
            _write_json(path, {})
    pending = _pending_path(settings)
    if pending.is_file():
        try:
            pending.unlink()
        except Exception:
            pass


def _save_tokens(
    settings: Settings,
    *,
    access_token: str,
    refresh_token: str = "",
    expires_in: int | None = None,
    refresh_expires_in: int | None = None,
    user_name: str = "",
    user_open_id: str = "",
    mock: bool = False,
) -> dict[str, Any]:
    now = _utc_now()
    exp_sec = int(expires_in) if expires_in else (7200 if not mock else 86400)
    record: dict[str, Any] = {
        "access_token": access_token,
        "refresh_token": refresh_token or "",
        "expires_at": _iso(now + timedelta(seconds=max(60, exp_sec))),
        "refresh_expires_at": (
            _iso(now + timedelta(seconds=max(60, int(refresh_expires_in))))
            if refresh_expires_in
            else ""
        ),
        "user_name": (user_name or "")[:80],
        "user_open_id": (user_open_id or "")[:80],
        "mock": bool(mock),
        "updated_at": _iso(now),
    }
    _write_json(_token_path(settings), record)
    return record


def is_connected(settings: Settings | None = None) -> bool:
    rec = load_token_record(settings)
    if not rec:
        return False
    if rec.get("mock") and rec.get("access_token"):
        return True
    return bool(rec.get("access_token"))


def serialize_oauth_status(settings: Settings | None = None) -> dict[str, Any]:
    """脱敏状态：永不返回 access/refresh token。"""
    settings = settings or get_settings()
    rec = load_token_record(settings)
    connected = bool(rec and rec.get("access_token"))
    expires_at = (rec or {}).get("expires_at") or ""
    exp = _parse_iso(expires_at)
    expired = bool(exp and exp <= _utc_now())
    app_ready = bool(settings.feishu_app_id and settings.feishu_app_secret) or bool(
        settings.feishu_mock
    )
    return {
        "connected": connected and not expired,
        "expired": bool(connected and expired),
        "mock": bool(settings.feishu_mock),
        "token_mock": bool((rec or {}).get("mock")),
        "user_name": ((rec or {}).get("user_name") or "") if connected else "",
        "has_refresh": bool((rec or {}).get("refresh_token")),
        "expires_at": expires_at if connected else "",
        "oauth_ready": app_ready,
        "redirect_uri": redirect_uri(settings),
        "scopes": oauth_scopes(settings),
        "identity_default": "user" if (connected and not expired) else "app",
        "hint": (
            "已连接飞书账号：导出将优先写到「我的」云文档"
            if connected and not expired
            else (
                "授权已过期，请重新连接飞书账号"
                if connected and expired
                else (
                    "未连接飞书账号。请先在开放平台「安全设置→重定向 URL」登记："
                    + redirect_uri(settings)
                    + "（须完全一致），再点连接；也可继续用应用空间兜底导出"
                )
            )
        ),
    }


def _store_pending_state(settings: Settings, state: str) -> None:
    _write_json(
        _pending_path(settings),
        {"state": state, "created_at": _iso(_utc_now())},
    )


def _consume_pending_state(settings: Settings, state: str | None) -> None:
    path = _pending_path(settings)
    data = _read_json(path)
    if path.is_file():
        try:
            path.unlink()
        except Exception:
            pass
    if not state:
        raise AppError("OAUTH_STATE_INVALID", "授权回调缺少 state，请重新发起授权", status_code=400)
    if not data or data.get("state") != state:
        raise AppError("OAUTH_STATE_INVALID", "授权 state 无效或已过期，请重新发起授权", status_code=400)
    created = _parse_iso(str(data.get("created_at") or ""))
    if created and (_utc_now() - created).total_seconds() > STATE_TTL_SEC:
        raise AppError("OAUTH_STATE_INVALID", "授权已超时，请重新发起授权", status_code=400)


def build_authorize_url(settings: Settings | None = None) -> str:
    """生成飞书授权页 URL，并落盘 state。Mock 下返回本机 callback 模拟同意。"""
    settings = settings or get_settings()
    state = secrets.token_urlsafe(24)
    _store_pending_state(settings, state)
    if settings.feishu_mock:
        q = urlencode({"code": f"mock_code_{uuid.uuid4().hex[:10]}", "state": state}, quote_via=quote)
        return f"{redirect_uri(settings)}?{q}"

    if not settings.feishu_app_id or not settings.feishu_app_secret:
        raise AppError(
            "FEISHU_NOT_CONFIGURED",
            "未配置飞书应用凭证。请在 .env 填写 FEISHU_APP_ID / FEISHU_APP_SECRET，或保持 FEISHU_MOCK=1",
            status_code=400,
        )
    # quote_via=quote：空格→%20（勿用 +），与飞书文档示例一致；redirect_uri 必须完整编码
    q = urlencode(
        {
            "client_id": settings.feishu_app_id,
            "response_type": "code",
            "redirect_uri": redirect_uri(settings),
            "scope": oauth_scopes(settings),
            "state": state,
        },
        quote_via=quote,
    )
    return f"{AUTHORIZE_URL}?{q}"


def mock_connect(settings: Settings | None = None, *, user_name: str = "Mock 用户") -> dict[str, Any]:
    """仅 FEISHU_MOCK=1：直接写入模拟 user token（测通授权态）。"""
    settings = settings or get_settings()
    if not settings.feishu_mock:
        raise AppError("FEISHU_MOCK_ONLY", "仅 FEISHU_MOCK=1 时可模拟授权", status_code=400)
    _save_tokens(
        settings,
        access_token=f"mock_user_{uuid.uuid4().hex}",
        refresh_token=f"mock_refresh_{uuid.uuid4().hex}",
        expires_in=86400,
        refresh_expires_in=86400 * 30,
        user_name=user_name or "Mock 用户",
        user_open_id="mock_open_id",
        mock=True,
    )
    return serialize_oauth_status(settings)


async def exchange_code_for_token(
    *,
    code: str,
    state: str | None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    _consume_pending_state(settings, state)
    code = (code or "").strip()
    if not code:
        raise AppError("OAUTH_DENIED", "未获得授权码（可能拒绝了授权）", status_code=400)

    if settings.feishu_mock:
        _save_tokens(
            settings,
            access_token=f"mock_user_{uuid.uuid4().hex}",
            refresh_token=f"mock_refresh_{uuid.uuid4().hex}",
            expires_in=86400,
            refresh_expires_in=86400 * 30,
            user_name="Mock 用户",
            user_open_id="mock_open_id",
            mock=True,
        )
        return serialize_oauth_status(settings)

    if not settings.feishu_app_id or not settings.feishu_app_secret:
        raise AppError(
            "FEISHU_NOT_CONFIGURED",
            "未配置飞书应用凭证，无法换取用户 token",
            status_code=400,
        )

    body = {
        "grant_type": "authorization_code",
        "client_id": settings.feishu_app_id,
        "client_secret": settings.feishu_app_secret,
        "code": code,
        "redirect_uri": redirect_uri(settings),
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(TOKEN_URL, json=body)
        try:
            data = r.json()
        except Exception:
            raise AppError(
                "OAUTH_TOKEN_FAILED",
                f"换取用户 token 失败（HTTP {r.status_code}）",
                status_code=502,
            ) from None

    # v2 可能 code==0 包一层，或直接返回 access_token
    if isinstance(data, dict) and data.get("code") not in (None, 0):
        msg = data.get("error_description") or data.get("msg") or data.get("error") or r.text[:200]
        raise AppError("OAUTH_TOKEN_FAILED", f"换取用户 token 失败：{msg}", status_code=502)

    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    access = str(payload.get("access_token") or "").strip()
    if not access:
        raise AppError("OAUTH_TOKEN_FAILED", "换取用户 token 未返回 access_token", status_code=502)

    _save_tokens(
        settings,
        access_token=access,
        refresh_token=str(payload.get("refresh_token") or ""),
        expires_in=payload.get("expires_in"),
        refresh_expires_in=payload.get("refresh_token_expires_in")
        or payload.get("refresh_expires_in"),
        user_name=str(payload.get("name") or payload.get("user_name") or ""),
        user_open_id=str(payload.get("open_id") or payload.get("user_id") or ""),
        mock=False,
    )
    return serialize_oauth_status(settings)


async def _refresh_user_token(settings: Settings, rec: dict[str, Any]) -> dict[str, Any]:
    refresh = str(rec.get("refresh_token") or "").strip()
    if not refresh:
        raise AppError(
            "OAUTH_REAUTH_REQUIRED",
            "用户授权已过期且无 refresh_token，请重新连接飞书账号",
            status_code=401,
        )
    if settings.feishu_mock or refresh.startswith("mock_refresh_"):
        return _save_tokens(
            settings,
            access_token=f"mock_user_{uuid.uuid4().hex}",
            refresh_token=refresh,
            expires_in=86400,
            refresh_expires_in=86400 * 30,
            user_name=str(rec.get("user_name") or "Mock 用户"),
            user_open_id=str(rec.get("user_open_id") or "mock_open_id"),
            mock=True,
        )

    if not settings.feishu_app_id or not settings.feishu_app_secret:
        raise AppError("FEISHU_NOT_CONFIGURED", "未配置飞书应用凭证，无法刷新用户 token", status_code=400)

    body = {
        "grant_type": "refresh_token",
        "client_id": settings.feishu_app_id,
        "client_secret": settings.feishu_app_secret,
        "refresh_token": refresh,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(TOKEN_URL, json=body)
        try:
            data = r.json()
        except Exception:
            raise AppError("OAUTH_REFRESH_FAILED", "刷新用户 token 失败", status_code=502) from None

    if isinstance(data, dict) and data.get("code") not in (None, 0):
        msg = data.get("error_description") or data.get("msg") or data.get("error") or "refresh failed"
        clear_tokens(settings)
        raise AppError(
            "OAUTH_REAUTH_REQUIRED",
            f"刷新用户授权失败，请重新连接飞书账号：{msg}",
            status_code=401,
        )

    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    access = str(payload.get("access_token") or "").strip()
    if not access:
        clear_tokens(settings)
        raise AppError("OAUTH_REAUTH_REQUIRED", "刷新用户授权失败，请重新连接", status_code=401)

    return _save_tokens(
        settings,
        access_token=access,
        refresh_token=str(payload.get("refresh_token") or refresh),
        expires_in=payload.get("expires_in"),
        refresh_expires_in=payload.get("refresh_token_expires_in")
        or payload.get("refresh_expires_in"),
        user_name=str(rec.get("user_name") or ""),
        user_open_id=str(rec.get("user_open_id") or ""),
        mock=False,
    )


async def get_user_access_token(settings: Settings | None = None) -> str | None:
    """若已授权则返回可用 user_access_token（必要时刷新）；未授权返回 None。"""
    settings = settings or get_settings()
    rec = load_token_record(settings)
    if not rec or not rec.get("access_token"):
        return None

    exp = _parse_iso(str(rec.get("expires_at") or ""))
    need_refresh = bool(exp and exp <= _utc_now() + timedelta(seconds=REFRESH_SKEW_SEC))
    if need_refresh:
        try:
            rec = await _refresh_user_token(settings, rec)
        except AppError as exc:
            if exc.code in {"OAUTH_REAUTH_REQUIRED", "OAUTH_REFRESH_FAILED"}:
                return None
            raise

    token = str(rec.get("access_token") or "").strip()
    return token or None


def callback_html(*, ok: bool, message: str, frontend_origin: str) -> str:
    title = "飞书授权成功" if ok else "飞书授权未完成"
    safe_msg = (
        message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    origin = (frontend_origin or "http://127.0.0.1:3040").rstrip("/")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
           max-width: 420px; margin: 48px auto; padding: 0 16px; color: #1f2329; }}
    h1 {{ font-size: 20px; }}
    p {{ line-height: 1.6; color: #646a73; }}
    a {{ color: #3370ff; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p>{safe_msg}</p>
  <p><a href="{origin}">返回 AI办公搭子</a></p>
  <script>setTimeout(function(){{ try {{ window.close(); }} catch (e) {{}} }}, 1600);</script>
</body>
</html>"""
