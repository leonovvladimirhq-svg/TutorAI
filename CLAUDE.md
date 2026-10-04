# CLAUDE.md — правила для ИИ-ассистента

TutorAI — бот-наставник в мессенджере **MAX** + веб-панель руководителя. Прототип для
ОП «Интегрированные коммуникации» ШК ВШЭ. Что продукт делает — [README.md](README.md),
сервисы и ключи — [docs/SERVICES.md](docs/SERVICES.md), восстановление — [docs/RESTORE.md](docs/RESTORE.md).
**Репозиторий публичный**: никаких секретов, паролей, токенов, кодов доступа, данных студентов.

## Стек

- Python 3.12, **maxapi 1.2.1** (MAX Bot API, aiogram-подобный), FastAPI + Jinja2 (панель)
- PostgreSQL 16 (`pgvector/pgvector:pg16`), SQLAlchemy 2 async, Alembic
- LLM: Qwen в Yandex AI Studio (OpenAI-совместимый endpoint, IAM-токен из ключа SA);
  STT: Yandex SpeechKit v1 (только OggOpus/LPCM — всё прочее перекодирует ffmpeg)
- Docker Compose: `db`, `migrate`, `bot_max` (`Dockerfile.max`, `requirements-max.txt`),
  `web` (`Dockerfile`, `requirements.txt`)

## Где что лежит

```
app/main_max.py        точка входа бота: роутеры, вебхук/polling, напоминания о рефлексии
app/maxbot/handlers/   start (коды, согласие, forget_me), goals, reflect, mentor, voice, …
app/maxbot/common.py   reply / edit / ack / clear_markup / send_to — ВСЕ ответы через них
app/services/          llm, stt, smart, reflection, report (.docx), consent, telemetry, …
app/db/                models.py, crud.py (вся работа с БД), session.py
app/web/               панель: main.py + templates/
alembic/versions/      миграции 0001…0005
app/bot/, app/main.py  LEGACY Telegram-версия (aiogram) — не запускается; тексты app/bot/texts.py ОБЩИЕ
```

## Команды

```bash
.venv/Scripts/python -m pytest -q                     # тесты (без БД/сети), должны быть зелёными
docker compose up -d --build                          # локально / на сервере
# сервер: ssh -i ~/.ssh/tutorai_ed25519 yc-user@<IP>  (IP — docs/SERVICES.md)
cd /opt/tutorai && sudo chown -R yc-user:yc-user .git && git pull && sudo docker compose up -d --build
sudo docker compose logs bot_max --since 10m          # логи бота
sudo docker exec tutorai-db-1 sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB'   # БД
```

`git` на сервере — **без sudo** (иначе `.git/objects` становятся root-овыми и следующий pull
падает «insufficient permission»); sudo — только у docker.

## Ловушки MAX (проверено на проде)

1. Первое открытие бота — событие `bot_started`, а не текст `/start`; у него нет `.message`,
   отвечать через `event.send()` (это делает `common.reply`).
2. `edit` / `clear_markup` в maxapi **уже являются ответом на callback**. Вызов `ack` после
   них отменяет правку («кнопка не работает»). Уведомление — параметром `notification=`.
3. **Голосовые приходят только через вебхук.** В long-polling MAX шлёт пустой
   `message_created` без `message`. Поэтому прод — вебхук: MAX → Yandex API Gateway → `:8090`.
4. MAX копит подписки вебхука, а не заменяет; подписка снимается сама после 8 ч без 200.
   При старте `main_max._ensure_webhook_subscription` снимает чужие и ставит свою.
5. Пока бот лежит, апдейты теряются — MAX их не передоставляет.
6. `PATCH /me` (меню команд, `set_my_commands`) MAX убрал — 404; команды работают и так.
7. Токен — сырой строкой в `Authorization` (без `Bearer`); личный диалог адресуется по `user_id`.
8. `maxapi` (aiohttp ≥3.11) несовместим с `aiogram` (aiohttp <3.11) — отдельный образ.
9. FSM (`MemoryContext`) живёт в памяти и теряется при рестарте — поэтому код доступа
   ловится фильтром `LooksLikeCode` в любом состоянии.

## Ловушки сервера и Yandex Cloud

- **После любого простоя проверять три вещи:**
  1. docker: VM при каждой загрузке **намеренно** маскирует docker (`bootcmd` в user-data,
     решение владельца облака — не убирать без него): `sudo systemctl unmask docker.service
     docker.socket && sudo systemctl start docker && cd /opt/tutorai && sudo docker compose up -d`;
  2. API Gateway: `yc serverless api-gateway get <id>` — если `STOPPED`, то `... resume`;
  3. подписку MAX: переоформить (снять и поставить заново) — подробно в RESTORE.md.
- Облако может приостанавливать ресурсы целиком (`yc.iam.reaper`, 26.09.2026 — VM и шлюз).
- JSON-ключ сервисного аккаунта даёт доступ к API облака, **не к SSH**.
- SSH-ключи на этих образах (cloud-init EC2, без гостевого агента) применяются **только при
  первой загрузке** из user-data. «Ключ в метаданные + ребут», OS Login, `yc compute ssh` —
  не работают. Сменить ключ = пересоздать VM вокруг диска (RESTORE.md, раздел «В»).
- Ключ команды — `tutorai-deploy` (приватный — у Леонова, `~/.ssh/tutorai_ed25519`).
- До части IP-диапазонов YC трафик не доходит: рабочие `89.169.x`, `158.160.x`, `111.88.x`;
  «глухие» `51.250.x`, `93.77.x` (SSH виснет на KEX). Лечится статическим IP из рабочего.
- Имена ролей YC точные: `ai.languageModels.user`, `ai.speechkit-stt.user` (через дефис).
- AI Studio принимает запросы, только когда folder в URI модели = домашний каталог SA.
- Telegram из YC заблокирован (ТСПУ) — поэтому бот на MAX, а не в Telegram.

## Данные и приватность (152-ФЗ)

- Персональные данные студентов не покидают нашу БД; в телеметрию — только категории
  действий. Не логировать тексты ответов студентов.
- `/forget_me` удаляет студента и регистрацию, освобождает код; `consent_record` остаётся как
  аудит. Синтетику для проверок заводить с MAX-ID < 0 и удалять после.
- Коды доступа и пароль панели — только в чат пользователю, не в репозиторий.

## Соглашения

- Коммиты маленькие, сообщение на русском с префиксом: `feat:`, `fix:`, `docs:`, `chore:`
  (область в скобках: `feat(mentor):`). Тело — что и почему.
- Тексты бота — только в `app/bot/texts.py`; клавиатуры — `app/maxbot/keyboards.py`;
  доступ к БД — только через `app/db/crud.py`. Новая колонка/таблица = миграция Alembic.
- Комментарии и docstring — по-русски, объясняют «почему».
- Перед деплоем — `pytest`; после деплоя — проверить в логах `Зарегистрировано N обработчиков`
  и `Webhook сервер запущен`.
- Режим теста «все наставники видят всех» — `app_setting mentors_see_all` (переключатель в
  панели). Проверки доступа наставника — только через `crud.mentor_sees_student`.

## Windows (машина Леонова)

- Консоль cp1251: кириллица/эмодзи в bash-heredoc → python искажаются молча. Скрипты с не-ASCII
  писать файлом и запускать с `PYTHONIOENCODING=utf-8`; после замены проверять grep'ом.
- Кириллический `HOME` ломает `known_hosts` у ssh из git-bash — ключ копировать в ASCII-путь,
  `-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o IdentitiesOnly=yes`.
- `yc` — `C:\Users\Владимир\yandex-cloud\bin\yc`; venv проекта — `.venv/Scripts/python`.
