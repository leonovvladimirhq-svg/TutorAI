"""Логирование событий в event_log (основа для KPI)."""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EventLog

logger = logging.getLogger(__name__)


async def log_event(
    session: AsyncSession,
    student_id: int | None,
    event_type: str,
    payload: dict | None = None,
) -> None:
    """Пишет событие в event_log. Не должно ронять основной поток."""
    try:
        session.add(EventLog(student_id=student_id, type=event_type, payload=payload or {}))
        await session.commit()
    except Exception:  # noqa: BLE001 — событие не должно ломать пользовательский флоу
        logger.exception("Не удалось записать событие %s", event_type)
        await session.rollback()
