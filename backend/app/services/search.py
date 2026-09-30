from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings
from app.core.errors import AppError


async def web_search(settings: Settings, query: str, max_results: int = 5) -> list[dict[str, Any]]:
    if settings.search_mock:
        return [
            {
                "title": f"模拟结果：{query[:40]}",
                "url": "https://example.com/office-ai",
                "snippet": "（模拟检索）公开资料摘要，仅用于工程验收。",
            }
        ][:max_results]

    if not settings.tavily_api_key:
        raise AppError(
            "SEARCH_NOT_CONFIGURED",
            "未配置联网检索密钥。请在项目 .env 填写 TAVILY_API_KEY，并确认 SEARCH_MOCK=0 后重启后端。",
            status_code=400,
        )

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": settings.tavily_api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
            },
        )
        resp.raise_for_status()
        data = resp.json()
    results = []
    for item in data.get("results", [])[:max_results]:
        results.append(
            {
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "snippet": item.get("content") or item.get("snippet") or "",
            }
        )
    return results


async def fetch_url_text(url: str, max_chars: int = 6000) -> str:
    if not url.startswith(("http://", "https://")):
        return ""
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            text = resp.text
    except Exception:
        return ""
    # crude strip tags
    import re

    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]
