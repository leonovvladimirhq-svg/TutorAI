"""Часто используемые операции с БД."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AccessCode,
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
    """Удаляет персональные данные пользователя (152-ФЗ, /forget_me) — полный сброс.

    Удаляется студенческая запись (каскадом — профиль, цели, сообщения, рефлексия)
    и запись в реестре ролей (app_user). Код доступа, по которому человек вошёл,
    освобождается: его можно ввести заново и начать с самого начала — с согласия
    и пустого профиля. Наставник, закреплённый за кодом, при этом сохраняется.
    Записи consent_record остаются как аудит-след (отзыв согласия фиксируется отдельно);
    event_log/feedback обезличиваются (student_id → NULL по FK).
    """
    student = await get_student_by_tg(session, telegram_id)
    if student is not None:
        await session.delete(student)  # каскад по FK на дочерние таблицы
    app_user = await get_app_user_by_tg(session, telegram_id)
    if app_user is not None:
        await session.delete(app_user)
    for code in await session.scalars(select(AccessCode).where(AccessCode.used_by_tg == telegram_id)):
        code.used_by_tg = None
        code.used_at = None
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
    """Закрепить (или снять) наставника за студентом в реестре ролей.

    Привязка дублируется в код доступа, по которому студент вошёл, — чтобы она
    пережила /forget_me и повторный ввод того же кода.
    """
    user = await session.get(AppUser, user_id)
    if user is not None:
        user.mentor_tg = mentor_tg
        for code in await session.scalars(select(AccessCode).where(AccessCode.used_by_tg == user.telegram_id)):
            code.mentor_tg = mentor_tg
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


async def delete_reflection_session(session: AsyncSession, session_id: int) -> None:
    """Убрать пустую сессию (студент завершил досрочно, ничего не ответив)."""
    rs = await session.get(ReflectionSession, session_id)
    if rs is not None:
        await session.delete(rs)
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


# --- Коды доступа (access_code) --------------------------------------------

def _normalize_code(raw: str) -> str:
    """Оставляем только цифры: студент может ввести код с пробелами или дефисами."""
    return "".join(ch for ch in raw if ch.isdigit())


def format_code(code: str) -> str:
    """Читаемый вид кода: группы по 4 цифры."""
    return " ".join(code[i:i + 4] for i in range(0, len(code), 4))


def generate_code() -> str:
    import secrets
    return "".join(str(secrets.randbelow(10)) for _ in range(16))


async def create_access_codes(
    session: AsyncSession, role: str, count: int, label_prefix: str | None = None
) -> list[AccessCode]:
    """Сгенерировать count кодов для роли. label — «Студент 1», «Студент 2»…"""
    existing = await session.scalar(select(func.count()).select_from(AccessCode).where(AccessCode.role == role))
    start = (existing or 0) + 1
    created: list[AccessCode] = []
    for i in range(count):
        code = generate_code()
        while await session.scalar(select(AccessCode).where(AccessCode.code == code)) is not None:
            code = generate_code()
        label = f"{label_prefix} {start + i}" if label_prefix else None
        ac = AccessCode(code=code, role=role, label=label)
        session.add(ac)
        created.append(ac)
    await session.commit()
    for ac in created:
        await session.refresh(ac)
    return created


async def list_access_codes(session: AsyncSession) -> list[AccessCode]:
    result = await session.scalars(select(AccessCode).order_by(AccessCode.role, AccessCode.id))
    return list(result.all())


async def get_access_code(session: AsyncSession, raw: str) -> AccessCode | None:
    code = _normalize_code(raw)
    if len(code) != 16:
        return None
    return await session.scalar(select(AccessCode).where(AccessCode.code == code))


async def redeem_access_code(session: AsyncSession, ac: AccessCode, telegram_id: int, full_name: str | None) -> AppUser:
    """Активировать код: создать/обновить запись в реестре ролей и отметить код использованным.

    Наставник, закреплённый за кодом, переносится в app_user.mentor_tg.
    """
    user = await get_app_user_by_tg(session, telegram_id)
    if user is None:
        user = AppUser(telegram_id=telegram_id, role=ac.role, full_name=full_name)
        session.add(user)
    else:
        user.role = ac.role
        if full_name and not user.full_name:
            user.full_name = full_name
    if ac.role == "student":
        user.mentor_tg = ac.mentor_tg
    ac.used_by_tg = telegram_id
    ac.used_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(user)
    return user


async def set_access_code_mentor(session: AsyncSession, code_id: int, mentor_tg: int | None) -> None:
    """Закрепить наставника за кодом; если код уже активирован — и за пользователем."""
    ac = await session.get(AccessCode, code_id)
    if ac is None:
        return
    ac.mentor_tg = mentor_tg
    if ac.used_by_tg is not None:
        user = await get_app_user_by_tg(session, ac.used_by_tg)
        if user is not None and user.role == "student":
            user.mentor_tg = mentor_tg
    await session.commit()


async def release_access_code(session: AsyncSession, code_id: int) -> None:
    """Освободить код (пользователь при этом не удаляется — для этого есть /forget_me)."""
    ac = await session.get(AccessCode, code_id)
    if ac is not None:
        ac.used_by_tg = None
        ac.used_at = None
        await session.commit()


async def delete_access_code(session: AsyncSession, code_id: int) -> None:
    ac = await session.get(AccessCode, code_id)
    if ac is not None:
        await session.delete(ac)
        await session.commit()
