"""Точка входа: настройка aiogram и запуск long-polling."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers import dialogue, fallback, feedback, goals, profile, start, voice
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
    dp.include_router(feedback.router)
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

    # Из сети Yandex Cloud api.telegram.org недоступен — при заданном
    # TELEGRAM_PROXY ходим в Telegram через прокси, иначе напрямую.
    if settings.telegram_proxy:
        logger.info("Telegram: через прокси %s", settings.telegram_proxy.split("@")[-1])
        session = AiohttpSession(proxy=settings.telegram_proxy)
    else:
        logger.warning("Telegram: TELEGRAM_PROXY не задан — идём напрямую")
        session = None

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
