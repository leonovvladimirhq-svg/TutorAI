"""Тест извлечения и фильтрации фактов (LLM замокан)."""
from __future__ import annotations

from app.services import llm, profiler


async def test_extract_facts_filters_and_clamps(monkeypatch):
    async def fake_chat_json(messages, **kwargs):
        return {
            "facts": [
                {"block": "identity", "key": "course", "value": "1 курс", "confidence": 0.9},
                {"block": "bogus", "key": "x", "value": "y", "confidence": 0.5},   # неизвестный блок
                {"block": "skills", "key": "", "value": "z"},                       # пустой ключ
                {"block": "skills", "key": "tool", "value": "Excel", "confidence": 5},  # клампим
            ]
        }

    monkeypatch.setattr(llm, "chat_json", fake_chat_json)
    facts = await profiler.extract_facts("какой-то ответ")

    keys = {(f["block"], f["key"]) for f in facts}
    assert keys == {("identity", "course"), ("skills", "tool")}
    tool = next(f for f in facts if f["key"] == "tool")
    assert tool["confidence"] == 1.0


async def test_extract_facts_handles_empty(monkeypatch):
    async def fake_chat_json(messages, **kwargs):
        return {"facts": []}

    monkeypatch.setattr(llm, "chat_json", fake_chat_json)
    assert await profiler.extract_facts("ничего полезного") == []


async def test_extract_facts_handles_non_dict(monkeypatch):
    async def fake_chat_json(messages, **kwargs):
        return None

    monkeypatch.setattr(llm, "chat_json", fake_chat_json)
    assert await profiler.extract_facts("сломанный ответ") == []
