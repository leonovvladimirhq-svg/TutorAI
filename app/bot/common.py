"""Общие хелперы для хендлеров."""
from __future__ import annotations

from aiogram.types import Message

from app.bot import texts
from app.bot.keyboards import main_menu_kb


async def show_main_menu(message: Message) -> None:
    await message.answer(texts.MENU_TITLE, reply_markup=main_menu_kb())
