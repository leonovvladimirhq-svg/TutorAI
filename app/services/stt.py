"""Распознавание речи через Yandex SpeechKit (короткое аудио, OggOpus).

Telegram voice — OggOpus, что SpeechKit v1 принимает напрямую.
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def recognize(audio: bytes) -> str:
    """Распознать короткое аудио (<30с, <1МБ). Возвращает текст или пустую строку."""
    params = {
        "topic": "general",
        "lang": settings.speechkit_lang,
        "folderId": settings.yc_folder_id,
    }
    headers = {"Authorization": f"Api-Key {settings.yc_api_key}"}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                settings.speechkit_stt_url, params=params, headers=headers, content=audio
            )
            resp.raise_for_status()
            return resp.json().get("result", "").strip()
    except Exception:  # noqa: BLE001
        logger.exception("Ошибка распознавания речи")
        return ""
