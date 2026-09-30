def test_catalog_lists(client):
    skills = client.get("/api/skills").json()["items"]
    experts = client.get("/api/experts").json()["items"]
    assert len(skills) >= 3
    assert len(experts) >= 2


def test_invalid_skill(client):
    r = client.post(
        "/api/tasks",
        json={"prompt": "测试", "urls": [], "skill_id": "no_such_skill"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "SKILL_NOT_FOUND"


def test_create_with_skill(client):
    r = client.post(
        "/api/tasks",
        json={
            "prompt": "调研钉钉与飞书",
            "urls": [],
            "skill_id": "competitor_research",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["skill_id"] == "competitor_research"
    assert data["status"] == "plan_ready"
    assert data["plan"]["title"] == "竞品调研计划"
    assert any("竞品" in s["name"] for s in data["plan"]["steps"])


def test_create_with_expert_default_skill(client):
    r = client.post(
        "/api/tasks",
        json={"prompt": "明天汇报材料", "urls": [], "expert_id": "briefing_aide"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["expert_id"] == "briefing_aide"
    assert data["skill_id"] == "meeting_minutes"
    assert "会议" in data["plan"]["title"] or any("会议" in s["name"] for s in data["plan"]["steps"])
