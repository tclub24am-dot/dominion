#!/bin/bash
# ============================================================
# S-GLOBAL DOMINION — scripts/certbot_issue.sh
# Получение SSL сертификата Let's Encrypt через Docker certbot
# Метод: webroot (nginx продолжает работать)
#
# ТРЕБОВАНИЯ:
#   - Запускать на продакшн сервере 89.169.39.111
#   - DNS: s-global.space → 89.169.39.111 (должен быть настроен)
#   - Порт 80 должен быть открыт и доступен из интернета
#   - docker compose -f docker-compose.prod.yml up -d (nginx должен работать)
#
# ИСПОЛЬЗОВАНИЕ:
#   bash scripts/certbot_issue.sh
# ============================================================

set -e

DOMAIN="s-global.space"
EMAIL="${CERTBOT_EMAIL:-admin@s-global.space}"
COMPOSE_FILE="docker-compose.prod.yml"

echo "🔐 S-GLOBAL DOMINION — SSL сертификат Let's Encrypt"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   Домен:  $DOMAIN"
echo "   Email:  $EMAIL"
echo "   Метод:  webroot (nginx продолжает работать)"
echo ""

# Проверяем что nginx запущен
if ! docker ps --filter "name=dominion_nginx" --filter "status=running" | grep -q dominion_nginx; then
    echo "❌ dominion_nginx не запущен! Запустите сначала:"
    echo "   docker compose -f $COMPOSE_FILE up -d"
    exit 1
fi

echo "✅ dominion_nginx работает"

# Получаем имя Docker volume для certbot_webroot
WEBROOT_VOLUME=$(docker inspect dominion_nginx --format '{{range .Mounts}}{{if eq .Destination "/var/www/certbot"}}{{.Name}}{{end}}{{end}}' 2>/dev/null || echo "")

if [ -z "$WEBROOT_VOLUME" ]; then
    echo "⚠  Volume certbot_webroot не найден в nginx. Используем standalone метод."
    echo "   Останавливаем nginx на время получения сертификата..."
    docker stop dominion_nginx

    docker run --rm \
      -p 80:80 \
      -v /etc/letsencrypt:/etc/letsencrypt \
      -v /var/lib/letsencrypt:/var/lib/letsencrypt \
      certbot/certbot:latest certonly \
      --standalone \
      --non-interactive \
      --agree-tos \
      --email "$EMAIL" \
      -d "$DOMAIN" \
      -d "www.$DOMAIN"

    echo "🚀 Перезапускаем nginx..."
    docker compose -f "$COMPOSE_FILE" up -d --no-deps nginx
else
    echo "✅ Volume certbot_webroot: $WEBROOT_VOLUME"
    echo "🌐 Запускаем certbot (webroot mode — nginx не останавливается)..."

    docker run --rm \
      -v /etc/letsencrypt:/etc/letsencrypt \
      -v /var/lib/letsencrypt:/var/lib/letsencrypt \
      -v "${WEBROOT_VOLUME}:/var/www/certbot" \
      certbot/certbot:latest certonly \
      --webroot \
      --webroot-path=/var/www/certbot \
      --non-interactive \
      --agree-tos \
      --email "$EMAIL" \
      -d "$DOMAIN" \
      -d "www.$DOMAIN"

    echo "🔄 Перезагружаем nginx конфиг (без остановки)..."
    docker exec dominion_nginx nginx -s reload
fi

echo ""
echo "✅ Сертификат получен!"
echo "   Путь: /etc/letsencrypt/live/$DOMAIN/"
ls -la /etc/letsencrypt/live/$DOMAIN/ 2>/dev/null || true

echo ""
echo "🔍 Проверяем HTTPS..."
sleep 2
curl -sk -o /dev/null -w "HTTPS статус: %{http_code}\n" "https://$DOMAIN/health" || \
curl -sk -o /dev/null -w "HTTPS localhost статус: %{http_code}\n" "https://localhost/health" || true

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🌟 SSL сертификат установлен. Цитадель защищена!"
echo ""
echo "📅 Автообновление — добавить в crontab (crontab -e):"
echo "   0 3 1,15 * * docker run --rm -v /etc/letsencrypt:/etc/letsencrypt -v /var/lib/letsencrypt:/var/lib/letsencrypt certbot/certbot:latest renew --quiet && docker exec dominion_nginx nginx -s reload"
