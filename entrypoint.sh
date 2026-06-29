#!/usr/bin/env bash
set -e

echo "[entrypoint] Применяю миграции Alembic..."
alembic upgrade head

echo "[entrypoint] Запускаю бота..."
exec python -m app.main
