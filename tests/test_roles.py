"""Тесты помощников ролей и сборки черновика из SMART-оценки."""
from __future__ import annotations

from app.services import smart
from app.services.roles import (
    ROLE_ADMIN,
    ROLE_DIRECTOR,
    ROLE_MENTOR,
    ROLE_STUDENT,
    ROLES,
    is_valid_role,
    role_description,
    role_label,
)


def test_role_labels_ru():
    assert role_label(ROLE_STUDENT) == "Студент"
    assert role_label(ROLE_MENTOR) == "Наставник"
    assert role_label(ROLE_DIRECTOR) == "Академический руководитель"
    assert role_label(ROLE_ADMIN) == "Администратор"


def test_role_label_unknown_passthrough():
    assert role_label("unknown") == "unknown"


def test_is_valid_role():
    assert is_valid_role(ROLE_STUDENT)
    assert is_valid_role(ROLE_ADMIN)
    assert not is_valid_role("teacher")


def test_all_roles_have_descriptions():
    assert len(ROLES) == 4
    for r in ROLES:
        assert role_description(r)  # непустое описание для каждой роли


def test_draft_from_evaluation():
    evaluation = {
        "title": "Повысить балл по матанализу",
        "is_smart": True,
        "components": {c: {"met": True, "value": f"val-{c}", "advice": ""} for c in smart.SMART_COMPONENTS},
        "comment": "",
    }
    draft = smart.draft_from_evaluation(evaluation)
    assert draft["title"] == "Повысить балл по матанализу"
    assert draft["specific"] == "val-specific"
    assert draft["time_bound"] == "val-time_bound"
    # черновик должен быть полным по SMART
    assert smart.validate(draft) == []
