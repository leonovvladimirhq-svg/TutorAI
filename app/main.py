"""Точка входа: настройка aiogram и запуск long-polling."""
from __future__ import annotations

import asyncio
import logging
import socket

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers import dialogue, fallback, goals, profile, start, voice
from app.bot.middleware import DbSessionMiddleware
from app.config import settings
from app.db.seed import seed_profiles
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    # сессия БД на каждый апдейт
    dp.update.outer_middleware(DbSessionMiddleware())

    # порядок важен: специализированные роутеры — раньше, fallback — последним
    dp.include_router(start.router)
    dp.include_router(voice.router)  # перехватывает голос до state-обработчиков
    dp.include_router(dialogue.router)
    dp.include_router(goals.router)
    dp.include_router(profile.router)
    dp.include_router(fallback.router)
    return dp


async def on_startup() -> None:
    async with AsyncSessionLocal() as session:
        await seed_profiles(session)


async def main() -> None:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    await on_startup()

    # api.telegram.org резолвится в IPv6, а у YC one-to-one NAT egress только по IPv4 →
    # форсируем IPv4 в TCP-коннекторе, иначе запросы к Telegram виснут и бот падает.
    session = AiohttpSession()
    session._connector_init["family"] = socket.AF_INET
    bot = Bot(
        token=settings.telegram_bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher()

    logger.info("TutorAI бот запускается (long-polling)…")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
