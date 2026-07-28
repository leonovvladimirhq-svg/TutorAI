"""Просмотр и редактирование профиля (порт app.bot.handlers.profile под maxapi)."""
from __future__ import annotations

from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.filters import StateFilter
from maxapi.types import Command, MessageCallback, MessageCreated
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.db import crud
from app.domain.profile_schema import PROFILE_BLOCKS_BY_KEY
from app.maxbot.common import ack, reply
from app.maxbot.keyboards import profile_edit_list_kb, profile_view_kb
from app.maxbot.states import ProfileEdit
from app.services import memory
from app.services.events import log_event

router = Router()

_STATUS_RU = {"draft": "черновик", "active": "активна", "done": "достигнута", "dropped": "снята"}


async def _render_profile(event, session: AsyncSession, student_id: int) -> None:
    attributes = await memory.profile_summary(session, student_id)
    goals = await crud.list_goals(session, student_id)

    if attributes == "(профиль пока пуст)" and not goals:
        await reply(event, texts.PROFILE_EMPTY, profile_view_kb())
        return

    if goals:
        goals_text = "\n".join(f"• {g.title} — {_STATUS_RU.get(g.status, g.status)}" for g in goals)
    else:
        goals_text = texts.PROFILE_NO_GOALS

    await reply(
        event,
        texts.PROFILE_HEADER.format(attributes=attributes, goals=goals_text),
        profile_view_kb(),
    )


@router.message_created(Command("edit_profile"))
async def cmd_edit_profile(event: MessageCreated, session: AsyncSession, context: MemoryContext) -> None:
    student = await crud.get_student_by_tg(session, event.from_user.user_id)
    if student is None or student.consent_at is None:
        await reply(event, texts.NOT_AUTHED)
        return
    await context.clear()
    await _render_profile(event, session, student.id)


@router.message_callback(F.callback.payload == "menu:profile")
async def menu_profile(event: MessageCallback, session: AsyncSession, context: MemoryContext) -> None:
    student = await crud.get_student_by_tg(session, event.from_user.user_id)
    if student is None or student.consent_at is None:
        await ack(event, notification=texts.NOT_AUTHED)
        return
    await context.clear()
    await ack(event)
    await _render_profile(event, session, student.id)


@router.message_callback(F.callback.payload == "profile:edit")
async def profile_edit(event: MessageCallback, session: AsyncSession) -> None:
    student = await crud.get_student_by_tg(session, event.from_user.user_id)
    if student is None:
        await ack(event, notification=texts.NOT_AUTHED)
        return
    attributes = await crud.list_attributes(session, student.id)
    if not attributes:
        await ack(event, notification=texts.NO_ATTRS_TO_EDIT)
        return
    await reply(event, texts.CHOOSE_ATTR_TO_EDIT, profile_edit_list_kb(attributes))
    await ack(event)


@router.message_callback(F.callback.payload.startswith("attredit:"))
async def attr_edit_start(event: MessageCallback, session: AsyncSession, context: MemoryContext) -> None:
    student = await crud.get_student_by_tg(session, event.from_user.user_id)
    attr_id = int(event.callback.payload.split(":", 1)[1])
    attr = await crud.get_attribute(session, attr_id)
    if student is None or attr is None or attr.student_id != student.id:
        await ack(event, notification=texts.NOT_AUTHED)
        return
    await context.set_state(ProfileEdit.waiting_value)
    await context.update_data(attr_id=attr_id)
    title = PROFILE_BLOCKS_BY_KEY[attr.block].title if attr.block in PROFILE_BLOCKS_BY_KEY else attr.block
    await reply(event, texts.ASK_NEW_VALUE.format(title=title, key=attr.key))
    await ack(event)


@router.message_created(StateFilter(ProfileEdit.waiting_value))
async def attr_edit_value(event: MessageCreated, session: AsyncSession, context: MemoryContext) -> None:
    student = await crud.get_student_by_tg(session, event.from_user.user_id)
    data = await context.get_data()
    attr = await crud.get_attribute(session, data.get("attr_id"))
    await context.clear()
    if student is None or attr is None or attr.student_id != student.id:
        await reply(event, texts.NOT_AUTHED)
        return
    await crud.update_attribute_value(session, attr, (event.message.body.text or "").strip())
    await log_event(session, student.id, "attribute_edited", {"attr_id": attr.id})
    await reply(event, texts.ATTR_UPDATED)
    await _render_profile(event, session, student.id)
