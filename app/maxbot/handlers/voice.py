"""Голосовой ввод: MAX audio → SpeechKit STT → текущий сценарий диалога.

Порт app.bot.handlers.voice под maxapi. Отличия от Telegram:
- голос приходит как вложение type=AUDIO в message.body.attachments (нет F.voice);
- скачиваем по payload.url через bot.download_bytes.
ВНИМАНИЕ: формат аудио MAX может отличаться от Telegram OggOpus. SpeechKit v1
принимает oggopus/lpcm; если MAX отдаёт mp3/m4a — распознавание не пройдёт.
Логируем размер и сигнатуру файла, чтобы определить формат на живом тесте.
"""
from __future__ import annotations

import logging

from maxapi import Router
from maxapi.context import MemoryContext
from maxapi.enums import AttachmentType
from maxapi.filters import BaseFilter
from maxapi.types import MessageCreated
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.config import settings
from app.db import crud
from app.maxbot.common import reply
from app.maxbot.handlers import dialogue, goals
from app.maxbot.states import Goals, Profiling
from app.services import stt
from app.services.events import log_event

logger = logging.getLogger(__name__)
router = Router()


class HasAudio(BaseFilter):
    """Пропускает только сообщения с аудио-вложением."""

    async def __call__(self, event) -> bool:
        body = getattr(getattr(event, "message", None), "body", None)
        atts = (getattr(body, "attachments", None) or []) if body else []
        return any(getattr(a, "type", None) == AttachmentType.AUDIO for a in atts)


def _audio_url(event) -> str | None:
    for a in (event.message.body.attachments or []):
        if getattr(a, "type", None) == AttachmentType.AUDIO:
            payload = getattr(a, "payload", None)
            logger.info("MAX audio payload: %r", payload)
            return getattr(payload, "url", None)
    return None


async def _transcribe(event, session: AsyncSession) -> str | None:
    """Проверки, скачивание и распознавание. Возвращает текст или None (с ответом юзеру)."""
    if not settings.enable_voice:
        await reply(event, texts.VOICE_DISABLED)
        return None
    student = await crud.get_student_by_tg(session, event.from_user.user_id)
    if student is None or student.consent_at is None:
        await reply(event, texts.NOT_AUTHED)
        return None

    url = _audio_url(event)
    if not url:
        logger.warning("MAX voice: URL аудио-вложения не найден")
        await reply(event, texts.VOICE_NOT_RECOGNIZED)
        return None

    audio = await event.bot.download_bytes(url)
    logger.info("MAX voice: скачано %d байт, сигнатура=%r", len(audio), audio[:8])
    text = await stt.recognize(audio)
    if not text:
        await reply(event, texts.VOICE_NOT_RECOGNIZED)
        return None

    await reply(event, texts.VOICE_RECOGNIZED.format(text=text))
    await log_event(session, student.id, "voice_recognized", {"chars": len(text)})
    return text


# Порядок важен: сначала голос в активных сценариях, потом «вне контекста».
# Роутер voice подключается ДО dialogue/goals, иначе их текстовые state-хендлеры
# перехватят аудио-сообщение раньше.
from maxapi.filters import StateFilter  # noqa: E402


@router.message_created(StateFilter(Profiling.chatting), HasAudio())
async def voice_profiling(event: MessageCreated, session: AsyncSession, context: MemoryContext) -> None:
    text = await _transcribe(event, session)
    if text:
        await dialogue.handle_profiling_text(event, session, context, text)


@router.message_created(StateFilter(Goals.chatting), HasAudio())
async def voice_goals(event: MessageCreated, session: AsyncSession, context: MemoryContext) -> None:
    text = await _transcribe(event, session)
    if text:
        await goals.handle_goals_text(event, session, context, text)


@router.message_created(HasAudio())
async def voice_no_context(event: MessageCreated, session: AsyncSession) -> None:
    text = await _transcribe(event, session)
    if text:
        await reply(event, texts.VOICE_NO_CONTEXT)
