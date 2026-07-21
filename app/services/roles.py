"""Роли пользователей TutorAI.

Роль привязана к Telegram ID и назначается в веб-панели (`app/web`). Четыре роли:
- ``student``        — студент (проходит профайлинг, ставит цели);
- ``mentor``         — наставник (сопровождает студентов);
- ``director``       — академический руководитель (общий контроль, делегирует);
- ``administrator``  — администратор (операционные задачи: добавить/убрать/изменить).
"""
from __future__ import annotations

ROLE_STUDENT = "student"
ROLE_MENTOR = "mentor"
ROLE_DIRECTOR = "director"
ROLE_ADMIN = "administrator"

ROLES = (ROLE_STUDENT, ROLE_MENTOR, ROLE_DIRECTOR, ROLE_ADMIN)

# Человекочитаемые названия ролей (RU) — для приветствия в боте и веб-панели.
ROLE_LABELS: dict[str, str] = {
    ROLE_STUDENT: "Студент",
    ROLE_MENTOR: "Наставник",
    ROLE_DIRECTOR: "Академический руководитель",
    ROLE_ADMIN: "Администратор",
}

# Зачем нужна каждая роль — контекст для панели администрирования.
ROLE_DESCRIPTIONS: dict[str, str] = {
    ROLE_STUDENT: "Проходит профайлинг, ставит цели по SMART и следит за прогрессом в боте.",
    ROLE_MENTOR: "Сопровождает студентов, видит агрегированный «пульс группы».",
    ROLE_DIRECTOR: "Академический руководитель: общий контроль; операционные задачи делегирует.",
    ROLE_ADMIN: "Администратор: операционные задачи — добавить, убрать, изменить роли и данные.",
}


def role_label(role: str) -> str:
    """Название роли по-русски (или сам код, если роль неизвестна)."""
    return ROLE_LABELS.get(role, role)


def role_description(role: str) -> str:
    return ROLE_DESCRIPTIONS.get(role, "")


def is_valid_role(role: str) -> bool:
    return role in ROLES
