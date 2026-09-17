"""Middleware: открывает сессию БД на каждый апдейт (порт app.bot.middleware).

maxapi отдаёт хендлеру только те ключи из data, что он объявил в сигнатуре
(dispatcher.call_handler фильтрует по inspect.signature). Кладём ``session`` в
data — хендлеры с параметром ``session: AsyncSession`` его получат.
"""
from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from maxapi.filters.middleware import BaseMiddleware

from app.db.session import AsyncSessionLocal
from app.services import telemetry


class DbSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        async with AsyncSessionLocal() as session:
            data["session"] = session
            return await handler(event, data)


class DashboardMiddleware(BaseMiddleware):
    """Телеметрия в общий дашборд мониторинга: одно событие на апдейт.

    Регистрируется outer — видит каждый апдейт до фильтров хендлеров. Снимает
    категорию действия (без ПДн), время обработки и ok/error; отправка в фоне,
    на ответ пользователю не влияет (см. app.services.telemetry).
    """

    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        user_id, user_name, action = telemetry.describe_event(event)
        t0 = time.monotonic()
        try:
            result = await handler(event, data)
        except Exception as e:
            telemetry.track(
                user_id, action, f"Ошибка: {type(e).__name__}", status="error",
                latency_ms=int((time.monotonic() - t0) * 1000), user_name=user_name,
            )
            raise
        telemetry.track(
            user_id, action,
            latency_ms=int((time.monotonic() - t0) * 1000), user_name=user_name,
        )
        return result
