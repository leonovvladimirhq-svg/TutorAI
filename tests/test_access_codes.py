"""Коды доступа: формат, нормализация ввода, распознавание кода в сообщении."""
import asyncio
from types import SimpleNamespace

from maxapi.types import MessageCreated

from app.db import crud
from app.maxbot.handlers.start import ForgetMeText, LooksLikeCode


def test_generate_code_is_16_digits():
    for _ in range(20):
        code = crud.generate_code()
        assert len(code) == 16 and code.isdigit()


def test_format_code_groups_by_four():
    assert crud.format_code("1234567890123456") == "1234 5678 9012 3456"


def test_normalize_accepts_spaces_and_dashes():
    assert crud._normalize_code(" 1234 5678-9012 3456 ") == "1234567890123456"
    assert crud._normalize_code("abc") == ""


def _msg(text: str):
    # минимальный объект с интерфейсом MessageCreated для фильтров
    ev = MessageCreated.__new__(MessageCreated)
    object.__setattr__(ev, "__dict__", {"message": SimpleNamespace(body=SimpleNamespace(text=text))})
    return ev


def test_looks_like_code_filter():
    f = LooksLikeCode()
    assert asyncio.run(f(_msg("1234 5678 9012 3456"))) is True
    assert asyncio.run(f(_msg("1234-5678-9012-3456"))) is True
    assert asyncio.run(f(_msg("1234567890123456"))) is True
    assert asyncio.run(f(_msg("123456789012345"))) is False       # 15 цифр
    assert asyncio.run(f(_msg("код 1234567890123456"))) is False  # лишний текст
    assert asyncio.run(f(_msg("привет"))) is False


def test_forget_me_text_filter():
    f = ForgetMeText()
    assert asyncio.run(f(_msg("Забыть меня"))) is True
    assert asyncio.run(f(_msg("forget me!"))) is True
    assert asyncio.run(f(_msg("не надо меня забывать"))) is False
