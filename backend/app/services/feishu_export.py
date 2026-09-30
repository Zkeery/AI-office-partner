from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import AppError


FEISHU_OPEN = "https://open.feishu.cn/open-apis"


def _plain_text(text: str) -> str:
    """Strip common Markdown markers for Feishu plain text runs."""
    out = text
    out = re.sub(r"\*\*(.+?)\*\*", r"\1", out)
    out = re.sub(r"__(.+?)__", r"\1", out)
    out = re.sub(r"`([^`]+)`", r"\1", out)
    out = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", out)
    out = out.replace("---", "—")
    return out.strip()


def _paragraphs_from_markdown(md: str) -> list[tuple[str, str]]:
    """Return list of (kind, text) where kind in text|h1|h2|h3."""
    chunks: list[tuple[str, str]] = []
    for raw in re.split(r"\n{2,}", md.strip()):
        line = raw.strip()
        if not line or line.strip("-") == "":
            continue
        first = line.split("\n", 1)[0].strip()
        if first.startswith("### "):
            chunks.append(("h3", _plain_text(first[4:]) or first))
        elif first.startswith("## "):
            chunks.append(("h2", _plain_text(first[3:]) or first))
        elif first.startswith("# "):
            chunks.append(("h1", _plain_text(first[2:]) or first))
        else:
            # Keep markdown tables as line-broken text instead of one long blob.
            if "|" in line and "\n" in line:
                text = "\n".join(p.strip() for p in line.splitlines() if p.strip() and not re.match(r"^\|?\s*-+", p))
            else:
                text = " ".join(p.strip() for p in line.splitlines() if p.strip())
            text = _plain_text(text)
            if text:
                chunks.append(("text", text[:4000]))
        if len(chunks) >= 40:
            break
    if not chunks:
        chunks.append(("text", "（空报告）"))
    return chunks


def _text_block(content: str, block_type: int = 2) -> dict[str, Any]:
    # 2 text, 3 heading1, 4 heading2, 5 heading3
    key = {2: "text", 3: "heading1", 4: "heading2", 5: "heading3"}[block_type]
    return {
        "block_type": block_type,
        key: {
            "elements": [{"text_run": {"content": content}}],
        },
    }


def markdown_to_blocks(md: str) -> list[dict[str, Any]]:
    mapping = {"text": 2, "h1": 3, "h2": 4, "h3": 5}
    return [_text_block(text, mapping[kind]) for kind, text in _paragraphs_from_markdown(md)]


def document_url(document_id: str, settings: Settings) -> str:
    base = (settings.feishu_doc_base_url or "https://feishu.cn").rstrip("/")
    return f"{base}/docx/{document_id}"


async def _tenant_token(settings: Settings) -> str:
    if not settings.feishu_app_id or not settings.feishu_app_secret:
        raise AppError(
            "FEISHU_NOT_CONFIGURED",
            "未配置飞书应用凭证。请在 .env 填写 FEISHU_APP_ID / FEISHU_APP_SECRET，或保持 FEISHU_MOCK=1",
            status_code=400,
        )
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{FEISHU_OPEN}/auth/v3/tenant_access_token/internal",
            json={
                "app_id": settings.feishu_app_id,
                "app_secret": settings.feishu_app_secret,
            },
        )
        data = r.json()
        if data.get("code") != 0 or not data.get("tenant_access_token"):
            raise AppError(
                "FEISHU_EXPORT_FAILED",
                f"获取飞书 token 失败：{data.get('msg') or r.text[:200]}",
                status_code=502,
            )
        return str(data["tenant_access_token"])


async def _create_document(token: str, title: str, folder_token: str) -> dict[str, Any]:
    body: dict[str, Any] = {"title": title[:200] or "调研报告"}
    if folder_token:
        body["folder_token"] = folder_token
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{FEISHU_OPEN}/docx/v1/documents",
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
        data = r.json()
        if data.get("code") != 0:
            raise AppError(
                "FEISHU_EXPORT_FAILED",
                f"创建飞书文档失败：{data.get('msg') or r.text[:200]}",
                status_code=502,
            )
        doc = data.get("data", {}).get("document") or {}
        document_id = doc.get("document_id")
        if not document_id:
            raise AppError("FEISHU_EXPORT_FAILED", "创建飞书文档未返回 document_id", status_code=502)
        return {"document_id": document_id, "revision_id": doc.get("revision_id")}


async def _append_blocks(token: str, document_id: str, blocks: list[dict[str, Any]]) -> None:
    # Root block id equals document_id for newly created docs.
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            f"{FEISHU_OPEN}/docx/v1/documents/{document_id}/blocks/{document_id}/children",
            headers={"Authorization": f"Bearer {token}"},
            json={"children": blocks, "index": 0},
        )
        data = r.json()
        if data.get("code") != 0:
            raise AppError(
                "FEISHU_EXPORT_FAILED",
                f"写入飞书正文失败：{data.get('msg') or r.text[:200]}",
                status_code=502,
            )


def _save_meta(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


async def _enable_link_share(token: str, document_id: str) -> dict[str, Any]:
    """Best-effort: allow opening the doc via link after Feishu login."""
    # type=docx — document_id 即权限 token
    url = (
        f"{FEISHU_OPEN}/drive/v1/permissions/{document_id}/public"
        f"?type=docx"
    )
    # v1/v2 枚举：security/comment 用 anyone_can_view，勿用 anyone_with_link（会 99992402）
    body = {
        "external_access_entity": "open",
        "security_entity": "anyone_can_view",
        "comment_entity": "anyone_can_view",
        "share_entity": "anyone",
        "link_share_entity": "anyone_readable",
        "invite_external": True,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.patch(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
        try:
            data = r.json()
        except Exception:
            data = {"http_status": r.status_code, "text": r.text[:300]}
        return {"ok": data.get("code") == 0, "response": data}


async def export_markdown_to_feishu(
    *,
    markdown: str,
    title: str,
    artifact_dir: Path,
    settings: Settings | None = None,
    as_app: bool = False,
) -> dict[str, Any]:
    """导出 Markdown 到飞书云文档。

    身份策略（1.24）：
    - 默认：已授权用户 → user_access_token，落「我的」云空间根目录；
    - 未授权或 as_app=True → tenant_access_token 应用兜底（可尊重 FEISHU_FOLDER_TOKEN）。
    """
    settings = settings or get_settings()
    safe_title = (title or "调研报告").strip() or "调研报告"
    meta_path = artifact_dir / "feishu_export.json"

    # 延迟导入，避免与 oauth ↔ export 循环依赖在模块加载期炸裂
    from app.services import feishu_oauth as feishu_oauth_service

    user_token: str | None = None
    if not as_app:
        user_token = await feishu_oauth_service.get_user_access_token(settings)
    use_user = bool(user_token) and not as_app
    identity = "user" if use_user else "app"
    space = "my" if use_user else "app"
    space_label = "我的云文档" if use_user else "应用空间"

    if settings.feishu_mock:
        document_id = f"mock_{uuid.uuid4().hex[:12]}"
        url = f"https://feishu.mock.local/docx/{document_id}"
        payload = {
            "document_id": document_id,
            "url": url,
            "title": safe_title,
            "mock": True,
            "identity": identity,
            "space": space,
            "space_label": space_label,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "preview": markdown[:500],
            "link_share": {"ok": True, "mock": True},
        }
        _save_meta(meta_path, payload)
        return payload

    if use_user:
        token = str(user_token)
        folder_token = ""  # 用户身份默认落云空间根目录
    else:
        token = await _tenant_token(settings)
        folder_token = settings.feishu_folder_token or ""

    created = await _create_document(token, safe_title, folder_token)
    document_id = created["document_id"]
    await _append_blocks(token, document_id, markdown_to_blocks(markdown))
    link_share = await _enable_link_share(token, document_id)
    url = document_url(document_id, settings)
    payload = {
        "document_id": document_id,
        "url": url,
        "title": safe_title,
        "mock": False,
        "identity": identity,
        "space": space,
        "space_label": space_label,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "link_share": link_share,
    }
    _save_meta(meta_path, payload)
    return payload