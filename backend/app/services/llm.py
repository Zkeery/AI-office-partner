from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import Settings
from app.core.errors import AppError


async def chat_completion(settings: Settings, system: str, user: str) -> str:
    if settings.llm_mock:
        return _mock_reply(system, user)
    if not settings.llm_api_key:
        raise AppError("MODEL_NOT_CONFIGURED", "模型未配置，无法执行任务", status_code=422)

    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.llm_model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"]


def _mock_reply(system: str, user: str) -> str:
    if "[EXECUTION_ANALYSIS]" in system:
        return json.dumps({"summary": "已整理输入与成稿结构（模拟分析，仅用于工程验收）", "findings": ["使用已提供材料", "无来源结论标待核实"]}, ensure_ascii=False)
    if "[SECTION_REWRITE]" in system:
        return "已按指令调整本节表述（模拟）。\n\n- 保留事实与来源，未核实的内容仍标待核实。\n"
    # Report / rewrite prompts also mention「计划」, so detect them first.
    if (
        "调研报告撰写" in system
        or "改写已有 Markdown" in system
        or "输出 Markdown 报告" in system
    ):
        rewrite_note = ""
        if "【改写指令】" in user:
            rewrite_note = "- 已按用户改写指令调整表述（模拟）。\n"
        if "表格分析" in system or "图表说明" in system or "table_analysis" in user:
            return (
                "# 表格分析报告（模拟）\n\n"
                "## 数据概览\n\n"
                f"针对需求：{user[:200]}\n\n"
                "- 本结果由 mock 模型生成，仅用于工程验收。\n"
                f"{rewrite_note}"
                "\n## 关键发现\n\n"
                "- 待核实：需对照上传表内字段复核。\n\n"
                "## 图表说明\n\n"
                "- 建议图型：柱状图（对比分类）或折线图（看趋势）。\n"
                "- 坐标含义：X=分类或时间，Y=表内数值列（以实际上传列为准）。\n"
                "- 读图结论：突出高低差异与异常点；无表数据时标待核实。\n\n"
                "## 异常与待核实\n\n"
                "- 待核实：需配置真实模型后复跑。\n\n"
                "## 建议动作\n\n"
                "- 核对关键列汇总后再做决策。\n"
            )
        if "邮件稿" in system or "email_draft" in user:
            return (
                "# 邮件稿（模拟）\n\n"
                "## 建议主题\n\n"
                "关于协作事项的确认（模拟）\n\n"
                "## 正文\n\n"
                f"针对需求：{user[:200]}\n\n"
                "您好，\n\n"
                "写此邮件是为说明事项要点（模拟）。\n\n"
                "请回复确认下一步。\n\n"
                "此致\n"
                f"{rewrite_note}"
            )
        if "方案模板" in system or "proposal_template" in user:
            return (
                "# 方案（模拟）\n\n"
                "## 背景与问题\n\n"
                f"针对需求：{user[:200]}\n\n"
                "## 目标与成功标准\n\n"
                "- 待核实\n\n"
                "## 方案要点\n\n"
                "- 本结果由 mock 模型生成，仅用于工程验收。\n"
                f"{rewrite_note}"
                "\n## 实施计划\n\n"
                "- 待核实\n\n"
                "## 风险与依赖\n\n"
                "- 待核实\n"
            )
        return (
            "# 调研报告（模拟）\n\n"
            "## 背景\n\n"
            f"针对需求：{user[:200]}\n\n"
            "## 要点\n\n"
            "- 本结果由 mock 模型生成，仅用于工程验收。\n"
            "- 未找到公开来源的信息已标为待核实。\n"
            f"{rewrite_note}"
            "\n## 结论\n\n"
            "待核实：需配置真实模型与检索后复跑。\n\n"
            "## 参考来源\n\n"
            "- （模拟）https://example.com/office-ai\n"
        )

    if "计划" in system or "JSON" in system or "steps" in system.lower():
        import re

        sid_match = re.search(r"skill_id=([a-z0-9_]+)", user)
        skill_key = sid_match.group(1) if sid_match else ""
        # Match skill from user only（system 里的规划说明会带「表格分析」等字样，不能用来判技能）
        blob = f"{skill_key}\n{user}"

        if "table_analysis" in blob:
            plan = {
                "title": "表格分析计划",
                "steps": [
                    {"name": "阅读上传表格", "goal": "提取字段与样例行", "tool_hint": "read_uploads"},
                    {"name": "汇总关键发现与图表说明", "goal": "基于表内数据", "tool_hint": "none"},
                    {"name": "起草分析报告", "goal": "可交差成稿", "tool_hint": "write_report"},
                ],
                "cost_factors": {"estimated_tokens": 3800},
            }
        elif "email_draft" in blob or "邮件稿" in user:
            plan = {
                "title": "邮件稿计划",
                "steps": [
                    {"name": "澄清收件人与目的", "goal": "对象与诉求清楚", "tool_hint": "none"},
                    {"name": "整理要点与边界", "goal": "可发送、不越权", "tool_hint": "read_uploads"},
                    {"name": "定稿邮件", "goal": "正式成稿", "tool_hint": "write_report"},
                ],
                "cost_factors": {"estimated_tokens": 3000},
            }
        elif "proposal_template" in blob or "方案模板" in user:
            plan = {
                "title": "方案模板计划",
                "steps": [
                    {"name": "澄清问题与目标", "goal": "范围可交差", "tool_hint": "none"},
                    {"name": "整理方案与实施风险", "goal": "主路径清晰", "tool_hint": "read_uploads"},
                    {"name": "起草方案", "goal": "书面成稿", "tool_hint": "write_report"},
                ],
                "cost_factors": {"estimated_tokens": 3600},
            }
        elif "weekly_report" in blob or "周报" in user:
            plan = {
                "title": "周报总结计划",
                "steps": [
                    {"name": "整理本周进展与问题", "goal": "完成项可核对", "tool_hint": "read_uploads"},
                    {"name": "列出下周计划", "goal": "可执行下一步", "tool_hint": "none"},
                    {"name": "起草周报", "goal": "可转发成稿", "tool_hint": "write_report"},
                ],
                "cost_factors": {"estimated_tokens": 3200},
            }
        elif "meeting_minutes" in blob or "会议纪要" in user:
            plan = {
                "title": "会议纪要计划",
                "steps": [
                    {"name": "阅读会议笔记/材料", "goal": "还原议题", "tool_hint": "read_uploads"},
                    {"name": "归纳决议与待办", "goal": "可转发", "tool_hint": "none"},
                    {"name": "起草会议纪要", "goal": "正式成稿", "tool_hint": "write_report"},
                ],
                "cost_factors": {"estimated_tokens": 3400},
            }
        elif "competitor_research" in blob or "竞品" in user:
            plan = {
                "title": "竞品调研计划",
                "steps": [
                    {"name": "明确竞品名单", "goal": "锁定对比对象", "tool_hint": "none"},
                    {"name": "联网检索公开资料", "goal": "收集可引用信息", "tool_hint": "web_search"},
                    {"name": "整理对比维度", "goal": "功能/定位/优劣势", "tool_hint": "none"},
                    {"name": "起草竞品调研报告", "goal": "可交差成稿", "tool_hint": "write_report"},
                ],
                "cost_factors": {"estimated_tokens": 4200},
            }
        elif "meeting_prep" in blob or "会议准备" in user:
            plan = {
                "title": "会议准备简报计划",
                "steps": [
                    {"name": "澄清会议目的", "goal": "听众与目标", "tool_hint": "none"},
                    {"name": "检索背景材料", "goal": "公开信息", "tool_hint": "web_search"},
                    {"name": "整理议题与口径", "goal": "可直接念", "tool_hint": "none"},
                    {"name": "起草会议简报", "goal": "短篇幅成稿", "tool_hint": "write_report"},
                ],
                "cost_factors": {"estimated_tokens": 3500},
            }
        elif "industry_brief" in blob or "行业速览" in user:
            plan = {
                "title": "行业速览计划",
                "steps": [
                    {"name": "界定行业范围", "goal": "边界清晰", "tool_hint": "none"},
                    {"name": "检索近期动态", "goal": "公开来源", "tool_hint": "web_search"},
                    {"name": "归纳趋势与风险", "goal": "可汇报要点", "tool_hint": "none"},
                    {"name": "起草行业速览", "goal": "一页成稿", "tool_hint": "write_report"},
                ],
                "cost_factors": {"estimated_tokens": 3800},
            }
        elif "policy_brief" in blob or "政策" in user:
            plan = {
                "title": "政策速读计划",
                "steps": [
                    {"name": "锁定政策主题/原文", "goal": "范围清楚", "tool_hint": "none"},
                    {"name": "检索公开政策信息", "goal": "可引用出处", "tool_hint": "web_search"},
                    {"name": "提炼适用与变化", "goal": "谁受影响、改什么", "tool_hint": "none"},
                    {"name": "起草政策速读", "goal": "可同步成稿", "tool_hint": "write_report"},
                ],
                "cost_factors": {"estimated_tokens": 3600},
            }
        elif "customer_reply" in blob or "对客" in user:
            plan = {
                "title": "对客话术计划",
                "steps": [
                    {"name": "澄清沟通场景与边界", "goal": "诉求清楚、不越权", "tool_hint": "read_uploads"},
                    {"name": "起草主话术与备选", "goal": "可直接使用", "tool_hint": "none"},
                    {"name": "定稿话术", "goal": "成稿可粘贴", "tool_hint": "write_report"},
                ],
                "cost_factors": {"estimated_tokens": 3000},
            }
        elif "project_update" in blob or "项目推进" in user:
            plan = {
                "title": "项目推进计划",
                "steps": [
                    {"name": "整理进度与阻塞", "goal": "可核对", "tool_hint": "read_uploads"},
                    {"name": "给出下一步与决策点", "goal": "可执行", "tool_hint": "none"},
                    {"name": "起草项目短更新", "goal": "可同步成稿", "tool_hint": "write_report"},
                ],
                "cost_factors": {"estimated_tokens": 3200},
            }
        elif "speech_script" in blob or "发言稿" in user or "汇报稿" in user:
            plan = {
                "title": "汇报发言稿计划",
                "steps": [
                    {"name": "澄清场合听众与时长", "goal": "能控场", "tool_hint": "none"},
                    {"name": "整理结论与必提事实", "goal": "可核对", "tool_hint": "read_uploads"},
                    {"name": "起草发言稿", "goal": "可上台念", "tool_hint": "write_report"},
                ],
                "cost_factors": {"estimated_tokens": 3200},
            }
        elif "event_retro" in blob or "复盘" in user:
            plan = {
                "title": "活动复盘计划",
                "steps": [
                    {"name": "对照目标与结果", "goal": "事实清楚", "tool_hint": "read_uploads"},
                    {"name": "归纳亮点问题与改进", "goal": "可执行", "tool_hint": "none"},
                    {"name": "起草复盘", "goal": "可同步成稿", "tool_hint": "write_report"},
                ],
                "cost_factors": {"estimated_tokens": 3200},
            }
        elif "internal_notice" in blob or "通知公告" in user or "内部通知" in user:
            plan = {
                "title": "通知公告计划",
                "steps": [
                    {"name": "澄清对象事项与时间", "goal": "要素齐全", "tool_hint": "read_uploads"},
                    {"name": "整理行动要求", "goal": "少歧义", "tool_hint": "none"},
                    {"name": "起草通知公告", "goal": "可张贴成稿", "tool_hint": "write_report"},
                ],
                "cost_factors": {"estimated_tokens": 2800},
            }
        else:
            plan = {
                "title": "调研报告计划",
                "steps": [
                    {"name": "澄清调研范围", "goal": "明确主题与读者", "tool_hint": "none"},
                    {"name": "联网检索公开资料", "goal": "收集可引用信息", "tool_hint": "web_search"},
                    {"name": "阅读上传材料", "goal": "吸收用户参考", "tool_hint": "read_uploads"},
                    {"name": "起草调研报告", "goal": "输出可交差 Markdown", "tool_hint": "write_report"},
                ],
                "cost_factors": {"estimated_tokens": 4000},
            }
        if "HIGH_COST" in user:
            plan["cost_factors"]["estimated_tokens"] = 500000
        return json.dumps(plan, ensure_ascii=False)

    return (
        "# 调研报告（模拟）\n\n"
        "## 背景\n\n"
        f"针对需求：{user[:200]}\n\n"
        "## 要点\n\n"
        "- 本结果由 mock 模型生成，仅用于工程验收。\n"
        "- 未找到公开来源的信息已标为待核实。\n\n"
        "## 结论\n\n"
        "待核实：需配置真实模型与检索后复跑。\n\n"
        "## 参考来源\n\n"
        "- （模拟）https://example.com/office-ai\n"
    )
