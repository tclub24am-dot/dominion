#!/bin/bash
# S-GLOBAL DOMINION — Скрипт восстановления
# VERSHINA v200.16 — Запускать из ~/dominion

set -e
cd ~/dominion

echo "=== СТАТУС КОНТЕЙНЕРОВ ==="
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

echo ""
echo "=== ЛОГИ dominion_app (последние 50 строк) ==="
docker logs dominion_app --tail 50 2>&1

echo ""
echo "=== ТЕСТ ПОДКЛЮЧЕНИЯ К API ==="
docker exec dominion_app curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" http://localhost:8001/api/v1/health 2>&1 || echo "CURL внутри контейнера не работает"

echo ""
echo "=== ПЕРЕСБОРКА FRONTEND ==="
docker compose build --no-cache frontend 2>&1

echo ""
echo "=== ПЕРЕЗАПУСК FRONTEND ==="
docker compose up -d --force-recreate frontend 2>&1

echo ""
echo "=== ПЕРЕЗАПУСК ASTERISK (с новыми переменными) ==="
docker compose up -d --force-recreate asterisk 2>&1

echo ""
echo "=== ФИНАЛЬНЫЙ СТАТУС ==="
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

echo ""
echo "✅ Восстановление завершено!"
