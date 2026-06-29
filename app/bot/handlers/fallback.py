"""Резервные хендлеры — включаются последними."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.db import crud

router = Router(name="fallback")


@router.callback_query(F.data.startswith("menu:"))
async def menu_not_ready(callback: CallbackQuery) -> None:
    """Пункты меню, чьи разделы ещё не подключены."""
    await callback.answer(texts.SECTION_SOON, show_alert=True)


@router.message()
async def any_message(message: Message, session: AsyncSession) -> None:
    student = await crud.get_student_by_tg(session, message.from_user.id)
    if student is None or student.consent_at is None:
        await message.answer(texts.NOT_AUTHED)
