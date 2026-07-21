"""Согласие на обработку ПДн (152-ФЗ): версия, краткое содержание, проверка актуальности.

Единый источник правды по согласию. Актуальность определяется последней записью
в ``consent_record`` со статусом ``accepted`` для текущей версии документа.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import crud

# Текущая версия документа. При изменении текста согласия — поднять версию,
# бот пере-запросит согласие у всех пользователей.
CONSENT_VERSION = "consent_tutorai_v1"

# Полный текст согласия (отправляется пользователю файлом .md).
CONSENT_DOC_PATH = Path(__file__).resolve().parent.parent / "legal" / f"{CONSENT_VERSION}.md"

STATUS_ACCEPTED = "accepted"
STATUS_DECLINED = "declined"
STATUS_REVOKED = "revoked"


def summary() -> dict[str, str]:
    """Поля для «краткого содержания» согласия (экран 2)."""
    return {
        "operator": settings.operator_name,
        "processing": "профиль, цели по SMART, диалог, аудио голосовых",
        "storage": settings.data_storage,
        "retention": "до отзыва — команда /forget_me",
        "version": CONSENT_VERSION,
    }


async def latest_consent(session: AsyncSession, telegram_id: int):
    return await crud.latest_consent_record(session, telegram_id)


async def needs_consent(session: AsyncSession, telegram_id: int) -> bool:
    """True, если у пользователя нет актуального согласия на текущую версию."""
    record = await crud.latest_consent_record(session, telegram_id)
    if record is None:
        return True
    return not (record.status == STATUS_ACCEPTED and record.doc_version == CONSENT_VERSION)


async def record_consent(session: AsyncSession, telegram_id: int, status: str) -> None:
    """Зафиксировать акт согласия/отказа/отзыва по текущей версии документа."""
    await crud.add_consent_record(session, telegram_id, CONSENT_VERSION, status)
