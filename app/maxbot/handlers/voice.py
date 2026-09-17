"""Голосовой ввод: MAX audio → текст → текущий сценарий диалога.

Порт app.bot.handlers.voice под maxapi. Отличия от Telegram:
- голос приходит как вложение type=AUDIO в message.body.attachments (нет F.voice),
  текста в сообщении нет — поэтому роутер voice стоит ДО текстовых state-хендлеров;
- у вложения может быть готовая транскрипция (поле transcription в Bot API MAX) —
  тогда SpeechKit не нужен;
- иначе скачиваем по payload.url через bot.download_bytes и отдаём в SpeechKit;
  контейнер MAX отличается от Telegram OggOpus, перекодирование — в services.stt.
"""
from __future__ import annotations

import logging

from maxapi import Router
from maxapi.context import MemoryContext
from maxapi.enums import AttachmentType
from maxapi.filters import BaseFilter, StateFilter
from maxapi.types import MessageCreated
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.config import settings
from app.db import crud
from app.maxbot.common import reply
from app.maxbot.handlers import dialogue, goals, reflect
from app.maxbot.states import Goals, Profiling, Reflection
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


def _audio_attachment(event):
    for a in (event.message.body.attachments or []):
        if getattr(a, "type", None) == AttachmentType.AUDIO:
            return a
    return None


async def _transcribe(event, session: AsyncSession) -> str | None:
    """Проверки, транскрипция/скачивание и распознавание. Возвращает текст или None (с ответом юзеру)."""
    if not settings.enable_voice:
        await reply(event, texts.VOICE_DISABLED)
        return None
    student = await crud.get_student_by_tg(session, event.from_user.user_id)
    if student is None or student.consent_at is None:
        await reply(event, texts.NOT_AUTHED)
        return None

    att = _audio_attachment(event)
    payload = getattr(att, "payload", None)
    transcription = (getattr(att, "transcription", None) or "").strip()
    logger.info("MAX audio: payload=%r transcription=%r", payload, transcription[:80] if transcription else None)

    text = transcription
    if not text:
        url = getattr(payload, "url", None)
        if not url:
            logger.warning("MAX voice: URL аудио-вложения не найден")
            await reply(event, texts.VOICE_NOT_RECOGNIZED)
            return None
        audio = await event.bot.download_bytes(url)
        logger.info("MAX voice: скачано %d байт, сигнатура=%r, контейнер=%s",
                    len(audio), audio[:12], stt.detect_container(audio))
        text = await stt.recognize(audio)
    if not text:
        await reply(event, texts.VOICE_NOT_RECOGNIZED)
        return None

    await reply(event, texts.VOICE_RECOGNIZED.format(text=text))
    await log_event(session, student.id, "voice_recognized",
                    {"chars": len(text), "source": "max_transcription" if transcription else "speechkit"})
    return text


# Порядок важен: сначала голос в активных сценариях, потом «вне контекста».
# Роутер voice подключается ДО dialogue/goals/reflect, иначе их текстовые
# state-хендлеры перехватят аудио-сообщение раньше.

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


@router.message_created(StateFilter(Reflection.answering), HasAudio())
async def voice_reflect_answer(event: MessageCreated, session: AsyncSession, context: MemoryContext) -> None:
    text = await _transcribe(event, session)
    if text:
        await reflect.handle_answer_text(event, session, context, text)


@router.message_created(StateFilter(Reflection.irrelevant_note), HasAudio())
async def voice_reflect_irrelevant(event: MessageCreated, session: AsyncSession, context: MemoryContext) -> None:
    text = await _transcribe(event, session)
    if text:
        await reflect.handle_irrelevant_text(event, session, context, text)


@router.message_created(StateFilter(Reflection.patterns), HasAudio())
async def voice_reflect_patterns(event: MessageCreated, session: AsyncSession, context: MemoryContext) -> None:
    text = await _transcribe(event, session)
    if text:
        await reflect.handle_patterns_text(event, session, context, text)


@router.message_created(HasAudio())
async def voice_no_context(event: MessageCreated, session: AsyncSession) -> None:
    text = await _transcribe(event, session)
    if text:
        await reply(event, texts.VOICE_NO_CONTEXT)
