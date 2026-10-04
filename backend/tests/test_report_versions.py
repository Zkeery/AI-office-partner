from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.db import session as db_session
from app.services import reports, table_analysis, tasks


ORIGINAL = "# 销售复盘\n\n## 数据概览\n\n销售额合计 300 元。\n\n## 建议\n\n保留这段原文及来源 https://example.com 。\n"


def seed(client, markdown=ORIGINAL, analysis_id=None):
    task_id = client.post("/api/tasks", json={"model_id": "mock", "prompt": "整理销售报告"}).json()["id"]
    with db_session.SessionLocal() as db:
        task = tasks.get_task(db, task_id)
        task.status = "succeeded"
        task.report_path = str(get_settings().artifacts_path / task_id / "report.md")
        reports.save(db, task, markdown, reason="generated", analysis_id=analysis_id)
    return task_id


def test_section_rewrite_preserves_everything_outside_selected_section(client, monkeypatch):
    task_id = seed(client)
    before = client.get(f"/api/tasks/{task_id}/report").json()
    target = next(section["id"] for section in before["sections"] if section["title"] == "数据概览")
    async def rewrite(_settings, system, user):
        assert "[SECTION_REWRITE]" in system
        assert "保留这段原文" not in user
        return "销售额合计 300 元，建议持续观察。"
    monkeypatch.setattr(tasks, "chat_completion", rewrite)
    response = client.post(f"/api/tasks/{task_id}/rewrite", json={"instruction": "补充一句建议", "scope": "section", "section_id": target, "expected_version": 1})
    assert response.status_code == 200
    after = client.get(f"/api/tasks/{task_id}/report").json()
    assert after["version"] == 2
    assert after["markdown"] == ORIGINAL.replace("销售额合计 300 元。", "销售额合计 300 元，建议持续观察。")
    history = client.get(f"/api/tasks/{task_id}/report/versions").json()
    assert [item["version"] for item in history["items"]] == [2, 1]
    preview = client.get(f"/api/tasks/{task_id}/report/versions/1").json()
    assert preview["markdown"] == ORIGINAL
    assert "-销售额合计 300 元，建议持续观察。" in preview["diff"]


def test_restore_adds_version_and_survives_missing_file_cache(client):
    task_id = seed(client)
    with db_session.SessionLocal() as db:
        task = tasks.get_task(db, task_id)
        reports.save(db, task, "# 新稿\n\n新内容", reason="rewrite", expected_version=1)
    result = client.post(f"/api/tasks/{task_id}/report/restore", json={"version": 1, "expected_version": 2})
    assert result.status_code == 200
    with db_session.SessionLocal() as db:
        cache = Path(tasks.get_task(db, task_id).report_path)
        cache.unlink()
    assert client.get(f"/api/tasks/{task_id}").json()["has_report"] is True
    document = client.get(f"/api/tasks/{task_id}/report").json()
    assert document["version"] == 3
    assert document["markdown"] == ORIGINAL
    assert cache.read_text(encoding="utf-8") == ORIGINAL
    assert client.get(f"/api/tasks/{task_id}/report/versions/2").json()["markdown"] == "# 新稿\n\n新内容"


def test_stale_version_is_rejected_before_model_call(client, monkeypatch):
    task_id = seed(client)
    async def unexpected(*_):
        raise AssertionError("the model must not run for stale edits")
    monkeypatch.setattr(tasks, "chat_completion", unexpected)
    response = client.post(f"/api/tasks/{task_id}/rewrite", json={"instruction": "修改", "expected_version": 99})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REPORT_CONFLICT"
    assert client.get(f"/api/tasks/{task_id}/report").json()["markdown"] == ORIGINAL


def test_another_edit_during_model_call_is_not_overwritten(client, monkeypatch):
    task_id = seed(client)
    async def competing_edit(*_):
        with db_session.SessionLocal() as db:
            task = tasks.get_task(db, task_id)
            reports.save(db, task, "# 已确认的新稿", reason="rewrite", expected_version=1)
        return "# 较早请求的模型结果"
    monkeypatch.setattr(tasks, "chat_completion", competing_edit)
    response = client.post(f"/api/tasks/{task_id}/rewrite", json={"instruction": "改写全文", "expected_version": 1})
    assert response.status_code == 409
    current = client.get(f"/api/tasks/{task_id}/report").json()
    assert current["version"] == 2
    assert current["markdown"] == "# 已确认的新稿"


def test_bad_section_output_does_not_change_original(client, monkeypatch):
    task_id = seed(client)
    section = client.get(f"/api/tasks/{task_id}/report").json()["sections"][0]["id"]
    async def wrong(*_):
        return "## 其他章节\n\n不应该写进来"
    monkeypatch.setattr(tasks, "chat_completion", wrong)
    response = client.post(f"/api/tasks/{task_id}/rewrite", json={"instruction": "改短", "scope": "section", "section_id": section, "expected_version": 1})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SECTION_SCOPE_INVALID"
    assert client.get(f"/api/tasks/{task_id}/report").json()["version"] == 1


def test_code_fences_are_not_treated_as_report_sections():
    fence = chr(96) * 3
    markdown = "# 标题\n\n## A\n\n" + fence + "python\n## 这不是章节\nprint(1)\n" + fence + "\n\n## B\n\n原样。\n"
    assert [section["title"] for section in reports.sections(markdown)] == ["A", "B"]
    changed = reports.replace_section(markdown, "section-1", "新正文")
    assert changed.startswith("# 标题\n\n## A\n\n新正文")
    assert changed.endswith("## B\n\n原样。\n")


def test_section_rewrite_cannot_sneak_in_a_new_document_title():
    from app.core.errors import AppError
    import pytest
    with pytest.raises(AppError) as failure:
        reports.replace_section(ORIGINAL, "section-1", "# 新文档\n\n### 小节\n\n越界正文")
    assert failure.value.code == "SECTION_SCOPE_INVALID"


def test_restore_also_restores_matching_data_snapshot(client, tmp_path):
    task_id = seed(client)
    settings = get_settings()
    source = tmp_path / "金额.csv"
    ids = []
    for amount in (300, 999):
        source.write_text(f"地区,金额\nA,{amount}\n", encoding="utf-8")
        ids.append(table_analysis.build_snapshot([{"filename": "金额.csv", "stored_path": str(source)}], settings.artifacts_path / task_id, "金额"))
    with db_session.SessionLocal() as db:
        task = tasks.get_task(db, task_id)
        reports.save(db, task, "# 第一批\n\n300", reason="generated", analysis_id=ids[0])
        reports.save(db, task, "# 第二批\n\n999", reason="generated", analysis_id=ids[1])
    assert client.get(f"/api/tasks/{task_id}/analysis").json()["analysis"]["tables"][0]["metrics"][0]["sum"] == 999
    assert client.post(f"/api/tasks/{task_id}/report/restore", json={"version": 2, "expected_version": 3}).status_code == 200
    restored = client.get(f"/api/tasks/{task_id}/analysis").json()["analysis"]
    assert restored["id"] == ids[0]
    assert restored["tables"][0]["metrics"][0]["sum"] == 300


def test_old_reports_get_initial_version_without_losing_content(client):
    task_id = client.post("/api/tasks", json={"model_id": "mock", "prompt": "旧报告"}).json()["id"]
    with db_session.SessionLocal() as db:
        task = tasks.get_task(db, task_id)
        task.status = "succeeded"
        path = get_settings().artifacts_path / task_id / "report.md"
        path.parent.mkdir(parents=True)
        path.write_text(ORIGINAL, encoding="utf-8")
        task.report_path = str(path)
        db.commit()
    result = client.get(f"/api/tasks/{task_id}/report").json()
    assert result["version"] == 1
    assert result["markdown"] == ORIGINAL
    assert client.get(f"/api/tasks/{task_id}/report/versions").json()["items"][0]["reason"] == "legacy"
