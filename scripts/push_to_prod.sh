#!/bin/bash
# ============================================================
# S-GLOBAL DOMINION — scripts/push_to_prod.sh
# Быстрый деплой кода на продакшн сервер 89.169.39.111
#
# ЗАПУСК (с локальной машины):
#   bash scripts/push_to_prod.sh
#
# ТРЕБОВАНИЯ:
#   - SSH ключ настроен для root@89.169.39.111
#   - rsync установлен локально
# ============================================================

set -e

SERVER="root@89.169.39.111"
REMOTE_DIR="/root/dominion"
LOCAL_DIR="/home/armsp/dominion"

echo "🚀 S-GLOBAL DOMINION — Деплой на продакшн"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   Источник: $LOCAL_DIR"
echo "   Цель:     $SERVER:$REMOTE_DIR"
echo ""

# Шаг 1: Синхронизация кода
echo "📦 Синхронизация кода..."
rsync -avz --progress \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='__pycache__' \
  --exclude='.env' \
  --exclude='nginx/certs' \
  --exclude='frontend/dist' \
  --exclude='backups' \
  --exclude='storage' \
  --exclude='*.pyc' \
  -e "ssh -o StrictHostKeyChecking=no" \
  "${LOCAL_DIR}/" "${SERVER}:${REMOTE_DIR}/"

echo ""
echo "🔨 Пересборка и перезапуск контейнеров на сервере..."
ssh -o StrictHostKeyChecking=no "$SERVER" "
  cd ${REMOTE_DIR}
  echo '📦 Сборка образов...'
  docker compose -f docker-compose.prod.yml build --no-cache frontend app
  echo '🚀 Перезапуск контейнеров...'
  docker compose -f docker-compose.prod.yml up -d
  echo '⏳ Ожидание запуска...'
  sleep 10
  echo '📊 Статус контейнеров:'
  docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
  echo ''
  echo '📋 Логи app (последние 20 строк):'
  docker logs dominion_app --tail=20
"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Деплой завершён!"
echo "   Проверьте: https://s-global.space/"
