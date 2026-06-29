"""Тест валидации SMART-целей."""
from __future__ import annotations

from app.services import smart


def test_validate_complete():
    draft = {
        "title": "Подтянуть успеваемость",
        "specific": "повысить балл по матанализу",
        "measurable": "с 6 до 8",
        "achievable": "2 часа практики в неделю",
        "relevant": "важно для стипендии",
        "time_bound": "к концу 2 модуля",
    }
    assert smart.validate(draft) == []


def test_validate_missing():
    draft = {"title": "Цель", "specific": "что-то", "measurable": "", "achievable": "да"}
    missing = smart.validate(draft)
    assert "measurable" in missing
    assert "relevant" in missing
    assert "time_bound" in missing
    assert "specific" not in missing
