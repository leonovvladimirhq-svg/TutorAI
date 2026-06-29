"""Просмотр и редактирование профиля в Telegram."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.keyboards import profile_edit_list_kb, profile_view_kb
from app.bot.states import ProfileEdit
from app.db import crud
from app.domain.profile_schema import PROFILE_BLOCKS_BY_KEY
from app.services import memory
from app.services.events import log_event

router = Router(name="profile")

_STATUS_RU = {"draft": "черновик", "active": "активна", "done": "достигнута", "dropped": "снята"}


async def _render_profile(message: Message, session: AsyncSession, student_id: int) -> None:
    attributes = await memory.profile_summary(session, student_id)
    goals = await crud.list_goals(session, student_id)

    if attributes == "(профиль пока пуст)" and not goals:
        await message.answer(texts.PROFILE_EMPTY, reply_markup=profile_view_kb())
        return

    if goals:
        goals_text = "\n".join(
            f"• {g.title} — {_STATUS_RU.get(g.status, g.status)}" for g in goals
        )
    else:
        goals_text = texts.PROFILE_NO_GOALS

    await message.answer(
        texts.PROFILE_HEADER.format(attributes=attributes, goals=goals_text),
        reply_markup=profile_view_kb(),
    )


@router.callback_query(F.data == "menu:profile")
async def menu_profile(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    student = await crud.get_student_by_tg(session, callback.from_user.id)
    if student is None or student.consent_at is None:
        await callback.answer(texts.NOT_AUTHED, show_alert=True)
        return
    await state.clear()
    await callback.answer()
    await _render_profile(callback.message, session, student.id)


@router.callback_query(F.data == "profile:edit")
async def profile_edit(callback: CallbackQuery, session: AsyncSession) -> None:
    student = await crud.get_student_by_tg(session, callback.from_user.id)
    if student is None:
        await callback.answer(texts.NOT_AUTHED, show_alert=True)
        return
    attributes = await crud.list_attributes(session, student.id)
    if not attributes:
        await callback.answer(texts.NO_ATTRS_TO_EDIT, show_alert=True)
        return
    await callback.message.answer(
        texts.CHOOSE_ATTR_TO_EDIT, reply_markup=profile_edit_list_kb(attributes)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("attredit:"))
async def attr_edit_start(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    student = await crud.get_student_by_tg(session, callback.from_user.id)
    attr_id = int(callback.data.split(":", 1)[1])
    attr = await crud.get_attribute(session, attr_id)
    if student is None or attr is None or attr.student_id != student.id:
        await callback.answer(texts.NOT_AUTHED, show_alert=True)
        return
    await state.set_state(ProfileEdit.waiting_value)
    await state.update_data(attr_id=attr_id)
    title = PROFILE_BLOCKS_BY_KEY[attr.block].title if attr.block in PROFILE_BLOCKS_BY_KEY else attr.block
    await callback.message.answer(texts.ASK_NEW_VALUE.format(title=title, key=attr.key))
    await callback.answer()


@router.message(ProfileEdit.waiting_value)
async def attr_edit_value(message: Message, session: AsyncSession, state: FSMContext) -> None:
    student = await crud.get_student_by_tg(session, message.from_user.id)
    data = await state.get_data()
    attr = await crud.get_attribute(session, data.get("attr_id"))
    await state.clear()
    if student is None or attr is None or attr.student_id != student.id:
        await message.answer(texts.NOT_AUTHED)
        return
    await crud.update_attribute_value(session, attr, (message.text or "").strip())
    await log_event(session, student.id, "attribute_edited", {"attr_id": attr.id})
    await message.answer(texts.ATTR_UPDATED)
    await _render_profile(message, session, student.id)
