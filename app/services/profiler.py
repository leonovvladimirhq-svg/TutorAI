"""Профайлер: коучинговый вопрос + извлечение фактов (extract → confirm → commit).

Принцип (план §3): в профиль попадает только то, что подтвердил студент.
Извлечение — отдельный лёгкий вызов LLM; коммит — после подтверждения в диалоге.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.profile_schema import PROFILE_BLOCK_KEYS, ProfileBlock
from app.services import llm, memory

logger = logging.getLogger(__name__)

MAX_TURNS_PER_BLOCK = 2

COACH_SYSTEM = (
    "Вы — TutorAI, доброжелательный ИИ-наставник студента-первокурсника. "
    "Стиль — тёплый, коучинговый, поддерживающий. Обращайтесь к студенту строго на «Вы». "
    "Ваша задача — помочь студенту раскрыть себя и собрать учебно-карьерный профиль. "
    "Задавайте по одному короткому, конкретному вопросу за раз. Не повторяйте уже заданное, "
    "опирайтесь на то, что студент уже рассказал. Не выдумывайте за студента факты. "
    "Пишите только текст вопроса, без префиксов и пояснений."
)

EXTRACT_SYSTEM = (
    "Вы извлекаете факты о студенте из его реплики для структурированного профиля. "
    "Верните СТРОГО JSON вида: "
    '{"facts": [{"block": "<ключ блока>", "key": "<короткий_снейк_кейс>", '
    '"value": "<кратко по-русски>", "confidence": <0..1>}]}. '
    "Допустимые ключи блока: " + ", ".join(PROFILE_BLOCK_KEYS) + ". "
    "Извлекайте только явно сказанное. Если фактов нет — верните {\"facts\": []}. "
    "Никакого текста кроме JSON."
)


async def next_coach_question(
    session: AsyncSession, student_id: int, block: ProfileBlock
) -> str:
    """Сформулировать следующий вопрос по текущему блоку профиля."""
    summary = await memory.profile_summary(session, student_id)
    history = await memory.recent_messages(session, student_id, limit=10)

    messages = [{"role": "system", "content": COACH_SYSTEM}]
    messages.append({
        "role": "system",
        "content": f"Уже известно о студенте:\n{summary}",
    })
    messages.extend(history)
    messages.append({
        "role": "system",
        "content": (
            f"Сейчас сфокусируйтесь на теме «{block.title}» ({block.description}). "
            "Задайте один короткий вопрос по этой теме."
        ),
    })

    try:
        question = await llm.chat(messages, max_tokens=200)
        if question:
            return question
    except Exception:  # noqa: BLE001
        logger.exception("Ошибка генерации вопроса, использую запасной")

    # запасной вариант — из таксономии
    return block.sample_questions[0] if block.sample_questions else f"Расскажите про: {block.title}."


async def extract_facts(answer: str, question: str | None = None) -> list[dict]:
    """Извлечь факты-кандидаты из реплики студента."""
    user_content = answer if not question else f"Вопрос: {question}\nОтвет студента: {answer}"
    messages = [
        {"role": "system", "content": EXTRACT_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    try:
        parsed = await llm.chat_json(messages, max_tokens=600)
    except Exception:  # noqa: BLE001
        logger.exception("Ошибка извлечения фактов")
        return []

    if not isinstance(parsed, dict):
        return []
    facts = parsed.get("facts", [])
    if not isinstance(facts, list):
        return []

    clean: list[dict] = []
    for f in facts:
        if not isinstance(f, dict):
            continue
        block = str(f.get("block", "")).strip()
        key = str(f.get("key", "")).strip()
        value = str(f.get("value", "")).strip()
        if block not in PROFILE_BLOCK_KEYS or not key or not value:
            continue
        try:
            confidence = float(f.get("confidence", 0.7))
        except (TypeError, ValueError):
            confidence = 0.7
        clean.append({
            "block": block,
            "key": key[:128],
            "value": value[:500],
            "confidence": max(0.0, min(1.0, confidence)),
        })
    return clean
