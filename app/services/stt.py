"""Распознавание речи через Yandex SpeechKit (короткое аудио).

SpeechKit v1 (stt:recognize) принимает только OggOpus и LPCM. Telegram присылал
OggOpus напрямую; MAX отдаёт голосовые в другом контейнере (по опыту интеграторов —
не oggopus; точный формат зависит от клиента), поэтому:
- определяем контейнер по сигнатуре файла;
- всё, что не OggOpus, перекодируем ffmpeg'ом в OggOpus (моно, 48 кГц) — ffmpeg
  ставится в образ бота (Dockerfile.max);
- при отсутствии ffmpeg честно логируем и пробуем отправить как есть.
"""
from __future__ import annotations

import asyncio
import logging
import shutil

import httpx

from app.config import settings
from app.services.iam import get_iam_token

logger = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 1_000_000  # ограничение SpeechKit v1 на синхронное распознавание


def detect_container(audio: bytes) -> str:
    """Контейнер по сигнатуре: ogg / mp3 / m4a / wav / webm / amr / unknown."""
    head = audio[:16]
    if head.startswith(b"OggS"):
        return "ogg"
    if head.startswith(b"ID3") or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "mp3"
    if head[4:8] == b"ftyp":
        return "m4a"
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return "wav"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"
    if head.startswith(b"#!AMR"):
        return "amr"
    return "unknown"


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


async def to_oggopus(audio: bytes) -> bytes | None:
    """Перекодировать любой контейнер в OggOpus (mono, 48 kHz) через ffmpeg (stdin → stdout)."""
    if not ffmpeg_available():
        logger.warning("ffmpeg не найден — перекодировать аудио не могу")
        return None
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", "pipe:0", "-vn", "-ac", "1", "-ar", "48000",
        "-c:a", "libopus", "-b:a", "32k", "-f", "ogg", "pipe:1",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, err = await asyncio.wait_for(proc.communicate(audio), timeout=60)
    if proc.returncode != 0 or not out:
        logger.error("ffmpeg завершился с кодом %s: %s", proc.returncode, err.decode(errors="replace")[:500])
        return None
    return out


async def recognize(audio: bytes) -> str:
    """Распознать короткое аудио (<30с, <1МБ). Возвращает текст или пустую строку."""
    container = detect_container(audio)
    logger.info("STT: %d байт, контейнер=%s", len(audio), container)
    if container != "ogg":
        converted = await to_oggopus(audio)
        if converted is not None:
            logger.info("STT: перекодировано в OggOpus, %d байт", len(converted))
            audio = converted
    if len(audio) > MAX_AUDIO_BYTES:
        logger.warning("STT: аудио %d байт превышает лимит %d", len(audio), MAX_AUDIO_BYTES)
        return ""

    token = await get_iam_token()
    params = {
        "topic": "general",
        "lang": settings.speechkit_lang,
        "folderId": settings.yc_folder_id,
        "format": "oggopus",
    }
    headers = {"Authorization": f"Bearer {token}"}
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
