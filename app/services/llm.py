"""Клиент Qwen через Yandex AI Studio (OpenAI-совместимый endpoint).

Аутентификация — Api-Key сервисного аккаунта (OpenAI SDK шлёт его как `Authorization`).
Модель задаётся URI gpt://<folder>/qwen.../latest.

qwen3.6-35b-a3b — reasoning-модель: цепочка рассуждений приходит в нестандартном поле
reasoning_content, а финальный ответ — в content. Нам нужен только content; рассуждения
игнорируем. Если бюджета max_tokens не хватает, модель «застревает» в рассуждениях и
возвращает content=None (finish_reason=length) — это логируем как предупреждение.
"""
from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

Message = dict[str, str]


def _client() -> AsyncOpenAI:
    # Yandex принимает Api-Key как Bearer-совместимый ключ на OpenAI-эндпоинте.
    return AsyncOpenAI(api_key=settings.yc_api_key, base_url=settings.llm_endpoint)


async def chat(
    messages: list[Message],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """Вызов модели; возвращает текст ответа (content)."""
    client = _client()
    resp = await client.chat.completions.create(
        model=settings.model_uri,
        messages=messages,
        temperature=settings.llm_temperature if temperature is None else temperature,
        max_tokens=settings.llm_max_tokens if max_tokens is None else max_tokens,
    )
    choice = resp.choices[0]
    content = (choice.message.content or "").strip()
    if not content:
        # reasoning-модель не дошла до ответа — почти всегда упёрлась в лимит токенов
        logger.warning(
            "Пустой content от модели (finish_reason=%s). Поднимите max_tokens — "
            "reasoning-модель израсходовала бюджет на рассуждения.",
            choice.finish_reason,
        )
    return content


def extract_json(text: str) -> dict | list | None:
    """Достаёт JSON из ответа модели (на случай обрамляющего текста / ```json блоков)."""
    text = text.strip()
    if text.startswith("```"):
        # срезаем ```json ... ```
        text = text.strip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # ищем JSON-фрагмент; берём тот, чья открывающая скобка встречается раньше
    candidates: list[tuple[int, str]] = []
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            candidates.append((start, text[start : end + 1]))
    for _, fragment in sorted(candidates):
        try:
            return json.loads(fragment)
        except json.JSONDecodeError:
            continue
    return None


async def chat_json(
    messages: list[Message],
    *,
    temperature: float = 0.1,
    max_tokens: int | None = None,
) -> dict | list | None:
    """Вызов модели с ожиданием JSON-ответа; парсит результат."""
    raw = await chat(messages, temperature=temperature, max_tokens=max_tokens)
    parsed = extract_json(raw)
    if parsed is None:
        logger.warning("Не удалось распарсить JSON из ответа модели: %r", raw[:200])
    return parsed
