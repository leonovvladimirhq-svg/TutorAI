"""Начальная инициализация БД.

Вход в бота — по роли из app_user (роли назначает академ. руководитель в веб-панели),
поэтому тестовые профили с паролями больше не создаются. Опционально можно назначить
первого академического руководителя через переменную окружения BOOTSTRAP_DIRECTOR_TG
(Telegram ID) — чтобы было кому зайти в систему на старте.
"""
from __future__ import annotations

import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import crud
from app.services.roles import ROLE_DIRECTOR

logger = logging.getLogger(__name__)


async def seed_profiles(session: AsyncSession) -> None:
    """Идемпотентный сид. Назначает bootstrap-руководителя, если задан env."""
    raw = os.getenv("BOOTSTRAP_DIRECTOR_TG", "").strip()
    if not raw:
        logger.info("Сид: BOOTSTRAP_DIRECTOR_TG не задан — пропускаю")
        return
    try:
        tg_id = int(raw)
    except ValueError:
        logger.warning("Сид: BOOTSTRAP_DIRECTOR_TG=%r не является числом", raw)
        return
    existing = await crud.get_app_user_by_tg(session, tg_id)
    if existing is None:
        await crud.add_app_user(session, tg_id, ROLE_DIRECTOR, "Академический руководитель")
        logger.info("Сид: назначен академический руководитель (tg_id=%s)", tg_id)
    else:
        logger.info("Сид: роль для tg_id=%s уже существует (%s)", tg_id, existing.role)
