from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.core.errors import AppError

TEXT_READ_EXT = {".txt", ".md", ".markdown", ".csv", ".json"}
TABLE_UPLOAD_EXT = {".csv", ".xlsx"}
LIST_VISIBLE_EXT = TEXT_READ_EXT | {".docx", ".pdf", ".xlsx"}
WRITE_NAME_ALLOW = {"report.md", "report.docx", "report.xlsx", "report.pptx"}
# 历史「导出到工作区」留下的成品，列表里默认隐藏，避免资料库被交差文件淹没
PRODUCT_EXPORT_NAMES = {n.lower() for n in WRITE_NAME_ALLOW}
MAX_READ_BYTES = 512 * 1024
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_LIST = 200


def workspace_config_path(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    return settings.data_path / "workspace.json"


def load_workspace_root(settings: Settings | None = None) -> Path | None:
    settings = settings or get_settings()
    cfg = workspace_config_path(settings)
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            root = (data.get("root") or "").strip()
            if root:
                return Path(root).expanduser().resolve()
        except Exception:
            pass
    env_root = getattr(settings, "local_workspace_root", "") or ""
    if env_root.strip():
        return Path(env_root).expanduser().resolve()
    return None


def save_workspace_root(root: str, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    path = Path(root).expanduser().resolve()
    if path.exists() and path.is_file():
        raise AppError(
            "WORKSPACE_INVALID",
            "这里要填「文件夹」路径，不能填某个文件（例如 .x / .md）。请选包含材料的文件夹。",
        )
    if not path.exists() or not path.is_dir():
        raise AppError("WORKSPACE_INVALID", "路径不存在或不是文件夹，请填本机已有的文件夹绝对路径")
    settings.data_path.mkdir(parents=True, exist_ok=True)
    workspace_config_path(settings).write_text(
        json.dumps({"root": str(path)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def require_root(settings: Settings | None = None) -> Path:
    root = load_workspace_root(settings)
    if root is None:
        raise AppError("WORKSPACE_NOT_SET", "请先设置资料库文件夹")
    if not root.exists() or not root.is_dir():
        raise AppError("WORKSPACE_INVALID", "资料库路径无效，请重新设置")
    return root


def safe_resolve(root: Path, rel: str) -> Path:
    rel = (rel or "").strip().replace("\\", "/")
    if rel.startswith("/"):
        raise AppError("PATH_DENIED", "不允许使用绝对路径")
    candidate = (root / rel).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise AppError("PATH_DENIED", "路径超出授权资料库") from exc
    return candidate


def list_entries(rel: str = "", settings: Settings | None = None) -> list[dict[str, Any]]:
    root = require_root(settings)
    target = safe_resolve(root, rel) if rel else root
    if not target.exists() or not target.is_dir():
        raise AppError("WORKSPACE_INVALID", "目录不存在")
    items: list[dict[str, Any]] = []
    for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if len(items) >= MAX_LIST:
            break
        if child.is_symlink():
            continue
        if child.is_file():
            if child.name.lower() in PRODUCT_EXPORT_NAMES:
                continue
            if child.suffix.lower() not in LIST_VISIBLE_EXT:
                continue
        try:
            st = child.stat()
            mtime = st.st_mtime
            size = st.st_size if child.is_file() else 0
        except OSError:
            continue
        items.append(
            {
                "name": child.name,
                "rel": str(child.relative_to(root)).replace("\\", "/"),
                "is_dir": child.is_dir(),
                "size": size,
                "mtime": mtime,
            }
        )
    items.sort(key=lambda i: (not i["is_dir"], -(i.get("mtime") or 0), i["name"].lower()))
    return items


def read_text_file(rel: str, settings: Settings | None = None) -> dict[str, Any]:
    root = require_root(settings)
    path = safe_resolve(root, rel)
    if not path.is_file():
        raise AppError("WORKSPACE_INVALID", "不是文件")
    if path.suffix.lower() not in TEXT_READ_EXT:
        raise AppError(
            "FILE_TYPE_NOT_ALLOWED",
            f"左侧预览暂不支持 {path.suffix or '该'} 文件；请用 .txt / .md / .csv。Excel 请用「选作表格分析」。",
        )
    size = path.stat().st_size
    if size > MAX_READ_BYTES:
        raise AppError("FILE_TOO_LARGE", "文件超过 512KB，请换较小文件")
    text = path.read_text(encoding="utf-8", errors="ignore")
    return {"rel": rel, "name": path.name, "content": text, "size": size}


def upload_table_file(
    *,
    filename: str,
    data: bytes,
    rel_dir: str = "",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Write a CSV/Excel table into the authorized workspace folder."""
    from app.services.files import safe_filename

    if len(data) > MAX_UPLOAD_BYTES:
        raise AppError("UPLOAD_TOO_LARGE", "单个文件不能超过 20MB")
    name = safe_filename(filename)
    ext = Path(name).suffix.lower()
    if ext not in TABLE_UPLOAD_EXT:
        raise AppError("UPLOAD_TYPE_NOT_ALLOWED", "资料库表格上传仅支持 .csv / .xlsx")
    root = require_root(settings)
    target_dir = safe_resolve(root, rel_dir) if rel_dir else root
    if not target_dir.exists() or not target_dir.is_dir():
        raise AppError("WORKSPACE_INVALID", "目标文件夹不存在")
    dest = target_dir / name
    if dest.exists():
        stem = dest.stem
        dest = target_dir / f"{stem}_new{ext}"
    dest.write_bytes(data)
    rel = str(dest.relative_to(root)).replace("\\", "/")
    return {"name": dest.name, "rel": rel, "size": len(data), "is_dir": False}


def collect_workspace_excerpts(settings: Settings | None = None, limit_files: int = 8, max_chars: int = 8000) -> str:
    try:
        root = require_root(settings)
    except AppError:
        return ""
    chunks: list[str] = []
    total = 0
    count = 0
    for path in sorted(root.rglob("*")):
        if count >= limit_files:
            break
        if not path.is_file() or path.is_symlink():
            continue
        if path.suffix.lower() not in TEXT_READ_EXT:
            continue
        try:
            path.relative_to(root.resolve())
        except ValueError:
            continue
        if path.stat().st_size > MAX_READ_BYTES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")[:1500]
        piece = f"[{path.relative_to(root)}] {text}"
        chunks.append(piece)
        total += len(piece)
        count += 1
        if total >= max_chars:
            break
    return "\n---\n".join(chunks)


def export_report_files(
    *,
    task_id: str,
    md_text: str | None,
    docx_src: Path | None,
    formats: list[str],
    confirm: bool,
    subdir: str = "",
    settings: Settings | None = None,
    xlsx_src: Path | None = None,
    pptx_src: Path | None = None,
) -> list[str]:
    if not confirm:
        raise AppError("WRITE_CONFIRM_REQUIRED", "写入资料库前请确认")
    root = require_root(settings)
    target_dir = safe_resolve(root, subdir) if subdir else root
    if not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
        # re-check escape after mkdir
        target_dir = safe_resolve(root, subdir) if subdir else root

    written: list[str] = []
    formats = [f.lower() for f in formats] or ["md"]
    if "md" in formats:
        if not md_text:
            raise AppError("REPORT_NOT_READY", "没有可导出的 Markdown 报告")
        dest = target_dir / "report.md"
        if dest.name.lower() not in WRITE_NAME_ALLOW:
            raise AppError("PATH_DENIED", "不允许的文件名")
        dest.write_text(md_text, encoding="utf-8")
        written.append(str(dest.relative_to(root)).replace("\\", "/"))
    if "docx" in formats:
        if not docx_src or not docx_src.exists():
            raise AppError("REPORT_NOT_READY", "没有可导出的 Word 报告")
        dest = target_dir / "report.docx"
        dest.write_bytes(docx_src.read_bytes())
        written.append(str(dest.relative_to(root)).replace("\\", "/"))
    if "xlsx" in formats:
        if not xlsx_src or not xlsx_src.exists():
            raise AppError("REPORT_NOT_READY", "没有可导出的表格报告")
        dest = target_dir / "report.xlsx"
        dest.write_bytes(xlsx_src.read_bytes())
        written.append(str(dest.relative_to(root)).replace("\\", "/"))
    if "pptx" in formats:
        if not pptx_src or not pptx_src.exists():
            raise AppError("REPORT_NOT_READY", "没有可导出的 PPT 报告")
        dest = target_dir / "report.pptx"
        dest.write_bytes(pptx_src.read_bytes())
        written.append(str(dest.relative_to(root)).replace("\\", "/"))
    return written
