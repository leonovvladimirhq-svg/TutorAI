"""Старт, согласие на обработку данных и идентификация по роли (Telegram ID).

Вход основан на реестре ролей (app_user): роль назначает академический руководитель
в веб-панели. Незнакомый Telegram ID — блокируется с подсказкой. Пароли/выбор профиля
больше не используются.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.common import show_main_menu
from app.bot.keyboards import consent_kb, main_menu_kb
from app.db import crud
from app.services import kpi
from app.services.events import log_event
from app.services.roles import ROLE_STUDENT, role_label

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    tg_id = message.from_user.id
    role = await crud.get_role_by_tg(session, tg_id)

    # 1. Роль не назначена — блокируем с подсказкой (показываем Telegram ID).
    if role is None:
        await message.answer(texts.NOT_REGISTERED.format(tg_id=tg_id))
        return

    # 2. Наставник / академический руководитель — только приветствие с ролью.
    if role != ROLE_STUDENT:
        await message.answer(texts.GREETING_ROLE_ONLY.format(role=role_label(role)))
        return

    # 3. Студент — приветствие, при необходимости согласие, затем меню.
    student = await crud.get_student_by_tg(session, tg_id)
    if student is not None and student.consent_at is not None:
        await message.answer(texts.GREETING_STUDENT.format(role=role_label(role)))
        await show_main_menu(message)
        return
    await message.answer(texts.CONSENT, reply_markup=consent_kb())


@router.callback_query(F.data == "consent:decline")
async def consent_decline(callback: CallbackQuery) -> None:
    await callback.message.edit_text(texts.CONSENT_DECLINED)
    await callback.answer()


@router.callback_query(F.data == "consent:accept")
async def consent_accept(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    tg_id = callback.from_user.id
    app_user = await crud.get_app_user_by_tg(session, tg_id)
    if app_user is None or app_user.role != ROLE_STUDENT:
        # Роль отозвали, пока висел экран согласия.
        await callback.message.edit_text(texts.NOT_REGISTERED.format(tg_id=tg_id))
        await callback.answer()
        return

    student = await crud.get_or_create_student_by_tg(session, tg_id, app_user.full_name)
    await crud.bind_telegram(session, student, tg_id)  # фиксирует consent_at
    await state.clear()
    await log_event(session, student.id, "auth_success", {"role": app_user.role})
    await callback.message.edit_text(texts.GREETING_STUDENT.format(role=role_label(app_user.role)))
    await callback.answer()
    await show_main_menu(callback.message)


@router.message(Command("menu"))
async def cmd_menu(message: Message, session: AsyncSession, state: FSMContext) -> None:
    role = await crud.get_role_by_tg(session, message.from_user.id)
    if role != ROLE_STUDENT:
        await message.answer(texts.NOT_AUTHED)
        return
    student = await crud.get_student_by_tg(session, message.from_user.id)
    if student is None or student.consent_at is None:
        await message.answer(texts.NOT_AUTHED)
        return
    await state.clear()
    await show_main_menu(message)


@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession) -> None:
    """Сводка KPI (для команды разработки)."""
    data = await kpi.compute(session)
    await message.answer(kpi.format_kpi(data))


@router.callback_query(F.data == "menu:home")
async def menu_home(callback: CallbackQuery) -> None:
    await callback.message.answer(texts.MENU_TITLE, reply_markup=main_menu_kb())
    await callback.answer()
