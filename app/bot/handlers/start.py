"""Старт, согласие на обработку данных (152-ФЗ) и права субъекта ПДн.

Вход основан на реестре ролей (app_user): роль назначается в веб-панели.
Согласие берётся со всех ролей (двухэкранный флоу) и версионируется
(см. app.services.consent). Команды прав субъекта: /my_data, /edit_profile, /forget_me.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.common import show_main_menu
from app.bot.handlers.profile import _render_profile
from app.bot.keyboards import (
    consent_intro_kb,
    consent_kb,
    forget_me_confirm_kb,
    main_menu_kb,
)
from app.db import crud
from app.services import consent, kpi
from app.services.events import log_event
from app.services.roles import ROLE_STUDENT, role_label

router = Router(name="start")


# --- Старт и согласие ------------------------------------------------------

@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    tg_id = message.from_user.id
    role = await crud.get_role_by_tg(session, tg_id)

    # 1. Роль не назначена — блокируем с подсказкой (показываем Telegram ID).
    if role is None:
        await message.answer(texts.NOT_REGISTERED.format(tg_id=tg_id))
        return

    # 2. Нет актуального согласия — показываем экран 1 (интро + «Прочитать согласие»).
    if await consent.needs_consent(session, tg_id):
        await message.answer(texts.CONSENT_INTRO, reply_markup=consent_intro_kb())
        return

    # 3. Согласие есть — маршрутизируем по роли.
    await _route_by_role(message, session, role)


async def _route_by_role(message: Message, session: AsyncSession, role: str) -> None:
    """После согласия: студенту — меню, остальным ролям — приветствие."""
    if role != ROLE_STUDENT:
        await message.answer(texts.GREETING_ROLE_ONLY.format(role=role_label(role)))
        return
    student = await crud.get_or_create_student_by_tg(session, message.from_user.id)
    if student.consent_at is None:
        await crud.bind_telegram(session, student, message.from_user.id)
    await message.answer(texts.GREETING_STUDENT.format(role=role_label(role)))
    await show_main_menu(message)


@router.callback_query(F.data == "consent:read")
async def consent_read(callback: CallbackQuery) -> None:
    """Экран 2: краткое содержание + кнопки (полный текст / согласен / не согласен)."""
    await callback.message.edit_text(
        texts.CONSENT_SUMMARY.format(**consent.summary()), reply_markup=consent_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "consent:fulltext")
async def consent_fulltext(callback: CallbackQuery) -> None:
    """Отправляет полный текст согласия файлом .md (кнопки остаются на месте)."""
    await callback.message.answer_document(
        FSInputFile(consent.CONSENT_DOC_PATH), caption=texts.CONSENT_FULLTEXT_CAPTION
    )
    await callback.answer()


@router.callback_query(F.data == "consent:decline")
async def consent_decline(callback: CallbackQuery, session: AsyncSession) -> None:
    await consent.record_consent(session, callback.from_user.id, consent.STATUS_DECLINED)
    await callback.message.edit_text(texts.CONSENT_DECLINED)
    await callback.answer()


@router.callback_query(F.data == "consent:accept")
async def consent_accept(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    tg_id = callback.from_user.id
    app_user = await crud.get_app_user_by_tg(session, tg_id)
    if app_user is None:
        # Роль отозвали, пока висел экран согласия.
        await callback.message.edit_text(texts.NOT_REGISTERED.format(tg_id=tg_id))
        await callback.answer()
        return

    await consent.record_consent(session, tg_id, consent.STATUS_ACCEPTED)
    await state.clear()

    if app_user.role == ROLE_STUDENT:
        student = await crud.get_or_create_student_by_tg(session, tg_id, app_user.full_name)
        await crud.bind_telegram(session, student, tg_id)  # фиксирует consent_at
        await log_event(session, student.id, "auth_success", {"role": app_user.role})
        await callback.message.edit_text(
            texts.GREETING_STUDENT.format(role=role_label(app_user.role))
        )
        await callback.answer()
        await show_main_menu(callback.message)
    else:
        await callback.message.edit_text(
            texts.GREETING_ROLE_ONLY.format(role=role_label(app_user.role))
        )
        await callback.answer()


# --- Меню и служебные команды ----------------------------------------------

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


# --- Права субъекта ПДн: /my_data, /edit_profile, /forget_me ---------------

@router.message(Command("my_data"))
async def cmd_my_data(message: Message, session: AsyncSession) -> None:
    tg_id = message.from_user.id
    if await crud.get_role_by_tg(session, tg_id) is None:
        await message.answer(texts.NOT_REGISTERED.format(tg_id=tg_id))
        return
    data = await crud.collect_my_data(session, tg_id)
    if data.get("consent_status") == consent.STATUS_ACCEPTED:
        consent_str = f"дано (версия <code>{data.get('consent_version')}</code>)"
    else:
        consent_str = "не дано"
    if data.get("has_profile"):
        profile_str = texts.MY_DATA_PROFILE.format(
            attributes=data.get("attributes_count", 0),
            messages=data.get("messages_count", 0),
            goals=len(data.get("goals", [])),
        )
    else:
        profile_str = texts.MY_DATA_NO_PROFILE
    await message.answer(
        texts.MY_DATA.format(
            telegram_id=tg_id,
            role=role_label(data.get("role") or "—"),
            consent=consent_str,
            profile=profile_str,
        )
    )


@router.message(Command("edit_profile"))
async def cmd_edit_profile(message: Message, session: AsyncSession, state: FSMContext) -> None:
    student = await crud.get_student_by_tg(session, message.from_user.id)
    if student is None or student.consent_at is None:
        await message.answer(texts.NOT_AUTHED)
        return
    await state.clear()
    await _render_profile(message, session, student.id)


@router.message(Command("forget_me"))
async def cmd_forget_me(message: Message) -> None:
    await message.answer(texts.FORGET_ME_CONFIRM, reply_markup=forget_me_confirm_kb())


@router.callback_query(F.data == "forget:yes")
async def forget_yes(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    tg_id = callback.from_user.id
    await consent.record_consent(session, tg_id, consent.STATUS_REVOKED)
    await crud.forget_me(session, tg_id)
    await state.clear()
    await callback.message.edit_text(texts.FORGET_ME_DONE)
    await callback.answer()


@router.callback_query(F.data == "forget:no")
async def forget_no(callback: CallbackQuery) -> None:
    await callback.message.edit_text(texts.FORGET_ME_CANCELLED)
    await callback.answer()
