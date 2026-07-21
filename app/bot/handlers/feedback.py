"""Сбор обратной связи: 👍/👎 + необязательный комментарий.

Вызывается из меню (context=menu) и после формирования SMART-целей
(context=smart_goal, ref_id=goal.id). Оценка сохраняется сразу, комментарий —
опционально следующим сообщением.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.bot.keyboards import feedback_rating_kb, feedback_skip_kb
from app.bot.states import Feedback as FeedbackState
from app.db import crud
from app.services.events import log_event

router = Router(name="feedback")


@router.callback_query(F.data == "menu:feedback")
async def feedback_from_menu(callback: CallbackQuery) -> None:
    await callback.message.answer(texts.FEEDBACK_ASK, reply_markup=feedback_rating_kb("menu"))
    await callback.answer()


@router.callback_query(F.data.startswith("fb:") & ~F.data.startswith("fb:skip"))
async def feedback_rating(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    # fb:<up|down>:<context>:<ref_id or ''>
    parts = callback.data.split(":")
    rating = parts[1] if len(parts) > 1 else "up"
    context = parts[2] if len(parts) > 2 else "menu"
    ref_id = int(parts[3]) if len(parts) > 3 and parts[3] else None

    student = await crud.get_student_by_tg(session, callback.from_user.id)
    fb = await crud.add_feedback(
        session,
        telegram_id=callback.from_user.id,
        rating=rating,
        context=context,
        student_id=student.id if student else None,
        ref_id=ref_id,
    )
    await log_event(
        session,
        student.id if student else None,
        "feedback",
        {"rating": rating, "context": context, "ref_id": ref_id},
    )
    await state.set_state(FeedbackState.waiting_comment)
    await state.update_data(fb_id=fb.id)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await callback.message.answer(texts.FEEDBACK_ASK_COMMENT, reply_markup=feedback_skip_kb())


@router.callback_query(F.data == "fb:skip")
async def feedback_skip(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
    await callback.message.answer(texts.FEEDBACK_THANKS)


@router.message(FeedbackState.waiting_comment)
async def feedback_comment(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    fb_id = data.get("fb_id")
    await state.clear()
    if fb_id is not None and (message.text or "").strip():
        await crud.set_feedback_comment(session, fb_id, message.text.strip())
    await message.answer(texts.FEEDBACK_THANKS)
