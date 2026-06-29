# TutorAI — ИИ-наставник студента (прототип)

Telegram-бот, который помогает студенту выстраивать образовательную/карьерную траекторию:
коучинговый профайлинг, постановка целей по SMART, голосовой ввод. Прототип ОП
«Интегрированные коммуникации» ШК ВШЭ. Подробности — в `TutorAI_План_реализации.md`.

> Отдельный бот; в дальнейшем сольётся с «Ведомость AI» в единого ИИ-агента студента.

## Стек

- Python 3.12, **aiogram 3** (long-polling)
- PostgreSQL 16 (`pgvector`-ready), SQLAlchemy 2 async + Alembic
- LLM: **Qwen** через **Yandex AI Studio** (OpenAI-совместимый endpoint)
- STT: **Yandex SpeechKit**
- Docker + docker-compose

## Структура

```
app/
  config.py            # настройки из .env
  main.py              # entrypoint: aiogram Dispatcher (polling)
  db/                  # модели, сессия, сид
  bot/handlers/        # /start+авторизация, диалог, цели, профиль, голос
  services/            # iam, llm, stt, profiler, smart, memory, events
  domain/              # таксономия профиля
alembic/               # миграции
```

## Запуск (Docker)

1. Скопируйте `.env.example` → `.env` и заполните значения
   (`TELEGRAM_BOT_TOKEN`, `YC_FOLDER_ID`, креды БД).
2. Положите ключ сервисного аккаунта в `secrets/sa-key.json` (вне git).
3. Поднимите окружение:

```bash
docker compose up -d --build
```

Миграции Alembic и сид 3 тестовых профилей применяются автоматически при старте.

## Тестовые профили

| Профиль   | Пароль  |
|-----------|---------|
| Профиль 1 | `12345` |
| Профиль 2 | `ABCD`  |
| Профиль 3 | `ABCD`  |

После `/start` → согласие на обработку данных → выбор профиля → ввод пароля → вход.

## Локальная разработка (без Docker)

```bash
python -m venv .venv && source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# поднимите Postgres и пропишите DATABASE_URL на localhost
alembic upgrade head
python -m app.main
```

## Безопасность

Секреты (`.env`, `secrets/*.json`) **не коммитятся** (см. `.gitignore`).
Токен бота и ключ сервисного аккаунта храните только локально.

## Деплой

См. [DEPLOY.md](DEPLOY.md): запуск локально / на готовом сервере и развёртывание новой VM
в Yandex Cloud. Домен не нужен (бот на long-polling). Перед запуском нужны `YC_FOLDER_ID`,
`LLM_MODEL_URI` и роли сервисного аккаунта (AI Studio + SpeechKit).
