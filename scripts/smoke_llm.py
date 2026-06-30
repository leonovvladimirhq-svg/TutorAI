"""Ручной smoke-тест LLM: шлёт пробный запрос Qwen по Api-Key.

Запуск (после заполнения .env с YC_API_KEY):
    python -m scripts.smoke_llm
"""
from __future__ import annotations

import asyncio

from app.config import settings
from app.services.llm import chat


async def main() -> None:
    print(f"folder_id: {settings.yc_folder_id}")
    print(f"model:     {settings.model_uri}")
    # reasoning-модель тратит ~1.5к токенов на рассуждения до ответа — лимит держим высоким
    reply = await chat(
        [
            {"role": "system", "content": "Ты — ассистент. Отвечай кратко по-русски."},
            {"role": "user", "content": "Скажи одно слово: работает."},
        ],
        max_tokens=2000,
    )
    print(f"ответ модели: {reply!r}")


if __name__ == "__main__":
    asyncio.run(main())
