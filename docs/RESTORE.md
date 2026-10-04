# Восстановление TutorAI

Что делать, если что-то пропало или сломалось. Разделы — от частого к редкому.
Ключи и ID — в [SERVICES.md](SERVICES.md). Команды `yc` — с машины, где настроен профиль
сервисного аккаунта (`yc config profile list`).

| Ситуация | Раздел |
|---|---|
| Нужен код на новом компьютере | [А](#а-код) |
| Бот молчит / VM перезагрузилась или была выключена | [Б](#б-вернуть-прод-после-остановки-или-перезагрузки-vm) |
| Не пускает по SSH / нужно сменить SSH-ключ | [В](#в-пересоздать-vm-вокруг-того-же-диска) |
| VM или диск потеряны — поднять из снапшота или с нуля | [Г](#г-поднять-прод-на-новой-vm) |
| Нужно сохранить или вернуть базу данных | [Д](#д-база-данных) |

---

## А. Код

```bash
git clone https://github.com/leonovvladimirhq-svg/TutorAI.git
```

Если GitHub недоступен — из локального бандла (лежит в `C:\Backups\TutorAI\<дата>\`, см.
[BACKUP_LOG.md](BACKUP_LOG.md)):

```bash
git bundle verify TutorAI-all-refs.bundle      # должно быть «The bundle records a complete history»
git clone TutorAI-all-refs.bundle TutorAI
```

Отложенная ветка с Qwen 3.6 / Api-Key — тег `archive/qwen3.6-apikey-2026-06-30`
(`git checkout archive/qwen3.6-apikey-2026-06-30`).

---

## Б. Вернуть прод после остановки или перезагрузки VM

Самый частый случай. **Включать выключенную VM — только по согласованию с владельцем облака
(Иван)**: её могли выключить намеренно.

```bash
# 1. VM запущена? (с локальной машины)
yc compute instance get tutorai-bot-v2 --folder-id b1g0emak4eh8q5t66vfn | grep status
yc compute instance start tutorai-bot-v2 --folder-id b1g0emak4eh8q5t66vfn   # если STOPPED и согласовано

# 2. На VM: docker при каждой загрузке замаскирован (намеренно, см. deploy/user-data.yaml)
ssh -i ~/.ssh/tutorai_ed25519 yc-user@89.169.157.225
sudo systemctl unmask docker.service docker.socket && sudo systemctl start docker
cd /opt/tutorai && sudo docker compose up -d
sudo docker compose ps                      # db (healthy), web, bot_max — Up; migrate — Exited (0)

# 3. Шлюз вебхука (с локальной машины): облако могло его остановить
yc serverless api-gateway get d5dionud12kserpjrtv6 | grep status
yc serverless api-gateway resume d5dionud12kserpjrtv6                         # если STOPPED

# 4. Подписка MAX — сбросить после простоя (на VM)
sudo docker exec tutorai-bot_max-1 python -m scripts.max_resubscribe

# 5. Проверка: написать боту /start и смотреть, приходят ли запросы
sudo docker compose logs bot_max --since 5m | grep "POST /max/webhook"
```

Признаки, какой шаг нужен: `docker compose ps` → «no such file docker.sock» — шаг 2;
бот `Up`, но в логе нет ни одного `POST /max/webhook` — шаги 3–4.
Сообщения, отправленные боту, пока он лежал, MAX не передоставляет — их нужно отправить заново.

---

## В. Пересоздать VM вокруг того же диска

Когда не пускает по SSH или нужно вшить другой ключ. На этих образах ключ из метаданных
на живой машине **не применяется** — только при первой загрузке нового инстанса. Данные на
диске сохраняются.

```bash
export YC_CLI_INITIALIZATION_SILENCE=true
F=b1g0emak4eh8q5t66vfn; VM=fhmikodv9j3049bba11k; DISK=fhmal47dob7nb85nrqfe   # сверить: yc compute instance get $VM
yc compute instance stop --id $VM
yc compute instance detach-disk $VM --disk-id $DISK
yc compute instance delete --id $VM                                   # диск отсоединён — не тронется
yc compute instance create --name tutorai-bot-v2 --folder-id $F --zone ru-central1-a \
  --platform standard-v3 --cores 2 --core-fraction 50 --memory 4G \
  --use-boot-disk disk-id=$DISK,auto-delete=false \
  --network-interface subnet-id=e9bunl8lm7shbk7h96vv,nat-address=89.169.157.225 \
  --service-account-id aje20h52ep8h0c96uo2g \
  --metadata-from-file user-data=deploy/user-data.yaml
```

В `deploy/user-data.yaml` ключ Ивана закомментирован (не публикуем) — вписать его из
метаданных старой VM (`yc compute instance get <id> --full`) до удаления. Если `create`
сорвался — просто повторить: диск и статический IP в безопасности. После — раздел Б.

---

## Г. Поднять прод на новой VM

**Из снапшота (с данными).** Последние снапшоты — в [SERVICES.md](SERVICES.md).

```bash
yc compute disk create tutorai-restored --folder-id b1g0emak4eh8q5t66vfn --zone ru-central1-a \
  --source-snapshot-name tutorai-v2-ssd-backup-2026-09-29 --type network-ssd
# затем create из раздела В с disk-id нового диска; IP — статический из рабочего диапазона 89.169.x
```

**С нуля (без данных).**

1. VM: Ubuntu 22.04, 2 vCPU, 4 ГБ, статический IP из диапазона `89.169.x` / `158.160.x`.
   В user-data — блок `users:` из `deploy/user-data.yaml` плюс установка Docker:
   ```yaml
   runcmd:
     - curl -fsSL https://get.docker.com | sh
     - usermod -aG docker yc-user
     - git clone https://github.com/leonovvladimirhq-svg/TutorAI.git /opt/tutorai
     - chown -R yc-user:yc-user /opt/tutorai
   ```
2. На VM: `/opt/tutorai/.env` (по `.env.example`, значения — из менеджера паролей) и
   `/opt/tutorai/secrets/sa-key.json`.
3. Шлюз вебхука: в `deploy/apigw-webhook.yaml` заменить IP на новый и
   `yc serverless api-gateway update d5dionud12kserpjrtv6 --spec deploy/apigw-webhook.yaml`
   (или `create`, если шлюза нет; новый адрес — в `MAX_WEBHOOK_URL`).
4. `cd /opt/tutorai && sudo docker compose up -d --build` — миграции применятся сами,
   бот при старте сам оформит подписку вебхука.
5. Панель → «Коды доступа» → сгенерировать коды; режим «Кого видят наставники» — по ситуации.

---

## Д. База данных

Данные живут в томе `tutorai_postgres-data` на диске VM; резервная копия — **снапшоты диска**
(SERVICES.md). Отдельный SQL-дамп снимать, когда VM запущена:

```bash
# дамп (на VM) → скачать на свою машину, в git НЕ класть (там персональные данные)
sudo docker exec tutorai-db-1 sh -c 'pg_dump -U $POSTGRES_USER -d $POSTGRES_DB -Fc' > tutorai-$(date +%F).dump
scp -i ~/.ssh/tutorai_ed25519 yc-user@89.169.157.225:tutorai-*.dump C:/Backups/TutorAI/

# восстановление в пустую БД (стек поднят, миграции применены)
cat tutorai-YYYY-MM-DD.dump | sudo docker exec -i tutorai-db-1 sh -c \
  'pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --clean --if-exists --no-owner'
```

---

## Проверка после любого восстановления

- [ ] `sudo docker compose ps`: `db` healthy, `web` и `bot_max` Up, `migrate` Exited (0)
- [ ] в логе бота: `Зарегистрировано N обработчиков событий` и `Webhook сервер запущен`
- [ ] боту в MAX `/start` → ответ; голосовое → «🎙 Распознал: …»
- [ ] панель `http://<IP>:8080` открывается, вход работает
- [ ] `alembic_version` = последняя миграция в `alembic/versions/`
