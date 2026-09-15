"""Часто используемые операции с БД."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AppSetting,
    AppUser,
    ConsentRecord,
    ConversationMessage,
    Feedback,
    Goal,
    GoalReflection,
    ProfileAttribute,
    ReflectionSession,
    Student,
)


# --- Роли (app_user) -------------------------------------------------------

async def get_app_user_by_tg(session: AsyncSession, telegram_id: int) -> AppUser | None:
    return await session.scalar(select(AppUser).where(AppUser.telegram_id == telegram_id))


async def get_role_by_tg(session: AsyncSession, telegram_id: int) -> str | None:
    user = await get_app_user_by_tg(session, telegram_id)
    return user.role if user else None


async def list_app_users(session: AsyncSession) -> list[AppUser]:
    result = await session.scalars(select(AppUser).order_by(AppUser.role, AppUser.id))
    return list(result.all())


async def add_app_user(
    session: AsyncSession, telegram_id: int, role: str, full_name: str | None = None
) -> AppUser:
    """Создаёт или обновляет запись роли по telegram_id (upsert)."""
    user = await get_app_user_by_tg(session, telegram_id)
    if user is None:
        user = AppUser(telegram_id=telegram_id, role=role, full_name=full_name)
        session.add(user)
    else:
        user.role = role
        if full_name is not None:
            user.full_name = full_name
    await session.commit()
    await session.refresh(user)
    return user


async def set_app_user_role(session: AsyncSession, user_id: int, role: str) -> None:
    user = await session.get(AppUser, user_id)
    if user is not None:
        user.role = role
        await session.commit()


async def delete_app_user(session: AsyncSession, user_id: int) -> None:
    user = await session.get(AppUser, user_id)
    if user is not None:
        await session.delete(user)
        await session.commit()


async def get_or_create_student_by_tg(
    session: AsyncSession, telegram_id: int, label: str | None = None
) -> Student:
    """Возвращает студенческую запись по telegram_id, создавая её при отсутствии.

    Пароль не используется — идентификация по telegram_id (роль из app_user).
    """
    student = await get_student_by_tg(session, telegram_id)
    if student is None:
        student = Student(
            telegram_id=telegram_id,
            profile_label=(label or "Студент")[:64],
            password_hash=None,
        )
        session.add(student)
        await session.commit()
        await session.refresh(student)
    return student


# --- Студенты / профиль ----------------------------------------------------

async def get_student_by_tg(session: AsyncSession, telegram_id: int) -> Student | None:
    return await session.scalar(select(Student).where(Student.telegram_id == telegram_id))


async def get_student(session: AsyncSession, student_id: int) -> Student | None:
    return await session.get(Student, student_id)


async def list_profiles(session: AsyncSession) -> list[Student]:
    result = await session.scalars(select(Student).order_by(Student.id))
    return list(result.all())


async def bind_telegram(session: AsyncSession, student: Student, telegram_id: int) -> None:
    """Привязывает Telegram-аккаунт к профилю и фиксирует согласие.

    Если этот telegram_id уже привязан к другому профилю — отвязывает его.
    """
    existing = await get_student_by_tg(session, telegram_id)
    if existing is not None and existing.id != student.id:
        existing.telegram_id = None

    student.telegram_id = telegram_id
    if student.consent_at is None:
        student.consent_at = datetime.now(timezone.utc)
    await session.commit()


async def add_message(
    session: AsyncSession,
    student_id: int,
    role: str,
    content: str,
    modality: str = "text",
) -> ConversationMessage:
    msg = ConversationMessage(
        student_id=student_id, role=role, content=content, modality=modality
    )
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    return msg


async def upsert_attribute(
    session: AsyncSession,
    student_id: int,
    block: str,
    key: str,
    value: str,
    confidence: float,
    source_ref: int | None,
    status: str,
) -> ProfileAttribute:
    """Создаёт или обновляет атрибут профиля по паре (block, key)."""
    attr = await session.scalar(
        select(ProfileAttribute).where(
            ProfileAttribute.student_id == student_id,
            ProfileAttribute.block == block,
            ProfileAttribute.key == key,
        )
    )
    if attr is None:
        attr = ProfileAttribute(
            student_id=student_id,
            block=block,
            key=key,
            value=value,
            confidence=confidence,
            source_ref=source_ref,
            status=status,
        )
        session.add(attr)
    else:
        attr.value = value
        attr.confidence = confidence
        attr.source_ref = source_ref
        attr.status = status
    await session.commit()
    await session.refresh(attr)
    return attr


async def set_block_done(session: AsyncSession, student: Student, block_key: str) -> None:
    progress = dict(student.profiling_progress or {})
    progress[block_key] = "done"
    student.profiling_progress = progress
    await session.commit()


async def list_attributes(session: AsyncSession, student_id: int) -> list[ProfileAttribute]:
    """Подтверждённые/отредактированные атрибуты профиля."""
    result = await session.scalars(
        select(ProfileAttribute)
        .where(
            ProfileAttribute.student_id == student_id,
            ProfileAttribute.status.in_(["confirmed", "edited"]),
        )
        .order_by(ProfileAttribute.block, ProfileAttribute.id)
    )
    return list(result.all())


async def get_attribute(session: AsyncSession, attr_id: int) -> ProfileAttribute | None:
    return await session.get(ProfileAttribute, attr_id)


async def update_attribute_value(
    session: AsyncSession, attr: ProfileAttribute, value: str
) -> None:
    attr.value = value[:500]
    attr.status = "edited"
    await session.commit()


async def list_goals(session: AsyncSession, student_id: int) -> list[Goal]:
    result = await session.scalars(
        select(Goal).where(Goal.student_id == student_id).order_by(Goal.id)
    )
    return list(result.all())


async def add_goal(
    session: AsyncSession,
    student_id: int,
    draft: dict,
    status: str = "active",
    source_ref: int | None = None,
) -> Goal:
    goal = Goal(
        student_id=student_id,
        title=draft.get("title", "Цель")[:255],
        specific=draft.get("specific"),
        measurable=draft.get("measurable"),
        achievable=draft.get("achievable"),
        relevant=draft.get("relevant"),
        time_bound=draft.get("time_bound"),
        status=status,
        source_ref=source_ref,
    )
    session.add(goal)
    await session.commit()
    await session.refresh(goal)
    return goal


# --- Согласие на обработку ПДн (consent_record) ----------------------------

async def add_consent_record(
    session: AsyncSession, telegram_id: int, doc_version: str, status: str
) -> ConsentRecord:
    record = ConsentRecord(telegram_id=telegram_id, doc_version=doc_version, status=status)
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


async def latest_consent_record(
    session: AsyncSession, telegram_id: int
) -> ConsentRecord | None:
    return await session.scalar(
        select(ConsentRecord)
        .where(ConsentRecord.telegram_id == telegram_id)
        .order_by(ConsentRecord.id.desc())
        .limit(1)
    )


# --- Права субъекта: /my_data, /forget_me ----------------------------------

async def collect_my_data(session: AsyncSession, telegram_id: int) -> dict:
    """Сводка данных пользователя для /my_data."""
    role = await get_role_by_tg(session, telegram_id)
    student = await get_student_by_tg(session, telegram_id)
    consent = await latest_consent_record(session, telegram_id)
    data: dict = {
        "telegram_id": telegram_id,
        "role": role,
        "consent_status": consent.status if consent else None,
        "consent_version": consent.doc_version if consent else None,
        "has_profile": student is not None,
    }
    if student is not None:
        attrs = await session.scalar(
            select(func.count()).select_from(ProfileAttribute).where(
                ProfileAttribute.student_id == student.id
            )
        )
        msgs = await session.scalar(
            select(func.count()).select_from(ConversationMessage).where(
                ConversationMessage.student_id == student.id
            )
        )
        goals = await list_goals(session, student.id)
        data.update(
            attributes_count=attrs or 0,
            messages_count=msgs or 0,
            goals=[g.title for g in goals],
        )
    return data


async def forget_me(session: AsyncSession, telegram_id: int) -> None:
    """Удаляет персональные данные пользователя (152-ФЗ, /forget_me).

    Удаляется студенческая запись (каскадом — профиль, цели, сообщения);
    имя в реестре ролей обезличивается. Записи consent_record сохраняются как
    аудит-след, event_log/feedback обезличиваются (student_id → NULL по FK).
    Роль (app_user) не удаляется, чтобы не ломать доступ; при желании её снимут
    в веб-панели.
    """
    student = await get_student_by_tg(session, telegram_id)
    if student is not None:
        await session.delete(student)  # каскад по FK на дочерние таблицы
    app_user = await get_app_user_by_tg(session, telegram_id)
    if app_user is not None:
        app_user.full_name = None
    await session.commit()


# --- Обратная связь (feedback) ---------------------------------------------

async def add_feedback(
    session: AsyncSession,
    telegram_id: int,
    rating: str,
    context: str = "menu",
    comment: str | None = None,
    student_id: int | None = None,
    ref_id: int | None = None,
) -> Feedback:
    fb = Feedback(
        telegram_id=telegram_id,
        student_id=student_id,
        rating=rating,
        context=context,
        comment=comment,
        ref_id=ref_id,
    )
    session.add(fb)
    await session.commit()
    await session.refresh(fb)
    return fb


async def set_feedback_comment(session: AsyncSession, feedback_id: int, comment: str) -> None:
    fb = await session.get(Feedback, feedback_id)
    if fb is not None:
        fb.comment = comment[:2000]
        await session.commit()


async def list_feedback(session: AsyncSession, limit: int = 200) -> list[Feedback]:
    result = await session.scalars(
        select(Feedback).order_by(Feedback.id.desc()).limit(limit)
    )
    return list(result.all())


# --- Модуль наставника: привязка, подтверждение целей ----------------------

async def set_app_user_mentor(session: AsyncSession, user_id: int, mentor_tg: int | None) -> None:
    """Закрепить (или снять) наставника за студентом в реестре ролей."""
    user = await session.get(AppUser, user_id)
    if user is not None:
        user.mentor_tg = mentor_tg
        await session.commit()


async def list_mentors(session: AsyncSession) -> list[AppUser]:
    result = await session.scalars(
        select(AppUser).where(AppUser.role == "mentor").order_by(AppUser.full_name, AppUser.id)
    )
    return list(result.all())


async def list_students_of_mentor(session: AsyncSession, mentor_tg: int) -> list[AppUser]:
    """Студенты (записи реестра ролей), закреплённые за наставником."""
    result = await session.scalars(
        select(AppUser)
        .where(AppUser.role == "student", AppUser.mentor_tg == mentor_tg)
        .order_by(AppUser.full_name, AppUser.id)
    )
    return list(result.all())


async def get_goal(session: AsyncSession, goal_id: int) -> Goal | None:
    return await session.get(Goal, goal_id)


async def set_goal_confirm(
    session: AsyncSession, goal_id: int, status: str, comment: str | None = None
) -> Goal | None:
    """Наставник подтвердил (confirmed) или отклонил (rejected) цель."""
    goal = await session.get(Goal, goal_id)
    if goal is None:
        return None
    goal.confirm_status = status
    goal.mentor_comment = comment
    goal.confirmed_at = datetime.now(timezone.utc) if status == "confirmed" else None
    await session.commit()
    await session.refresh(goal)
    return goal


async def set_goal_irrelevant(session: AsyncSession, goal_id: int, note: str | None) -> None:
    """Актуализация: студент отметил, что цель больше не актуальна."""
    goal = await session.get(Goal, goal_id)
    if goal is not None:
        goal.status = "dropped"
        goal.relevance_note = note
        await session.commit()


# --- Настройки периода (app_setting) ---------------------------------------

async def get_setting(session: AsyncSession, key: str) -> str | None:
    row = await session.get(AppSetting, key)
    return row.value if row is not None else None


async def set_setting(session: AsyncSession, key: str, value: str | None) -> None:
    row = await session.get(AppSetting, key)
    if row is None:
        session.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    await session.commit()


# --- Рефлексия (reflection_session / goal_reflection) ----------------------

async def create_reflection_session(session: AsyncSession, student_id: int) -> ReflectionSession:
    rs = ReflectionSession(student_id=student_id)
    session.add(rs)
    await session.commit()
    await session.refresh(rs)
    return rs


async def add_goal_reflection(
    session: AsyncSession, session_id: int, goal_id: int, outcome: str, answers: dict
) -> GoalReflection:
    gr = GoalReflection(session_id=session_id, goal_id=goal_id, outcome=outcome, answers=answers)
    session.add(gr)
    await session.commit()
    await session.refresh(gr)
    return gr


async def complete_reflection_session(
    session: AsyncSession, session_id: int, student_patterns: str | None, ai_summary: str | None
) -> None:
    rs = await session.get(ReflectionSession, session_id)
    if rs is not None:
        rs.student_patterns = student_patterns
        rs.ai_summary = ai_summary
        rs.completed_at = datetime.now(timezone.utc)
        await session.commit()


async def latest_completed_reflection(
    session: AsyncSession, student_id: int
) -> ReflectionSession | None:
    result = await session.scalars(
        select(ReflectionSession)
        .where(ReflectionSession.student_id == student_id, ReflectionSession.completed_at.is_not(None))
        .order_by(ReflectionSession.completed_at.desc())
        .limit(1)
    )
    return result.first()


async def list_goal_reflections(session: AsyncSession, session_id: int) -> list[GoalReflection]:
    result = await session.scalars(
        select(GoalReflection).where(GoalReflection.session_id == session_id).order_by(GoalReflection.id)
    )
    return list(result.all())


async def set_reflection_reminded(session: AsyncSession, student: Student) -> None:
    student.reflection_reminded_at = datetime.now(timezone.utc)
    await session.commit()


async def list_students_for_reminder(session: AsyncSession) -> list[Student]:
    """Студенты с согласием, которым напоминание о рефлексии ещё не отправлялось."""
    result = await session.scalars(
        select(Student).where(
            Student.consent_at.is_not(None), Student.reflection_reminded_at.is_(None)
        )
    )
    return list(result.all())


# --- Сводка для руководителя -----------------------------------------------

async def director_stats(session: AsyncSession) -> list[dict]:
    """По каждому студенту: наставник, цели и их подтверждение, рефлексия.

    Возвращает список словарей — удобно для шаблона панели.
    """
    users = await session.scalars(
        select(AppUser).where(AppUser.role == "student").order_by(AppUser.full_name, AppUser.id)
    )
    mentors = {m.telegram_id: m for m in await list_mentors(session)}
    rows: list[dict] = []
    for u in users.all():
        student = await get_student_by_tg(session, u.telegram_id)
        goals = await list_goals(session, student.id) if student else []
        refl = await latest_completed_reflection(session, student.id) if student else None
        first_goal_at = min((g.created_at for g in goals), default=None)
        mentor = mentors.get(u.mentor_tg) if u.mentor_tg else None
        rows.append({
            "user": u,
            "mentor": mentor,
            "has_consent": bool(student and student.consent_at),
            "goals_total": len(goals),
            "goals_confirmed": sum(1 for g in goals if g.confirm_status == "confirmed"),
            "goals_rejected": sum(1 for g in goals if g.confirm_status == "rejected"),
            "goals_pending": sum(1 for g in goals if g.confirm_status == "pending"),
            "first_goal_at": first_goal_at,
            "reflection_done_at": refl.completed_at if refl else None,
        })
    return rows
