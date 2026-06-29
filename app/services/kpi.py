"""Базовые KPI прототипа (план §7): простые измеримые показатели.

- доля целей, оформленных по SMART (все 5 компонентов);
- полнота и подтверждённость профиля;
- вовлечённость (активные за 7 дней, использование голоса, входы).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EventLog, Goal, ProfileAttribute, Student
from app.domain.profile_schema import PROFILE_BLOCK_KEYS


def _pct(part: int, whole: int) -> int:
    return round(100 * part / whole) if whole else 0


async def compute(session: AsyncSession) -> dict:
    students = list(await session.scalars(select(Student).where(Student.consent_at.is_not(None))))
    students_total = len(students)

    # полнота профиля: средняя доля проработанных блоков
    total_blocks = len(PROFILE_BLOCK_KEYS)
    if students_total:
        done_shares = [
            sum(1 for v in (s.profiling_progress or {}).values() if v == "done") / total_blocks
            for s in students
        ]
        avg_blocks_done = round(100 * sum(done_shares) / students_total)
    else:
        avg_blocks_done = 0

    attrs_total = await session.scalar(select(func.count(ProfileAttribute.id))) or 0
    attrs_ok = await session.scalar(
        select(func.count(ProfileAttribute.id)).where(
            ProfileAttribute.status.in_(["confirmed", "edited"])
        )
    ) or 0

    goals = list(await session.scalars(select(Goal)))
    goals_total = len(goals)
    goals_smart = sum(1 for g in goals if g.is_complete())
    goals_progress = sum(1 for g in goals if g.progress and g.progress > 0)

    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    active_7d = await session.scalar(
        select(func.count(func.distinct(EventLog.student_id))).where(EventLog.created_at >= week_ago)
    ) or 0
    logins = await session.scalar(
        select(func.count(EventLog.id)).where(EventLog.type == "auth_success")
    ) or 0
    voice_uses = await session.scalar(
        select(func.count(EventLog.id)).where(EventLog.type == "voice_recognized")
    ) or 0

    return {
        "students_total": students_total,
        "avg_blocks_done": avg_blocks_done,
        "attrs_total": attrs_total,
        "attrs_confirmed_share": _pct(attrs_ok, attrs_total),
        "goals_total": goals_total,
        "goals_smart_share": _pct(goals_smart, goals_total),
        "goals_progress_share": _pct(goals_progress, goals_total),
        "active_7d": active_7d,
        "logins": logins,
        "voice_uses": voice_uses,
    }


def format_kpi(d: dict) -> str:
    return (
        "📊 <b>KPI прототипа</b>\n\n"
        f"Студентов (с согласием): <b>{d['students_total']}</b>\n"
        f"Средняя заполненность профиля: <b>{d['avg_blocks_done']}%</b>\n"
        f"Атрибутов профиля: <b>{d['attrs_total']}</b> "
        f"(подтверждённых: {d['attrs_confirmed_share']}%)\n\n"
        f"Целей всего: <b>{d['goals_total']}</b>\n"
        f"Доля целей по SMART: <b>{d['goals_smart_share']}%</b>\n"
        f"Целей с прогрессом: <b>{d['goals_progress_share']}%</b>\n\n"
        f"Активных за 7 дней: <b>{d['active_7d']}</b>\n"
        f"Входов: <b>{d['logins']}</b> · голосовых: <b>{d['voice_uses']}</b>"
    )
