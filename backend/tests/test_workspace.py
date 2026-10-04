from __future__ import annotations

from pathlib import Path


def test_workspace_not_set(client):
    r = client.get("/api/workspace/entries")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "WORKSPACE_NOT_SET"


def test_workspace_set_list_deny_export(client, tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "note.txt").write_text("工作区笔记：份额上升", encoding="utf-8")
    (root / "report.md").write_text("# old export", encoding="utf-8")
    (root / "sales.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    bad = client.put("/api/workspace", json={"root": str(tmp_path / "missing")})
    assert bad.status_code == 400

    ok = client.put("/api/workspace", json={"root": str(root)})
    assert ok.status_code == 200
    assert ok.json()["configured"] is True

    entries = client.get("/api/workspace/entries").json()["items"]
    names = {i["name"] for i in entries}
    assert "note.txt" in names
    assert "sales.csv" in names
    assert "report.md" not in names  # 成品报告不在资料库列表
    assert all("mtime" in i for i in entries)

    denied = client.get("/api/workspace/file", params={"rel": "../outside.txt"})
    assert denied.status_code == 400
    assert denied.json()["error"]["code"] == "PATH_DENIED"

    preview = client.get("/api/workspace/file", params={"rel": "note.txt"}).json()
    assert "份额上升" in preview["content"]

    r = client.post("/api/tasks", json={"model_id": "mock", "prompt": "结合工作区", "urls": []})
    task_id = r.json()["id"]
    client.post(f"/api/tasks/{task_id}/confirm", json={})
    import time

    for _ in range(50):
        detail = client.get(f"/api/tasks/{task_id}").json()
        if detail["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.1)
    assert detail["status"] == "succeeded"

    disabled = client.post(
        "/api/workspace/export",
        json={"task_id": task_id, "formats": ["md", "docx", "xlsx", "pptx"], "confirm": True},
    )
    assert disabled.status_code == 400
    assert disabled.json()["error"]["code"] == "WORKSPACE_EXPORT_DISABLED"
    assert not (root / "report.docx").exists()


def test_workspace_refs_attach(client, tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "brief.md").write_text("# 简报\n份额上升明显", encoding="utf-8")
    assert client.put("/api/workspace", json={"root": str(root)}).status_code == 200

    r = client.post("/api/tasks", json={"model_id": "mock", "prompt": "读工作区简报", "urls": []})
    task_id = r.json()["id"]
    assert r.json()["status"] == "plan_ready"

    attached = client.post(
        f"/api/tasks/{task_id}/workspace-refs",
        json={"paths": ["brief.md"]},
    )
    assert attached.status_code == 200
    uploads = attached.json()["uploads"]
    assert len(uploads) == 1
    assert uploads[0]["filename"] == "brief.md"
    assert "份额上升" in (uploads[0].get("text_excerpt") or "")

    # escape denied
    denied = client.post(
        f"/api/tasks/{task_id}/workspace-refs",
        json={"paths": ["../outside.md"]},
    )
    assert denied.status_code == 400
    assert denied.json()["error"]["code"] in {"PATH_DENIED", "FILE_NOT_FOUND", "VALIDATION_ERROR"}


def test_workspace_upload_table_and_list_xlsx(client, tmp_path):
    import io

    root = tmp_path / "ws"
    root.mkdir()
    assert client.put("/api/workspace", json={"root": str(root)}).status_code == 200

    csv_bytes = "商品,销量\nA,10\n".encode("utf-8")
    up = client.post(
        "/api/workspace/upload",
        files={"file": ("sales.csv", io.BytesIO(csv_bytes), "text/csv")},
        data={"rel_dir": ""},
    )
    assert up.status_code == 200
    assert up.json()["rel"] == "sales.csv"
    assert (root / "sales.csv").exists()

    from openpyxl import Workbook

    wb = Workbook()
    wb.active.append(["x", "y"])
    wb.active.append([1, 2])
    xlsx_buf = io.BytesIO()
    wb.save(xlsx_buf)
    xlsx_buf.seek(0)
    up2 = client.post(
        "/api/workspace/upload",
        files={
            "file": (
                "sheet.xlsx",
                xlsx_buf,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={"rel_dir": ""},
    )
    assert up2.status_code == 200
    assert up2.json()["rel"] == "sheet.xlsx"

    entries = client.get("/api/workspace/entries").json()["items"]
    names = {i["name"] for i in entries}
    assert "sales.csv" in names
    assert "sheet.xlsx" in names

    bad = client.post(
        "/api/workspace/upload",
        files={"file": ("note.txt", io.BytesIO(b"hi"), "text/plain")},
        data={"rel_dir": ""},
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "UPLOAD_TYPE_NOT_ALLOWED"


def test_execute_default_skips_workspace_dump(client, tmp_path, monkeypatch):
    """执行默认不得把资料库全文塞进成稿上下文；无关材料不得带偏。"""
    import time

    root = tmp_path / "ws"
    root.mkdir()
    marker = "UNIQUE_WS_MARKER_HYDROGEN_PRD_SHOULD_NOT_LEAK"
    (root / "unrelated_prd.md").write_text(
        f"# 氢能可研无关材料\n{marker}\n", encoding="utf-8"
    )
    assert client.put("/api/workspace", json={"root": str(root)}).status_code == 200

    captured: dict = {}

    async def capture_write(settings, task, search_bits):
        captured["bits"] = list(search_bits)
        return "# 周报（测试）\n\n无资料库泄漏。\n"

    monkeypatch.setattr("app.services.tasks._write_report", capture_write)

    r = client.post(
        "/api/tasks",
        json={"model_id": "mock", "prompt": "写一份本周工作周报：完成点验、梳理归档", "urls": []},
    )
    assert r.status_code == 200
    task_id = r.json()["id"]
    assert client.post(f"/api/tasks/{task_id}/confirm", json={}).status_code == 200

    detail = None
    for _ in range(80):
        detail = client.get(f"/api/tasks/{task_id}").json()
        if detail["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.05)
    assert detail is not None
    assert detail["status"] == "succeeded", detail
    assert "bits" in captured
    blob = "\n".join(captured["bits"])
    assert marker not in blob
    assert "本地资料库材料" not in blob
    assert "unrelated_prd" not in blob
    assert "用户添加的参考材料" not in blob


def test_execute_with_workspace_refs_still_uses_them(client, tmp_path, monkeypatch):
    """主动从资料库添加参考后，摘录应进入成稿上下文。"""
    import time

    root = tmp_path / "ws"
    root.mkdir()
    marker = "UNIQUE_WS_MARKER_BRIEF_SHOULD_APPEAR"
    (root / "brief.md").write_text(f"# 简报\n{marker}\n份额上升\n", encoding="utf-8")
    (root / "noise.md").write_text("# 噪音\nOTHER_NOISE_FILE\n", encoding="utf-8")
    assert client.put("/api/workspace", json={"root": str(root)}).status_code == 200

    captured: dict = {}

    async def capture_write(settings, task, search_bits):
        captured["bits"] = list(search_bits)
        return "# 报告（测试）\n\n含参考。\n"

    monkeypatch.setattr("app.services.tasks._write_report", capture_write)

    r = client.post("/api/tasks", json={"model_id": "mock", "prompt": "根据简报写要点", "urls": []})
    task_id = r.json()["id"]
    attached = client.post(
        f"/api/tasks/{task_id}/workspace-refs",
        json={"paths": ["brief.md"]},
    )
    assert attached.status_code == 200
    assert client.post(f"/api/tasks/{task_id}/confirm", json={}).status_code == 200

    detail = None
    for _ in range(80):
        detail = client.get(f"/api/tasks/{task_id}").json()
        if detail["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.05)
    assert detail is not None
    assert detail["status"] == "succeeded", detail
    assert "bits" in captured
    blob = "\n".join(captured["bits"])
    assert marker in blob
    # 未勾选的噪音文件不应因默认灌库出现
    assert "OTHER_NOISE_FILE" not in blob
