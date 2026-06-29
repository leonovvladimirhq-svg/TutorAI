"""Идемпотентный сид тестовых профилей.

Для демонстрации (см. план, п.5): 3 профиля с паролями. Профили 2 и 3 имеют
одинаковый пароль — поэтому вход построен как «выбор профиля → пароль».
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Student
from app.services.security import hash_password

logger = logging.getLogger(__name__)

# (метка профиля, пароль)
TEST_PROFILES: list[tuple[str, str]] = [
    ("Профиль 1", "12345"),
    ("Профиль 2", "ABCD"),
    ("Профиль 3", "ABCD"),
]


async def seed_profiles(session: AsyncSession) -> None:
    """Создаёт отсутствующие тестовые профили. Безопасно вызывать многократно."""
    created = 0
    for label, password in TEST_PROFILES:
        exists = await session.scalar(select(Student).where(Student.profile_label == label))
        if exists is None:
            session.add(Student(profile_label=label, password_hash=hash_password(password)))
            created += 1
    if created:
        await session.commit()
        logger.info("Сид: создано профилей — %d", created)
    else:
        logger.info("Сид: все тестовые профили уже существуют")
