"""Точка входа бота MAX: настройка maxapi и запуск long-polling (порт app.main).

Транспорт — maxapi; бизнес-логика и тексты общие с Telegram-версией.
"""
from __future__ import annotations

import asyncio
import json
import logging
import warnings
from datetime import date

from maxapi import Bot, Dispatcher
from maxapi.methods.types import getted_updates as _getted_updates
from maxapi.types import BotCommand

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

# Команды в меню бота MAX (метод в maxapi помечен устаревшим, но других способов
# показать команды из кода нет; при ошибке просто логируем).
BOT_COMMANDS = (
    BotCommand(name="start", description="Начать / главное меню"),
    BotCommand(name="menu", description="Главное меню"),
    BotCommand(name="my_data", description="Какие мои данные хранятся"),
    BotCommand(name="forget_me", description="Забыть меня: удалить все мои данные"),
)


def _patch_raw_update_logging() -> None:
    """Самая дорогая ошибка интеграции — апдейт, который молча отбрасывается.

    maxapi при неизвестной структуре апдейта пишет одно предупреждение и теряет
    событие. Оборачиваем разбор: непринятые апдейты логируем целиком (без ПДн —
    тексты сообщений режем), а сообщения с вложениями — типы вложений.
    """
    original = _getted_updates.get_update_model

    async def logged(event: dict, bot):
        model = await original(event, bot)
        if model is None:
            safe = json.loads(json.dumps(event, ensure_ascii=False))
            body = (safe.get("message") or {}).get("body") or {}
            if body.get("text"):
                body["text"] = f"<{len(body['text'])} символов>"
            logger.warning("Апдейт не разобран maxapi, сырой payload: %s", json.dumps(safe, ensure_ascii=False)[:4000])
        else:
            atts = ((event.get("message") or {}).get("body") or {}).get("attachments") or []
            types = [a.get("type") for a in atts if isinstance(a, dict)]
            if any(t not in ("inline_keyboard", None) for t in types):
                logger.info("Апдейт %s с вложениями: %s", event.get("update_type"), types)
        return model

    _getted_updates.get_update_model = logged


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
    _patch_raw_update_logging()

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            await bot.set_my_commands(*BOT_COMMANDS)
        logger.info("Команды бота установлены: %s", ", ".join(c.name for c in BOT_COMMANDS))
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось установить команды бота (не критично)")

    asyncio.create_task(reflection_reminder_loop(bot))
    if settings.max_webhook_url:
        await _ensure_webhook_subscription(bot)
        logger.info("MAX бот запускается (webhook :%s, %s)…", settings.max_webhook_port, settings.max_webhook_url)
        await dp.handle_webhook(
            bot, host="0.0.0.0", port=settings.max_webhook_port, path="/max/webhook",
            secret=settings.max_webhook_secret or None,
        )
        return
    logger.info("MAX бот запускается (long-polling)…")
    await dp.start_polling(bot)


async def _ensure_webhook_subscription(bot) -> None:
    """Одна актуальная подписка: чужие/старые URL снимаем (MAX их копит, а не заменяет),
    свою ставим, если её нет. Подписка сама отваливается после 8 ч без ответов 200."""
    url = settings.max_webhook_url
    subs = await bot.get_subscriptions()
    present = False
    for sub in subs.subscriptions:
        if sub.url == url:
            present = True
            continue
        logger.info("Снимаю старую подписку вебхука: %s", sub.url)
        await bot.unsubscribe_webhook(sub.url)
    if not present:
        await bot.subscribe_webhook(url=url, secret=settings.max_webhook_secret or None)
        logger.info("Подписка вебхука оформлена: %s", url)
    else:
        logger.info("Подписка вебхука уже есть: %s", url)


if __name__ == "__main__":
    asyncio.run(main())
