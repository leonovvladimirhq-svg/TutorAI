"""SMART-цели: дефолтный каталог под первокурсника, генерация и валидация.

Используется классическая методика SMART без модификаций (п.12):
Specific, Measurable, Achievable, Relevant, Time-bound.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import llm, memory

logger = logging.getLogger(__name__)

SMART_COMPONENTS = ["specific", "measurable", "achievable", "relevant", "time_bound"]

# Типовые направления целей для студента 1 курса (заголовок + подсказка для модели).
DEFAULT_GOALS: list[dict[str, str]] = [
    {"title": "Подтянуть успеваемость в первом модуле",
     "hint": "повышение среднего балла по ключевым дисциплинам"},
    {"title": "Развить навык публичных выступлений",
     "hint": "регулярная практика презентаций и обратная связь"},
    {"title": "Освоить базовый рабочий инструмент",
     "hint": "например, Excel, Figma или инструмент по профилю программы"},
    {"title": "Влиться в студенческое сообщество",
     "hint": "участие в студенческой организации, проекте или мероприятии"},
    {"title": "Определиться с карьерным направлением",
     "hint": "исследование сфер, встречи/беседы, пробные задачи"},
]

SMART_SYSTEM = (
    "Вы — наставник, помогающий студенту-первокурснику сформулировать учебную цель "
    "по классической методике SMART (Specific, Measurable, Achievable, Relevant, Time-bound). "
    "На основе намерения студента и его профиля составьте одну реалистичную цель. "
    "Верните СТРОГО JSON: {\"title\": \"...\", \"specific\": \"...\", \"measurable\": \"...\", "
    "\"achievable\": \"...\", \"relevant\": \"...\", \"time_bound\": \"...\"}. "
    "Все поля — на русском, конкретно и кратко. Срок привяжите к учебному модулю или семестру. "
    "Никакого текста кроме JSON."
)


def validate(draft: dict) -> list[str]:
    """Возвращает список незаполненных SMART-компонентов."""
    return [c for c in SMART_COMPONENTS if not str(draft.get(c, "")).strip()]


async def draft_goal(
    session: AsyncSession,
    student_id: int,
    intent: str,
    feedback: str | None = None,
    previous: dict | None = None,
) -> dict | None:
    """Сгенерировать SMART-черновик цели из намерения студента (+ обратной связи)."""
    summary = await memory.profile_summary(session, student_id)
    messages = [
        {"role": "system", "content": SMART_SYSTEM},
        {"role": "system", "content": f"Профиль студента:\n{summary}"},
    ]
    user = f"Намерение студента: {intent}"
    if previous:
        user += f"\nПредыдущий черновик: {previous}"
    if feedback:
        user += f"\nЧто поправить: {feedback}"
    messages.append({"role": "user", "content": user})

    try:
        parsed = await llm.chat_json(messages, max_tokens=700)
    except Exception:  # noqa: BLE001
        logger.exception("Ошибка генерации SMART-цели")
        return None

    if not isinstance(parsed, dict):
        return None
    draft = {"title": str(parsed.get("title", intent)).strip()[:255]}
    for c in SMART_COMPONENTS:
        draft[c] = str(parsed.get(c, "")).strip()[:1000]
    return draft
