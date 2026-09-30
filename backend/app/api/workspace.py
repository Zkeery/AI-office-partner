from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel, Field

from app.core.errors import AppError
from app.services import workspace as ws
from app.services.files import read_upload_bytes

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


class WorkspaceSet(BaseModel):
    root: str = Field(min_length=1, max_length=1000)


class WorkspaceExport(BaseModel):
    task_id: str
    formats: list[str] = Field(default_factory=lambda: ["md"])
    confirm: bool = False
    subdir: str = ""


@router.get("")
def get_workspace() -> dict[str, Any]:
    root = ws.load_workspace_root()
    return {"configured": root is not None, "root": str(root) if root else ""}


@router.put("")
def set_workspace(body: WorkspaceSet) -> dict[str, Any]:
    path = ws.save_workspace_root(body.root)
    return {"configured": True, "root": str(path)}


@router.get("/entries")
def entries(rel: str = "") -> dict[str, Any]:
    return {"items": ws.list_entries(rel)}


@router.get("/file")
def file_content(rel: str) -> dict[str, Any]:
    return ws.read_text_file(rel)


@router.post("/upload")
async def upload_workspace_table(
    file: UploadFile = File(...),
    rel_dir: str = Form(default=""),
) -> dict[str, Any]:
    data = await read_upload_bytes(file)
    return ws.upload_table_file(
        filename=file.filename or "table.bin",
        data=data,
        rel_dir=rel_dir or "",
    )


@router.post("/export")
def export_to_workspace(body: WorkspaceExport) -> dict[str, Any]:
    """已停用：报告不再写入资料库，避免原料与交差成品混在一起。"""
    raise AppError(
        "WORKSPACE_EXPORT_DISABLED",
        "报告请在任务页下载 Markdown / Word / Excel / PPT，或导出到飞书；不再写入资料库。",
    )
