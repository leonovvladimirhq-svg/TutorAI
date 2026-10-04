"""Переоформить подписку вебхука MAX: снять все подписки бота и поставить свою заново.

Зачем: после долгого простоя (VM или API Gateway были выключены) MAX может держать
«зависшую» подписку — в списке она есть, а апдейты не приходят. Бот при старте ставит
подписку, только если её нет, поэтому сбросить состояние нужно вручную.

Запуск на сервере (в контейнере бота, там есть .env и maxapi):
    sudo docker exec tutorai-bot_max-1 python -m scripts.max_resubscribe
"""
from __future__ import annotations

import asyncio
import warnings

warnings.simplefilter("ignore", DeprecationWarning)

from maxapi import Bot  # noqa: E402

from app.config import settings  # noqa: E402


async def main() -> None:
    if not settings.max_webhook_url:
        raise SystemExit("MAX_WEBHOOK_URL пуст — бот в режиме long-polling, подписка не нужна")
    bot = Bot(settings.max_bot_token)
    before = await bot.get_subscriptions()
    print("было:", [s.url for s in before.subscriptions])
    for sub in before.subscriptions:
        await bot.unsubscribe_webhook(sub.url)
    await bot.subscribe_webhook(url=settings.max_webhook_url, secret=settings.max_webhook_secret or None)
    after = await bot.get_subscriptions()
    print("стало:", [s.url for s in after.subscriptions])


if __name__ == "__main__":
    asyncio.run(main())
