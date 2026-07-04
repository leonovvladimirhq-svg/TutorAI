"""Роли пользователей TutorAI.

Роль привязана к Telegram ID и назначается академическим руководителем через
веб-панель (`app/web`). Три роли:
- ``student``   — студент (проходит профайлинг, ставит цели);
- ``mentor``    — наставник;
- ``director``  — академический руководитель.
"""
from __future__ import annotations

ROLE_STUDENT = "student"
ROLE_MENTOR = "mentor"
ROLE_DIRECTOR = "director"

ROLES = (ROLE_STUDENT, ROLE_MENTOR, ROLE_DIRECTOR)

# Человекочитаемые названия ролей (RU) — для приветствия в боте и веб-панели.
ROLE_LABELS: dict[str, str] = {
    ROLE_STUDENT: "Студент",
    ROLE_MENTOR: "Наставник",
    ROLE_DIRECTOR: "Академический руководитель",
}


def role_label(role: str) -> str:
    """Название роли по-русски (или сам код, если роль неизвестна)."""
    return ROLE_LABELS.get(role, role)


def is_valid_role(role: str) -> bool:
    return role in ROLES
