"""Клиент Qwen через Yandex AI Studio (OpenAI-совместимый endpoint).

Аутентификация — IAM-токеном (Bearer). Модель задаётся URI gpt://<folder>/qwen.../latest.
"""
from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from app.config import settings
from app.services.iam import get_iam_token

logger = logging.getLogger(__name__)

Message = dict[str, str]


async def _client() -> AsyncOpenAI:
    token = await get_iam_token()
    return AsyncOpenAI(api_key=token, base_url=settings.llm_endpoint)


async def chat(
    messages: list[Message],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """Вызов модели; возвращает текст ответа."""
    client = await _client()
    resp = await client.chat.completions.create(
        model=settings.model_uri,
        messages=messages,
        temperature=settings.llm_temperature if temperature is None else temperature,
        max_tokens=settings.llm_max_tokens if max_tokens is None else max_tokens,
    )
    return (resp.choices[0].message.content or "").strip()


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
