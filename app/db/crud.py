"""Часто используемые операции с БД."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AppUser, ConversationMessage, Goal, ProfileAttribute, Student


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
