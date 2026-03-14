#!/bin/bash
# ============================================================
# S-GLOBAL DOMINION — scripts/deploy_server.sh
# Протокол: VERSHINA v200.17 PRODUCTION
# Сервер: 89.169.39.111 / s-global.space
#
# ЗАПУСК НА СЕРВЕРЕ (одна команда):
#   cd /root/dominion && bash scripts/deploy_server.sh
#
# Скрипт выполняет:
#   1. Проверку зависимостей (Docker, Docker Compose, Certbot)
#   2. Проверку .env файла
#   3. Получение SSL-сертификата (Let's Encrypt)
#   4. Настройку firewall (UFW)
#   5. Сборку и запуск всех контейнеров
#   6. Инициализацию БД и мастер-пользователя
#   7. Проверку работоспособности
# ============================================================
set -euo pipefail

# ── Конфигурация ──────────────────────────────────────────────
DOMAIN="s-global.space"
SERVER_IP="89.169.39.111"
PROJECT_DIR="/root/dominion"
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env"

# ── Цвета ─────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}ℹ️  $1${NC}"; }
log_success() { echo -e "${GREEN}✅ $1${NC}"; }
log_warn()    { echo -e "${YELLOW}⚠️  $1${NC}"; }
log_error()   { echo -e "${RED}❌ $1${NC}" >&2; }
log_step()    { echo -e "\n${CYAN}${BOLD}══════════════════════════════════════${NC}"; echo -e "${CYAN}${BOLD}  $1${NC}"; echo -e "${CYAN}${BOLD}══════════════════════════════════════${NC}"; }

# ── Баннер ────────────────────────────────────────────────────
echo -e "${YELLOW}${BOLD}"
echo "  ╔═══════════════════════════════════════════╗"
echo "  ║   S-GLOBAL DOMINION — PRODUCTION DEPLOY   ║"
echo "  ║   Протокол: VERSHINA v200.17               ║"
echo "  ║   Сервер: ${DOMAIN}              ║"
echo "  ╚═══════════════════════════════════════════╝"
echo -e "${NC}"

# ── Проверка: запуск от root ──────────────────────────────────
if [ "$(id -u)" -ne 0 ]; then
    log_error "Скрипт должен запускаться от root!"
    exit 1
fi

# ── Переход в директорию проекта ─────────────────────────────
cd "${PROJECT_DIR}"
log_info "Рабочая директория: $(pwd)"

# ============================================================
# ШАГ 1: Проверка зависимостей
# ============================================================
log_step "ШАГ 1: Проверка зависимостей"

check_command() {
    if command -v "$1" &>/dev/null; then
        log_success "$1 найден: $(command -v $1)"
    else
        log_error "$1 не найден! Установите: $2"
        exit 1
    fi
}

check_command "docker" "apt-get install -y docker.io"
check_command "docker-compose" "apt-get install -y docker-compose-plugin"

# Проверяем docker compose v2 (плагин)
if docker compose version &>/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
    log_success "Docker Compose v2 (плагин): OK"
elif docker-compose version &>/dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
    log_success "Docker Compose v1: OK"
else
    log_error "Docker Compose не найден!"
    log_info "Установка: apt-get install -y docker-compose-plugin"
    exit 1
fi

# Certbot (опционально — если нет, SSL пропускаем)
if command -v certbot &>/dev/null; then
    log_success "Certbot найден"
    HAS_CERTBOT=1
else
    log_warn "Certbot не найден. SSL-сертификат нужно получить вручную."
    log_info "Установка: apt-get install -y certbot python3-certbot-nginx"
    HAS_CERTBOT=0
fi

# ============================================================
# ШАГ 2: Проверка .env файла
# ============================================================
log_step "ШАГ 2: Проверка конфигурации .env"

if [ ! -f "${ENV_FILE}" ]; then
    log_warn ".env файл не найден. Создаём из шаблона..."
    if [ -f ".env.production" ]; then
        cp .env.production .env
        log_warn "ВНИМАНИЕ: Заполните .env реальными значениями!"
        log_warn "Откройте: nano .env"
        log_warn "Затем перезапустите скрипт."
        exit 1
    else
        log_error "Шаблон .env.production не найден!"
        exit 1
    fi
fi

# Проверяем критические переменные
MISSING_VARS=0
check_env_var() {
    local VAR="$1"
    local VALUE
    VALUE=$(grep "^${VAR}=" "${ENV_FILE}" | cut -d'=' -f2- | tr -d '"' | tr -d "'")
    if [ -z "${VALUE}" ] || echo "${VALUE}" | grep -q "REPLACE_WITH"; then
        log_error "Переменная ${VAR} не заполнена в .env!"
        MISSING_VARS=1
    else
        log_success "${VAR}: ✓"
    fi
}

check_env_var "SECRET_KEY"
check_env_var "POSTGRES_PASSWORD"
check_env_var "DATABASE_URL"
check_env_var "REDIS_PASSWORD"
check_env_var "MASTER_BOOTSTRAP_PASSWORD"
check_env_var "EXTERNAL_IP"

if [ "${MISSING_VARS}" -eq 1 ]; then
    log_error "Заполните все обязательные переменные в .env и перезапустите скрипт."
    exit 1
fi

# Устанавливаем права на .env
chmod 600 "${ENV_FILE}"
log_success ".env защищён (chmod 600)"

# ============================================================
# ШАГ 3: Настройка Firewall (UFW)
# ============================================================
log_step "ШАГ 3: Настройка Firewall"

if command -v ufw &>/dev/null; then
    ufw --force reset
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow 22/tcp    comment "SSH"
    ufw allow 80/tcp    comment "HTTP (redirect to HTTPS)"
    ufw allow 443/tcp   comment "HTTPS"
    ufw allow 5060/udp  comment "SIP UDP (Asterisk)"
    ufw allow 5061/tcp  comment "SIP TCP (Asterisk)"
    ufw allow 8089/tcp  comment "Asterisk WebRTC WSS"
    ufw allow 10000:20000/udp comment "RTP Media (Asterisk)"
    # Закрываем внутренние порты
    ufw deny 8001/tcp   comment "FastAPI — только через Nginx"
    ufw deny 5432/tcp   comment "PostgreSQL — только Docker"
    ufw deny 6379/tcp   comment "Redis — только Docker"
    ufw deny 11434/tcp  comment "Ollama — только Docker"
    ufw deny 8008/tcp   comment "Synapse — только Docker"
    ufw --force enable
    log_success "UFW настроен и активирован"
    ufw status numbered
else
    log_warn "UFW не найден. Настройте firewall вручную."
fi

# ============================================================
# ШАГ 4: SSL-сертификат (Let's Encrypt)
# ============================================================
log_step "ШАГ 4: SSL-сертификат Let's Encrypt"

SSL_CERT="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"

if [ -f "${SSL_CERT}" ]; then
    log_success "SSL-сертификат уже существует: ${SSL_CERT}"
    # Проверяем срок действия
    EXPIRY=$(openssl x509 -enddate -noout -in "${SSL_CERT}" 2>/dev/null | cut -d= -f2)
    log_info "Срок действия: ${EXPIRY}"
elif [ "${HAS_CERTBOT}" -eq 1 ]; then
    log_info "Получаем SSL-сертификат для ${DOMAIN}..."
    log_warn "Убедитесь что DNS ${DOMAIN} → ${SERVER_IP} уже настроен!"
    read -p "DNS настроен? Продолжить получение сертификата? (yes/no): " SSL_CONFIRM
    if [ "${SSL_CONFIRM}" = "yes" ]; then
        # Временно запускаем nginx для ACME challenge
        certbot certonly \
            --standalone \
            --non-interactive \
            --agree-tos \
            --email admin@s-global.space \
            -d "${DOMAIN}" \
            -d "www.${DOMAIN}" \
            --preferred-challenges http
        log_success "SSL-сертификат получен!"

        # Настройка автообновления
        (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet && ${COMPOSE_CMD} -f ${PROJECT_DIR}/${COMPOSE_FILE} restart nginx") | crontab -
        log_success "Автообновление SSL настроено (cron)"
    else
        log_warn "SSL пропущен. Nginx не запустится без сертификата!"
        log_warn "Получите сертификат вручную: certbot certonly --standalone -d ${DOMAIN}"
    fi
else
    log_warn "Certbot не установлен. Получите SSL вручную:"
    log_warn "  apt-get install -y certbot"
    log_warn "  certbot certonly --standalone -d ${DOMAIN} -d www.${DOMAIN}"
fi

# ============================================================
# ШАГ 5: Сборка и запуск контейнеров
# ============================================================
log_step "ШАГ 5: Сборка и запуск контейнеров"

log_info "Останавливаем старые контейнеры (если есть)..."
${COMPOSE_CMD} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" down --remove-orphans 2>/dev/null || true

log_info "Собираем образы (это может занять 5-10 минут)..."
${COMPOSE_CMD} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build --no-cache

log_info "Запускаем контейнеры..."
${COMPOSE_CMD} -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d

log_info "Ожидаем запуска сервисов (30 сек)..."
sleep 30

# Проверяем статус
log_info "Статус контейнеров:"
${COMPOSE_CMD} -f "${COMPOSE_FILE}" ps

# ============================================================
# ШАГ 6: Инициализация БД
# ============================================================
log_step "ШАГ 6: Инициализация базы данных"

log_info "Ожидаем готовности БД..."
for i in $(seq 1 30); do
    if docker exec dominion_db pg_isready -U dominion_user -d dominion_db &>/dev/null; then
        log_success "БД готова!"
        break
    fi
    echo -n "."
    sleep 2
done

# Создаём таблицы (если первый деплой)
log_info "Инициализация схемы БД..."
docker exec -e PYTHONPATH=/app dominion_app python -m app.create_db 2>&1 | tail -5 || \
    log_warn "create_db завершился с ошибкой (возможно таблицы уже существуют)"

# Создаём мастер-пользователя (если первый деплой)
log_info "Создание мастер-пользователя (Спартак)..."
docker exec -e PYTHONPATH=/app dominion_app python -m app.create_master_user 2>&1 | tail -5 || \
    log_warn "create_master_user завершился с ошибкой (возможно пользователь уже существует)"

# Создаём аккаунты руководителей (Алик, Михаил, Левон, Екатерина, Логист)
log_info "Создание аккаунтов руководителей..."
docker exec -e PYTHONPATH=/app dominion_app python /app/scripts/create_test_users.py 2>&1 | tail -10 || \
    log_warn "create_test_users завершился с ошибкой (возможно пользователи уже существуют)"

# Активируем логиста (на случай если is_active=false)
log_info "Активация аккаунта логиста..."
docker exec dominion_db psql -U dominion_user -d dominion_db \
    -c "UPDATE users SET is_active = true WHERE username = 'logist';" 2>&1 || true

# Загружаем данные логистики за 10 марта (ВкусВилл, маржа 49.9к)
log_info "Загрузка данных логистики за 10.03.2026..."
docker exec dominion_app mkdir -p /app/scripts 2>/dev/null || true
docker cp "${PROJECT_DIR}/scripts/load_m4_march_10.py" dominion_app:/app/scripts/load_m4_march_10.py 2>/dev/null || true
docker exec -e PYTHONPATH=/app dominion_app python /app/scripts/load_m4_march_10.py 2>&1 | tail -10 || \
    log_warn "load_m4_march_10 завершился с ошибкой (возможно данные уже загружены)"

# ============================================================
# ШАГ 7: Проверка работоспособности
# ============================================================
log_step "ШАГ 7: Проверка работоспособности"

# Health check API
log_info "Проверяем API health check..."
for i in $(seq 1 10); do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/health 2>/dev/null || echo "000")
    if [ "${HTTP_CODE}" = "200" ]; then
        log_success "API отвечает: HTTP ${HTTP_CODE}"
        break
    fi
    log_warn "API не отвечает (попытка ${i}/10, код: ${HTTP_CODE})..."
    sleep 5
done

# Проверяем HTTPS (если SSL настроен)
if [ -f "${SSL_CERT}" ]; then
    log_info "Проверяем HTTPS..."
    HTTPS_CODE=$(curl -s -o /dev/null -w "%{http_code}" https://${DOMAIN}/health 2>/dev/null || echo "000")
    if [ "${HTTPS_CODE}" = "200" ]; then
        log_success "HTTPS работает: HTTP ${HTTPS_CODE}"
    else
        log_warn "HTTPS вернул код: ${HTTPS_CODE}"
    fi
fi

# ============================================================
# ИТОГ
# ============================================================
log_step "ДЕПЛОЙ ЗАВЕРШЁН"

echo -e "${GREEN}${BOLD}"
echo "  ╔═══════════════════════════════════════════════════╗"
echo "  ║   ✅ S-GLOBAL DOMINION ЗАПУЩЕН!                   ║"
echo "  ╠═══════════════════════════════════════════════════╣"
echo "  ║   🌐 Сайт:    https://${DOMAIN}          ║"
echo "  ║   🔌 API:     https://${DOMAIN}/api/      ║"
echo "  ║   📞 SIP:     sip:${SERVER_IP}:5060       ║"
echo "  ║   🎙️  WebRTC:  wss://${DOMAIN}/ws-sip/    ║"
echo "  ╠═══════════════════════════════════════════════════╣"
echo "  ║   Логи:  docker compose -f ${COMPOSE_FILE} logs -f  ║"
echo "  ╚═══════════════════════════════════════════════════╝"
echo -e "${NC}"

log_info "Настройка автобэкапа БД (cron):"
echo "  Добавьте в crontab: 0 3 * * * cd ${PROJECT_DIR} && bash scripts/dump_db.sh cron >> /var/log/dominion_backup.log 2>&1"
