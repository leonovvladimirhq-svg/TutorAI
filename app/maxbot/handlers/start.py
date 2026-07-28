"""Старт, согласие 152-ФЗ и права субъекта ПДн (порт app.bot.handlers.start под maxapi).

Идентификатор пользователя в MAX — event.from_user.user_id. В доменной модели поле
исторически называется telegram_id (используется как generic external id); при полном
переходе на MAX стоит переименовать/обобщить (миграция), пока — переиспользуем как есть.
"""
from __future__ import annotations

from maxapi import F, Router
from maxapi.context import MemoryContext
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
)
from app.services import consent, kpi
from app.services.events import log_event
from app.services.roles import ROLE_STUDENT, role_label

router = Router()


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
        await reply(event, texts.NOT_REGISTERED.format(tg_id=uid))
        return
    if await consent.needs_consent(session, uid):
        await reply(event, texts.CONSENT_INTRO, consent_intro_kb())
        return
    await _route_by_role(event, session, role)


async def _route_by_role(event, session: AsyncSession, role: str) -> None:
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
    else:
        await edit(event, texts.GREETING_ROLE_ONLY.format(role=role_label(app_user.role)))


# --- Меню и служебные команды ----------------------------------------------

@router.message_created(Command("menu"))
async def cmd_menu(event: MessageCreated, session: AsyncSession, context: MemoryContext) -> None:
    uid = event.from_user.user_id
    role = await crud.get_role_by_tg(session, uid)
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
async def cmd_my_data(event: MessageCreated, session: AsyncSession) -> None:
    uid = event.from_user.user_id
    if await crud.get_role_by_tg(session, uid) is None:
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


@router.message_created(Command("forget_me"))
async def cmd_forget_me(event: MessageCreated) -> None:
    await reply(event, texts.FORGET_ME_CONFIRM, forget_me_confirm_kb())


@router.message_callback(F.callback.payload == "forget:yes")
async def forget_yes(event: MessageCallback, session: AsyncSession, context: MemoryContext) -> None:
    uid = event.from_user.user_id
    await consent.record_consent(session, uid, consent.STATUS_REVOKED)
    await crud.forget_me(session, uid)
    await context.clear()
    await edit(event, texts.FORGET_ME_DONE)


@router.message_callback(F.callback.payload == "forget:no")
async def forget_no(event: MessageCallback) -> None:
    await edit(event, texts.FORGET_ME_CANCELLED)
