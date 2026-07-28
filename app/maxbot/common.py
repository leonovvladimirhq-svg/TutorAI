"""Общие хелперы для хендлеров MAX (порт app.bot.common).

Централизуют формат HTML и разницу вызовов: reply — новое сообщение в чат
(работает и для MessageCreated, и для MessageCallback через .message.answer);
edit — правка сообщения, на котором нажата кнопка; ack — подтверждение callback.
"""
from __future__ import annotations

from maxapi.enums import ParseMode

from app.bot import texts
from app.maxbot.keyboards import main_menu_kb


def _atts(kb):
    return [kb] if kb is not None else None


async def reply(event, text: str, kb=None) -> None:
    """Отправить новое сообщение в чат.

    У текстовых апдейтов (MessageCreated/MessageCallback) есть .message с .answer();
    у события bot_started сообщения ещё нет — там свой метод .send().
    """
    msg = getattr(event, "message", None)
    if msg is not None:
        await msg.answer(text, attachments=_atts(kb), parse_mode=ParseMode.HTML)
    else:
        await event.send(text, attachments=_atts(kb), parse_mode=ParseMode.HTML)


async def edit(cb, text: str, kb=None) -> None:
    """Отредактировать сообщение, на котором нажата inline-кнопка."""
    await cb.edit(text=text, attachments=_atts(kb), format=ParseMode.HTML)


async def ack(cb) -> None:
    """Подтвердить нажатие callback (аналог answerCallbackQuery)."""
    await cb.answer()


async def show_main_menu(event) -> None:
    await reply(event, texts.MENU_TITLE, main_menu_kb())
