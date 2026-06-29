"""Старт, согласие на обработку данных и авторизация по профилю+паролю."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.common import show_main_menu
from app.bot.keyboards import consent_kb, main_menu_kb, profile_choice_kb
from app.bot.states import Auth
from app.db import crud
from app.services.events import log_event
from app.services.security import verify_password

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    student = await crud.get_student_by_tg(session, message.from_user.id)
    if student is not None and student.consent_at is not None:
        await message.answer(texts.ALREADY_AUTHED.format(label=student.profile_label))
        await show_main_menu(message)
        return
    await message.answer(texts.CONSENT, reply_markup=consent_kb())


@router.callback_query(F.data == "consent:decline")
async def consent_decline(callback: CallbackQuery) -> None:
    await callback.message.edit_text(texts.CONSENT_DECLINED)
    await callback.answer()


@router.callback_query(F.data == "consent:accept")
async def consent_accept(callback: CallbackQuery, session: AsyncSession) -> None:
    profiles = await crud.list_profiles(session)
    await callback.message.edit_text(
        texts.CHOOSE_PROFILE, reply_markup=profile_choice_kb(profiles)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("profile:"))
async def profile_chosen(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    student_id = int(callback.data.split(":", 1)[1])
    student = await crud.get_student(session, student_id)
    if student is None:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    await state.set_state(Auth.waiting_password)
    await state.update_data(student_id=student_id)
    await callback.message.edit_text(texts.ASK_PASSWORD.format(label=student.profile_label))
    await callback.answer()


@router.message(Auth.waiting_password)
async def check_password(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    student = await crud.get_student(session, data["student_id"])
    if student is None:
        await state.clear()
        await message.answer(texts.NOT_AUTHED)
        return

    if not verify_password(message.text or "", student.password_hash):
        await message.answer(texts.WRONG_PASSWORD)
        return

    await crud.bind_telegram(session, student, message.from_user.id)
    await state.clear()
    await log_event(session, student.id, "auth_success", {"label": student.profile_label})
    await message.answer(texts.AUTH_SUCCESS.format(label=student.profile_label))
    await show_main_menu(message)


@router.message(Command("menu"))
async def cmd_menu(message: Message, session: AsyncSession, state: FSMContext) -> None:
    student = await crud.get_student_by_tg(session, message.from_user.id)
    if student is None or student.consent_at is None:
        await message.answer(texts.NOT_AUTHED)
        return
    await state.clear()
    await show_main_menu(message)


@router.callback_query(F.data == "menu:home")
async def menu_home(callback: CallbackQuery) -> None:
    await callback.message.answer(texts.MENU_TITLE, reply_markup=main_menu_kb())
    await callback.answer()
