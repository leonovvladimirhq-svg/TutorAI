"""Middleware: открывает сессию БД на каждый апдейт (порт app.bot.middleware).

maxapi отдаёт хендлеру только те ключи из data, что он объявил в сигнатуре
(dispatcher.call_handler фильтрует по inspect.signature). Кладём ``session`` в
data — хендлеры с параметром ``session: AsyncSession`` его получат.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from maxapi.filters.middleware import BaseMiddleware

from app.db.session import AsyncSessionLocal


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
