# TutorAI — ИИ-наставник студента (прототип)

Telegram-бот, который помогает студенту выстраивать образовательную/карьерную траекторию:
коучинговый профайлинг, постановка целей по SMART, голосовой ввод. Доступ — по ролям
(Студент / Наставник / Академический руководитель), которыми управляет академический
руководитель через веб-панель. Прототип ОП «Интегрированные коммуникации» ШК ВШЭ.
Подробности — в `TutorAI_План_реализации.md`.

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
  main.py              # entrypoint бота: aiogram Dispatcher (polling)
  db/                  # модели (Student, AppUser-роли, …), сессия, сид
  bot/handlers/        # /start+роли, диалог, цели, профиль, голос
  services/            # iam, llm, stt, profiler, smart, memory, events, roles
  domain/              # таксономия профиля
  web/                 # веб-панель академ. руководителя (FastAPI + Jinja2)
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

Поднимаются три сервиса: `migrate` (одноразово применяет миграции Alembic), `bot`
(long-polling) и `web` (веб-панель на порту `WEB_PORT`, по умолчанию 8080).

## Роли и доступ

Вход в бота — **по роли, привязанной к Telegram ID** (паролей и выбора профиля больше нет):

- **Студент** — профайлинг, цели по SMART, профиль;
- **Наставник** / **Академический руководитель** — в боте пока только приветствие с ролью.

Роли назначает **академический руководитель** в веб-панели: `http://<хост>:8080`
(логин/пароль из `WEB_ADMIN_USER` / `WEB_ADMIN_PASSWORD`, по умолчанию `academ` / `ABCD`).
Там он вводит Telegram ID и выбирает роль. Пока роль не назначена, бот показывает
пользователю его Telegram ID и просит передать его руководителю.

> Первого руководителя можно назначить без панели — переменной `BOOTSTRAP_DIRECTOR_TG`
> (Telegram ID) в `.env`. Свой Telegram ID пользователь узнаёт, отправив боту `/start`.

## Локальная разработка (без Docker)

```bash
python -m venv .venv && source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# поднимите Postgres и пропишите DATABASE_URL на localhost
alembic upgrade head
python -m app.main                                      # бот
uvicorn app.web.main:app --host 0.0.0.0 --port 8080     # веб-панель (в отдельном процессе)
```

## Безопасность

Секреты (`.env`, `secrets/*.json`) **не коммитятся** (см. `.gitignore`).
Токен бота и ключ сервисного аккаунта храните только локально.

## Деплой

См. [DEPLOY.md](DEPLOY.md): запуск локально / на готовом сервере и развёртывание новой VM
в Yandex Cloud. Домен не нужен (бот на long-polling). Перед запуском нужны `YC_FOLDER_ID`,
`LLM_MODEL_URI` и роли сервисного аккаунта (AI Studio + SpeechKit).
