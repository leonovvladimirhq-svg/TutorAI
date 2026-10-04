# TutorAI — ИИ-наставник студента

Бот в мессенджере **MAX** для студентов ОП «Интегрированные коммуникации» Школы
коммуникаций НИУ ВШЭ. Помогает студенту поставить цели по SMART, подвести по ним итоги
(рефлексия) и передаёт всё это наставнику в виде отчёта Word. Наставник подтверждает или
возвращает цели прямо в боте. Руководитель управляет доступами и сроками в веб-панели.

> **Статус на 04.10.2026:** прототип, этап тестирования со студентами. Сервер (VM в Yandex
> Cloud) **выключен** с 29.09.2026 владельцем облака — как включить, см.
> [docs/RESTORE.md](docs/RESTORE.md#б-вернуть-прод-после-остановки-или-перезагрузки-vm).

## Что умеет

| Кто | Что делает |
|---|---|
| **Студент** | входит по коду доступа (16 цифр) → даёт согласие 152-ФЗ → заполняет профиль в диалоге → ставит цели (бот разбирает их по SMART) → «📝 Подвести итоги» по каждой цели. Можно отвечать голосом. `/forget_me` («забыть меня») удаляет всё |
| **Наставник** | получает каждую новую цель с кнопками «Подтвердить / Отклонить» (с причиной), видит своих студентов, скачивает отчёт `.docx` по студенту или общий по группе |
| **Руководитель** | веб-панель: коды доступа, роли, закрепление наставников, сроки периода, сводка «кто что прислал», отзывы |

## Как устроено

```
Студент / наставник ── MAX ──► Yandex API Gateway (HTTPS) ──► бот bot_max (:8090) ─┐
Руководитель ── браузер ──────────────────────────────────► веб-панель web (:8080) ┤
                                                                                   ├─ PostgreSQL (db)
            Yandex AI Studio (Qwen) · Yandex SpeechKit (голос) ◄── бот ─────────────┘
```

Всё работает в Docker на одной VM: `db` (PostgreSQL 16), `migrate` (миграции, одноразово),
`bot_max` (бот), `web` (панель). Внешние сервисы и ключи — [docs/SERVICES.md](docs/SERVICES.md).

## Запуск с нуля

Нужны: Docker с Compose, токен бота MAX, ключ сервисного аккаунта Yandex Cloud
(список всего — в [docs/SERVICES.md](docs/SERVICES.md)).

```bash
git clone https://github.com/leonovvladimirhq-svg/TutorAI.git && cd TutorAI
cp .env.example .env                 # заполнить значения (комментарии внутри)
mkdir -p secrets && cp /путь/к/ключу-SA.json secrets/sa-key.json
docker compose up -d --build
docker compose logs -f bot_max       # ждём «Webhook сервер запущен» или «long-polling»
```

Панель: `http://<адрес-сервера>:8080`, логин и пароль — `WEB_ADMIN_USER` / `WEB_ADMIN_PASSWORD`
из `.env`. Первый вход в бота — сгенерировать коды в панели («Коды доступа») и ввести код в боте.

Если `MAX_WEBHOOK_URL` пустой, бот работает в режиме long-polling — так проще для локальной
проверки, но **голосовые сообщения в этом режиме не доходят** (см. [docs/DECISIONS.md](docs/DECISIONS.md)).

Полное восстановление на новом сервере, из снапшота или после аварии — [docs/RESTORE.md](docs/RESTORE.md).

## Разработка

```bash
python -m venv .venv && .venv/Scripts/activate      # Linux/macOS: source .venv/bin/activate
pip install -r requirements-max.txt
python -m pytest -q                                 # тесты (без БД и сети)
```

Обновить сервер: `cd /opt/tutorai && git pull && sudo docker compose up -d --build`.

## Документация

| Документ | О чём |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Правила для ИИ-ассистента: стек, команды, ловушки |
| [docs/SERVICES.md](docs/SERVICES.md) | Внешние сервисы, ключи, аккаунты, где что лежит |
| [docs/RESTORE.md](docs/RESTORE.md) | Восстановление с нуля и после аварий |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Важные решения: что и почему |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | История изменений по датам |
| [docs/BACKUP_LOG.md](docs/BACKUP_LOG.md) | Журнал бэкапов |
| [docs/archive/](docs/archive/) | Устаревшие документы (Telegram-версия) |

Секреты (`.env`, `secrets/`, `*-key.json`) в git **не хранятся** — см. `.gitignore`.
