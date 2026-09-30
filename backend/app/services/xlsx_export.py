from __future__ import annotations

import re
from pathlib import Path

from openpyxl import Workbook


def _row_kind(line: str) -> tuple[str, str]:
    if line.startswith("### "):
        return "标题3", line[4:].strip()
    if line.startswith("## "):
        return "标题2", line[3:].strip()
    if line.startswith("# "):
        return "标题1", line[2:].strip()
    if re.match(r"^[-*]\s+", line):
        return "要点", re.sub(r"^[-*]\s+", "", line).strip()
    if re.match(r"^\d+\.\s+", line):
        return "要点", re.sub(r"^\d+\.\s+", "", line).strip()
    return "正文", line


def markdown_to_xlsx(md: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "报告"
    ws.append(["类型", "内容"])
    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        kind, content = _row_kind(line)
        if not content:
            continue
        ws.append([kind, content])
    ws.column_dimensions["A"].width = 10
    ws.column_dimensions["B"].width = 80
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    wb.save(tmp)
    tmp.replace(dest)
    return dest


def ensure_xlsx_from_markdown(md_path: Path, xlsx_path: Path) -> Path:
    md = md_path.read_text(encoding="utf-8")
    return markdown_to_xlsx(md, xlsx_path)
