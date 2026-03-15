#!/bin/bash
# ============================================================
# S-GLOBAL DOMINION — ЗАПУСК ЦИТАДЕЛИ v200.31
# Скрипт полного восстановления: SSL + Docker стек
# Запуск: sudo bash scripts/launch_citadel_v200_31.sh
# ============================================================

set -e
DOMINION_DIR="/home/armsp/dominion"
DOMAIN="s-global.space"
EMAIL="tclub24am@gmail.com"

echo "╔══════════════════════════════════════════════════════╗"
echo "║     S-GLOBAL DOMINION — ЗАПУСК ЦИТАДЕЛИ v200.31     ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ─── ШАГ 1: Зачистка портов ────────────────────────────────
echo "[1/5] Зачистка портов 80 и 443..."
fuser -k 80/tcp 2>/dev/null && echo "  → Порт 80 освобождён" || echo "  → Порт 80 уже свободен"
fuser -k 443/tcp 2>/dev/null && echo "  → Порт 443 освобождён" || echo "  → Порт 443 уже свободен"
sleep 1

# ─── ШАГ 2: Остановка nginx (если запущен) ─────────────────
echo "[2/5] Остановка nginx контейнера..."
docker stop dominion_nginx 2>/dev/null && echo "  → dominion_nginx остановлен" || echo "  → dominion_nginx не запущен"
sleep 2

# ─── ШАГ 3: Получение SSL сертификата ──────────────────────
echo "[3/5] Получение SSL сертификата для ${DOMAIN}..."

# Проверяем, есть ли уже действующий сертификат
if [ -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]; then
    echo "  → Сертификат уже существует, проверяем срок действия..."
    EXPIRY=$(openssl x509 -enddate -noout -in "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" 2>/dev/null | cut -d= -f2)
    echo "  → Действителен до: ${EXPIRY}"
    echo "  → Пропускаем получение нового сертификата"
else
    echo "  → Сертификат не найден, запускаем certbot standalone..."
    docker run --rm \
        -p 80:80 \
        -v "/etc/letsencrypt:/etc/letsencrypt" \
        -v "/var/lib/letsencrypt:/var/lib/letsencrypt" \
        certbot/certbot certonly \
        --standalone \
        -d "${DOMAIN}" \
        --non-interactive \
        --agree-tos \
        -m "${EMAIL}" \
        --no-eff-email

    if [ $? -eq 0 ]; then
        echo "  ✅ SSL сертификат успешно получен!"
    else
        echo "  ❌ ОШИБКА получения сертификата!"
        echo "  Проверьте: DNS ${DOMAIN} → $(curl -s ifconfig.me 2>/dev/null || echo 'N/A')"
        exit 1
    fi
fi

# ─── ШАГ 4: Запуск полного стека ───────────────────────────
echo "[4/5] Запуск полного стека Docker Compose..."
cd "${DOMINION_DIR}"
docker compose -f docker-compose.prod.yml up -d --remove-orphans

echo "  → Ожидаем инициализацию контейнеров (15 сек)..."
sleep 15

# ─── ШАГ 5: Верификация ────────────────────────────────────
echo "[5/5] Верификация статуса контейнеров..."
echo ""
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""

# Проверяем nginx
NGINX_STATUS=$(docker inspect --format='{{.State.Status}}' dominion_nginx 2>/dev/null || echo "not found")
if [ "${NGINX_STATUS}" = "running" ]; then
    echo "  ✅ dominion_nginx: RUNNING"
else
    echo "  ❌ dominion_nginx: ${NGINX_STATUS}"
    echo "  Логи nginx:"
    docker logs dominion_nginx --tail=10 2>&1
fi

# Проверяем HTTP доступность
echo ""
echo "  Проверка HTTP доступности https://${DOMAIN}..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://${DOMAIN}/" 2>/dev/null || echo "000")
if [ "${HTTP_CODE}" = "200" ] || [ "${HTTP_CODE}" = "301" ] || [ "${HTTP_CODE}" = "302" ]; then
    echo "  ✅ https://${DOMAIN}/ → HTTP ${HTTP_CODE} — ДОСТУПЕН!"
else
    echo "  ⚠️  https://${DOMAIN}/ → HTTP ${HTTP_CODE}"
fi

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║           ЗАПУСК ЦИТАДЕЛИ ЗАВЕРШЁН                  ║"
echo "╚══════════════════════════════════════════════════════╝"
