"""Сборка контекста для LLM: сводка профиля + недавняя история диалога."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ConversationMessage, ProfileAttribute
from app.domain.profile_schema import PROFILE_BLOCKS_BY_KEY


async def profile_summary(session: AsyncSession, student_id: int) -> str:
    """Текстовая сводка подтверждённого/отредактированного профиля по блокам."""
    rows = await session.scalars(
        select(ProfileAttribute)
        .where(
            ProfileAttribute.student_id == student_id,
            ProfileAttribute.status.in_(["confirmed", "edited"]),
        )
        .order_by(ProfileAttribute.block, ProfileAttribute.id)
    )
    by_block: dict[str, list[str]] = {}
    for attr in rows:
        by_block.setdefault(attr.block, []).append(f"{attr.key}: {attr.value}")

    if not by_block:
        return "(профиль пока пуст)"

    parts: list[str] = []
    for block_key, items in by_block.items():
        title = PROFILE_BLOCKS_BY_KEY[block_key].title if block_key in PROFILE_BLOCKS_BY_KEY else block_key
        parts.append(f"{title}:\n" + "\n".join(f"  • {i}" for i in items))
    return "\n".join(parts)


async def recent_messages(
    session: AsyncSession, student_id: int, limit: int = 10
) -> list[dict[str, str]]:
    """Последние реплики диалога в формате сообщений LLM (хронологически)."""
    rows = await session.scalars(
        select(ConversationMessage)
        .where(ConversationMessage.student_id == student_id)
        .order_by(ConversationMessage.id.desc())
        .limit(limit)
    )
    msgs = list(rows)[::-1]
    out: list[dict[str, str]] = []
    for m in msgs:
        role = "assistant" if m.role == "assistant" else "user"
        out.append({"role": role, "content": m.content})
    return out
