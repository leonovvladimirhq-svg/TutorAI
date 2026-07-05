"""Таксономия цифрового профиля студента.

Определяет блоки профиля и порядок их проработки в коучинговом диалоге.
Профиль — источник истины (см. план §3): каждый атрибут хранится в profile_attribute
с провенансом и статусом подтверждения.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProfileBlock:
    key: str               # машинный ключ блока
    title: str             # человекочитаемое название (RU)
    description: str       # что собираем
    sample_questions: list[str] = field(default_factory=list)


# Порядок = порядок проработки в диалоге профайлинга.
PROFILE_BLOCKS: list[ProfileBlock] = [
    ProfileBlock(
        key="identity",
        title="О себе",
        description="Имя, курс, программа, бэкграунд, откуда пришёл на программу.",
        sample_questions=[
            "Расскажите немного о себе: как Вас зовут, на каком Вы курсе и программе?",
            "Что привело Вас на эту программу?",
        ],
    ),
    ProfileBlock(
        key="skills",
        title="Навыки и компетенции",
        description="Сильные стороны, текущие умения, инструменты, опыт.",
        sample_questions=[
            "Какие навыки Вы считаете своими сильными сторонами?",
            "С какими инструментами или темами Вы уже уверенно работаете?",
        ],
    ),
    ProfileBlock(
        key="interests",
        title="Интересы",
        description="Профессиональные и учебные интересы, темы, которые увлекают.",
        sample_questions=[
            "Какие темы или направления Вам особенно интересны?",
        ],
    ),
    ProfileBlock(
        key="values",
        title="Ценности и мотивация",
        description="Что важно в учёбе и работе, что мотивирует, ради чего учитесь.",
        sample_questions=[
            "Что для Вас важнее всего в учёбе и будущей работе?",
            "Что обычно Вас мотивирует двигаться вперёд?",
        ],
    ),
    ProfileBlock(
        key="career_goals",
        title="Карьерные цели",
        description="Кем видит себя, в какой сфере, горизонт 1–3 года и дальше.",
        sample_questions=[
            "Кем Вы видите себя через пару лет после выпуска?",
        ],
    ),
    ProfileBlock(
        key="learning_goals",
        title="Учебные цели",
        description="Чего хочет достичь в учёбе в этом модуле/году (основа для SMART-целей).",
        sample_questions=[
            "Каких результатов Вы хотите достичь в учёбе в ближайшем модуле?",
        ],
    ),
    ProfileBlock(
        key="constraints",
        title="Организация учёбы",
        description=(
            "Учебная нагрузка, приоритеты, планирование времени, что помогает или мешает "
            "эффективно учиться (в учебном, а не в личном контексте)."
        ),
        sample_questions=[
            "Как Вы обычно организуете учебную нагрузку и расставляете приоритеты в занятиях?",
        ],
    ),
]

PROFILE_BLOCK_KEYS = [b.key for b in PROFILE_BLOCKS]
PROFILE_BLOCKS_BY_KEY = {b.key: b for b in PROFILE_BLOCKS}


def next_block(progress: dict | None) -> ProfileBlock | None:
    """Вернуть следующий непокрытый блок профиля по карте прогресса.

    progress: {block_key: "done" | "in_progress"}; None трактуется как пустой.
    """
    progress = progress or {}
    for block in PROFILE_BLOCKS:
        if progress.get(block.key) != "done":
            return block
    return None
