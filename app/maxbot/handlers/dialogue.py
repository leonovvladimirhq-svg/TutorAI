"""Коучинговый диалог-профайлинг (порт app.bot.handlers.dialogue под maxapi)."""
from __future__ import annotations

from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.filters import StateFilter
from maxapi.types import MessageCallback, MessageCreated
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.db import crud
from app.domain.profile_schema import PROFILE_BLOCKS_BY_KEY, next_block
from app.maxbot.common import ack, clear_markup, reply, show_main_menu
from app.maxbot.keyboards import candidate_kb
from app.maxbot.states import Profiling
from app.services import profiler
from app.services.events import log_event

router = Router()


async def _send_question(event, session: AsyncSession, student_id: int, block_key: str) -> None:
    block = PROFILE_BLOCKS_BY_KEY[block_key]
    question = await profiler.next_coach_question(session, student_id, block)
    await crud.add_message(session, student_id, "assistant", question)
    await reply(event, question)


async def _start_or_continue(event, session: AsyncSession, context: MemoryContext, student) -> None:
    target = next_block(student.profiling_progress)
    if target is None:
        await reply(event, texts.PROFILING_ALL_DONE)
        await show_main_menu(event)
        return
    await context.set_state(Profiling.chatting)
    await context.set_data({"block": target.key, "turns": 0, "queue": []})
    await reply(event, texts.PROFILING_INTRO)
    await _send_question(event, session, student.id, target.key)


@router.message_callback(F.callback.payload == "menu:profiling")
async def menu_profiling(event: MessageCallback, session: AsyncSession, context: MemoryContext) -> None:
    student = await crud.get_student_by_tg(session, event.from_user.user_id)
    if student is None or student.consent_at is None:
        await ack(event, notification=texts.NOT_AUTHED)
        return
    await ack(event)
    await _start_or_continue(event, session, context, student)


async def _show_next_or_advance(event, session: AsyncSession, context: MemoryContext, student) -> None:
    """Показать следующего кандидата на подтверждение либо продвинуть диалог."""
    data = await context.get_data()
    queue: list[dict] = data.get("queue", [])
    if queue:
        cand = queue[0]
        block = PROFILE_BLOCKS_BY_KEY[cand["block"]]
        await reply(
            event,
            texts.CANDIDATE_PROMPT.format(title=block.title, value=cand["value"]),
            candidate_kb(),
        )
        return
    await _advance(event, session, context, student)


async def _advance(event, session: AsyncSession, context: MemoryContext, student) -> None:
    """Переход к следующему вопросу или завершение блока/профиля."""
    data = await context.get_data()
    block_key: str = data["block"]
    turns: int = data.get("turns", 0) + 1

    if turns >= profiler.MAX_TURNS_PER_BLOCK:
        await crud.set_block_done(session, student, block_key)
        target = next_block(student.profiling_progress)
        if target is None:
            await context.clear()
            await log_event(session, student.id, "profiling_complete", {})
            await reply(event, texts.PROFILING_COMPLETE)
            await show_main_menu(event)
            return
        await context.update_data(block=target.key, turns=0)
        await _send_question(event, session, student.id, target.key)
    else:
        await context.update_data(turns=turns)
        await _send_question(event, session, student.id, block_key)


async def handle_profiling_text(event, session: AsyncSession, context: MemoryContext, text: str) -> None:
    """Обработать реплику студента (из текста или распознанного голоса)."""
    student = await crud.get_student_by_tg(session, event.from_user.user_id)
    if student is None:
        await context.clear()
        await reply(event, texts.NOT_AUTHED)
        return

    data = await context.get_data()

    # режим коррекции ранее извлечённого факта
    correction = data.get("awaiting_correction")
    if correction:
        await crud.upsert_attribute(
            session, student.id, correction["block"], correction["key"],
            text.strip()[:500], correction.get("confidence", 0.7),
            data.get("source_ref"), status="edited",
        )
        await context.update_data(awaiting_correction=None)
        await reply(event, texts.CORRECTION_SAVED)
        await _show_next_or_advance(event, session, context, student)
        return

    # обычный ответ студента
    user_msg = await crud.add_message(session, student.id, "user", text)
    facts = await profiler.extract_facts(text)
    if facts:
        await context.update_data(queue=facts, source_ref=user_msg.id)
    await _show_next_or_advance(event, session, context, student)


@router.message_created(StateFilter(Profiling.chatting))
async def profiling_answer(event: MessageCreated, session: AsyncSession, context: MemoryContext) -> None:
    await handle_profiling_text(event, session, context, event.message.body.text or "")


@router.message_callback(StateFilter(Profiling.chatting), F.callback.payload == "cand:confirm")
async def candidate_confirm(event: MessageCallback, session: AsyncSession, context: MemoryContext) -> None:
    student = await crud.get_student_by_tg(session, event.from_user.user_id)
    if student is None:
        await context.clear()
        await ack(event, notification=texts.NOT_AUTHED)
        return
    data = await context.get_data()
    queue: list[dict] = data.get("queue", [])
    if queue:
        cand = queue.pop(0)
        await crud.upsert_attribute(
            session, student.id, cand["block"], cand["key"], cand["value"],
            cand.get("confidence", 0.7), data.get("source_ref"), status="confirmed",
        )
        await context.update_data(queue=queue)
        await log_event(session, student.id, "attribute_confirmed", {"block": cand["block"], "key": cand["key"]})
    await clear_markup(event)
    await ack(event, notification=texts.CANDIDATE_CONFIRMED)
    await _show_next_or_advance(event, session, context, student)


@router.message_callback(StateFilter(Profiling.chatting), F.callback.payload == "cand:skip")
async def candidate_skip(event: MessageCallback, session: AsyncSession, context: MemoryContext) -> None:
    student = await crud.get_student_by_tg(session, event.from_user.user_id)
    if student is None:
        await context.clear()
        await ack(event, notification=texts.NOT_AUTHED)
        return
    data = await context.get_data()
    queue: list[dict] = data.get("queue", [])
    if queue:
        queue.pop(0)
        await context.update_data(queue=queue)
    await clear_markup(event)
    await ack(event, notification=texts.CANDIDATE_SKIPPED)
    await _show_next_or_advance(event, session, context, student)


@router.message_callback(StateFilter(Profiling.chatting), F.callback.payload == "cand:correct")
async def candidate_correct(event: MessageCallback, context: MemoryContext) -> None:
    data = await context.get_data()
    queue: list[dict] = data.get("queue", [])
    if queue:
        cand = queue.pop(0)
        await context.update_data(queue=queue, awaiting_correction=cand)
    await clear_markup(event)
    await ack(event)
    await reply(event, texts.ASK_CORRECTION)
