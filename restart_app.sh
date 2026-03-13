#!/bin/bash
# S-GLOBAL DOMINION — Перезапуск app с новым .env
# VERSHINA v200.16

cd /home/armsp/dominion

echo "=== ПЕРЕЗАПУСК dominion_app ==="
docker compose --env-file .env up -d --force-recreate app 2>&1

echo ""
echo "=== ОЖИДАНИЕ 15 СЕКУНД ==="
sleep 15

echo ""
echo "=== СТАТУС ==="
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

echo ""
echo "=== ЛОГИ dominion_app (последние 50 строк) ==="
docker logs dominion_app --tail 50 2>&1

echo ""
echo "=== ТЕСТ API ==="
docker exec dominion_app curl -s -o /dev/null -w "HTTP: %{http_code}" http://localhost:8001/ 2>&1 || echo "curl не доступен"

echo ""
echo "=== ПРОЦЕССЫ В КОНТЕЙНЕРЕ ==="
docker exec dominion_app ps aux 2>&1

echo ""
echo "=== ПОРТЫ В КОНТЕЙНЕРЕ ==="
docker exec dominion_app ss -tlnp 2>&1 || docker exec dominion_app netstat -tlnp 2>&1 || echo "ss/netstat не доступны"

echo "DONE"
