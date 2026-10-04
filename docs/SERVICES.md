# Внешние сервисы, ключи и аккаунты

Единственное место, где перечислено, **от чего зависит TutorAI** и **где лежат ключи**.
Значения секретов здесь не пишем (репозиторий публичный) — только имена и место хранения.
Актуально на **04.10.2026**.

## Сводка

| Сервис | Зачем | Чей аккаунт | Переменные `.env` | Где значение | Оплата / срок |
|---|---|---|---|---|---|
| **MAX Bot API** | сам бот: сообщения, кнопки, файлы, голос | Тараскин Иван (самозанятый), бот создан через @MasterBot | `MAX_BOT_TOKEN`, `MAX_WEBHOOK_URL`, `MAX_WEBHOOK_SECRET`, `MAX_WEBHOOK_PORT` | `.env` на VM | бесплатно; ⚠ токен светился в переписке — перевыпустить до студентов (задача Ивана) |
| **Yandex Cloud** — облако `hse` | всё облачное ниже | организация `organization-ihorrible01`, владелец — Иван (логин `ihorrible01`) | — | — | по факту; 26.09.2026 облако приостанавливалось (`yc.iam.reaper`) |
| ↳ Compute (VM) | Docker со всем стеком | каталог `project5-nastavnik-ai` | — | — | ~ВМ + диск + статический IP |
| ↳ API Gateway | HTTPS-адрес для вебхука MAX | тот же каталог | `MAX_WEBHOOK_URL` | спецификация — [deploy/apigw-webhook.yaml](../deploy/apigw-webhook.yaml) | по запросам (копейки) |
| ↳ AI Studio (Qwen) | диалог, разбор SMART, проверка рефлексии, сводки | каталог `project2-chatbotdpo` (домашний каталог SA) | `YC_FOLDER_ID`, `LLM_MODEL_URI`, `LLM_ENDPOINT`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS` | `.env` на VM | по токенам |
| ↳ SpeechKit STT | голос → текст | тот же SA | `ENABLE_VOICE`, `SPEECHKIT_STT_URL`, `SPEECHKIT_LANG` | `.env` на VM | по секундам аудио |
| ↳ IAM: ключ сервисного аккаунта | авторизация в AI Studio и SpeechKit (IAM-токен из ключа) | SA `leonov-deployer` | `YC_SA_KEY_FILE` (путь) | файл `secrets/sa-key.json` на VM; у Леонова — `leonov-deployer-key.json` | бессрочно, пока не отозван |
| **PostgreSQL** | все данные: роли, коды, цели, рефлексия, согласия | — (контейнер `db`) | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL` | `.env` на VM; данные — том `tutorai_postgres-data` на диске VM | — |
| **Веб-панель** | управление доступами | — | `WEB_ADMIN_USER`, `WEB_ADMIN_PASSWORD`, `WEB_SESSION_SECRET`, `WEB_PORT` | `.env` на VM | ⚠ см. «Требует внимания» |
| **Дашборд мониторинга** (опц.) | телеметрия действий в общий дашборд проектов | команда (VM `vkr-checker`, project3) | `DASHBOARD_URL`, `DASHBOARD_TOKEN` | `.env` на VM | — |
| **GitHub** | код | `leonovvladimirhq-svg/TutorAI` — **публичный** | — | — | бесплатно |
| SSH-доступ к VM | вход в шелл сервера | ключ команды `tutorai-deploy` + личный ключ Ивана | — | приватный: у Леонова `~/.ssh/tutorai_ed25519` | бессрочно |
| ~~Telegram Bot API~~ | legacy, не используется | бот `@tutor_hse_ai_bot` | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_PROXY` | старый `.env` | из YC заблокирован |

GitHub Actions и секреты CI **не используются** (папки `.github/` нет).

## Идентификаторы инфраструктуры

Не секреты (без ключей бесполезны), но без них восстановление превращается в поиск.
ID и IP меняются при пересоздании — сверять командой `yc compute instance list`.

| Что | Значение |
|---|---|
| Облако `hse` | `b1gtf2pdbkfrkhbd3rt6` |
| Каталог VM — `project5-nastavnik-ai` | `b1g0emak4eh8q5t66vfn` |
| Каталог AI Studio — `project2-chatbotdpo` | `b1gvtru3guuc1oipcs4p` |
| VM `tutorai-bot-v2` | `fhmikodv9j3049bba11k`, зона `ru-central1-a` |
| Загрузочный диск VM | `fhmal47dob7nb85nrqfe` |
| Подсеть VM | `e9bunl8lm7shbk7h96vv` (ru-central1-a) |
| Статический внешний IP | `89.169.157.225` (диапазон `89.169.x` — рабочий, см. CLAUDE.md) |
| Ресурсы VM (с ~29.09, урезал Иван) | standard-v2, 2 vCPU × 20%, 4 ГБ RAM (до этого 2 × 100%, 8 ГБ) |
| Runtime-SA, привязан к VM | `project5-runtime` `aje20h52ep8h0c96uo2g` (код пока его не использует — берёт ключ из файла) |
| Deploy-SA | `leonov-deployer` `ajercun172vma0sg1eig` (домашний каталог — project2, роль `editor` на облаке) |
| API Gateway вебхука | `tutorai-max-webhook`, `d5dionud12kserpjrtv6` → `https://d5dionud12kserpjrtv6.fovt0b64.apigw.yandexcloud.net/max/webhook` |
| Снапшоты диска | `tutorai-v2-ssd-backup-2026-09-29` (8,1 ГБ, снял Иван), `tutorai-bot-v2-boot-disk-2026-08-16` |
| Бот MAX | «Наставник ИИ», `@se13742907_1_bot`, id `352221074` |
| Модель | `gpt://b1gvtru3guuc1oipcs4p/qwen3-235b-a22b-fp8/latest` |
| Порты VM | 22 (SSH), 8080 (панель), 8090 (вебхук; снаружи нужен только шлюзу) |

## Где сейчас лежат секретные значения

| Секрет | Где | Что сделать |
|---|---|---|
| `.env` прода (токен MAX, секрет вебхука, пароль БД, пароль панели, секрет сессии) | `/opt/tutorai/.env` на VM (VM выключена; диск и снапшот целы) | перенести в менеджер паролей |
| ключ SA (`sa-key.json`) | `/opt/tutorai/secrets/` на VM; у Леонова — `C:\Tutor_AI\leonov-deployer-key.json` и копия в `Загрузки\Telegram Desktop` | хранить в менеджере паролей, копию из «Загрузок» удалить |
| приватный SSH-ключ `tutorai-deploy` | `~/.ssh/tutorai_ed25519` у Леонова | копия в менеджере паролей (без неё в VM не зайти) |
| локальный `.env` у Леонова | `C:\Tutor_AI\.env` (от 30.06, Telegram-эпоха) | устарел; актуальный — на VM |

Если менеджера паролей ещё нет — завести (1Password, Bitwarden, KeePassXC) и положить туда
всё из этой таблицы. Других копий секретов (в чатах, «Загрузках») — избегать.

## Требует внимания

- **Пароль веб-панели.** Адрес панели и логин опубликованы в старых версиях документации в
  этом публичном репозитории вместе с паролем по умолчанию. Если на проде он не сменён —
  через панель видны коды доступа и данные студентов. Сменить `WEB_ADMIN_PASSWORD` и
  `WEB_SESSION_SECRET` в `.env` на VM, затем `sudo docker compose up -d web`.
- **Токен бота MAX** — перевыпустить перед запуском со студентами (светился в переписке).
- **Биллинг облака** — 26.09.2026 облако приостанавливалось; выяснить причину у Ивана.
