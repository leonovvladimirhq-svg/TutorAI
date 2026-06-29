# Деплой TutorAI

Бот работает на **long-polling**, поэтому домен/публичный HTTPS не нужны — достаточно
машины с доступом в интернет и Docker.

## Что нужно от заказчика

1. **`YC_FOLDER_ID`** — ID каталога Yandex Cloud, где включён AI Studio.
   Сервисный аккаунт `leonov-deployer` сейчас не видит облака на уровне CLI
   (узкие права), поэтому folder_id нужно указать явно.
2. **`LLM_MODEL_URI`** — точный URI модели Qwen в AI Studio
   (например `gpt://<folder>/qwen3-235b-a22b-fp8/latest`; подставьте доступную в вашем каталоге).
3. **Роли сервисного аккаунта** в этом каталоге:
   - `ai.languageModels.user` — вызовы Qwen;
   - `ai.speechkitStt.user` — распознавание речи;
   - для создания VM: `compute.editor` + `vpc.user` (или развернуть на готовом сервере).

## Вариант A. Локально / на готовом сервере (быстро)

```bash
git clone https://github.com/leonovvladimirhq-svg/TutorAI.git && cd TutorAI
cp .env.example .env            # заполнить TELEGRAM_BOT_TOKEN, YC_FOLDER_ID, LLM_MODEL_URI, креды БД
mkdir -p secrets && cp /путь/к/leonov-deployer-key.json secrets/sa-key.json
docker compose up -d --build
docker compose logs -f bot      # ждём "Run polling for bot @tutor_hse_ai_bot"
```

Проверка модели до запуска (опционально):
```bash
docker compose run --rm bot python -m scripts.smoke_llm
```

## Вариант B. Новая VM в Yandex Cloud

```bash
# профиль yc с ключом SA
yc config profile create tutorai-deploy
yc config set service-account-key secrets/sa-key.json --profile tutorai-deploy
yc config set folder-id <YC_FOLDER_ID> --profile tutorai-deploy

# создать VM (Ubuntu 22.04, 2 vCPU / 4 ГБ, публичный IP)
yc compute instance create \
  --name tutorai-bot \
  --zone ru-central1-a \
  --network-interface subnet-name=default-ru-central1-a,nat-ip-version=ipv4 \
  --create-boot-disk image-folder-id=standard-images,image-family=ubuntu-2204-lts,size=20 \
  --memory 4G --cores 2 \
  --ssh-key ~/.ssh/id_rsa.pub \
  --profile tutorai-deploy

# на VM: установить Docker, скопировать репозиторий + .env + secrets/sa-key.json,
# затем docker compose up -d --build
```

> Postgres поднимается контейнером в compose (для прода — заменить на Managed PostgreSQL,
> поправив `DATABASE_URL`).

## Обновление

```bash
git pull && docker compose up -d --build
```

## Эксплуатация

- Логи: `docker compose logs -f bot`
- Миграции применяются автоматически при старте (entrypoint).
- KPI: команда `/stats` в боте.
- Тестовые профили: «Профиль 1» → `12345`, «Профиль 2/3» → `ABCD`.
