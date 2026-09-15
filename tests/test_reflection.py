"""Инварианты рефлексии по требованиям заказчика (п. 3.3)."""
import asyncio

from app.services import reflection as r


def test_questions_cover_customer_requirements():
    keys = [k for k, _ in r.QUESTIONS]
    # обязательный по протоколу вопрос «за счёт чего получилось»
    assert "thanks_to" in keys
    # раскрывающие вопросы: что конкретно, что иначе, самооценка/оценка наставника, похвала
    for k in ("what_done", "why", "differently", "self_assess", "praise"):
        assert k in keys
    assert set(keys) == set(r.QUESTION_LABELS)


def test_outcomes_include_irrelevant():
    # актуализация: цель могла потерять актуальность
    assert "irrelevant" in r.OUTCOME_LABELS
    assert set(r.OUTCOME_LABELS) == {"achieved", "partial", "not_achieved", "irrelevant"}


def test_short_answer_is_probed_without_llm():
    # отписка «достиг» отсекается локально, без обращения к модели
    ok, probe = asyncio.run(r.check_substantive("Что получилось?", "достиг"))
    assert ok is False and probe


def test_patterns_prompt_asks_student_first():
    # порядок: сначала студент сам формулирует, потом ИИ
    assert "потом" in r.PATTERNS_PROMPT.lower() or "затем" in r.PATTERNS_PROMPT.lower()
