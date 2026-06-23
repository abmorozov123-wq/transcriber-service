from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "transcriber-service"
    public_base_url: str = "http://localhost:8000"
    data_dir: Path = Path("./data")
    database_url: str = "sqlite:///./data/transcriber.db"

    upload_token: str = Field(default="change-me")
    download_token_secret: str = Field(default="change-me-too")
    max_upload_mb: int = 1024

    telegram_bot_token: str | None = None
    runpod_api_key: str | None = None
    runpod_endpoint_id: str | None = None
    runpod_dummy_mode: bool = True
    auto_submit_runpod: bool = False
    worker_poll_interval_seconds: int = 15

    hf_token: str | None = None
    llm_provider: str = "deepseek"
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"


@lru_cache
def get_settings() -> Settings:
    return Settings()
