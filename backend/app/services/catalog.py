from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.errors import AppError

CATALOG_DIR = Path(__file__).resolve().parents[1] / "catalog"


@lru_cache
def _load_json(name: str) -> list[dict[str, Any]]:
    path = CATALOG_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def clear_catalog_cache() -> None:
    _load_json.cache_clear()


def list_skills() -> list[dict[str, Any]]:
    return list(_load_json("skills.json"))


def list_experts() -> list[dict[str, Any]]:
    return list(_load_json("experts.json"))


def list_scenes() -> list[dict[str, Any]]:
    return list(_load_json("scenes.json"))


def get_skill(skill_id: str) -> dict[str, Any]:
    for item in list_skills():
        if item["id"] == skill_id:
            return item
    raise AppError("SKILL_NOT_FOUND", f"未知技能：{skill_id}", status_code=404)


def get_expert(expert_id: str) -> dict[str, Any]:
    for item in list_experts():
        if item["id"] == expert_id:
            return item
    raise AppError("EXPERT_NOT_FOUND", f"未知专家：{expert_id}", status_code=404)


def get_scene(scene_id: str) -> dict[str, Any]:
    for item in list_scenes():
        if item["id"] == scene_id:
            return item
    raise AppError("SCENE_NOT_FOUND", f"未知场景：{scene_id}", status_code=404)


def resolve_skill_and_expert(
    skill_id: str | None, expert_id: str | None
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    expert = get_expert(expert_id) if expert_id else None
    if skill_id:
        skill = get_skill(skill_id)
    elif expert:
        skill = get_skill(expert["default_skill_id"])
    else:
        skill = None
    return skill, expert


def detect_scene(prompt: str) -> dict[str, Any]:
    """Rule-based scene detection for free-form prompts."""
    text = (prompt or "").strip().lower()
    if not text:
        return {
            "scene_id": None,
            "confidence": 0.0,
            "skill_id": None,
            "expert_id": None,
            "label": None,
            "needs_table_upload": False,
            "reason": "空输入",
        }

    best: dict[str, Any] | None = None
    best_score = 0
    for scene in list_scenes():
        score = 0
        matched: list[str] = []
        for kw in scene.get("keywords") or []:
            k = str(kw).lower()
            if k and k in text:
                score += max(2, len(k) // 2)
                matched.append(str(kw))
        if score > best_score:
            best_score = score
            best = {**scene, "_matched": matched}

    if not best or best_score <= 0:
        return {
            "scene_id": None,
            "confidence": 0.0,
            "skill_id": None,
            "expert_id": None,
            "label": None,
            "needs_table_upload": False,
            "reason": "未匹配到场景关键词",
        }

    # Soft confidence: 1 strong keyword ~0.55, more ~0.9
    confidence = min(0.95, 0.4 + best_score * 0.12)
    return {
        "scene_id": best["id"],
        "confidence": round(confidence, 2),
        "skill_id": best.get("skill_id"),
        "expert_id": best.get("expert_id"),
        "label": best.get("name"),
        "needs_table_upload": bool(best.get("needs_table_upload")),
        "reason": "匹配：" + "、".join(best.get("_matched") or []),
    }


def public_scene(scene: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": scene["id"],
        "name": scene["name"],
        "category": scene.get("category"),
        "blurb": scene.get("blurb") or "",
        "prompt_template": scene.get("prompt_template") or "",
        "skill_id": scene.get("skill_id"),
        "expert_id": scene.get("expert_id"),
        "needs_table_upload": bool(scene.get("needs_table_upload")),
    }
