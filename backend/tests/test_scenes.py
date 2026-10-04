from __future__ import annotations

import io
from pathlib import Path

from openpyxl import Workbook

from app.services.catalog import clear_catalog_cache

clear_catalog_cache()


def test_list_scenes(client):
    r = client.get("/api/scenes")
    assert r.status_code == 200
    items = r.json()["items"]
    ids = {x["id"] for x in items}
    assert {
        "competitor_research",
        "meeting_minutes",
        "weekly_report",
        "email_draft",
        "proposal_template",
        "table_analysis",
        "policy_brief",
        "customer_reply",
        "project_update",
        "speech_script",
        "event_retro",
        "internal_notice",
    } <= ids


def test_list_experts_and_skills_expanded(client):
    skills = client.get("/api/skills").json()["items"]
    experts = client.get("/api/experts").json()["items"]
    skill_ids = {x["id"] for x in skills}
    expert_ids = {x["id"] for x in experts}
    assert {
        "policy_brief",
        "customer_reply",
        "project_update",
        "speech_script",
        "event_retro",
        "internal_notice",
    } <= skill_ids
    assert {
        "policy_reader",
        "customer_voice",
        "project_coordinator",
        "speech_coach",
        "retro_facilitator",
        "notice_writer",
    } <= expert_ids
    for row in skills:
        assert row.get("strength")
        assert row.get("best_for")
        assert row.get("output_shape")
    for row in experts:
        assert row.get("strength")
        assert row.get("best_for")
        assert row.get("output_shape")


def test_detect_scene_policy(client):
    r = client.post("/api/scenes/detect", json={"prompt": "帮我做一份新规政策速读，说明适用谁和关键变化"})
    assert r.status_code == 200
    assert r.json()["scene_id"] == "policy_brief"


def test_policy_skill_plan(client):
    r = client.post(
        "/api/tasks",
        json={"model_id": "mock",
            "prompt": "解读某地数据保护新规对业务的影响",
            "urls": [],
            "skill_id": "policy_brief",
            "expert_id": "policy_reader",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "plan_ready"
    assert body["skill_id"] == "policy_brief"
    assert "政策" in (body["title"] or "") or any("政策" in s["name"] for s in body["steps"])


def test_detect_scene_weekly(client):
    r = client.post("/api/scenes/detect", json={"prompt": "帮我写一份本周周报总结"})
    assert r.status_code == 200
    body = r.json()
    assert body["scene_id"] == "weekly_report"
    assert body["skill_id"] == "weekly_report"
    assert body["confidence"] >= 0.5


def test_detect_scene_minutes(client):
    r = client.post("/api/scenes/detect", json={"prompt": "把这段会议记录整理成会议纪要，列出决议和待办"})
    assert r.status_code == 200
    assert r.json()["scene_id"] == "meeting_minutes"


def test_detect_scene_email(client):
    r = client.post("/api/scenes/detect", json={"prompt": "帮我写一封催款邮件稿，语气正式"})
    assert r.status_code == 200
    body = r.json()
    assert body["scene_id"] == "email_draft"
    assert body["skill_id"] == "email_draft"
    assert body["confidence"] >= 0.5


def test_detect_scene_proposal(client):
    r = client.post("/api/scenes/detect", json={"prompt": "按方案模板写一份新产品立项方案"})
    assert r.status_code == 200
    assert r.json()["scene_id"] == "proposal_template"


def test_email_skill_plan(client):
    r = client.post(
        "/api/tasks",
        json={"model_id": "mock",
            "prompt": "写邮件：通知客户下周演示改期",
            "urls": [],
            "skill_id": "email_draft",
            "expert_id": "biz_writer",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "plan_ready"
    assert body["skill_id"] == "email_draft"
    assert "邮件" in (body["title"] or "") or any("邮件" in s["name"] for s in body["steps"])


def test_proposal_skill_plan(client):
    r = client.post(
        "/api/tasks",
        json={"model_id": "mock",
            "prompt": "起草客户成功体系落地的方案模板",
            "urls": [],
            "skill_id": "proposal_template",
            "expert_id": "biz_writer",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "plan_ready"
    assert body["skill_id"] == "proposal_template"
    assert "方案" in (body["title"] or "") or any("方案" in s["name"] for s in body["steps"])


def test_weekly_skill_plan(client):
    r = client.post(
        "/api/tasks",
        json={"model_id": "mock",
            "prompt": "写周报：本周完成登录改版，下周做埋点",
            "urls": [],
            "skill_id": "weekly_report",
            "expert_id": "ops_writer",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "plan_ready"
    assert body["skill_id"] == "weekly_report"
    assert "周报" in (body["title"] or "") or any("周报" in s["name"] for s in body["steps"])


def test_detect_scene_speech_script(client):
    r = client.post(
        "/api/scenes/detect",
        json={"prompt": "帮我写一份汇报发言稿，下周周会上台讲项目进展"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["scene_id"] == "speech_script"
    assert body["skill_id"] == "speech_script"
    assert body["confidence"] >= 0.5


def test_detect_scene_event_retro(client):
    r = client.post(
        "/api/scenes/detect",
        json={"prompt": "写一份活动复盘总结，对照目标和结果"},
    )
    assert r.status_code == 200
    assert r.json()["scene_id"] == "event_retro"


def test_detect_scene_internal_notice(client):
    r = client.post(
        "/api/scenes/detect",
        json={"prompt": "起草一份内部通知公告，告知全员下周办公室搬迁"},
    )
    assert r.status_code == 200
    assert r.json()["scene_id"] == "internal_notice"


def test_speech_script_skill_plan(client):
    r = client.post(
        "/api/tasks",
        json={"model_id": "mock",
            "prompt": "写发言稿：周会口头汇报本周交付",
            "urls": [],
            "skill_id": "speech_script",
            "expert_id": "speech_coach",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "plan_ready"
    assert body["skill_id"] == "speech_script"
    assert "发言" in (body["title"] or "") or any(
        "发言" in s["name"] or "场合" in s["name"] for s in body["steps"]
    )


def test_event_retro_skill_plan(client):
    r = client.post(
        "/api/tasks",
        json={"model_id": "mock",
            "prompt": "活动复盘：春季开放日",
            "urls": [],
            "skill_id": "event_retro",
            "expert_id": "retro_facilitator",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "plan_ready"
    assert body["skill_id"] == "event_retro"
    assert "复盘" in (body["title"] or "") or any(
        "复盘" in s["name"] or "目标" in s["name"] for s in body["steps"]
    )


def test_internal_notice_skill_plan(client):
    r = client.post(
        "/api/tasks",
        json={"model_id": "mock",
            "prompt": "内部通知：下周一提交考勤表",
            "urls": [],
            "skill_id": "internal_notice",
            "expert_id": "notice_writer",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "plan_ready"
    assert body["skill_id"] == "internal_notice"
    assert "通知" in (body["title"] or "") or any(
        "通知" in s["name"] or "对象" in s["name"] for s in body["steps"]
    )


def test_table_analysis_csv_upload(client, tmp_path):
    create = client.post(
        "/api/tasks",
        json={"model_id": "mock",
            "prompt": "基于上传表格分析销售情况",
            "urls": [],
            "skill_id": "table_analysis",
            "expert_id": "data_analyst",
        },
    )
    assert create.status_code == 200
    task_id = create.json()["id"]

    csv_bytes = "商品,销量,金额\nA,10,100\nB,3,30\n".encode("utf-8")
    up = client.post(
        f"/api/tasks/{task_id}/uploads",
        files={"file": ("sales.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert up.status_code == 200
    excerpt = up.json()["text_excerpt"]
    assert "销量" in excerpt
    assert "A" in excerpt

    replan = client.post(f"/api/tasks/{task_id}/replan", json={})
    assert replan.status_code == 200
    assert replan.json()["status"] == "plan_ready"

    client.post(f"/api/tasks/{task_id}/confirm", json={})
    # wait
    import time

    for _ in range(40):
        st = client.get(f"/api/tasks/{task_id}").json()["status"]
        if st in {"succeeded", "failed"}:
            break
        time.sleep(0.15)
    assert client.get(f"/api/tasks/{task_id}").json()["status"] == "succeeded"
    report = client.get(f"/api/tasks/{task_id}/report").json()["markdown"]
    assert "报告" in report or "背景" in report or "数据概览" in report
    assert "图表说明" in report
    plan_steps = create.json()["steps"]
    # replan may change steps; check latest task steps include chart step intent
    latest = client.get(f"/api/tasks/{task_id}").json()
    step_names = " ".join(s["name"] for s in latest.get("steps") or plan_steps)
    assert "图表" in step_names or "图表说明" in report


def test_xlsx_text_extract(tmp_path):
    from app.services.files import extract_xlsx_text

    wb = Workbook()
    ws = wb.active
    ws.append(["地区", "营收"])
    ws.append(["华东", 12])
    ws.append(["华北", 8])
    path = Path(tmp_path) / "t.xlsx"
    wb.save(path)
    text = extract_xlsx_text(path)
    assert "华东" in text
    assert "营收" in text
