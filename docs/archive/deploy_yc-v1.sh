#!/usr/bin/env bash
# Создание экономичной VM в Yandex Cloud и подготовка к деплою TutorAI.
#
# Требуется: настроенный профиль yc с ключом сервисного аккаунта и FOLDER_ID
# каталога «наставник AI». Роли SA: compute.editor, vpc.user (+ AI Studio/SpeechKit для работы бота).
#
# Использование:
#   FOLDER_ID=<folder> SSH_KEY=~/.ssh/id_rsa.pub bash scripts/deploy_yc.sh
set -euo pipefail

: "${FOLDER_ID:?Укажите FOLDER_ID каталога «наставник AI»}"
PROFILE="${YC_PROFILE:-tutorai-deploy}"
ZONE="${ZONE:-ru-central1-a}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_rsa.pub}"
VM_NAME="${VM_NAME:-tutorai-bot}"

echo ">> Каталог: $FOLDER_ID, зона: $ZONE, профиль: $PROFILE"
yc config set folder-id "$FOLDER_ID" --profile "$PROFILE"

echo ">> Ищу подсеть в зоне $ZONE…"
SUBNET_ID=$(yc vpc subnet list --folder-id "$FOLDER_ID" --profile "$PROFILE" --format json \
  | python -c 'import sys,json,os;d=json.load(sys.stdin);z=os.environ["ZONE"];print(next((s["id"] for s in d if s.get("zone_id")==z), ""))')

if [ -z "$SUBNET_ID" ]; then
  echo "!! Подсеть в $ZONE не найдена. Создайте сеть/подсеть (yc vpc network create / subnet create) и повторите." >&2
  exit 1
fi
echo ">> Подсеть: $SUBNET_ID"

# Экономичная конфигурация: 2 vCPU с гарантированной долей 50%, 4 ГБ RAM, network-HDD 20 ГБ.
# Платформа standard-v3; не прерываемая (бот должен работать постоянно).
echo ">> Создаю VM $VM_NAME…"
yc compute instance create \
  --name "$VM_NAME" \
  --zone "$ZONE" \
  --folder-id "$FOLDER_ID" \
  --profile "$PROFILE" \
  --platform standard-v3 \
  --cores 2 \
  --core-fraction 50 \
  --memory 4G \
  --create-boot-disk image-folder-id=standard-images,image-family=ubuntu-2204-lts,type=network-hdd,size=20 \
  --network-interface subnet-id="$SUBNET_ID",nat-ip-version=ipv4 \
  --metadata-from-file user-data=deploy/cloud-init.yaml \
  --ssh-key "$SSH_KEY"

IP=$(yc compute instance get "$VM_NAME" --folder-id "$FOLDER_ID" --profile "$PROFILE" --format json \
  | python -c 'import sys,json;d=json.load(sys.stdin);print(d["network_interfaces"][0]["primary_v4_address"]["one_to_one_nat"]["address"])')

cat <<EOF

✅ VM создана. Публичный IP: $IP

Дальше (залить секреты и запустить):
  scp .env yc-user@$IP:/opt/tutorai/.env
  scp secrets/sa-key.json yc-user@$IP:/opt/tutorai/secrets/sa-key.json
  ssh yc-user@$IP 'cd /opt/tutorai && sudo docker compose up -d --build && sudo docker compose logs -f bot'

(cloud-init ставит Docker и клонирует репозиторий ~1–2 минуты после создания.)
EOF
