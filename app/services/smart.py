"""SMART-цели: каталог направлений, оценка цели студента и коучинг, генерация черновика.

Методика SMART без модификаций (п.12): Specific, Measurable, Achievable, Relevant, Time-bound.

Ключевой сценарий «Своя цель»: студент формулирует цель своими словами, а система
ОЦЕНИВАЕТ её по каждому критерию SMART и, если чего-то не хватает, коучит студента
(объясняет, что улучшить, и задаёт наводящий вопрос), чтобы он сам довёл цель до SMART.
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

# "/no_think" отключает рассуждения Qwen3 — иначе <think>-блок съедает лимит токенов и
# JSON не успевает сгенерироваться (главная причина «Не удалось сформировать черновик»).
SMART_SYSTEM = (
    "/no_think\n"
    "Вы — наставник, помогающий студенту-первокурснику сформулировать учебную цель "
    "по классической методике SMART (Specific, Measurable, Achievable, Relevant, Time-bound). "
    "На основе намерения студента и его профиля составьте одну реалистичную цель. "
    "Верните СТРОГО JSON: {\"title\": \"...\", \"specific\": \"...\", \"measurable\": \"...\", "
    "\"achievable\": \"...\", \"relevant\": \"...\", \"time_bound\": \"...\"}. "
    "Все поля — на русском, конкретно и кратко. Срок привяжите к учебному модулю или семестру. "
    "Никакого текста кроме JSON."
)

EVALUATE_SYSTEM = (
    "/no_think\n"
    "Вы — наставник по постановке целей. Студент присылает цель своими словами. "
    "Оцените её по каждому критерию SMART (Specific, Measurable, Achievable, Relevant, "
    "Time-bound) в учебно-профессиональном контексте. Для каждого критерия определите, "
    "выполнен ли он (met: true/false), и дайте короткий совет: если критерий выполнен — "
    "как коротко его сформулировать (value); если нет — что именно улучшить и наводящий "
    "вопрос, помогающий студенту доформулировать самому (advice). Не переписывайте цель за "
    "студента целиком — направляйте его. Если цель не относится к учёбе/профессиональному "
    "развитию, мягко отметьте это в relevant и помогите повернуть её в учебную плоскость. "
    "Верните СТРОГО JSON вида: {\"title\": \"<краткое название цели>\", \"components\": {"
    "\"specific\": {\"met\": <bool>, \"value\": \"<кратко>\", \"advice\": \"<совет+вопрос>\"}, "
    "\"measurable\": {...}, \"achievable\": {...}, \"relevant\": {...}, \"time_bound\": {...}}, "
    "\"comment\": \"<короткий общий комментарий>\"}. Все тексты — на русском. Никакого текста кроме JSON."
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
    """Сгенерировать SMART-черновик цели из намерения студента (для шаблонных целей)."""
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
        parsed = await llm.chat_json(messages, max_tokens=1500)
    except Exception:  # noqa: BLE001
        logger.exception("Ошибка генерации SMART-цели")
        return None

    if not isinstance(parsed, dict):
        return None
    draft = {"title": str(parsed.get("title", intent)).strip()[:255]}
    for c in SMART_COMPONENTS:
        draft[c] = str(parsed.get(c, "")).strip()[:1000]
    return draft


async def evaluate_goal(
    session: AsyncSession, student_id: int, goal_text: str
) -> dict | None:
    """Оценить сформулированную студентом цель по SMART.

    Возвращает нормализованный словарь:
    {
        "title": str,
        "is_smart": bool,
        "components": {comp: {"met": bool, "value": str, "advice": str}},
        "comment": str,
    }
    или None, если модель не ответила корректно.
    """
    summary = await memory.profile_summary(session, student_id)
    messages = [
        {"role": "system", "content": EVALUATE_SYSTEM},
        {"role": "system", "content": f"Профиль студента:\n{summary}"},
        {"role": "user", "content": f"Цель студента: {goal_text}"},
    ]
    try:
        parsed = await llm.chat_json(messages, max_tokens=1500)
    except Exception:  # noqa: BLE001
        logger.exception("Ошибка оценки SMART-цели")
        return None

    if not isinstance(parsed, dict):
        return None
    raw_components = parsed.get("components")
    if not isinstance(raw_components, dict):
        return None

    components: dict[str, dict] = {}
    all_met = True
    for c in SMART_COMPONENTS:
        item = raw_components.get(c)
        if not isinstance(item, dict):
            item = {}
        met = bool(item.get("met", False))
        components[c] = {
            "met": met,
            "value": str(item.get("value", "")).strip()[:1000],
            "advice": str(item.get("advice", "")).strip()[:1000],
        }
        all_met = all_met and met

    return {
        "title": str(parsed.get("title", goal_text)).strip()[:255] or goal_text[:255],
        "is_smart": all_met,
        "components": components,
        "comment": str(parsed.get("comment", "")).strip()[:1000],
    }


def draft_from_evaluation(evaluation: dict) -> dict:
    """Собирает черновик цели (для сохранения) из подтверждённой SMART-оценки."""
    draft = {"title": evaluation.get("title", "Цель")[:255]}
    for c in SMART_COMPONENTS:
        draft[c] = str(evaluation["components"].get(c, {}).get("value", "")).strip()[:1000]
    return draft
