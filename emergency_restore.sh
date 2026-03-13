#!/bin/bash
# S-GLOBAL DOMINION — АВАРИЙНОЕ ВОССТАНОВЛЕНИЕ
# Удаляет все остановленные контейнеры и запускает систему заново

set -e
cd /home/armsp/dominion

echo "=== УДАЛЕНИЕ ОСТАНОВЛЕННЫХ КОНТЕЙНЕРОВ ==="
docker container prune -f 2>&1

echo ""
echo "=== ЗАПУСК db И redis ==="
docker compose up -d db redis 2>&1

echo ""
echo "=== ОЖИДАНИЕ ГОТОВНОСТИ db (30 секунд) ==="
sleep 30

echo ""
echo "=== СТАТУС db ==="
docker ps --filter name=dominion_db --format 'table {{.Names}}\t{{.Status}}'

echo ""
echo "=== ЗАПУСК app ==="
docker compose up -d app 2>&1

echo ""
echo "=== ОЖИДАНИЕ ЗАПУСКА app (20 секунд) ==="
sleep 20

echo ""
echo "=== ФИНАЛЬНЫЙ СТАТУС ==="
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

echo ""
echo "=== ТЕСТ API ==="
curl -s -o /dev/null -w "HTTP_CODE: %{http_code}\n" http://localhost:8001/ 2>&1 || echo "curl не доступен из WSL"

echo "DONE"
