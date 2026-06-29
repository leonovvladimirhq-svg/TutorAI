"""Тест извлечения JSON из ответов модели."""
from __future__ import annotations

from app.services.llm import extract_json


def test_plain_json_object():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_json_in_code_fence():
    raw = '```json\n{"facts": [{"key": "course", "value": "1"}]}\n```'
    assert extract_json(raw) == {"facts": [{"key": "course", "value": "1"}]}


def test_json_with_surrounding_text():
    raw = 'Вот результат: [{"x": 1}] — готово.'
    assert extract_json(raw) == [{"x": 1}]


def test_unparseable_returns_none():
    assert extract_json("просто текст без json") is None
