"""Рефлексия: подведение итогов по целям (требования заказчика, протокол п. 3.3).

Сценарий по каждой цели: «получилось?» → коучинговые вопросы (что конкретно / почему /
за счёт чего / что иначе / самооценка и оценка наставника / за что похвалить) →
формальные ответы доуточняются → следующая цель. После всех целей студент САМ
формулирует закономерности, и только затем ИИ даёт сводку. Цель, потерявшая
актуальность, снимается с пояснением. Степень достижения не оценивается.

Сценарий не бесконечный: под каждым вопросом есть «Пропустить вопрос» и «Завершить»;
доуточнений — не больше одного на вопрос и не больше MAX_PROBES_PER_GOAL на цель.
При досрочном завершении всё уже сказанное сохраняется, наставник это увидит.

Данные сценария в FSM-контексте: rs_id, goal_ids, idx, outcome, q_idx, answers,
probes (по текущему вопросу), goal_probes (по текущей цели), partial (накопленный
ответ при доуточнении).
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
from app.maxbot.keyboards import reflect_outcome_kb, reflect_question_kb
from app.maxbot.states import Reflection
from app.services import reflection as rsvc
from app.services.events import log_event

logger = logging.getLogger(__name__)
router = Router()

REFLECT_STATES = (Reflection.outcome, Reflection.answering, Reflection.irrelevant_note, Reflection.patterns)


# --- шаги сценария ---------------------------------------------------------

async def _ask_goal(event, session: AsyncSession, context: MemoryContext) -> None:
    """Показать текущую цель и спросить «получилось?»."""
    data = await context.get_data()
    goal_ids: list[int] = data["goal_ids"]
    idx: int = data["idx"]
    goal = await crud.get_goal(session, goal_ids[idx])
    await context.set_state(Reflection.outcome)
    await context.update_data(answers={}, q_idx=0, probes=0, goal_probes=0, partial="")
    await reply(
        event,
        texts.REFLECT_GOAL_HEADER.format(n=idx + 1, total=len(goal_ids), title=goal.title if goal else "—"),
        reflect_outcome_kb(),
    )


async def _ask_question(event, context: MemoryContext) -> None:
    data = await context.get_data()
    _, prompt = rsvc.QUESTIONS[data["q_idx"]]
    await context.set_state(Reflection.answering)
    await reply(event, prompt, reflect_question_kb())


async def _next_goal_or_patterns(event, session: AsyncSession, context: MemoryContext) -> None:
    data = await context.get_data()
    idx = data["idx"] + 1
    await context.update_data(idx=idx)
    if idx < len(data["goal_ids"]):
        await _ask_goal(event, session, context)
        return
    await context.set_state(Reflection.patterns)
    await reply(event, rsvc.PATTERNS_PROMPT, reflect_question_kb())


async def _save_current_goal(session: AsyncSession, data: dict) -> bool:
    """Сохранить ответы по текущей цели (если студент уже выбрал итог)."""
    outcome = data.get("outcome")
    if not outcome or data.get("idx", 0) >= len(data.get("goal_ids") or []):
        return False
    answers: dict = dict(data.get("answers") or {})
    partial = (data.get("partial") or "").strip()
    q_idx = data.get("q_idx", 0)
    if partial and q_idx < len(rsvc.QUESTIONS):
        answers[rsvc.QUESTIONS[q_idx][0]] = partial[:2000]  # недоуточнённый ответ тоже сохраняем
    goal_id = data["goal_ids"][data["idx"]]
    await crud.add_goal_reflection(session, data["rs_id"], goal_id, outcome, answers)
    return True


async def _finish_goal(event, session: AsyncSession, context: MemoryContext) -> None:
    data = await context.get_data()
    await _save_current_goal(session, data)
    await context.update_data(outcome=None)
    await reply(event, texts.REFLECT_GOAL_DONE)
    await _next_goal_or_patterns(event, session, context)


async def _complete(event, session: AsyncSession, context: MemoryContext, student_patterns: str | None, early: bool) -> None:
    """Закрыть сессию: собрать материал, сводка ИИ (если есть о чём), сообщить студенту."""
    data = await context.get_data()
    rs_id: int = data["rs_id"]
    await context.clear()

    block: list[dict] = []
    for gr in await crud.list_goal_reflections(session, rs_id):
        goal = await crud.get_goal(session, gr.goal_id)
        block.append({
            "title": goal.title if goal else "—",
            "outcome": gr.outcome,
            "answers": gr.answers or {},
            "relevance_note": (gr.answers or {}).get("note") if gr.outcome == "irrelevant" else None,
        })

    if not block and not student_patterns:
        # ничего не сказано — пустую сессию не считаем пройденной рефлексией
        await crud.delete_reflection_session(session, rs_id)
        await reply(event, texts.REFLECT_FINISHED_EARLY)
        await show_main_menu(event)
        return

    summary = None
    if block:
        await reply(event, texts.REFLECT_AI_INTRO)
        summary = await rsvc.summarize_patterns(block, student_patterns or "")
    await crud.complete_reflection_session(session, rs_id, student_patterns or None, summary or None)
    student = await crud.get_student_by_tg(session, event.from_user.user_id)
    await log_event(session, student.id if student else None, "reflection_completed",
                    {"session_id": rs_id, "early": early, "goals": len(block)})
    if block:
        await reply(event, summary or texts.REFLECT_AI_FAILED)
    await reply(event, texts.REFLECT_FINISHED_EARLY if early else texts.REFLECT_DONE)
    await show_main_menu(event)


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


# --- кнопки «пропустить» / «завершить» -------------------------------------

@router.message_callback(StateFilter(*REFLECT_STATES), F.callback.payload == "rq:finish")
async def finish_early(event: MessageCallback, session: AsyncSession, context: MemoryContext) -> None:
    data = await context.get_data()
    await _save_current_goal(session, data)
    await clear_markup(event, notification=texts.BTN_REFLECT_FINISH)
    await _complete(event, session, context, None, early=True)


@router.message_callback(StateFilter(Reflection.answering), F.callback.payload == "rq:skip")
async def skip_question(event: MessageCallback, session: AsyncSession, context: MemoryContext) -> None:
    data = await context.get_data()
    q_idx: int = data.get("q_idx", 0) + 1
    await clear_markup(event, notification=texts.BTN_REFLECT_SKIP)
    await context.update_data(q_idx=q_idx, probes=0, partial="")
    if q_idx < len(rsvc.QUESTIONS):
        await _ask_question(event, context)
        return
    await _finish_goal(event, session, context)


@router.message_callback(StateFilter(Reflection.patterns), F.callback.payload == "rq:skip")
async def skip_patterns(event: MessageCallback, session: AsyncSession, context: MemoryContext) -> None:
    await clear_markup(event, notification=texts.BTN_REFLECT_SKIP)
    await _complete(event, session, context, None, early=False)


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
        await reply(event, texts.REFLECT_ASK_IRRELEVANT, reflect_question_kb())
        return
    await context.update_data(q_idx=0, probes=0, goal_probes=0, partial="")
    await _ask_question(event, context)


async def handle_irrelevant_text(event, session: AsyncSession, context: MemoryContext, text: str) -> None:
    note = text.strip()[:1000]
    data = await context.get_data()
    goal_id = data["goal_ids"][data["idx"]]
    await crud.set_goal_irrelevant(session, goal_id, note or None)
    await crud.add_goal_reflection(session, data["rs_id"], goal_id, "irrelevant", {"note": note})
    await context.update_data(outcome=None)
    await reply(event, texts.REFLECT_IRRELEVANT_SAVED)
    await _next_goal_or_patterns(event, session, context)


@router.message_created(StateFilter(Reflection.irrelevant_note))
async def irrelevant_note(event: MessageCreated, session: AsyncSession, context: MemoryContext) -> None:
    await handle_irrelevant_text(event, session, context, event.message.body.text or "")


# --- коучинговые вопросы с доуточнением -----------------------------------

async def handle_answer_text(event, session: AsyncSession, context: MemoryContext, text: str) -> None:
    """Ответ на текущий вопрос (текстом или распознанным голосом)."""
    text = text.strip()
    data = await context.get_data()
    q_idx: int = data["q_idx"]
    key, prompt = rsvc.QUESTIONS[q_idx]
    combined = (data.get("partial") or "").strip()
    combined = f"{combined} {text}".strip() if combined else text

    probes: int = data.get("probes", 0)
    goal_probes: int = data.get("goal_probes", 0)
    can_probe = probes < rsvc.MAX_PROBES_PER_QUESTION and goal_probes < rsvc.MAX_PROBES_PER_GOAL
    if can_probe:
        substantive, probe = await rsvc.check_substantive(prompt, combined)
        if not substantive:
            # Отписка — доуточняем один раз, ответ накапливаем, чтобы ничего не потерять.
            await context.update_data(probes=probes + 1, goal_probes=goal_probes + 1, partial=combined)
            await reply(event, texts.REFLECT_PROBE_PREFIX + probe, reflect_question_kb())
            return

    answers: dict = dict(data.get("answers") or {})
    answers[key] = combined[:2000]
    q_idx += 1
    await context.update_data(answers=answers, q_idx=q_idx, probes=0, partial="")
    if q_idx < len(rsvc.QUESTIONS):
        await _ask_question(event, context)
        return
    await _finish_goal(event, session, context)


@router.message_created(StateFilter(Reflection.answering))
async def answer(event: MessageCreated, session: AsyncSession, context: MemoryContext) -> None:
    await handle_answer_text(event, session, context, event.message.body.text or "")


# --- закономерности: сначала студент, потом ИИ ----------------------------

async def handle_patterns_text(event, session: AsyncSession, context: MemoryContext, text: str) -> None:
    await _complete(event, session, context, text.strip()[:3000], early=False)


@router.message_created(StateFilter(Reflection.patterns))
async def patterns(event: MessageCreated, session: AsyncSession, context: MemoryContext) -> None:
    await handle_patterns_text(event, session, context, event.message.body.text or "")
