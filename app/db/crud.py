"""Часто используемые операции с БД."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ConversationMessage, ProfileAttribute, Student


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
