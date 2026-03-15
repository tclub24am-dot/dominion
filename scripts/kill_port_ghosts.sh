#!/bin/bash
# ============================================================
# S-GLOBAL DOMINION — scripts/kill_port_ghosts.sh
# Зачистка портов 80/443 + SSL + запуск стека
# Запускать на сервере: bash scripts/kill_port_ghosts.sh
# ============================================================

set -e

echo "🛡️ Охота на призраков началась..."

# ── ШАГ 1: Останавливаем ВСЁ что держит порты ──────────────
systemctl stop nginx apache2 2>/dev/null || true
systemctl disable nginx apache2 2>/dev/null || true
docker stop dominion_nginx 2>/dev/null || true
fuser -k 80/tcp 443/tcp 2>/dev/null || true
sleep 2

echo "✅ Порты очищены."

# ── ШАГ 2: Проверяем что порт 80 реально свободен ───────────
if lsof -i :80 -n -P 2>/dev/null | grep -q LISTEN; then
    echo "❌ Порт 80 всё ещё занят!"
    lsof -i :80 -n -P
    exit 1
fi
echo "✅ Порт 80 свободен — запускаем Certbot..."

# ── ШАГ 3: Certbot standalone (порт 80 свободен) ────────────
# Системный certbot не установлен → используем Docker certbot
docker run --rm \
  -p 80:80 \
  -v /etc/letsencrypt:/etc/letsencrypt \
  -v /var/lib/letsencrypt:/var/lib/letsencrypt \
  certbot/certbot:latest certonly \
  --standalone \
  --non-interactive \
  --agree-tos \
  -m tclub24am@gmail.com \
  -d s-global.space \
  -d www.s-global.space

echo "🔐 SSL-сертификат получен!"
ls -la /etc/letsencrypt/live/s-global.space/

# ── ШАГ 4: Запуск Цитадели (nginx теперь найдёт сертификат) ─
echo "🚀 Перезапуск Цитадели..."
docker compose -f docker-compose.prod.yml up -d

echo ""
echo "✅ Готово! Проверка HTTPS:"
sleep 5
curl -sk -o /dev/null -w "HTTPS статус: %{http_code}\n" https://s-global.space/health || true

echo ""
echo "📅 Автообновление (добавить в crontab -e):"
echo "  0 3 1,15 * * docker run --rm -v /etc/letsencrypt:/etc/letsencrypt -v /var/lib/letsencrypt:/var/lib/letsencrypt certbot/certbot:latest renew --quiet && docker exec dominion_nginx nginx -s reload"
