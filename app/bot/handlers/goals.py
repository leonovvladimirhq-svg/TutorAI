"""Постановка целей по SMART с подтверждением и сохранением."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.keyboards import goal_draft_kb, goal_templates_kb, goals_menu_kb
from app.bot.states import Goals
from app.db import crud
from app.services import smart
from app.services.events import log_event

router = Router(name="goals")

_STATUS_RU = {"draft": "черновик", "active": "активна", "done": "достигнута", "dropped": "снята"}


async def _render_goals(message: Message, session: AsyncSession, student_id: int) -> None:
    goals = await crud.list_goals(session, student_id)
    if not goals:
        body = texts.NO_GOALS
    else:
        lines = []
        for g in goals:
            progress = f", прогресс {g.progress}%" if g.progress else ""
            complete = " ✅" if g.is_complete() else ""
            lines.append(
                texts.GOAL_LINE.format(
                    title=g.title, status=_STATUS_RU.get(g.status, g.status),
                    progress=progress, complete=complete,
                )
            )
        body = "\n".join(lines)
    await message.answer(texts.GOALS_HEADER.format(body=body), reply_markup=goals_menu_kb())


async def _make_and_show_draft(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    student_id: int,
    intent: str,
    feedback: str | None = None,
) -> None:
    data = await state.get_data()
    previous = data.get("draft")
    await message.answer(texts.GOAL_DRAFTING)
    draft = await smart.draft_goal(session, student_id, intent, feedback=feedback, previous=previous)
    if not draft:
        await message.answer(texts.GOAL_DRAFT_FAILED)
        return
    await state.set_state(Goals.chatting)
    await state.update_data(intent=intent, draft=draft, awaiting=None)
    await message.answer(texts.GOAL_DRAFT.format(**draft), reply_markup=goal_draft_kb())


@router.callback_query(F.data == "menu:goals")
async def menu_goals(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    student = await crud.get_student_by_tg(session, callback.from_user.id)
    if student is None or student.consent_at is None:
        await callback.answer(texts.NOT_AUTHED, show_alert=True)
        return
    await state.clear()
    await callback.answer()
    await _render_goals(callback.message, session, student.id)


@router.callback_query(F.data == "goals:new")
async def goals_new(callback: CallbackQuery) -> None:
    await callback.message.answer(
        texts.CHOOSE_GOAL_TEMPLATE, reply_markup=goal_templates_kb(smart.DEFAULT_GOALS)
    )
    await callback.answer()


@router.callback_query(F.data == "goalnew:own")
async def goal_own(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Goals.chatting)
    await state.update_data(awaiting="own_title", draft=None, intent=None)
    await callback.message.answer(texts.ASK_OWN_GOAL)
    await callback.answer()


@router.callback_query(F.data.startswith("goalnew:"))
async def goal_template(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    student = await crud.get_student_by_tg(session, callback.from_user.id)
    if student is None:
        await callback.answer(texts.NOT_AUTHED, show_alert=True)
        return
    idx = int(callback.data.split(":", 1)[1])
    template = smart.DEFAULT_GOALS[idx]
    intent = f"{template['title']} ({template['hint']})"
    await callback.answer()
    await _make_and_show_draft(callback.message, session, state, student.id, intent)


@router.message(Goals.chatting)
async def goals_message(message: Message, session: AsyncSession, state: FSMContext) -> None:
    student = await crud.get_student_by_tg(session, message.from_user.id)
    if student is None:
        await state.clear()
        await message.answer(texts.NOT_AUTHED)
        return
    data = await state.get_data()
    awaiting = data.get("awaiting")
    text = (message.text or "").strip()

    if awaiting == "own_title":
        await _make_and_show_draft(message, session, state, student.id, text)
    elif awaiting == "feedback":
        intent = data.get("intent") or text
        await _make_and_show_draft(message, session, state, student.id, intent, feedback=text)


@router.callback_query(Goals.chatting, F.data == "goaldraft:save")
async def goal_save(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    student = await crud.get_student_by_tg(session, callback.from_user.id)
    data = await state.get_data()
    draft = data.get("draft")
    if student is None or not draft:
        await callback.answer()
        return
    missing = smart.validate(draft)
    if missing:
        await state.update_data(awaiting="feedback")
        labels = ", ".join(texts.SMART_LABELS_RU.get(m, m) for m in missing)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer()
        await callback.message.answer(texts.GOAL_INCOMPLETE.format(missing=labels))
        return
    goal = await crud.add_goal(session, student.id, draft, status="active")
    await log_event(session, student.id, "goal_created", {"goal_id": goal.id, "title": goal.title})
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(texts.GOAL_SAVED)
    await callback.message.answer(texts.GOAL_SAVED)
    await _render_goals(callback.message, session, student.id)


@router.callback_query(Goals.chatting, F.data == "goaldraft:edit")
async def goal_edit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(awaiting="feedback")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await callback.message.answer(texts.ASK_GOAL_FEEDBACK)


@router.callback_query(Goals.chatting, F.data == "goaldraft:cancel")
async def goal_cancel(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    student = await crud.get_student_by_tg(session, callback.from_user.id)
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await callback.message.answer(texts.GOAL_CANCELLED)
    if student is not None:
        await _render_goals(callback.message, session, student.id)
