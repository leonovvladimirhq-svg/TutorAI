"""Ручной smoke-тест LLM: получает IAM-токен и шлёт пробный запрос Qwen.

Запуск (после заполнения .env и secrets/sa-key.json):
    python -m scripts.smoke_llm
"""
from __future__ import annotations

import asyncio

from app.config import settings
from app.services.llm import chat


async def main() -> None:
    print(f"folder_id: {settings.yc_folder_id}")
    print(f"model:     {settings.model_uri}")
    reply = await chat(
        [
            {"role": "system", "content": "Ты — ассистент. Отвечай кратко по-русски."},
            {"role": "user", "content": "Скажи одно слово: работает."},
        ],
        max_tokens=50,
    )
    print(f"ответ модели: {reply!r}")


if __name__ == "__main__":
    asyncio.run(main())
