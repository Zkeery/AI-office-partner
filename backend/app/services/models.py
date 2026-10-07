"""Public model choices and isolated, per-task provider configuration."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from app.core.config import Settings
from app.core.errors import AppError

PROVIDERS = {
    "deepseek": ("DeepSeek", "深度求索"),
    "openai": ("GPT", "OpenAI"),
    "qwen": ("通义千问", "阿里云百炼"),
    "doubao": ("豆包", "火山方舟"),
}


def _legacy_provider(settings: Settings) -> str | None:
    host = urlparse(settings.llm_base_url).hostname or ""
    if host == "api.deepseek.com":
        return "deepseek"
    if host == "api.openai.com":
        return "openai"
    if host in {"dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com"}:
        return "qwen"
    if host == "ark.cn-beijing.volces.com":
        return "doubao"
    return None


def _profile(settings: Settings, model_id: str) -> tuple[str, str, str]:
    key = getattr(settings, f"{model_id}_api_key").strip()
    base = getattr(settings, f"{model_id}_base_url").strip()
    model = getattr(settings, f"{model_id}_model").strip()
    # Existing deployment keeps working without copying its key into another file.
    if not key and not settings.llm_mock and _legacy_provider(settings) == model_id:
        key, base, model = settings.llm_api_key.strip(), settings.llm_base_url.strip(), settings.llm_model.strip()
    return key, base, model


def list_models(settings: Settings) -> list[dict[str, Any]]:
    items = []
    for model_id, (label, provider) in PROVIDERS.items():
        key, base, model = _profile(settings, model_id)
        ready = bool(key and base and model)
        items.append({"id": model_id, "label": label, "provider": provider,
                      "model": model, "available": ready, "status": "configured" if ready else "unconfigured",
                      "hint": "已配置" if ready else "待管理员配置"})
    if settings.llm_mock:
        items.append({"id": "mock", "label": "模拟测试", "provider": "本地",
                      "model": "mock", "available": True, "status": "mock", "hint": "仅工程测试，不调用真实模型"})
    return items


def resolve_model(settings: Settings, model_id: str, model_name: str | None = None) -> Settings:
    if not model_id:
        raise AppError("MODEL_REQUIRED", "请先选择本次任务使用的模型", status_code=422)
    if model_id == "mock" and settings.llm_mock:
        return settings.model_copy(update={"llm_mock": True, "llm_api_key": "", "llm_model": "mock"})
    if model_id not in PROVIDERS:
        raise AppError("MODEL_NOT_FOUND", "所选模型不存在，请重新选择", status_code=422)
    key, base, configured_model = _profile(settings, model_id)
    if not key or not base or not configured_model:
        raise AppError("MODEL_NOT_CONFIGURED", f"{PROVIDERS[model_id][0]} 尚未配置，暂时无法使用", status_code=422)
    return settings.model_copy(update={"llm_mock": False, "llm_api_key": key,
                                       "llm_base_url": base, "llm_model": model_name or configured_model})


def default_model_id(settings: Settings) -> str:
    """Use the administrator's explicit global configuration, never catalog order."""
    if settings.llm_mock:
        return "mock"
    try:
        provider = _legacy_provider(settings)
    except ValueError:
        provider = None
    if provider and all(value.strip() for value in (
        settings.llm_api_key, settings.llm_base_url, settings.llm_model,
    )):
        return provider
    raise AppError(
        "DEFAULT_MODEL_NOT_CONFIGURED",
        "默认模型尚未配置，请联系管理员完成模型接入。",
        status_code=422,
    )


def selection_metadata(settings: Settings, model_id: str | None = None, model_name: str | None = None) -> dict[str, str]:
    if model_id is None:
        model_id = default_model_id(settings)
    resolved = resolve_model(settings, model_id, model_name)
    return {"model_id": model_id, "model_name": resolved.llm_model,
            "model_label": "模拟测试" if model_id == "mock" else PROVIDERS[model_id][0]}


def task_settings(settings: Settings, metadata: dict[str, Any]) -> Settings:
    # Only pre-feature historical records have no selection; never assign them a guessed provider.
    if not metadata.get("model_id"):
        return settings
    return resolve_model(settings, metadata["model_id"], metadata.get("model_name"))
