"""Точка входа бота MAX: настройка maxapi и запуск long-polling (порт app.main).

Транспорт — maxapi; бизнес-логика и тексты общие с Telegram-версией. Пока
подключён только роутер start (PoC); остальные добавляются по мере портирования.
"""
from __future__ import annotations

import asyncio
import logging

from maxapi import Bot, Dispatcher

from app.config import settings
from app.db.seed import seed_profiles
from app.db.session import AsyncSessionLocal
from app.maxbot.handlers import dialogue, fallback, feedback, goals, profile, start, voice
from app.maxbot.middleware import DbSessionMiddleware

logger = logging.getLogger(__name__)


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    # сессия БД на каждый апдейт (кладёт session в data для хендлеров)
    dp.register_outer_middleware(DbSessionMiddleware())
    # порядок роутеров важен: voice раньше dialogue/goals (иначе их текстовые
    # state-хендлеры перехватят аудио), fallback — последним.
    dp.include_routers(
        start.router,
        voice.router,
        dialogue.router,
        goals.router,
        profile.router,
        feedback.router,
        fallback.router,
    )
    return dp


async def on_startup() -> None:
    async with AsyncSessionLocal() as session:
        await seed_profiles(session)


async def main() -> None:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    if not settings.max_bot_token:
        raise SystemExit("MAX_BOT_TOKEN не задан — укажите токен бота MAX в .env")

    await on_startup()

    bot = Bot(settings.max_bot_token)
    dp = build_dispatcher()

    logger.info("MAX бот запускается (long-polling)…")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
