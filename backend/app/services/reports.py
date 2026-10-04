"""Durable report revisions. SQLite is authoritative; report.md is a repairable cache."""

from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import ReportVersion, Task, utcnow
from app.services.files import atomic_write_text

MAX_REPORT_CHARS = 200_000


def validate_markdown(markdown: str) -> str:
    if not isinstance(markdown, str) or not markdown.strip():
        raise AppError("EMPTY_REPORT", "模型没有返回有效正文，请重试；原版本已保留")
    if len(markdown) > MAX_REPORT_CHARS:
        raise AppError("REPORT_TOO_LARGE", "正文超过 20 万字，请缩小任务范围；原版本已保留")
    return markdown


def latest(db: Session, task_id: str) -> ReportVersion | None:
    return db.scalar(
        select(ReportVersion)
        .where(ReportVersion.task_id == task_id)
        .order_by(ReportVersion.version.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    )


def materialize(task: Task, revision: ReportVersion) -> Path:
    if not task.report_path:
        raise AppError("REPORT_NOT_READY", "报告尚未生成", status_code=404)
    path = Path(task.report_path)
    if not path.exists() or path.read_text(encoding="utf-8") != revision.markdown:
        atomic_write_text(path, revision.markdown)
    return path


def current(db: Session, task: Task) -> ReportVersion:
    revision = latest(db, task.id)
    if revision is not None:
        # A replanned task can have old versions but no current report yet.
        if not task.report_path:
            raise AppError("REPORT_NOT_READY", "报告尚未生成", status_code=404)
        materialize(task, revision)
        return revision
    if not task.report_path or not Path(task.report_path).is_file():
        raise AppError("REPORT_NOT_READY", "报告尚未生成", status_code=404)
    markdown = Path(task.report_path).read_text(encoding="utf-8")
    return save(db, task, markdown, reason="legacy", expected_version=0)


def save(
    db: Session,
    task: Task,
    markdown: str,
    *,
    reason: str,
    instruction: str = "",
    analysis_id: str | None = None,
    expected_version: int | None = None,
) -> ReportVersion:
    validate_markdown(markdown)
    previous = latest(db, task.id)
    number = previous.version if previous else 0
    if expected_version is not None and number != expected_version:
        raise AppError("REPORT_CONFLICT", "报告已被更新，请刷新后再修改；你的操作没有覆盖新版本", status_code=409)
    if not task.report_path:
        raise AppError("REPORT_NOT_READY", "尚未设置报告产物路径", status_code=404)
    revision = ReportVersion(
        task_id=task.id,
        version=number + 1,
        markdown=markdown,
        reason=reason,
        instruction=instruction[:2000],
        analysis_id=analysis_id,
    )
    db.add(revision)
    task.updated_at = utcnow()
    try:
        # The unique task/version key also protects against two concurrent writers.
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError("REPORT_CONFLICT", "报告已被更新，请刷新后再修改", status_code=409) from exc
    db.refresh(revision)
    materialize(task, revision)
    return revision


def _headings(markdown: str) -> list[dict[str, Any]]:
    headings: list[dict[str, Any]] = []
    offset = 0
    fence_char = ""
    fence_size = 0
    for line in markdown.splitlines(keepends=True):
        fence = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence:
            mark = fence.group(1)
            if not fence_char:
                fence_char, fence_size = mark[0], len(mark)
            elif mark[0] == fence_char and len(mark) >= fence_size:
                fence_char = ""
            offset += len(line)
            continue
        match = re.match(r"^ {0,3}(#{1,6})[ \t]+(.+?)\s*#*\s*$", line) if not fence_char else None
        if match:
            headings.append({"start": offset, "body_start": offset + len(line), "level": len(match[1]), "title": match[2].strip()})
        offset += len(line)
    return headings


def sections(markdown: str) -> list[dict[str, Any]]:
    """Find editable sections outside code fences, retaining exact character offsets."""
    headings = _headings(markdown)
    nested = [h["level"] for h in headings if h["level"] > 1]
    level = min(nested) if nested else 1
    selected = [h for h in headings if h["level"] == level]
    result: list[dict[str, Any]] = []
    first = selected[0]["start"] if selected else len(markdown)
    title = headings[0] if headings and headings[0]["start"] == 0 and headings[0]["level"] == 1 else None
    preamble_start = title["body_start"] if title and level > 1 else 0
    if first > preamble_start and markdown[preamble_start:first].strip():
        result.append({"start": 0, "body_start": preamble_start, "end": first, "level": 1, "title": "开头 / 摘要"})
    for index, heading in enumerate(selected):
        result.append({**heading, "end": selected[index + 1]["start"] if index + 1 < len(selected) else len(markdown)})
    if not result:
        result = [{"start": 0, "body_start": 0, "end": len(markdown), "level": 1, "title": "正文"}]
    return [{**part, "id": f"section-{index + 1}"} for index, part in enumerate(result)]


def replace_section(markdown: str, section_id: str, replacement: str) -> str:
    part = next((p for p in sections(markdown) if p["id"] == section_id), None)
    if part is None:
        raise AppError("SECTION_NOT_FOUND", "该章节不存在，请刷新后重新选择", status_code=404)
    body = validate_markdown(replacement).strip()
    # Some models repeat the selected heading. Keep the original heading exactly once.
    heading = markdown[part["start"]:part["body_start"]].strip()
    if heading and body.splitlines()[0].strip() == heading:
        body = "\n".join(body.splitlines()[1:]).strip()
    validate_markdown(body)
    for candidate in _headings(body):
        if candidate["level"] <= part["level"]:
            raise AppError("SECTION_SCOPE_INVALID", "模型返回了其他章节，未保存这次修改，请换一种指令重试")
    original = markdown[part["body_start"]:part["end"]]
    leading = re.match(r"^\s*", original).group(0)
    trailing = re.search(r"\s*$", original).group(0)
    if not trailing and part["end"] < len(markdown):
        trailing = "\n\n"
    return markdown[:part["body_start"]] + leading + body + trailing + markdown[part["end"]:]


def metadata(revision: ReportVersion) -> dict[str, Any]:
    return {
        "version": revision.version,
        "reason": revision.reason,
        "instruction": revision.instruction,
        "created_at": revision.created_at,
        "characters": len(revision.markdown),
    }


def list_versions(db: Session, task: Task) -> dict[str, Any]:
    head = current(db, task)
    items = db.scalars(select(ReportVersion).where(ReportVersion.task_id == task.id).order_by(ReportVersion.version.desc()))
    return {"current_version": head.version, "items": [metadata(row) for row in items]}


def get_version(db: Session, task: Task, version: int) -> ReportVersion:
    revision = db.scalar(select(ReportVersion).where(ReportVersion.task_id == task.id, ReportVersion.version == version))
    if revision is None:
        raise AppError("VERSION_NOT_FOUND", "报告版本不存在", status_code=404)
    return revision


def version_preview(db: Session, task: Task, version: int) -> dict[str, Any]:
    head = current(db, task)
    revision = get_version(db, task, version)
    lines = list(difflib.unified_diff(head.markdown.splitlines(), revision.markdown.splitlines(), fromfile=f"当前 v{head.version}", tofile=f"选中 v{version}", lineterm=""))
    return {
        **metadata(revision),
        "markdown": revision.markdown,
        "current_version": head.version,
        "diff": "\n".join(lines[:2000]),
        "diff_truncated": len(lines) > 2000,
    }
