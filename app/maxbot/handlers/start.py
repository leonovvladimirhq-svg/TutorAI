"""Старт, вход по коду доступа, согласие 152-ФЗ и права субъекта ПДн (порт под maxapi).

Идентификатор пользователя в MAX — event.from_user.user_id. В доменной модели поле
исторически называется telegram_id (используется как generic external id); при полном
переходе на MAX стоит переименовать/обобщить (миграция), пока — переиспользуем как есть.

Вход: незарегистрированный пользователь вводит 16-значный код доступа (выдаёт
руководитель в веб-панели) и получает роль из кода. Ручное назначение по MAX-ID в
панели тоже работает. /forget_me — полный сброс: данные, регистрация, код освобождается.
"""
from __future__ import annotations

import logging

from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.filters import BaseFilter, StateFilter
from maxapi.types import BotStarted, Command, CommandStart, MessageCallback, MessageCreated
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.db import crud
from app.maxbot.common import ack, edit, reply, show_main_menu
from app.maxbot.keyboards import (
    consent_intro_kb,
    consent_kb,
    forget_me_confirm_kb,
    main_menu_kb,
    mentor_menu_kb,
)
from app.maxbot.states import Registration
from app.services import consent, kpi
from app.services.events import log_event
from app.services.roles import ROLE_MENTOR, ROLE_STUDENT, role_label

logger = logging.getLogger(__name__)
router = Router()


def _text(event) -> str:
    body = getattr(getattr(event, "message", None), "body", None)
    return (getattr(body, "text", None) or "").strip()


def _display_name(event) -> str | None:
    """Имя из профиля MAX — чтобы в панели и отчётах не было голых ID."""
    u = getattr(event, "from_user", None)
    if u is None:
        return None
    name = " ".join(p for p in (getattr(u, "first_name", None), getattr(u, "last_name", None)) if p)
    return name[:128] or None


class LooksLikeCode(BaseFilter):
    """Сообщение — 16 цифр (с пробелами/дефисами). Работает вне состояния: FSM живёт
    в памяти и после перезапуска бота теряется, а код человек всё равно пришлёт."""

    async def __call__(self, event) -> bool:
        if not isinstance(event, MessageCreated):
            return False
        digits = "".join(ch for ch in _text(event) if ch.isdigit())
        stripped = "".join(ch for ch in _text(event) if not ch.isspace() and ch != "-")
        return len(digits) == 16 and stripped.isdigit()


class ForgetMeText(BaseFilter):
    """«Забыть меня» / «forget me» текстом — без слэш-команды."""

    async def __call__(self, event) -> bool:
        if not isinstance(event, MessageCreated):
            return False
        return _text(event).lower().strip("!. ") in texts.FORGET_ME_TRIGGERS


# --- Старт и согласие ------------------------------------------------------

# В MAX первое открытие бота приходит событием bot_started («Вы начали общение
# с ботом»), а не текстовой командой /start. Обрабатываем оба входа одинаково.
@router.bot_started()
async def on_bot_started(event: BotStarted, session: AsyncSession, context: MemoryContext) -> None:
    await _do_start(event, session, context)


@router.message_created(CommandStart())
async def cmd_start(event: MessageCreated, session: AsyncSession, context: MemoryContext) -> None:
    await _do_start(event, session, context)


async def _do_start(event, session: AsyncSession, context: MemoryContext) -> None:
    await context.clear()
    uid = event.from_user.user_id
    role = await crud.get_role_by_tg(session, uid)

    if role is None:
        await context.set_state(Registration.waiting_code)
        await reply(event, texts.NOT_REGISTERED.format(tg_id=uid))
        return
    if await consent.needs_consent(session, uid):
        await reply(event, texts.CONSENT_INTRO, consent_intro_kb())
        return
    await _route_by_role(event, session, role)


async def _route_by_role(event, session: AsyncSession, role: str) -> None:
    if role == ROLE_MENTOR:
        await reply(event, texts.GREETING_MENTOR, mentor_menu_kb())
        return
    if role != ROLE_STUDENT:
        await reply(event, texts.GREETING_ROLE_ONLY.format(role=role_label(role)))
        return
    uid = event.from_user.user_id
    student = await crud.get_or_create_student_by_tg(session, uid)
    if student.consent_at is None:
        await crud.bind_telegram(session, student, uid)
    await reply(event, texts.GREETING_STUDENT.format(role=role_label(role)))
    await show_main_menu(event)


@router.message_callback(F.callback.payload == "consent:read")
async def consent_read(event: MessageCallback) -> None:
    await edit(event, texts.CONSENT_SUMMARY.format(**consent.summary()), consent_kb())


@router.message_callback(F.callback.payload == "consent:fulltext")
async def consent_fulltext(event: MessageCallback) -> None:
    # TODO: перейти на загрузку файла .md через bot.upload_file — пока отдаём текстом.
    with open(consent.CONSENT_DOC_PATH, encoding="utf-8") as f:
        body = f.read()
    await reply(event, texts.CONSENT_FULLTEXT_CAPTION + "\n\n" + body)
    await ack(event)


@router.message_callback(F.callback.payload == "consent:decline")
async def consent_decline(event: MessageCallback, session: AsyncSession) -> None:
    await consent.record_consent(session, event.from_user.user_id, consent.STATUS_DECLINED)
    await edit(event, texts.CONSENT_DECLINED)


@router.message_callback(F.callback.payload == "consent:accept")
async def consent_accept(
    event: MessageCallback, session: AsyncSession, context: MemoryContext
) -> None:
    uid = event.from_user.user_id
    app_user = await crud.get_app_user_by_tg(session, uid)
    if app_user is None:
        await context.set_state(Registration.waiting_code)
        await edit(event, texts.NOT_REGISTERED.format(tg_id=uid))
        return

    await consent.record_consent(session, uid, consent.STATUS_ACCEPTED)
    await context.clear()

    if app_user.role == ROLE_STUDENT:
        student = await crud.get_or_create_student_by_tg(session, uid, app_user.full_name)
        await crud.bind_telegram(session, student, uid)
        await log_event(session, student.id, "auth_success", {"role": app_user.role})
        await edit(event, texts.GREETING_STUDENT.format(role=role_label(app_user.role)))
        await show_main_menu(event)
    elif app_user.role == ROLE_MENTOR:
        await edit(event, texts.GREETING_MENTOR, mentor_menu_kb())
    else:
        await edit(event, texts.GREETING_ROLE_ONLY.format(role=role_label(app_user.role)))


# --- Меню и служебные команды ----------------------------------------------

@router.message_created(Command("menu"))
async def cmd_menu(event: MessageCreated, session: AsyncSession, context: MemoryContext) -> None:
    uid = event.from_user.user_id
    role = await crud.get_role_by_tg(session, uid)
    if role == ROLE_MENTOR:
        await context.clear()
        await reply(event, texts.GREETING_MENTOR, mentor_menu_kb())
        return
    if role != ROLE_STUDENT:
        await reply(event, texts.NOT_AUTHED)
        return
    student = await crud.get_student_by_tg(session, uid)
    if student is None or student.consent_at is None:
        await reply(event, texts.NOT_AUTHED)
        return
    await context.clear()
    await show_main_menu(event)


@router.message_created(Command("stats"))
async def cmd_stats(event: MessageCreated, session: AsyncSession) -> None:
    data = await kpi.compute(session)
    await reply(event, kpi.format_kpi(data))


@router.message_callback(F.callback.payload == "menu:home")
async def menu_home(event: MessageCallback) -> None:
    await reply(event, texts.MENU_TITLE, main_menu_kb())
    await ack(event)


# --- Права субъекта ПДн: /my_data, /forget_me ------------------------------

@router.message_created(Command("my_data"))
async def cmd_my_data(event: MessageCreated, session: AsyncSession, context: MemoryContext) -> None:
    uid = event.from_user.user_id
    if await crud.get_role_by_tg(session, uid) is None:
        await context.set_state(Registration.waiting_code)
        await reply(event, texts.NOT_REGISTERED.format(tg_id=uid))
        return
    data = await crud.collect_my_data(session, uid)
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
    await reply(
        event,
        texts.MY_DATA.format(
            telegram_id=uid,
            role=role_label(data.get("role") or "—"),
            consent=consent_str,
            profile=profile_str,
        ),
    )


# Команда работает в любом состоянии диалога (роутер start — первый в цепочке),
# плюс текстом «забыть меня» — в MAX меню команд не всегда под рукой.
@router.message_created(Command("forget_me"))
@router.message_created(ForgetMeText())
async def cmd_forget_me(event: MessageCreated, session: AsyncSession, context: MemoryContext) -> None:
    uid = event.from_user.user_id
    if await crud.get_role_by_tg(session, uid) is None and await crud.get_student_by_tg(session, uid) is None:
        await reply(event, texts.FORGET_ME_NOTHING)
        return
    await context.clear()
    await reply(event, texts.FORGET_ME_CONFIRM, forget_me_confirm_kb())


@router.message_callback(F.callback.payload == "forget:yes")
async def forget_yes(event: MessageCallback, session: AsyncSession, context: MemoryContext) -> None:
    uid = event.from_user.user_id
    await consent.record_consent(session, uid, consent.STATUS_REVOKED)
    await crud.forget_me(session, uid)
    await context.clear()
    logger.info("forget_me: данные и регистрация MAX-ID %s удалены", uid)
    await edit(event, texts.FORGET_ME_DONE)


@router.message_callback(F.callback.payload == "forget:no")
async def forget_no(event: MessageCallback) -> None:
    await edit(event, texts.FORGET_ME_CANCELLED)


# --- Вход по коду доступа ---------------------------------------------------
# Регистрируется ПОСЛЕ команд: в состоянии «жду код» /start, /menu и /forget_me
# должны отрабатывать своими хендлерами, а не считаться неверным кодом.

@router.message_created(StateFilter(Registration.waiting_code))
@router.message_created(LooksLikeCode())
async def enter_code(event: MessageCreated, session: AsyncSession, context: MemoryContext) -> None:
    uid = event.from_user.user_id
    raw = _text(event)
    existing_role = await crud.get_role_by_tg(session, uid)
    if existing_role is not None:
        await context.clear()
        await reply(event, texts.CODE_ALREADY_REGISTERED.format(role=role_label(existing_role)))
        return
    if raw.startswith("/"):
        return  # команды (/start и т.п.) обрабатываются своими хендлерами
    ac = await crud.get_access_code(session, raw)
    if ac is None:
        await context.set_state(Registration.waiting_code)
        await reply(event, texts.CODE_INVALID)
        return
    if ac.used_by_tg is not None and ac.used_by_tg != uid:
        await context.set_state(Registration.waiting_code)
        await reply(event, texts.CODE_ALREADY_USED)
        return
    app_user = await crud.redeem_access_code(session, ac, uid, _display_name(event))
    logger.info("Код доступа %s активирован: MAX-ID %s → роль %s", ac.label or ac.id, uid, app_user.role)
    await context.clear()
    await reply(event, texts.CODE_ACCEPTED.format(role=role_label(app_user.role)))
    # дальше — как обычный старт: согласие → меню по роли
    if await consent.needs_consent(session, uid):
        await reply(event, texts.CONSENT_INTRO, consent_intro_kb())
        return
    await _route_by_role(event, session, app_user.role)
