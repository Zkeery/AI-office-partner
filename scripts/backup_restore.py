"""Offline, verified backups. No secrets or model calls are printed or sent.

Usage:
  python scripts/backup_restore.py backup --data-dir data --output backups/2026-10-04
  python scripts/backup_restore.py restore --backup backups/2026-10-04 --target .runtime/restore-drill
Only pass --workspace-root when the whole external library should be included.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.core.process_lock import data_lock


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def contained(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("备份路径越界")
    return path


def copy_tree(source: Path, target: Path, *, skip: set[str] | None = None):
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    for item in source.iterdir():
        if item.name in (skip or set()):
            continue
        if item.is_symlink():
            raise ValueError("备份目录含符号链接，请先将所需文件复制到实际目录")
        dest = target / item.name
        if item.is_dir():
            copy_tree(item, dest)
        elif item.is_file():
            shutil.copy2(item, dest)
            dest.chmod(0o600)


def backup(data_dir: Path, output: Path, workspace_root: Path | None = None) -> dict:
    data_dir, output = data_dir.resolve(), output.resolve()
    if output.exists() or output.is_relative_to(data_dir):
        raise ValueError("备份目的地必须不存在，且位于数据目录之外")
    if not (data_dir / "office.db").is_file():
        raise ValueError("数据目录没有 office.db")
    if workspace_root:
        workspace_root = workspace_root.resolve()
        if not workspace_root.is_dir() or output.is_relative_to(workspace_root):
            raise ValueError("资料库不存在，或备份目的地位于资料库内")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".backup-", dir=output.parent))
    try:
        with data_lock(data_dir):
            copy_tree(data_dir, stage / "data", skip={".service.lock", "office.db", "office.db-wal", "office.db-shm", "office.db-journal"})
            with sqlite3.connect(f"{(data_dir / 'office.db').as_uri()}?mode=ro", uri=True) as source, sqlite3.connect(stage / "data/office.db") as dest:
                source.backup(dest)
                if dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("数据库完整性检查失败")
            (stage / "data/office.db").chmod(0o600)
            if workspace_root and not workspace_root.is_relative_to(data_dir):
                copy_tree(workspace_root, stage / "workspace")
        manifest = {"format": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                    "source_data": str(data_dir), "source_workspace": str(workspace_root) if workspace_root else None,
                    "files": {str(path.relative_to(stage)): digest(path) for path in sorted(stage.rglob("*")) if path.is_file()}}
        (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (stage / "manifest.json").chmod(0o600)
        stage.rename(output)
        return {"path": str(output), "files": len(manifest["files"]), "integrity": "ok"}
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def restore(backup_dir: Path, target: Path) -> dict:
    backup_dir, target = backup_dir.resolve(), target.resolve()
    if target.exists() or target.is_relative_to(backup_dir):
        raise ValueError("恢复目的地必须是备份目录之外的新目录；不会覆盖现有数据")
    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != 1 or "data/office.db" not in manifest.get("files", {}):
        raise ValueError("备份清单格式无效")
    expected = set(manifest["files"])
    actual = {str(p.relative_to(backup_dir)) for p in backup_dir.rglob("*") if p.is_file() and p.name != "manifest.json"}
    if expected != actual or any(p.is_symlink() for p in backup_dir.rglob("*")):
        raise ValueError("备份文件集合与清单不一致")
    for rel, checksum in manifest["files"].items():
        path = contained(backup_dir, rel)
        if not path.is_file() or digest(path) != checksum:
            raise ValueError(f"备份校验失败：{rel}")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".restore-", dir=target.parent))
    old_data = manifest["source_data"]
    workspace_source = manifest.get("source_workspace")
    workspace_target = target / "workspace"
    try:
        copy_tree(backup_dir / "data", stage)
        if (backup_dir / "workspace").is_dir():
            copy_tree(backup_dir / "workspace", stage / "workspace")
        (stage / "workspace").mkdir(exist_ok=True, mode=0o700)
        cfg = stage / "workspace.json"
        if cfg.exists():
            original = json.loads(cfg.read_text(encoding="utf-8")).get("root")
            workspace_source = workspace_source or original
            if original and Path(original).is_relative_to(Path(old_data)):
                workspace_target = target / Path(original).relative_to(old_data)
            cfg.write_text(json.dumps({"root": str(workspace_target)}, ensure_ascii=False), encoding="utf-8")

        def rebase(value):
            if isinstance(value, dict):
                return {key: rebase(item) for key, item in value.items()}
            if isinstance(value, list):
                return [rebase(item) for item in value]
            if isinstance(value, str):
                if value == old_data or value.startswith(old_data + os.sep):
                    return str(target) + value[len(old_data):]
                if workspace_source and (value == workspace_source or value.startswith(workspace_source + os.sep)):
                    return str(workspace_target) + value[len(workspace_source):]
            return value

        with sqlite3.connect(stage / "office.db") as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in tables:
                if table not in {"tasks", "uploads", "task_steps", "task_events", "schedules", "schedule_runs", "report_versions", "model_calls"}:
                    continue
                columns = {row[1] for row in db.execute(f'PRAGMA table_info("{table}")')}
                for col in columns & {"report_path", "stored_path", "plan_json", "detail_json", "payload_json", "input_config_json", "input_manifest_json"}:
                    for row_id, value in db.execute(f'SELECT rowid, "{col}" FROM "{table}"').fetchall():
                        if not value:
                            continue
                        updated = json.dumps(rebase(json.loads(value)), ensure_ascii=False) if col.endswith("_json") else rebase(value)
                        db.execute(f'UPDATE "{table}" SET "{col}"=? WHERE rowid=?', (updated, row_id))
                if table == "schedules":
                    db.execute("UPDATE schedules SET enabled=0")
                    if "active_run_id" in columns:
                        db.execute("UPDATE schedules SET active_run_id=NULL")
                if table == "tasks":
                    db.execute("UPDATE tasks SET status='paused' WHERE status='running'")
                    db.execute("UPDATE tasks SET status='failed' WHERE status='planning'")
                    if "operation_token" in columns:
                        db.execute("UPDATE tasks SET operation_token=?", (str(uuid.uuid4()),))
                if table == "task_steps":
                    db.execute("UPDATE task_steps SET status='pending' WHERE status='running'")
                if table == "schedule_runs":
                    db.execute("UPDATE schedule_runs SET status='interrupted', error='RUN_INTERRUPTED: 从备份恢复，未确认完成' WHERE status='running'")
                if table == "model_calls":
                    db.execute("UPDATE model_calls SET status='interrupted' WHERE status='pending'")
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("恢复后的数据库完整性检查失败")
            # Validate every attached file and current report after rebasing.
            for table, column in [("uploads", "stored_path"), ("tasks", "report_path")]:
                if table not in tables:
                    continue
                for (value,) in db.execute(f'SELECT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL'):
                    path = Path(value)
                    if not path.is_relative_to(target) or not (stage / path.relative_to(target)).is_file():
                        raise ValueError("恢复后的材料或报告缺失，请检查备份完整性")
        for path in stage.rglob("*.json"):
            if path == cfg:
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, UnicodeError):
                continue
            path.write_text(json.dumps(rebase(data), ensure_ascii=False, indent=2), encoding="utf-8")
        stage.rename(target)
        return {"path": str(target), "files_verified": len(expected), "integrity": "ok", "schedules": "disabled"}
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("backup")
    b.add_argument("--data-dir", type=Path, required=True)
    b.add_argument("--output", type=Path, required=True)
    b.add_argument("--workspace-root", type=Path)
    r = sub.add_parser("restore")
    r.add_argument("--backup", type=Path, required=True)
    r.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = backup(args.data_dir, args.output, args.workspace_root) if args.command == "backup" else restore(args.backup, args.target)
        print(json.dumps(result, ensure_ascii=False))
    except (ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
