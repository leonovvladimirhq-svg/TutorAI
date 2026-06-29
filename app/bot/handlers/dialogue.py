"""Коучинговый диалог-профайлинг с подтверждением извлечённых фактов."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.common import show_main_menu
from app.bot.keyboards import candidate_kb
from app.bot.states import Profiling
from app.db import crud
from app.domain.profile_schema import PROFILE_BLOCKS_BY_KEY, next_block
from app.services import profiler
from app.services.events import log_event

router = Router(name="dialogue")


async def _send_question(message: Message, session: AsyncSession, student_id: int, block_key: str) -> None:
    block = PROFILE_BLOCKS_BY_KEY[block_key]
    question = await profiler.next_coach_question(session, student_id, block)
    await crud.add_message(session, student_id, "assistant", question)
    await message.answer(question)


async def _start_or_continue(message: Message, session: AsyncSession, state: FSMContext, student) -> None:
    target = next_block(student.profiling_progress)
    if target is None:
        await message.answer(texts.PROFILING_ALL_DONE)
        await show_main_menu(message)
        return
    await state.set_state(Profiling.chatting)
    await state.set_data({"block": target.key, "turns": 0, "queue": []})
    await message.answer(texts.PROFILING_INTRO)
    await _send_question(message, session, student.id, target.key)


@router.callback_query(F.data == "menu:profiling")
async def menu_profiling(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    student = await crud.get_student_by_tg(session, callback.from_user.id)
    if student is None or student.consent_at is None:
        await callback.answer(texts.NOT_AUTHED, show_alert=True)
        return
    await callback.answer()
    await _start_or_continue(callback.message, session, state, student)


async def _show_next_or_advance(
    message: Message, session: AsyncSession, state: FSMContext, student
) -> None:
    """Показать следующего кандидата на подтверждение либо продвинуть диалог."""
    data = await state.get_data()
    queue: list[dict] = data.get("queue", [])
    if queue:
        cand = queue[0]
        block = PROFILE_BLOCKS_BY_KEY[cand["block"]]
        await message.answer(
            texts.CANDIDATE_PROMPT.format(title=block.title, value=cand["value"]),
            reply_markup=candidate_kb(),
        )
        return
    await _advance(message, session, state, student)


async def _advance(message: Message, session: AsyncSession, state: FSMContext, student) -> None:
    """Переход к следующему вопросу или завершение блока/профиля."""
    data = await state.get_data()
    block_key: str = data["block"]
    turns: int = data.get("turns", 0) + 1

    if turns >= profiler.MAX_TURNS_PER_BLOCK:
        await crud.set_block_done(session, student, block_key)
        target = next_block(student.profiling_progress)
        if target is None:
            await state.clear()
            await log_event(session, student.id, "profiling_complete", {})
            await message.answer(texts.PROFILING_COMPLETE)
            await show_main_menu(message)
            return
        await state.update_data(block=target.key, turns=0)
        await _send_question(message, session, student.id, target.key)
    else:
        await state.update_data(turns=turns)
        await _send_question(message, session, student.id, block_key)


@router.message(Profiling.chatting)
async def profiling_answer(message: Message, session: AsyncSession, state: FSMContext) -> None:
    student = await crud.get_student_by_tg(session, message.from_user.id)
    if student is None:
        await state.clear()
        await message.answer(texts.NOT_AUTHED)
        return

    data = await state.get_data()

    # режим коррекции ранее извлечённого факта
    correction = data.get("awaiting_correction")
    if correction:
        await crud.upsert_attribute(
            session,
            student.id,
            correction["block"],
            correction["key"],
            (message.text or "").strip()[:500],
            correction.get("confidence", 0.7),
            data.get("source_ref"),
            status="edited",
        )
        await state.update_data(awaiting_correction=None)
        await message.answer(texts.CORRECTION_SAVED)
        await _show_next_or_advance(message, session, state, student)
        return

    # обычный ответ студента
    user_msg = await crud.add_message(session, student.id, "user", message.text or "")
    facts = await profiler.extract_facts(message.text or "")
    if facts:
        await state.update_data(queue=facts, source_ref=user_msg.id)
    await _show_next_or_advance(message, session, state, student)


@router.callback_query(Profiling.chatting, F.data == "cand:confirm")
async def candidate_confirm(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    student = await crud.get_student_by_tg(session, callback.from_user.id)
    if student is None:
        await state.clear()
        await callback.answer(texts.NOT_AUTHED, show_alert=True)
        return
    data = await state.get_data()
    queue: list[dict] = data.get("queue", [])
    if queue:
        cand = queue.pop(0)
        await crud.upsert_attribute(
            session, student.id, cand["block"], cand["key"], cand["value"],
            cand.get("confidence", 0.7), data.get("source_ref"), status="confirmed",
        )
        await state.update_data(queue=queue)
        await log_event(session, student.id, "attribute_confirmed", {"block": cand["block"], "key": cand["key"]})
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(texts.CANDIDATE_CONFIRMED)
    await _show_next_or_advance(callback.message, session, state, student)


@router.callback_query(Profiling.chatting, F.data == "cand:skip")
async def candidate_skip(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    student = await crud.get_student_by_tg(session, callback.from_user.id)
    if student is None:
        await state.clear()
        await callback.answer(texts.NOT_AUTHED, show_alert=True)
        return
    data = await state.get_data()
    queue: list[dict] = data.get("queue", [])
    if queue:
        queue.pop(0)
        await state.update_data(queue=queue)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(texts.CANDIDATE_SKIPPED)
    await _show_next_or_advance(callback.message, session, state, student)


@router.callback_query(Profiling.chatting, F.data == "cand:correct")
async def candidate_correct(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    queue: list[dict] = data.get("queue", [])
    if queue:
        cand = queue.pop(0)
        await state.update_data(queue=queue, awaiting_correction=cand)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await callback.message.answer(texts.ASK_CORRECTION)
