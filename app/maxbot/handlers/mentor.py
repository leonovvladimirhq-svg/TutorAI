"""Модуль наставника: свои студенты, цели, отчёт .docx, подтверждение целей.

Контур подтверждения (протокол, п. 3.4): при постановке цели студентом наставнику
приходит цель с кнопками «Подтвердить» / «Отклонить»; при отклонении наставник пишет
причину, и она уходит студенту. Решения видны руководителю в сводке веб-панели.
Безопасность: наставник видит и подтверждает только цели закреплённых за ним студентов.
"""
from __future__ import annotations

import logging

from maxapi import F, Router
from maxapi.context import MemoryContext
from maxapi.enums import ParseMode, UploadType
from maxapi.filters import StateFilter
from maxapi.types import InputMediaBuffer, MessageCallback, MessageCreated
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.db import crud
from app.maxbot.common import ack, clear_markup, edit, format_goal_for_mentor, reply, send_to
from app.maxbot.keyboards import mentor_confirm_kb, mentor_menu_kb, mentor_student_kb, mentor_students_kb
from app.maxbot.states import MentorReject
from app.services import report
from app.services.events import log_event
from app.services.roles import ROLE_MENTOR

logger = logging.getLogger(__name__)
router = Router()

_STATUS_RU = {"draft": "черновик", "active": "активна", "done": "достигнута", "dropped": "снята"}


async def _is_mentor(session: AsyncSession, tg: int) -> bool:
    return await crud.get_role_by_tg(session, tg) == ROLE_MENTOR


async def _own_student(session: AsyncSession, mentor_tg: int, app_user_id: int):
    """Студент (запись реестра), с которым этот наставник может работать, — иначе None.

    Закреплённый за ним, либо любой — в режиме теста «все наставники видят всех»."""
    from app.db.models import AppUser
    u = await session.get(AppUser, app_user_id)
    if not await crud.mentor_sees_student(session, mentor_tg, u):
        return None
    return u


async def _empty_text(session: AsyncSession, visible) -> str:
    """Пустой список: «никто ещё ничего не прислал» + сколько студентов уже в боте."""
    text = texts.MENTOR_NO_STUDENTS
    if visible:
        tpl = texts.MENTOR_ALL_SILENT if await crud.mentors_see_all(session) else texts.MENTOR_ASSIGNED_SILENT
        text += tpl.format(n=len(visible))
    return text


async def _pending_goals(session: AsyncSession, u) -> list:
    student = await crud.get_student_by_tg(session, u.telegram_id)
    goals = await crud.list_goals(session, student.id) if student else []
    return [g for g in goals if g.confirm_status == "pending" and g.status != "dropped"]


async def _students_with_goals(session: AsyncSession, users) -> list:
    """Из закреплённых студентов — те, кто прислал хотя бы одну цель.

    Наставник видит в списке только тех, кто уже что-то отправил: пустой список
    однозначно означает «пока никто ничего не прислал».
    """
    result = []
    for u in users:
        student = await crud.get_student_by_tg(session, u.telegram_id)
        if student is not None and await crud.list_goals(session, student.id):
            result.append(u)
    return result


async def _student_card(session: AsyncSession, u) -> str:
    student = await crud.get_student_by_tg(session, u.telegram_id)
    goals = await crud.list_goals(session, student.id) if student else []
    refl = await crud.latest_completed_reflection(session, student.id) if student else None
    return texts.MENTOR_STUDENT_CARD.format(
        name=u.full_name or f"ID {u.telegram_id}", tg=u.telegram_id,
        goals=len(goals),
        confirmed=sum(1 for g in goals if g.confirm_status == "confirmed"),
        rejected=sum(1 for g in goals if g.confirm_status == "rejected"),
        pending=sum(1 for g in goals if g.confirm_status == "pending"),
        reflection=("пройдена " + refl.completed_at.strftime("%d.%m.%Y")) if refl else "ещё нет",
    )


# --- Меню наставника -------------------------------------------------------

@router.message_callback(F.callback.payload == "mstudents")
async def my_students(event: MessageCallback, session: AsyncSession) -> None:
    tg = event.from_user.user_id
    if not await _is_mentor(session, tg):
        await ack(event, notification=texts.MENTOR_ONLY)
        return
    visible = await crud.students_visible_to_mentor(session, tg)
    active = await _students_with_goals(session, visible)
    if not active:
        # Пусто = никто ещё ничего не прислал (так и объясняем наставнику).
        await edit(event, await _empty_text(session, visible), mentor_menu_kb())
        return
    await edit(event, texts.MENTOR_PICK_STUDENT, mentor_students_kb(active))


@router.message_callback(F.callback.payload.startswith("mstud:"))
async def student_card(event: MessageCallback, session: AsyncSession) -> None:
    tg = event.from_user.user_id
    u = await _own_student(session, tg, int(event.callback.payload.split(":", 1)[1]))
    if u is None:
        await ack(event, notification=texts.MENTOR_ONLY)
        return
    pending = await _pending_goals(session, u)
    await edit(event, await _student_card(session, u), mentor_student_kb(u.id, len(pending)))


@router.message_callback(F.callback.payload.startswith("mpending:"))
async def student_pending(event: MessageCallback, session: AsyncSession) -> None:
    """Цели, ждущие решения, — каждая отдельным сообщением с кнопками «Подтвердить / Отклонить».

    Нужна, когда цель поставлена раньше, чем наставник впервые открыл бота:
    уведомление в момент постановки до него тогда не дошло."""
    tg = event.from_user.user_id
    u = await _own_student(session, tg, int(event.callback.payload.split(":", 1)[1]))
    if u is None:
        await ack(event, notification=texts.MENTOR_ONLY)
        return
    pending = await _pending_goals(session, u)
    if not pending:
        await ack(event, notification=texts.MENTOR_PENDING_NONE)
        return
    await ack(event)
    name = u.full_name or f"ID {u.telegram_id}"
    await reply(event, texts.MENTOR_PENDING_INTRO.format(name=name))
    for g in pending:
        await reply(event, format_goal_for_mentor(name, g), mentor_confirm_kb(g.id))


@router.message_callback(F.callback.payload.startswith("mgoals:"))
async def student_goals(event: MessageCallback, session: AsyncSession) -> None:
    tg = event.from_user.user_id
    u = await _own_student(session, tg, int(event.callback.payload.split(":", 1)[1]))
    if u is None:
        await ack(event, notification=texts.MENTOR_ONLY)
        return
    student = await crud.get_student_by_tg(session, u.telegram_id)
    goals = await crud.list_goals(session, student.id) if student else []
    if not goals:
        body = texts.MENTOR_NO_GOALS
    else:
        body = "\n".join(
            texts.MENTOR_GOAL_LINE.format(
                title=g.title, status=_STATUS_RU.get(g.status, g.status),
                confirm=texts.CONFIRM_RU.get(g.confirm_status, g.confirm_status),
            ) for g in goals
        )
    pending = sum(1 for g in goals if g.confirm_status == "pending" and g.status != "dropped")
    await edit(event, texts.MENTOR_GOALS_HEADER.format(name=u.full_name or u.telegram_id, body=body),
               mentor_student_kb(u.id, pending))


@router.message_callback(F.callback.payload.startswith("mreport:"))
async def student_report(event: MessageCallback, session: AsyncSession) -> None:
    tg = event.from_user.user_id
    u = await _own_student(session, tg, int(event.callback.payload.split(":", 1)[1]))
    if u is None:
        await ack(event, notification=texts.MENTOR_ONLY)
        return
    await ack(event, notification=texts.MENTOR_REPORT_BUILDING)
    try:
        data, filename = await report.build_student_report(session, u)
        media = InputMediaBuffer(buffer=data, filename=filename, type=UploadType.FILE)
        await event.message.answer(
            texts.MENTOR_REPORT_CAPTION.format(name=u.full_name or u.telegram_id),
            attachments=[media], parse_mode=ParseMode.HTML,
        )
        student = await crud.get_student_by_tg(session, u.telegram_id)
        await log_event(session, student.id if student else None, "mentor_report", {"mentor": tg})
    except Exception:  # noqa: BLE001
        logger.exception("Ошибка формирования отчёта для наставника %s по %s", tg, u.telegram_id)
        await reply(event, texts.MENTOR_REPORT_FAILED)


@router.message_callback(F.callback.payload == "mreport_all")
async def group_report(event: MessageCallback, session: AsyncSession) -> None:
    """Общий отчёт по всем студентам наставника одним .docx (сводка + карта каждого)."""
    tg = event.from_user.user_id
    mentor_user = await crud.get_app_user_by_tg(session, tg)
    if mentor_user is None or mentor_user.role != ROLE_MENTOR:
        await ack(event, notification=texts.MENTOR_ONLY)
        return
    visible = await crud.students_visible_to_mentor(session, tg)
    if not await _students_with_goals(session, visible):
        await edit(event, await _empty_text(session, visible), mentor_menu_kb())
        return
    await ack(event, notification=texts.MENTOR_REPORT_BUILDING)
    try:
        data, filename, count = await report.build_group_report(session, mentor_user)
        media = InputMediaBuffer(buffer=data, filename=filename, type=UploadType.FILE)
        await event.message.answer(
            texts.MENTOR_REPORT_ALL_CAPTION.format(count=count),
            attachments=[media], parse_mode=ParseMode.HTML,
        )
        await log_event(session, None, "mentor_group_report", {"mentor": tg, "students": count})
    except Exception:  # noqa: BLE001
        logger.exception("Ошибка формирования общего отчёта для наставника %s", tg)
        await reply(event, texts.MENTOR_REPORT_FAILED)


# --- Контур подтверждения целей --------------------------------------------

async def _goal_for_mentor(session: AsyncSession, mentor_tg: int, goal_id: int):
    """Цель + студент, если цель принадлежит студенту этого наставника."""
    goal = await crud.get_goal(session, goal_id)
    if goal is None:
        return None, None
    student = await crud.get_student(session, goal.student_id)
    if student is None or student.telegram_id is None:
        return None, None
    app_user = await crud.get_app_user_by_tg(session, student.telegram_id)
    if not await crud.mentor_sees_student(session, mentor_tg, app_user):
        return None, None
    return goal, student


@router.message_callback(F.callback.payload.startswith("mconfirm:"))
async def goal_confirm(event: MessageCallback, session: AsyncSession) -> None:
    tg = event.from_user.user_id
    goal, student = await _goal_for_mentor(session, tg, int(event.callback.payload.split(":", 1)[1]))
    if goal is None:
        await ack(event, notification=texts.MENTOR_ONLY)
        return
    if goal.confirm_status != "pending":
        await clear_markup(event, notification=texts.MENTOR_ALREADY_DECIDED)
        return
    await crud.set_goal_confirm(session, goal.id, "confirmed")
    await log_event(session, student.id, "goal_confirmed", {"goal_id": goal.id, "mentor": tg})
    await clear_markup(event, notification=texts.MENTOR_CONFIRMED_DONE)
    await reply(event, texts.MENTOR_CONFIRMED_DONE)
    await send_to(event.bot, student.telegram_id, texts.STUDENT_GOAL_CONFIRMED.format(title=goal.title))


@router.message_callback(F.callback.payload.startswith("mreject:"))
async def goal_reject_start(event: MessageCallback, session: AsyncSession, context: MemoryContext) -> None:
    tg = event.from_user.user_id
    goal, _ = await _goal_for_mentor(session, tg, int(event.callback.payload.split(":", 1)[1]))
    if goal is None:
        await ack(event, notification=texts.MENTOR_ONLY)
        return
    if goal.confirm_status != "pending":
        await clear_markup(event, notification=texts.MENTOR_ALREADY_DECIDED)
        return
    await context.set_state(MentorReject.waiting_reason)
    await context.update_data(reject_goal_id=goal.id)
    await clear_markup(event)
    await reply(event, texts.MENTOR_ASK_REASON)


@router.message_created(StateFilter(MentorReject.waiting_reason))
async def goal_reject_reason(event: MessageCreated, session: AsyncSession, context: MemoryContext) -> None:
    tg = event.from_user.user_id
    data = await context.get_data()
    goal_id = data.get("reject_goal_id")
    await context.clear()
    reason = (event.message.body.text or "").strip()[:1000]
    goal, student = await _goal_for_mentor(session, tg, int(goal_id)) if goal_id else (None, None)
    if goal is None:
        await reply(event, texts.MENTOR_ONLY)
        return
    await crud.set_goal_confirm(session, goal.id, "rejected", reason or None)
    await log_event(session, student.id, "goal_rejected", {"goal_id": goal.id, "mentor": tg})
    await reply(event, texts.MENTOR_REJECTED_DONE)
    await send_to(
        event.bot, student.telegram_id,
        texts.STUDENT_GOAL_REJECTED.format(title=goal.title, comment=reason or "без комментария"),
    )
