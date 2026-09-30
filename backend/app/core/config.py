from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_host: str = "127.0.0.1"
    app_port: int = 8040
    frontend_origin: str = "http://127.0.0.1:3040"
    data_dir: str = str(PROJECT_ROOT / "data")

    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_mock: bool = True
    llm_price_per_1k_cny: float = 0.02

    tavily_api_key: str = ""
    search_mock: bool = True

    cost_soft_limit_cny: float = 5.0
    agent_max_steps: int = 12
    task_keep_recent: int = 8
    task_archive_after_days: int = 7
    schedule_run_keep: int = 20
    local_workspace_root: str = ""

    feishu_mock: bool = True
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_folder_token: str = ""
    # Optional tenant doc host, e.g. https://xxx.feishu.cn
    feishu_doc_base_url: str = "https://feishu.cn"
    # 1.23 飞书群通知（密钥仍只用 APP_ID/SECRET；目标群与时机可 env 或 UI 偏好覆盖）
    feishu_notify_chat_id: str = ""
    feishu_notify_on: str = "failed"  # off | failed | always
    # 1.24 用户 OAuth（token 存 data/，不进 env；redirect 默认同本机 APP_HOST:PORT）
    feishu_oauth_redirect_uri: str = "http://127.0.0.1:8040/api/feishu/oauth/callback"
    feishu_oauth_scopes: str = "offline_access docx:document drive:drive"

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir).expanduser().resolve()

    @property
    def db_path(self) -> Path:
        return self.data_path / "office.db"

    @property
    def uploads_path(self) -> Path:
        return self.data_path / "uploads"

    @property
    def artifacts_path(self) -> Path:
        return self.data_path / "artifacts"


@lru_cache
def get_settings() -> Settings:
    return Settings()
