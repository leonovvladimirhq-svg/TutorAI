"""Конфигурация приложения из переменных окружения (.env)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: str = "000000:CHANGE_ME"

    # Database
    database_url: str = "postgresql+asyncpg://tutorai:change_me@db:5432/tutorai"

    # Yandex Cloud / AI Studio
    yc_sa_key_file: str = "/secrets/sa-key.json"
    yc_folder_id: str = "CHANGE_ME"
    llm_endpoint: str = "https://llm.api.cloud.yandex.net/v1"
    llm_model_uri: str = "gpt://{folder}/qwen3-235b-a22b-fp8/latest"
    llm_temperature: float = 0.4
    llm_max_tokens: int = 2000

    # SpeechKit
    enable_voice: bool = True
    speechkit_stt_url: str = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
    speechkit_lang: str = "ru-RU"

    # App
    log_level: str = "INFO"

    @property
    def model_uri(self) -> str:
        """URI модели с подставленным folder_id."""
        return self.llm_model_uri.replace("{folder}", self.yc_folder_id)


settings = Settings()
