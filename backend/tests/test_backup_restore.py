import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

script = Path(__file__).resolve().parents[2] / "scripts/backup_restore.py"
spec = importlib.util.spec_from_file_location("backup_restore", script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_backup_restores_files_db_paths_and_disables_schedules(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "uploads").mkdir()
    (data / "artifacts").mkdir()
    material = data / "uploads/source.txt"
    report = data / "artifacts/report.md"
    material.write_text("材料完整内容", encoding="utf-8")
    report.write_text("# 可恢复报告", encoding="utf-8")
    with sqlite3.connect(data / "office.db") as db:
        db.executescript("CREATE TABLE tasks (id TEXT, status TEXT, report_path TEXT, plan_json TEXT); CREATE TABLE uploads (stored_path TEXT); CREATE TABLE schedules (enabled INTEGER, active_run_id TEXT);")
        db.execute("INSERT INTO tasks VALUES (?, ?, ?, ?)", ("t", "succeeded", str(report), json.dumps({"file": str(material)})))
        db.execute("INSERT INTO uploads VALUES (?)", (str(material),))
        db.execute("INSERT INTO schedules VALUES (1, 'old-run')")
    bundle = tmp_path / "backup"
    assert module.backup(data, bundle)["integrity"] == "ok"
    material.unlink()
    report.unlink()
    target = tmp_path / "restored"
    assert module.restore(bundle, target)["schedules"] == "disabled"
    with sqlite3.connect(target / "office.db") as db:
        restored_report = Path(db.execute("SELECT report_path FROM tasks").fetchone()[0])
        restored_material = Path(db.execute("SELECT stored_path FROM uploads").fetchone()[0])
        assert restored_report.read_text(encoding="utf-8") == "# 可恢复报告"
        assert restored_material.read_text(encoding="utf-8") == "材料完整内容"
        assert db.execute("SELECT enabled, active_run_id FROM schedules").fetchone() == (0, None)
    with pytest.raises(ValueError, match="新目录"):
        module.restore(bundle, target)
    (bundle / "data/uploads/source.txt").write_text("corrupted", encoding="utf-8")
    with pytest.raises(ValueError, match="校验失败"):
        module.restore(bundle, tmp_path / "bad-restore")
    assert not (tmp_path / "bad-restore").exists()
