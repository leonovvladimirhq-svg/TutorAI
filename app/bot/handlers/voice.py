"""Голосовой ввод: Telegram voice → SpeechKit STT → текущий сценарий диалога."""
from __future__ import annotations

from io import BytesIO

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.handlers import dialogue, goals
from app.bot.states import Goals, Profiling
from app.config import settings
from app.db import crud
from app.services import stt
from app.services.events import log_event

router = Router(name="voice")


@router.message(F.voice)
async def on_voice(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if not settings.enable_voice:
        await message.answer(texts.VOICE_DISABLED)
        return

    student = await crud.get_student_by_tg(session, message.from_user.id)
    if student is None or student.consent_at is None:
        await message.answer(texts.NOT_AUTHED)
        return

    # скачиваем голосовое (OggOpus) и распознаём
    buffer = BytesIO()
    await message.bot.download(message.voice, destination=buffer)
    text = await stt.recognize(buffer.getvalue())

    if not text:
        await message.answer(texts.VOICE_NOT_RECOGNIZED)
        return

    await message.answer(texts.VOICE_RECOGNIZED.format(text=text))
    await log_event(session, student.id, "voice_recognized", {"chars": len(text)})

    # маршрутизируем распознанный текст в текущий сценарий
    current = await state.get_state()
    if current == Profiling.chatting.state:
        await dialogue.handle_profiling_text(message, session, state, text)
    elif current == Goals.chatting.state:
        await goals.handle_goals_text(message, session, state, text)
    else:
        await message.answer(texts.VOICE_NO_CONTEXT)
