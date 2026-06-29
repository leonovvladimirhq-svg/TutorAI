"""Часто используемые операции с БД."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Student


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
