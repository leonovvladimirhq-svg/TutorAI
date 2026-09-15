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


async def edit(cb, text: str, kb=None, notification: str | None = None) -> None:
    """Отредактировать сообщение, на котором нажата inline-кнопка.

    ВАЖНО: в maxapi edit реализован через send_callback — это И ЕСТЬ ответ на
    callback. Отдельный ack после edit вызывать НЕЛЬЗЯ: второй ответ на тот же
    callback отменяет правку. notification — опциональное всплывающее уведомление.
    """
    await cb.edit(text=text, attachments=_atts(kb), format=ParseMode.HTML, notification=notification)


async def ack(cb, notification: str | None = None) -> None:
    """Подтвердить нажатие callback без изменения сообщения (answerCallbackQuery).

    notification — всплывающее уведомление (аналог aiogram show_alert=True).
    Использовать, когда сообщение НЕ редактируется (иначе см. edit/clear_markup).
    """
    await cb.answer(notification=notification)


async def clear_markup(cb, notification: str | None = None) -> None:
    """Убрать inline-клавиатуру (сохранив текст). Тоже ответ на callback — отдельный
    ack не нужен. notification — опциональное всплывающее уведомление."""
    body = getattr(cb.message, "body", None)
    text = body.text if body else None
    try:
        await cb.edit(text=text, attachments=[], format=ParseMode.HTML, notification=notification)
    except Exception:  # noqa: BLE001 — если правка не прошла, хотя бы ответим на callback
        await cb.answer(notification=notification)


async def show_main_menu(event) -> None:
    await reply(event, texts.MENU_TITLE, main_menu_kb())


async def send_to(bot, user_id: int, text: str, kb=None) -> bool:
    """Отправить сообщение другому пользователю по его MAX-ID (уведомления между ролями).

    Возвращает False, если доставить не удалось (например, адресат ещё не открывал бота) —
    сценарий отправителя при этом не ломаем.
    """
    try:
        await bot.send_message(user_id=user_id, text=text, attachments=_atts(kb), parse_mode=ParseMode.HTML)
        return True
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).exception("Не удалось отправить сообщение пользователю %s", user_id)
        return False
