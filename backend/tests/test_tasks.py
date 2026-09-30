from __future__ import annotations

import time


def _wait_status(client, task_id: str, want: set[str], timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    detail = {}
    while time.time() < deadline:
        detail = client.get(f"/api/tasks/{task_id}").json()
        if detail.get("status") in want:
            return detail
        time.sleep(0.1)
    return detail


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_plan_ready(client):
    r = client.post("/api/tasks", json={"prompt": "调研 AI 办公助手", "urls": []})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "plan_ready"
    assert data["plan"] and len(data["plan"]["steps"]) >= 3


def test_cannot_succeed_without_confirm(client):
    r = client.post("/api/tasks", json={"prompt": "调研", "urls": []})
    task_id = r.json()["id"]
    detail = client.get(f"/api/tasks/{task_id}").json()
    assert detail["status"] == "plan_ready"
    assert detail["has_report"] is False


def test_confirm_run_report(client):
    r = client.post("/api/tasks", json={"prompt": "调研办公 AI", "urls": []})
    task_id = r.json()["id"]
    r2 = client.post(f"/api/tasks/{task_id}/confirm", json={"confirm_cost": False})
    assert r2.status_code == 200
    detail = _wait_status(client, task_id, {"succeeded", "failed"})
    assert detail["status"] == "succeeded"
    assert detail["has_report"] is True
    report = client.get(f"/api/tasks/{task_id}/report").json()
    assert "背景" in report["markdown"] or "调研" in report["markdown"]


def test_cost_confirm_required(client):
    r = client.post("/api/tasks", json={"prompt": "HIGH_COST 调研", "urls": []})
    task_id = r.json()["id"]
    detail = client.get(f"/api/tasks/{task_id}").json()
    assert detail["cost_estimate_cny"] > 5
    r2 = client.post(f"/api/tasks/{task_id}/confirm", json={"confirm_cost": False})
    assert r2.status_code == 400
    assert r2.json()["error"]["code"] == "COST_CONFIRM_REQUIRED"
    r3 = client.post(f"/api/tasks/{task_id}/confirm", json={"confirm_cost": True})
    assert r3.status_code == 200


def test_upload_reject_and_accept(client):
    r = client.post("/api/tasks", json={"prompt": "带材料调研", "urls": []})
    task_id = r.json()["id"]
    bad = client.post(
        f"/api/tasks/{task_id}/uploads",
        files={"file": ("x.exe", b"abc", "application/octet-stream")},
    )
    assert bad.status_code == 400
    ok = client.post(
        f"/api/tasks/{task_id}/uploads",
        files={"file": ("note.txt", "参考材料：竞品A份额上升".encode("utf-8"), "text/plain")},
    )
    assert ok.status_code == 200
    assert "竞品A" in ok.json()["text_excerpt"]


def test_pause_resume_and_delete(client):
    r = client.post("/api/tasks", json={"prompt": "暂停测试", "urls": []})
    task_id = r.json()["id"]
    client.post(f"/api/tasks/{task_id}/confirm", json={})
    detail = client.get(f"/api/tasks/{task_id}").json()
    if detail["status"] == "running":
        p = client.post(f"/api/tasks/{task_id}/pause")
        assert p.status_code == 200
        assert p.json()["status"] == "paused"
        client.post(f"/api/tasks/{task_id}/resume")
    _wait_status(client, task_id, {"succeeded", "failed", "paused"})
    d = client.delete(f"/api/tasks/{task_id}")
    assert d.status_code == 200
    assert client.get(f"/api/tasks/{task_id}").status_code == 404


def test_sse_ends_with_done(client):
    r = client.post("/api/tasks", json={"prompt": "SSE", "urls": []})
    task_id = r.json()["id"]
    client.post(f"/api/tasks/{task_id}/confirm", json={})
    detail = _wait_status(client, task_id, {"succeeded", "failed"}, timeout=8.0)
    assert detail["status"] == "succeeded"
    chunks: list[str] = []
    with client.stream("GET", f"/api/tasks/{task_id}/events") as resp:
        for line in resp.iter_lines():
            if line:
                chunks.append(line)
            if any("event: done" in c or "event: error" in c for c in chunks):
                break
    text = "\n".join(chunks)
    assert "event: done" in text or "event: error" in text


def test_recover_running_to_paused(client):
    from app.db import session as db_session
    from app.services import tasks as task_service

    r = client.post("/api/tasks", json={"prompt": "恢复", "urls": []})
    task_id = r.json()["id"]
    db = db_session.SessionLocal()
    try:
        task = task_service.get_task(db, task_id)
        task.status = "running"
        db.commit()
        n = task_service.recover_running_tasks(db)
        assert n >= 1
        task = task_service.get_task(db, task_id)
        assert task.status == "paused"
    finally:
        db.close()


def test_docx_export(client):
    r = client.post("/api/tasks", json={"prompt": "导出Word", "urls": []})
    task_id = r.json()["id"]
    assert client.get(f"/api/tasks/{task_id}/report.docx").status_code == 404
    client.post(f"/api/tasks/{task_id}/confirm", json={})
    _wait_status(client, task_id, {"succeeded", "failed"})
    r2 = client.get(f"/api/tasks/{task_id}/report.docx")
    assert r2.status_code == 200
    assert "wordprocessingml" in r2.headers.get("content-type", "")
    assert len(r2.content) > 100
    disp = r2.headers.get("content-disposition", "")
    assert "filename" in disp.lower()
    assert ".docx" in disp
    r3 = client.get(f"/api/tasks/{task_id}/report.docx")
    assert r3.status_code == 200
    assert len(r3.content) == len(r2.content)


def test_report_download_stem_sanitizes():
    from types import SimpleNamespace

    from app.services.tasks import report_download_stem

    assert report_download_stem(SimpleNamespace(title="周报/进度:A*B")) == "周报_进度_A_B"
    assert report_download_stem(SimpleNamespace(title="   ")) == "report"


def test_xlsx_export(client):
    r = client.post("/api/tasks", json={"prompt": "导出表格", "urls": []})
    task_id = r.json()["id"]
    assert client.get(f"/api/tasks/{task_id}/report.xlsx").status_code == 404
    client.post(f"/api/tasks/{task_id}/confirm", json={})
    _wait_status(client, task_id, {"succeeded", "failed"})
    r2 = client.get(f"/api/tasks/{task_id}/report.xlsx")
    assert r2.status_code == 200
    assert "spreadsheetml" in r2.headers.get("content-type", "")
    # xlsx is a zip container
    assert r2.content[:2] == b"PK"
    assert len(r2.content) > 100
    r3 = client.get(f"/api/tasks/{task_id}/report.xlsx")
    assert r3.status_code == 200
    assert len(r3.content) == len(r2.content)


def test_pptx_export(client):
    r = client.post("/api/tasks", json={"prompt": "导出PPT", "urls": []})
    task_id = r.json()["id"]
    assert client.get(f"/api/tasks/{task_id}/report.pptx").status_code == 404
    client.post(f"/api/tasks/{task_id}/confirm", json={})
    _wait_status(client, task_id, {"succeeded", "failed"})
    r2 = client.get(f"/api/tasks/{task_id}/report.pptx")
    assert r2.status_code == 200
    assert "presentationml" in r2.headers.get("content-type", "")
    assert r2.content[:2] == b"PK"
    assert len(r2.content) > 100
    r3 = client.get(f"/api/tasks/{task_id}/report.pptx")
    assert r3.status_code == 200
    assert len(r3.content) == len(r2.content)


def test_replan_and_retry_failed(client):
    r = client.post("/api/tasks", json={"prompt": "初版需求", "urls": []})
    task_id = r.json()["id"]
    assert r.json()["status"] == "plan_ready"

    replanned = client.post(
        f"/api/tasks/{task_id}/replan",
        json={"prompt": "改写后的需求：竞品对比"},
    )
    assert replanned.status_code == 200
    body = replanned.json()
    assert body["status"] == "plan_ready"
    assert "改写后的需求" in body["user_prompt"]
    assert body["plan"] and len(body["plan"]["steps"]) >= 3

    # mark failed then retry
    from app.core.config import get_settings
    from app.db import session as db_session
    from app.db.models import make_engine, make_session_factory
    from app.services import tasks as task_service

    settings = get_settings()
    db_session.engine = make_engine(f"sqlite:///{settings.db_path}")
    db_session.SessionLocal = make_session_factory(db_session.engine)
    db = db_session.SessionLocal()
    try:
        task = task_service.get_task(db, task_id)
        task.status = "failed"
        task.error_code = "MOCK_FAIL"
        task.error_message = "模拟失败"
        db.commit()
    finally:
        db.close()

    detail = client.get(f"/api/tasks/{task_id}").json()
    assert detail["status"] == "failed"

    retried = client.post(f"/api/tasks/{task_id}/confirm", json={"confirm_cost": True})
    assert retried.status_code == 200
    _wait_status(client, task_id, {"succeeded", "failed"})
    assert client.get(f"/api/tasks/{task_id}").json()["status"] == "succeeded"


def test_rewrite_report(client):
    r = client.post("/api/tasks", json={"prompt": "需要重写的报告", "urls": []})
    task_id = r.json()["id"]
    client.post(f"/api/tasks/{task_id}/confirm", json={})
    _wait_status(client, task_id, {"succeeded", "failed"})
    assert client.get(f"/api/tasks/{task_id}").json()["status"] == "succeeded"

    before = client.get(f"/api/tasks/{task_id}/report").json()["markdown"]
    assert "改写指令" not in before

    bad = client.post(f"/api/tasks/{task_id}/rewrite", json={"instruction": ""})
    assert bad.status_code == 422

    done = client.post(
        f"/api/tasks/{task_id}/rewrite",
        json={"instruction": "写得更短一些"},
    )
    assert done.status_code == 200
    after = client.get(f"/api/tasks/{task_id}/report").json()["markdown"]
    assert "已按用户改写指令" in after
    # export caches should regenerate
    assert client.get(f"/api/tasks/{task_id}/report.docx").status_code == 200


def test_export_feishu_mock(client):
    r = client.post("/api/tasks", json={"prompt": "导出飞书报告", "urls": []})
    task_id = r.json()["id"]

    not_ready = client.post(
        f"/api/tasks/{task_id}/export/feishu",
        json={"confirmed": True},
    )
    assert not_ready.status_code == 404
    assert not_ready.json()["error"]["code"] == "REPORT_NOT_READY"

    client.post(f"/api/tasks/{task_id}/confirm", json={})
    _wait_status(client, task_id, {"succeeded", "failed"})
    assert client.get(f"/api/tasks/{task_id}").json()["status"] == "succeeded"

    need_confirm = client.post(
        f"/api/tasks/{task_id}/export/feishu",
        json={"confirmed": False},
    )
    assert need_confirm.status_code == 400
    assert need_confirm.json()["error"]["code"] == "CONFIRM_REQUIRED"

    done = client.post(
        f"/api/tasks/{task_id}/export/feishu",
        json={"confirmed": True},
    )
    assert done.status_code == 200
    body = done.json()
    assert body["mock"] is True
    assert body["document_id"]
    assert "docx" in body["url"]
    # 1.24：未授权时应用兜底
    assert body.get("identity") == "app"
    assert body.get("space") == "app"


def test_feishu_markdown_plain_text():
    from app.services.feishu_export import markdown_to_blocks

    blocks = markdown_to_blocks("# 标题\n\n这是 **加粗** 与 `代码`。")
    assert blocks[0]["block_type"] == 3
    assert blocks[0]["heading1"]["elements"][0]["text_run"]["content"] == "标题"
    assert blocks[1]["block_type"] == 2
    text = blocks[1]["text"]["elements"][0]["text_run"]["content"]
    assert "**" not in text
    assert "`" not in text
    assert "加粗" in text
    assert "代码" in text


def test_merge_tasks(client):
    a = client.post("/api/tasks", json={"prompt": "合并源 A 调研", "urls": []}).json()["id"]
    b = client.post("/api/tasks", json={"prompt": "合并源 B 调研", "urls": []}).json()["id"]
    client.post(f"/api/tasks/{a}/confirm", json={})
    client.post(f"/api/tasks/{b}/confirm", json={})
    _wait_status(client, a, {"succeeded", "failed"})
    _wait_status(client, b, {"succeeded", "failed"})
    assert client.get(f"/api/tasks/{a}").json()["status"] == "succeeded"
    assert client.get(f"/api/tasks/{b}").json()["status"] == "succeeded"

    bad = client.post("/api/tasks/merge", json={"task_ids": [a]})
    assert bad.status_code == 422 or bad.json().get("error", {}).get("code") in {
        "VALIDATION_ERROR",
        None,
    }

    merged = client.post("/api/tasks/merge", json={"task_ids": [a, b]})
    assert merged.status_code == 200, merged.text
    primary = merged.json()
    assert primary["has_report"] is True
    assert primary["id"] in {a, b}
    other_id = b if primary["id"] == a else a
    assert other_id in primary["merged_from_ids"]

    listed = client.get("/api/tasks").json()["items"]
    listed_ids = {t["id"] for t in listed}
    assert primary["id"] in listed_ids
    assert other_id not in listed_ids

    with_merged = client.get("/api/tasks?include_merged=true").json()["items"]
    by_id = {t["id"]: t for t in with_merged}
    assert by_id[other_id]["status"] == "merged"
    assert by_id[other_id]["merged_into_id"] == primary["id"]

    report = client.get(f"/api/tasks/{primary['id']}/report").json()["markdown"]
    assert report.strip()
