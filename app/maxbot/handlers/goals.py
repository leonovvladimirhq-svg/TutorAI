"""Постановка целей по SMART (порт app.bot.handlers.goals под maxapi)."""
from __future__ import annotations

from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.filters import StateFilter
from maxapi.types import MessageCallback, MessageCreated
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.db import crud
from app.maxbot.common import ack, clear_markup, reply
from app.maxbot.keyboards import (
    feedback_rating_kb,
    goal_draft_kb,
    goal_templates_kb,
    goals_menu_kb,
)
from app.maxbot.states import Goals
from app.services import smart
from app.services.events import log_event

router = Router()

_STATUS_RU = {"draft": "черновик", "active": "активна", "done": "достигнута", "dropped": "снята"}
_SMART_LETTERS = {"specific": "S", "measurable": "M", "achievable": "A", "relevant": "R", "time_bound": "T"}


async def _render_goals(event, session: AsyncSession, student_id: int) -> None:
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
    await reply(event, texts.GOALS_HEADER.format(body=body), goals_menu_kb())


async def _make_and_show_draft(
    event, session: AsyncSession, context: MemoryContext,
    student_id: int, intent: str, feedback: str | None = None,
) -> None:
    data = await context.get_data()
    previous = data.get("draft")
    await reply(event, texts.GOAL_DRAFTING)
    draft = await smart.draft_goal(session, student_id, intent, feedback=feedback, previous=previous)
    if not draft:
        await reply(event, texts.GOAL_DRAFT_FAILED)
        return
    await context.set_state(Goals.chatting)
    await context.update_data(intent=intent, draft=draft, awaiting=None)
    await reply(event, texts.GOAL_DRAFT.format(**draft), goal_draft_kb())


def _format_evaluation(evaluation: dict) -> str:
    lines = [texts.GOAL_EVAL_HEADER]
    for comp in smart.SMART_COMPONENTS:
        item = evaluation["components"].get(comp, {})
        letter = _SMART_LETTERS[comp]
        label = texts.SMART_LABELS_RU.get(comp, comp)
        if item.get("met"):
            detail = item.get("value") or "сформулировано хорошо"
            lines.append(texts.GOAL_EVAL_LINE_OK.format(letter=letter, label=label, detail=detail))
        else:
            detail = item.get("advice") or "нужно уточнить"
            lines.append(texts.GOAL_EVAL_LINE_BAD.format(letter=letter, label=label, detail=detail))
    if evaluation.get("comment"):
        lines.append("\n" + evaluation["comment"])
    lines.append(texts.GOAL_EVAL_REFINE)
    return "\n".join(lines)


async def _evaluate_and_coach(
    event, session: AsyncSession, context: MemoryContext, student_id: int, goal_text: str
) -> None:
    await reply(event, texts.GOAL_EVALUATING)
    evaluation = await smart.evaluate_goal(session, student_id, goal_text)
    if not evaluation:
        await reply(event, texts.GOAL_EVAL_FAILED)
        return

    if evaluation["is_smart"]:
        draft = smart.draft_from_evaluation(evaluation)
        await context.set_state(Goals.chatting)
        await context.update_data(intent=goal_text, draft=draft, awaiting=None)
        await reply(event, texts.GOAL_EVAL_SMART)
        await reply(event, texts.GOAL_DRAFT.format(**draft), goal_draft_kb())
    else:
        await context.set_state(Goals.chatting)
        await context.update_data(awaiting="own_goal", last_goal=goal_text)
        await reply(event, _format_evaluation(evaluation))


@router.message_callback(F.callback.payload == "menu:goals")
async def menu_goals(event: MessageCallback, session: AsyncSession, context: MemoryContext) -> None:
    student = await crud.get_student_by_tg(session, event.from_user.user_id)
    if student is None or student.consent_at is None:
        await ack(event, notification=texts.NOT_AUTHED)
        return
    await context.clear()
    await ack(event)
    await _render_goals(event, session, student.id)


@router.message_callback(F.callback.payload == "goals:new")
async def goals_new(event: MessageCallback) -> None:
    await reply(event, texts.CHOOSE_GOAL_TEMPLATE, goal_templates_kb(smart.DEFAULT_GOALS))
    await ack(event)


@router.message_callback(F.callback.payload == "goalnew:own")
async def goal_own(event: MessageCallback, context: MemoryContext) -> None:
    await context.set_state(Goals.chatting)
    await context.update_data(awaiting="own_goal", draft=None, intent=None)
    await reply(event, texts.ASK_OWN_GOAL)
    await ack(event)


@router.message_callback(F.callback.payload.startswith("goalnew:"))
async def goal_template(event: MessageCallback, session: AsyncSession, context: MemoryContext) -> None:
    if event.callback.payload == "goalnew:own":
        return
    student = await crud.get_student_by_tg(session, event.from_user.user_id)
    if student is None:
        await ack(event, notification=texts.NOT_AUTHED)
        return
    idx = int(event.callback.payload.split(":", 1)[1])
    template = smart.DEFAULT_GOALS[idx]
    intent = f"{template['title']} ({template['hint']})"
    await ack(event)
    await _make_and_show_draft(event, session, context, student.id, intent)


async def handle_goals_text(event, session: AsyncSession, context: MemoryContext, raw_text: str) -> None:
    """Обработать реплику в сценарии целей (из текста или голоса)."""
    student = await crud.get_student_by_tg(session, event.from_user.user_id)
    if student is None:
        await context.clear()
        await reply(event, texts.NOT_AUTHED)
        return
    data = await context.get_data()
    awaiting = data.get("awaiting")
    text = raw_text.strip()

    if awaiting == "own_goal":
        await _evaluate_and_coach(event, session, context, student.id, text)
    elif awaiting == "feedback":
        intent = data.get("intent") or text
        await _make_and_show_draft(event, session, context, student.id, intent, feedback=text)


@router.message_created(StateFilter(Goals.chatting))
async def goals_message(event: MessageCreated, session: AsyncSession, context: MemoryContext) -> None:
    await handle_goals_text(event, session, context, event.message.body.text or "")


@router.message_callback(StateFilter(Goals.chatting), F.callback.payload == "goaldraft:save")
async def goal_save(event: MessageCallback, session: AsyncSession, context: MemoryContext) -> None:
    student = await crud.get_student_by_tg(session, event.from_user.user_id)
    data = await context.get_data()
    draft = data.get("draft")
    if student is None or not draft:
        await ack(event)
        return
    missing = smart.validate(draft)
    if missing:
        await context.update_data(awaiting="feedback")
        labels = ", ".join(texts.SMART_LABELS_RU.get(m, m) for m in missing)
        await clear_markup(event)
        await reply(event, texts.GOAL_INCOMPLETE.format(missing=labels))
        return
    goal = await crud.add_goal(session, student.id, draft, status="active")
    await log_event(session, student.id, "goal_created", {"goal_id": goal.id, "title": goal.title})
    await context.clear()
    await clear_markup(event, notification=texts.GOAL_SAVED)
    await reply(event, texts.GOAL_SAVED)
    await _render_goals(event, session, student.id)
    # Контекстная обратная связь по формулировке цели (👍/👎 + комментарий).
    await reply(event, texts.FEEDBACK_ASK_GOAL, feedback_rating_kb("smart_goal", goal.id))


@router.message_callback(StateFilter(Goals.chatting), F.callback.payload == "goaldraft:edit")
async def goal_edit(event: MessageCallback, context: MemoryContext) -> None:
    await context.update_data(awaiting="feedback")
    await clear_markup(event)
    await reply(event, texts.ASK_GOAL_FEEDBACK)


@router.message_callback(StateFilter(Goals.chatting), F.callback.payload == "goaldraft:cancel")
async def goal_cancel(event: MessageCallback, session: AsyncSession, context: MemoryContext) -> None:
    student = await crud.get_student_by_tg(session, event.from_user.user_id)
    await context.clear()
    await clear_markup(event)
    await reply(event, texts.GOAL_CANCELLED)
    if student is not None:
        await _render_goals(event, session, student.id)
