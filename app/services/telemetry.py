"""Телеметрия в общий дашборд мониторинга проектов Школы коммуникаций.

Дашборд (http://89.169.146.175:8080) собирает события со всех сервисов команды;
у каждого проекта свой ингест-токен. Отсюда уходит по одному событию на каждый
апдейт MAX (см. app.maxbot.middleware.DashboardMiddleware).

Принципы:
- «выстрелил и забыл» в фоновом потоке, таймаут 5 с — мониторинг не имеет права
  замедлить или уронить бота; без DASHBOARD_URL/DASHBOARD_TOKEN — тихий no-op;
- ПДн не передаём. Профиль студента, цели, рефлексия, тексты диалога остаются
  в нашей базе; в дашборд уходит только КАТЕГОРИЯ действия («Текстовое
  сообщение», «Голосовое сообщение», «Кнопка: …»), MAX-id и ok/error.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 5.0


def _post(payload: dict) -> None:
    try:
        httpx.post(
            f"{settings.dashboard_url.rstrip('/')}/api/ingest",
            json=payload,
            headers={"Authorization": f"Bearer {settings.dashboard_token}"},
            timeout=_TIMEOUT,
        )
    except Exception as e:  # noqa: BLE001 — телеметрия никогда не роняет бота
        logger.warning("Дашборд недоступен: %s", e)


def track(
    user_id: int | None,
    action: str,
    result: str = "",
    *,
    status: str = "ok",
    latency_ms: int | None = None,
    user_name: str = "",
) -> None:
    """Отправить событие «действие пользователя» в дашборд (в фоне)."""
    if not settings.dashboard_url or not settings.dashboard_token:
        return
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "occurred_at": ts,
        "user_ref": str(user_id) if user_id is not None else None,
        "user_name": user_name or None,
        "request_text": action,
        "response_text": result or None,
        "status": "error" if status == "error" else "ok",
        "latency_ms": latency_ms,
        "model": settings.model_uri,
        "dedup_key": f"{user_id}:{ts}:{action}"[:200],
    }
    threading.Thread(target=_post, args=(payload,), daemon=True).start()


def describe_event(event: Any) -> tuple[int | None, str, str]:
    """(user_id, имя, категория действия) для типизированного апдейта maxapi — без ПДн."""
    utype = str(getattr(event, "update_type", "") or "")
    user = None
    label = f"Событие {utype}"

    if utype == "bot_started":
        user = getattr(event, "user", None)
        label = "Открыл бота"

    elif utype == "message_created":
        message = getattr(event, "message", None)
        user = getattr(message, "sender", None)
        body = getattr(message, "body", None)
        text = (getattr(body, "text", None) or "").strip()
        attachments = getattr(body, "attachments", None) or []
        kinds = {str(getattr(a, "type", "") or "") for a in attachments}
        if "audio" in kinds:
            label = "Голосовое сообщение"
        elif kinds:
            label = "Сообщение с вложением: " + ", ".join(sorted(k for k in kinds if k))
        elif text.startswith("/"):
            label = "Команда " + text.split()[0].split("@")[0]
        else:
            label = "Текстовое сообщение"

    elif utype == "message_callback":
        callback = getattr(event, "callback", None)
        user = getattr(callback, "user", None)
        payload = str(getattr(callback, "payload", None) or "")
        # payload кнопок — служебные коды без ПДн; в дашборде видно, какими
        # кнопками пользуются
        label = f"Кнопка: {payload}" if payload else "Кнопка"

    user_id = getattr(user, "user_id", None)
    first = getattr(user, "first_name", None) or ""
    last = getattr(user, "last_name", None) or ""
    return user_id, f"{first} {last}".strip(), label
