"""Тест извлечения JSON из ответов модели."""
from __future__ import annotations

from app.services.llm import extract_json, strip_reasoning


def test_plain_json_object():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_strip_reasoning_block():
    raw = "<think>надо вернуть JSON {а тут скобки}</think>\n{\"title\": \"Цель\"}"
    assert strip_reasoning(raw) == '{"title": "Цель"}'
    assert extract_json(raw) == {"title": "Цель"}


def test_strip_unclosed_reasoning():
    # <think> без закрытия (ответ обрезан по лимиту токенов) — JSON недоступен, None
    raw = "<think>рассуждаю и не успел закрыть"
    assert strip_reasoning(raw) == ""
    assert extract_json(raw) is None


def test_json_after_think_with_code_fence():
    raw = '<think>считаю…</think>\n```json\n{"is_smart": true}\n```'
    assert extract_json(raw) == {"is_smart": True}


def test_json_in_code_fence():
    raw = '```json\n{"facts": [{"key": "course", "value": "1"}]}\n```'
    assert extract_json(raw) == {"facts": [{"key": "course", "value": "1"}]}


def test_json_with_surrounding_text():
    raw = 'Вот результат: [{"x": 1}] — готово.'
    assert extract_json(raw) == [{"x": 1}]


def test_unparseable_returns_none():
    assert extract_json("просто текст без json") is None
