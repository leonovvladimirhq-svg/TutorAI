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
    # Прокси до Telegram API: из сети Yandex Cloud api.telegram.org недоступен,
    # поэтому бот ходит через прокси. Пусто — идём напрямую (локальная разработка).
    # Формат: socks5://user:pass@host:1080 либо http://user:pass@host:3128
    telegram_proxy: str = ""

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

    # Веб-панель академического руководителя (управление ролями)
    web_admin_user: str = "academ"
    web_admin_password: str = "ABCD"
    web_session_secret: str = "change-me-please-web-secret"
    web_port: int = 8080

    # Оператор ПДн (152-ФЗ) — плейсхолдеры, точные реквизиты заполняются перед запуском.
    operator_name: str = "Школа коммуникаций НИУ ВШЭ"
    operator_email: str = ""  # e-mail ответственного за обработку ПДн (заполнить позже)
    data_storage: str = "Yandex Cloud, ru-central1 (РФ, УЗ-1)"

    # App
    log_level: str = "INFO"

    @property
    def model_uri(self) -> str:
        """URI модели с подставленным folder_id."""
        return self.llm_model_uri.replace("{folder}", self.yc_folder_id)


settings = Settings()
