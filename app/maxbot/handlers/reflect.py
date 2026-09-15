"""Рефлексия: подведение итогов по целям (требования заказчика, протокол п. 3.3).

Сценарий по каждой цели: «получилось?» → коучинговые вопросы (что конкретно / почему /
за счёт чего / что иначе / самооценка и оценка наставника / за что похвалить) →
формальные ответы доуточняются → следующая цель. После всех целей студент САМ
формулирует закономерности, и только затем ИИ даёт сводку. Цель, потерявшая
актуальность, снимается с пояснением. Степень достижения не оценивается.

Данные сценария в FSM-контексте: rs_id, goal_ids, idx, outcome, q_idx, answers,
probes, partial (накопленный ответ при доуточнении).
"""
from __future__ import annotations

import logging

from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.filters import StateFilter
from maxapi.types import MessageCallback, MessageCreated
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.db import crud
from app.maxbot.common import ack, clear_markup, reply, show_main_menu
from app.maxbot.keyboards import reflect_outcome_kb
from app.maxbot.states import Reflection
from app.services import reflection as rsvc
from app.services.events import log_event

logger = logging.getLogger(__name__)
router = Router()


# --- шаги сценария ---------------------------------------------------------

async def _ask_goal(event, session: AsyncSession, context: MemoryContext) -> None:
    """Показать текущую цель и спросить «получилось?»."""
    data = await context.get_data()
    goal_ids: list[int] = data["goal_ids"]
    idx: int = data["idx"]
    goal = await crud.get_goal(session, goal_ids[idx])
    await context.set_state(Reflection.outcome)
    await context.update_data(answers={}, q_idx=0, probes=0, partial="")
    await reply(
        event,
        texts.REFLECT_GOAL_HEADER.format(n=idx + 1, total=len(goal_ids), title=goal.title if goal else "—"),
        reflect_outcome_kb(),
    )


async def _ask_question(event, context: MemoryContext) -> None:
    data = await context.get_data()
    _, prompt = rsvc.QUESTIONS[data["q_idx"]]
    await context.set_state(Reflection.answering)
    await reply(event, prompt)


async def _next_goal_or_patterns(event, session: AsyncSession, context: MemoryContext) -> None:
    data = await context.get_data()
    idx = data["idx"] + 1
    await context.update_data(idx=idx)
    if idx < len(data["goal_ids"]):
        await _ask_goal(event, session, context)
        return
    await context.set_state(Reflection.patterns)
    await reply(event, rsvc.PATTERNS_PROMPT)


async def _finish_goal(event, session: AsyncSession, context: MemoryContext) -> None:
    data = await context.get_data()
    goal_id = data["goal_ids"][data["idx"]]
    await crud.add_goal_reflection(session, data["rs_id"], goal_id, data["outcome"], data.get("answers") or {})
    await reply(event, texts.REFLECT_GOAL_DONE)
    await _next_goal_or_patterns(event, session, context)


# --- вход ------------------------------------------------------------------

@router.message_callback(F.callback.payload == "menu:reflect")
async def menu_reflect(event: MessageCallback, session: AsyncSession, context: MemoryContext) -> None:
    student = await crud.get_student_by_tg(session, event.from_user.user_id)
    if student is None or student.consent_at is None:
        await ack(event, notification=texts.NOT_AUTHED)
        return
    goals = [g for g in await crud.list_goals(session, student.id) if g.status != "dropped"]
    if not goals:
        await ack(event)
        await reply(event, texts.REFLECT_NO_GOALS)
        return
    rs = await crud.create_reflection_session(session, student.id)
    await log_event(session, student.id, "reflection_started", {"session_id": rs.id, "goals": len(goals)})
    await context.clear()
    await context.set_data({"rs_id": rs.id, "goal_ids": [g.id for g in goals], "idx": 0})
    await ack(event)
    await reply(event, texts.REFLECT_INTRO)
    await _ask_goal(event, session, context)


# --- итог по цели ----------------------------------------------------------

@router.message_callback(StateFilter(Reflection.outcome), F.callback.payload.startswith("ro:"))
async def outcome_chosen(event: MessageCallback, session: AsyncSession, context: MemoryContext) -> None:
    outcome = event.callback.payload.split(":", 1)[1]
    if outcome not in rsvc.OUTCOME_LABELS:
        await ack(event)
        return
    await context.update_data(outcome=outcome)
    await clear_markup(event, notification=rsvc.OUTCOME_LABELS[outcome])
    if outcome == "irrelevant":
        await context.set_state(Reflection.irrelevant_note)
        await reply(event, texts.REFLECT_ASK_IRRELEVANT)
        return
    await context.update_data(q_idx=0, probes=0, partial="")
    await _ask_question(event, context)


@router.message_created(StateFilter(Reflection.irrelevant_note))
async def irrelevant_note(event: MessageCreated, session: AsyncSession, context: MemoryContext) -> None:
    note = (event.message.body.text or "").strip()[:1000]
    data = await context.get_data()
    goal_id = data["goal_ids"][data["idx"]]
    await crud.set_goal_irrelevant(session, goal_id, note or None)
    await crud.add_goal_reflection(session, data["rs_id"], goal_id, "irrelevant", {"note": note})
    await reply(event, texts.REFLECT_IRRELEVANT_SAVED)
    await _next_goal_or_patterns(event, session, context)


# --- коучинговые вопросы с доуточнением -----------------------------------

@router.message_created(StateFilter(Reflection.answering))
async def answer(event: MessageCreated, session: AsyncSession, context: MemoryContext) -> None:
    text = (event.message.body.text or "").strip()
    data = await context.get_data()
    q_idx: int = data["q_idx"]
    key, prompt = rsvc.QUESTIONS[q_idx]
    combined = (data.get("partial") or "").strip()
    combined = f"{combined} {text}".strip() if combined else text

    substantive, probe = await rsvc.check_substantive(prompt, combined)
    probes: int = data.get("probes", 0)
    if not substantive and probes < rsvc.MAX_PROBES_PER_QUESTION:
        # Отписка — доуточняем один раз, ответ накапливаем, чтобы ничего не потерять.
        await context.update_data(probes=probes + 1, partial=combined)
        await reply(event, texts.REFLECT_PROBE_PREFIX + probe)
        return

    answers: dict = dict(data.get("answers") or {})
    answers[key] = combined[:2000]
    q_idx += 1
    await context.update_data(answers=answers, q_idx=q_idx, probes=0, partial="")
    if q_idx < len(rsvc.QUESTIONS):
        await _ask_question(event, context)
        return
    await _finish_goal(event, session, context)


# --- закономерности: сначала студент, потом ИИ ----------------------------

@router.message_created(StateFilter(Reflection.patterns))
async def patterns(event: MessageCreated, session: AsyncSession, context: MemoryContext) -> None:
    student_patterns = (event.message.body.text or "").strip()[:3000]
    data = await context.get_data()
    rs_id: int = data["rs_id"]
    await context.clear()

    # Собираем материал по целям для сводки ИИ.
    block: list[dict] = []
    for gr in await crud.list_goal_reflections(session, rs_id):
        goal = await crud.get_goal(session, gr.goal_id)
        block.append({
            "title": goal.title if goal else "—",
            "outcome": gr.outcome,
            "answers": gr.answers or {},
            "relevance_note": (gr.answers or {}).get("note") if gr.outcome == "irrelevant" else None,
        })

    await reply(event, texts.REFLECT_AI_INTRO)
    summary = await rsvc.summarize_patterns(block, student_patterns)
    await crud.complete_reflection_session(session, rs_id, student_patterns or None, summary or None)
    student = await crud.get_student_by_tg(session, event.from_user.user_id)
    await log_event(session, student.id if student else None, "reflection_completed", {"session_id": rs_id})
    await reply(event, summary or texts.REFLECT_AI_FAILED)
    await reply(event, texts.REFLECT_DONE)
    await show_main_menu(event)
