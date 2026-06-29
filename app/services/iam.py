"""Получение IAM-токена Yandex Cloud из ключа сервисного аккаунта.

Схема: JWT (PS256, подписан приватным ключом SA) → обмен на IAM-токен.
Токен кэшируется в памяти и обновляется примерно раз в час (живёт до 12 ч).
"""
from __future__ import annotations

import asyncio
import json
import time

import httpx
import jwt

from app.config import settings

IAM_TOKEN_URL = "https://iam.api.cloud.yandex.net/iam/v1/tokens"

_lock = asyncio.Lock()
_token: str | None = None
_token_exp: float = 0.0


def _load_sa_key() -> dict:
    with open(settings.yc_sa_key_file, encoding="utf-8") as f:
        return json.load(f)


def build_jwt(key: dict) -> str:
    """Собирает подписанный JWT из ключа сервисного аккаунта.

    Приватный ключ Yandex содержит служебную строку перед PEM-блоком — отрезаем её.
    """
    private_key = key["private_key"]
    begin = private_key.find("-----BEGIN")
    if begin > 0:
        private_key = private_key[begin:]

    now = int(time.time())
    payload = {
        "aud": IAM_TOKEN_URL,
        "iss": key["service_account_id"],
        "iat": now,
        "exp": now + 3600,
    }
    return jwt.encode(
        payload,
        private_key,
        algorithm="PS256",
        headers={"kid": key["id"]},
    )


async def get_iam_token() -> str:
    """Возвращает действующий IAM-токен (с кэшем)."""
    global _token, _token_exp
    async with _lock:
        if _token and _token_exp - 60 > time.time():
            return _token

        key = await asyncio.to_thread(_load_sa_key)
        encoded = build_jwt(key)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(IAM_TOKEN_URL, json={"jwt": encoded})
            resp.raise_for_status()
            _token = resp.json()["iamToken"]
        _token_exp = time.time() + 3500
        return _token
