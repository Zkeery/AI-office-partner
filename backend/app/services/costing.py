from __future__ import annotations

from typing import Any

from app.core.config import Settings


def estimate_cost_cny(settings: Settings, plan: dict[str, Any]) -> float:
    factors = plan.get("cost_factors") or {}
    tokens = float(factors.get("estimated_tokens") or max(1500, len(plan.get("steps", [])) * 800))
    return round(tokens / 1000.0 * settings.llm_price_per_1k_cny, 4)
