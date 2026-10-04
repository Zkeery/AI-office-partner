from __future__ import annotations

import csv
import io
import re
from itertools import islice
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app.core.errors import AppError

ALLOWED_EXT = {".md", ".txt", ".markdown", ".pdf", ".docx", ".csv", ".xlsx"}
MAX_BYTES = 20 * 1024 * 1024
MAX_FILES = 3


def safe_filename(name: str) -> str:
    base = Path(name).name
    base = re.sub(r"[^\w.\u4e00-\u9fff\-]+", "_", base).strip("._")
    return base or "upload.bin"


def assert_allowed(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise AppError("UPLOAD_TYPE_NOT_ALLOWED", f"不支持的文件类型：{ext or '无扩展名'}")
    return ext


async def read_upload_bytes(file: UploadFile, max_bytes: int = MAX_BYTES) -> bytes:
    data = await file.read()
    if len(data) > max_bytes:
        raise AppError("UPLOAD_TOO_LARGE", "单个文件不能超过 20MB")
    return data


def _sheet_to_text(rows: list[list[Any]], max_rows: int = 40, max_cols: int = 12) -> str:
    lines: list[str] = []
    for i, row in enumerate(rows[:max_rows]):
        cells = [str(c if c is not None else "").strip() for c in row[:max_cols]]
        if not any(cells):
            continue
        lines.append(" | ".join(cells))
    if len(rows) > max_rows:
        lines.append(f"…（仅展示前 {max_rows} 行）")
    return "\n".join(lines)


def extract_csv_text(data: bytes, max_chars: int = 12000) -> str:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("gb18030")
    reader = csv.reader(io.StringIO(text))
    rows = list(islice(reader, 6))
    return ("以下仅为材料预览，执行时由程序读取完整表格：\n" + _sheet_to_text(rows))[:max_chars]


def extract_xlsx_text(path: Path, max_chars: int = 12000) -> str:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        parts = ["以下仅为材料预览，执行时由程序读取全部工作表与数据行："]
        for ws in wb.worksheets:
            rows = [list(row) for row in islice(ws.iter_rows(values_only=True), 6)]
            parts.append(f"工作表：{ws.title}\n" + _sheet_to_text(rows))
        return "\n\n".join(parts)[:max_chars]
    finally:
        wb.close()


def extract_text(path: Path, ext: str, max_chars: int = 12000) -> str:
    if ext in {".txt", ".md", ".markdown"}:
        return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    if ext == ".csv":
        return extract_csv_text(path.read_bytes(), max_chars=max_chars)
    if ext == ".xlsx":
        return extract_xlsx_text(path, max_chars=max_chars)
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        return "\n".join(parts)[:max_chars]
    if ext == ".docx":
        import docx

        doc = docx.Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)[:max_chars]
    return ""


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
