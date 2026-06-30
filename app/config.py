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
    # Аутентификация — Api-Key сервисного аккаунта (Authorization: Api-Key <key>).
    # Один ключ обслуживает и LLM, и SpeechKit. Приватный SA-ключ (JWT/IAM) в runtime
    # больше не нужен — yc_sa_key_file остаётся только для деплой-инструментов (yc CLI).
    yc_api_key: str = ""
    yc_sa_key_file: str = "/secrets/sa-key.json"
    # ВАЖНО: AI Studio и SpeechKit принимают запросы только в домашнем каталоге SA
    # leonov-deployer (b1gvtru3guuc1oipcs4p). Каталог project5 для AI-вызовов недоступен
    # этому SA (ограничение Яндекса на домашний каталог, роли его не снимают).
    yc_folder_id: str = "b1gvtru3guuc1oipcs4p"
    llm_endpoint: str = "https://llm.api.cloud.yandex.net/v1"
    # qwen3.6-35b-a3b — reasoning-модель: рассуждения в reasoning_content, ответ в content.
    # Из-за «мышления» расходует ~1.5к токенов сверх ответа → max_tokens держим высоким.
    llm_model_uri: str = "gpt://{folder}/qwen3.6-35b-a3b/latest"
    llm_temperature: float = 0.4
    llm_max_tokens: int = 4000

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
