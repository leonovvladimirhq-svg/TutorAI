"""Обратная связь 👍/👎 + необязательный комментарий (порт app.bot.handlers.feedback)."""
from __future__ import annotations

from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.filters import StateFilter
from maxapi.types import MessageCallback, MessageCreated
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.db import crud
from app.maxbot.common import ack, clear_markup, reply
from app.maxbot.keyboards import feedback_rating_kb, feedback_skip_kb
from app.maxbot.states import Feedback as FeedbackState
from app.services.events import log_event

router = Router()


@router.message_callback(F.callback.payload == "menu:feedback")
async def feedback_from_menu(event: MessageCallback) -> None:
    await reply(event, texts.FEEDBACK_ASK, feedback_rating_kb("menu"))
    await ack(event)


# Порядок важен: fb:skip обрабатывается своим хендлером; общий fb:-хендлер
# дополнительно защищён guard'ом на случай, если диспетчер не остановится на первом.
@router.message_callback(F.callback.payload == "fb:skip")
async def feedback_skip(event: MessageCallback, context: MemoryContext) -> None:
    await context.clear()
    await clear_markup(event)
    await ack(event)
    await reply(event, texts.FEEDBACK_THANKS)


@router.message_callback(F.callback.payload.startswith("fb:"))
async def feedback_rating(event: MessageCallback, session: AsyncSession, context: MemoryContext) -> None:
    payload = event.callback.payload
    if payload == "fb:skip":
        return
    # fb:<up|down>:<context>:<ref_id or ''>
    parts = payload.split(":")
    rating = parts[1] if len(parts) > 1 else "up"
    ctx = parts[2] if len(parts) > 2 else "menu"
    ref_id = int(parts[3]) if len(parts) > 3 and parts[3] else None

    uid = event.from_user.user_id
    student = await crud.get_student_by_tg(session, uid)
    fb = await crud.add_feedback(
        session, telegram_id=uid, rating=rating, context=ctx,
        student_id=student.id if student else None, ref_id=ref_id,
    )
    await log_event(
        session, student.id if student else None, "feedback",
        {"rating": rating, "context": ctx, "ref_id": ref_id},
    )
    await context.set_state(FeedbackState.waiting_comment)
    await context.update_data(fb_id=fb.id)
    await clear_markup(event)
    await ack(event)
    await reply(event, texts.FEEDBACK_ASK_COMMENT, feedback_skip_kb())


@router.message_created(StateFilter(FeedbackState.waiting_comment))
async def feedback_comment(event: MessageCreated, session: AsyncSession, context: MemoryContext) -> None:
    data = await context.get_data()
    fb_id = data.get("fb_id")
    await context.clear()
    text = (event.message.body.text or "").strip()
    if fb_id is not None and text:
        await crud.set_feedback_comment(session, fb_id, text)
    await reply(event, texts.FEEDBACK_THANKS)
