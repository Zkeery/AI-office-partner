"""Explicit, reproducible inputs for recurring tasks."""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import uuid
from pathlib import Path
from urllib.parse import urlparse

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models import ScheduleRun, Task
from app.services import files, reports, workspace


def read_config(row) -> dict:
    try:
        data = json.loads(row.input_config_json or "{}")
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def configure_inputs(settings: Settings, schedule_id: str, *, urls: list[str], workspace_paths: list[str], material_mode: str, include_upstream_result: bool) -> dict:
    if material_mode not in {"snapshot", "latest"}:
        raise AppError("VALIDATION_ERROR", "材料方式请选择固定快照或每次读取所选文件的最新版")
    if len(urls) > 3 or any(urlparse(url).scheme not in {"http", "https"} or not urlparse(url).hostname for url in urls):
        raise AppError("VALIDATION_ERROR", "参考链接最多 3 个，须使用 http 或 https")
    if len(workspace_paths) != len(set(workspace_paths)) or len(workspace_paths) + int(include_upstream_result) > files.MAX_FILES:
        raise AppError("UPLOAD_LIMIT", "材料最多 3 份，上游报告会占用其中 1 份；不能重复选择同一文件")
    config = {"urls": urls, "material_mode": material_mode, "include_upstream_result": include_upstream_result, "bindings": []}
    root = workspace.require_root(settings) if workspace_paths else None
    config["workspace_root"] = str(root) if root else None
    snapshot_dir = settings.data_path / "schedule_inputs" / schedule_id / uuid.uuid4().hex
    try:
        for rel in workspace_paths:
            src = workspace.safe_resolve(root, rel)
            if not src.is_file() or src.stat().st_size > files.MAX_BYTES:
                raise AppError("MATERIAL_MISSING", f"材料不存在或超过 20MB：{rel}")
            ext = files.assert_allowed(src.name)
            files.extract_text(src, ext)
            binding = {"path": rel, "filename": src.name}
            if material_mode == "snapshot":
                snapshot_dir.mkdir(parents=True, exist_ok=True)
                dest = snapshot_dir / f"{uuid.uuid4().hex}{ext}"
                data = src.read_bytes()
                if len(data) > files.MAX_BYTES:
                    raise AppError("UPLOAD_TOO_LARGE", "材料超过 20MB")
                dest.write_bytes(data)
                files.extract_text(dest, ext)
                binding.update(snapshot_rel=str(dest.relative_to(settings.data_path)), sha256=hashlib.sha256(data).hexdigest())
            config["bindings"].append(binding)
    except Exception:
        shutil.rmtree(snapshot_dir, ignore_errors=True)
        raise
    return config


async def attach_run_inputs(db: Session, task: Task, run: ScheduleRun, config: dict, settings: Settings) -> None:
    from app.services.tasks import add_upload

    manifest = {"urls": config.get("urls", []), "material_mode": config.get("material_mode", "snapshot"), "files": []}
    run.input_manifest_json = json.dumps(manifest, ensure_ascii=False)
    db.commit()
    for binding in config.get("bindings", []):
        if config.get("material_mode") == "latest":
            root = workspace.require_root(settings)
            if config.get("workspace_root") != str(root):
                raise AppError("MATERIAL_ROOT_CHANGED", "资料库位置已改变，请重新选择自动化材料")
            src = workspace.safe_resolve(root, binding["path"])
        else:
            src = workspace.safe_resolve(settings.data_path, binding.get("snapshot_rel", ""))
        if not src.is_file() or src.stat().st_size > files.MAX_BYTES:
            raise AppError("MATERIAL_MISSING", f"自动化材料「{binding['filename']}」缺失或超限，请重新配置")
        data = src.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if config.get("material_mode") != "latest" and digest != binding.get("sha256"):
            raise AppError("MATERIAL_CHANGED", "固定快照已被修改，请重新选择材料，未继续执行")
        await add_upload(db, task.id, UploadFile(filename=binding["filename"], file=io.BytesIO(data)), settings)
        manifest["files"].append({"filename": binding["filename"], "workspace_path": binding["path"], "sha256": digest, "bytes": len(data)})
        run.input_manifest_json = json.dumps(manifest, ensure_ascii=False)
        db.commit()
    if config.get("include_upstream_result"):
        source_run = db.get(ScheduleRun, run.upstream_run_id) if run.upstream_run_id else None
        source_task = db.get(Task, source_run.task_id) if source_run and source_run.status == "success" and source_run.task_id else None
        if not source_task:
            raise AppError("UPSTREAM_REQUIRED", "本自动化需要上游成功跑次的报告，请从上游成功事件触发")
        result = json.loads(source_run.input_manifest_json or "{}").get("result", {})
        if not result.get("version"):
            raise AppError("UPSTREAM_REQUIRED", "上游跑次缺少固定成果版本，请重新运行上游")
        revision = reports.get_version(db, source_task, result["version"])
        data = revision.markdown.encode("utf-8")
        if hashlib.sha256(data).hexdigest() != result.get("sha256"):
            raise AppError("UPSTREAM_CHANGED", "上游成果校验不一致，请重新运行上游")
        name = f"上游报告-v{revision.version}.md"
        await add_upload(db, task.id, UploadFile(filename=name, file=io.BytesIO(data)), settings)
        manifest["upstream"] = {"run_id": source_run.id, "task_id": source_task.id, "version": revision.version, "sha256": hashlib.sha256(data).hexdigest()}
    run.input_manifest_json = json.dumps(manifest, ensure_ascii=False)
    db.commit()
