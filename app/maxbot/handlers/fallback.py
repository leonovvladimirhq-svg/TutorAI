"""Резервные хендлеры — подключаются последними (порт app.bot.handlers.fallback)."""
from __future__ import annotations

from maxapi import F, Router
from maxapi.types import MessageCallback, MessageCreated
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.db import crud
from app.maxbot.common import ack, reply, show_main_menu

router = Router()


@router.message_callback(F.callback.payload.startswith("menu:"))
async def menu_not_ready(event: MessageCallback) -> None:
    """Пункты меню, чьи разделы ещё не подключены."""
    await ack(event, notification=texts.SECTION_SOON)


@router.message_created()
async def any_message(event: MessageCreated, session: AsyncSession) -> None:
    student = await crud.get_student_by_tg(session, event.from_user.user_id)
    if student is None or student.consent_at is None:
        await reply(event, texts.NOT_AUTHED)
        return
    # авторизован, но вне активного сценария — показываем меню
    await show_main_menu(event)
