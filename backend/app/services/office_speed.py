"""Office-oriented plan acceleration: write skills skip web search and stay short."""

from __future__ import annotations

from typing import Any

# 写类：靠用户材料/口述成稿，默认不联网（办公加速）
WRITE_SKILL_IDS = frozenset(
    {
        "weekly_report",
        "meeting_minutes",
        "email_draft",
        "proposal_template",
        "customer_reply",
        "project_update",
        "speech_script",
        "event_retro",
        "internal_notice",
        "table_analysis",
    }
)

# 研类：需要公开检索
RESEARCH_SKILL_IDS = frozenset(
    {
        "competitor_research",
        "industry_brief",
        "meeting_prep",
        "policy_brief",
    }
)

_DEFAULT_WRITE_STEPS = [
    {"name": "理清要点与材料", "goal": "抓住需求与可用输入", "tool_hint": "read_uploads"},
    {"name": "组织可交差结构", "goal": "段落骨架清楚", "tool_hint": "none"},
    {"name": "起草成稿", "goal": "输出可直接用的成品", "tool_hint": "write_report"},
]


def is_write_skill(skill_id: str | None) -> bool:
    return bool(skill_id) and skill_id in WRITE_SKILL_IDS


def is_research_skill(skill_id: str | None) -> bool:
    if not skill_id:
        return True
    return skill_id in RESEARCH_SKILL_IDS


def _is_search_step(step: dict[str, Any]) -> bool:
    hint = (step.get("tool_hint") or "").lower()
    name = step.get("name") or ""
    return "search" in hint or "web_search" in hint or "检索" in name


def _is_write_step(step: dict[str, Any]) -> bool:
    hint = (step.get("tool_hint") or "").lower()
    name = step.get("name") or ""
    return (
        "write" in hint
        or "write_report" in hint
        or "成稿" in name
        or "起草" in name
        or "定稿" in name
    )


def accelerate_plan(plan: dict[str, Any], skill_id: str | None) -> dict[str, Any]:
    """Tighten plans: write skills drop search and cap ~3 steps; research caps ~5."""
    out = dict(plan)
    if skill_id == "table_analysis":
        out["steps"] = [
            {"name": "读取完整表格", "goal": "读取全部文件、工作表和数据行", "tool_hint": "read_uploads"},
            {"name": "计算指标与图表", "goal": "程序计算汇总、分组、月度变化与异常", "tool_hint": "analyze_tables"},
            {"name": "生成分析成品", "goal": "解释真实计算结果并交付报告", "tool_hint": "write_report"},
        ]
        return out
    steps = list(out.get("steps") or [])
    if is_write_skill(skill_id):
        cleaned = [s for s in steps if not _is_search_step(s)]
        if len(cleaned) < 3:
            cleaned = list(_DEFAULT_WRITE_STEPS)
        write_steps = [s for s in cleaned if _is_write_step(s)]
        other = [s for s in cleaned if not _is_write_step(s)]
        if len(cleaned) > 3:
            other = other[:2]
            tail = write_steps[-1:] or [_DEFAULT_WRITE_STEPS[-1]]
            cleaned = other + tail
        if not any(_is_write_step(s) for s in cleaned):
            cleaned = cleaned[:2] + [_DEFAULT_WRITE_STEPS[-1]]
        out["steps"] = cleaned[:4]
        return out

    # research / default: keep one search if present, cap length
    if len(steps) > 5:
        write_steps = [s for s in steps if _is_write_step(s)]
        other = [s for s in steps if not _is_write_step(s)]
        other = other[:4]
        tail = write_steps[-1:] or [
            {"name": "起草报告", "goal": "可交差成稿", "tool_hint": "write_report"}
        ]
        out["steps"] = other + tail
    return out
