"""Точка входа бота MAX: настройка maxapi и запуск long-polling (порт app.main).

Транспорт — maxapi; бизнес-логика и тексты общие с Telegram-версией. Пока
подключён только роутер start (PoC); остальные добавляются по мере портирования.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from maxapi import Bot, Dispatcher

from app.config import settings
from app.db.seed import seed_profiles
from app.db.session import AsyncSessionLocal
from app.maxbot.handlers import dialogue, fallback, feedback, goals, mentor, profile, reflect, start, voice
from app.maxbot.middleware import DashboardMiddleware, DbSessionMiddleware
from app.bot import texts
from app.db import crud
from app.maxbot.common import send_to

logger = logging.getLogger(__name__)


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    # телеметрия в дашборд мониторинга — первой, чтобы засечь полное время обработки
    dp.register_outer_middleware(DashboardMiddleware())
    # сессия БД на каждый апдейт (кладёт session в data для хендлеров)
    dp.register_outer_middleware(DbSessionMiddleware())
    # порядок роутеров важен: voice раньше dialogue/goals (иначе их текстовые
    # state-хендлеры перехватят аудио), fallback — последним.
    dp.include_routers(
        start.router,
        mentor.router,
        voice.router,
        dialogue.router,
        goals.router,
        reflect.router,
        profile.router,
        feedback.router,
        fallback.router,
    )
    return dp


REMINDER_INTERVAL_SEC = 3600


async def reflection_reminder_loop(bot) -> None:
    """Раз в час: если наступил срок рефлексии (app_setting.reflection_deadline),
    напомнить каждому студенту, который ещё не подвёл итоги. Один раз на студента."""
    while True:
        try:
            async with AsyncSessionLocal() as session:
                deadline = await crud.get_setting(session, "reflection_deadline")
                if deadline and date.today() >= date.fromisoformat(deadline):
                    for student in await crud.list_students_for_reminder(session):
                        if not student.telegram_id:
                            continue
                        if await crud.latest_completed_reflection(session, student.id):
                            await crud.set_reflection_reminded(session, student)  # уже прошёл — не беспокоим
                            continue
                        if await send_to(bot, student.telegram_id, texts.REFLECT_REMINDER):
                            await crud.set_reflection_reminded(session, student)
        except Exception:  # noqa: BLE001
            logger.exception("Ошибка в цикле напоминаний о рефлексии")
        await asyncio.sleep(REMINDER_INTERVAL_SEC)


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
    asyncio.create_task(reflection_reminder_loop(bot))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
