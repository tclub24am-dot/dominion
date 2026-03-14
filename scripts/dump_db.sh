#!/bin/bash
# ============================================================
# S-GLOBAL DOMINION — scripts/dump_db.sh
# Протокол: VERSHINA v200.17
# Экспорт базы данных с локального сервера и импорт на боевой
#
# ИСПОЛЬЗОВАНИЕ:
#   # Экспорт (на локальной машине):
#   ./scripts/dump_db.sh export
#
#   # Импорт (на боевом сервере):
#   ./scripts/dump_db.sh import /path/to/dominion_backup.sql.gz
#
#   # Полный цикл: экспорт + загрузка на сервер + импорт:
#   ./scripts/dump_db.sh deploy 89.169.39.111
# ============================================================
set -euo pipefail

# ── Конфигурация ──────────────────────────────────────────────
CONTAINER="dominion_db"
DB_USER="${POSTGRES_USER:-dominion_user}"
DB_NAME="${POSTGRES_DB:-dominion_db}"
BACKUP_DIR="${BACKUP_DIR:-/root/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/dominion_${TIMESTAMP}.sql.gz"
REMOTE_USER="${REMOTE_USER:-root}"
REMOTE_DIR="/root/dominion/backups"

# ── Цвета для вывода ──────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info()    { echo -e "${BLUE}ℹ️  [DB] $1${NC}"; }
log_success() { echo -e "${GREEN}✅ [DB] $1${NC}"; }
log_warn()    { echo -e "${YELLOW}⚠️  [DB] $1${NC}"; }
log_error()   { echo -e "${RED}❌ [DB] $1${NC}" >&2; }

# ── Функция: экспорт БД ───────────────────────────────────────
do_export() {
    log_info "Начинаем экспорт базы данных '${DB_NAME}'..."
    log_info "Контейнер: ${CONTAINER}"
    log_info "Файл: ${BACKUP_FILE}"

    # Создаём директорию для бэкапов
    mkdir -p "${BACKUP_DIR}"

    # Проверяем что контейнер запущен
    if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
        log_error "Контейнер '${CONTAINER}' не запущен!"
        log_error "Запустите: docker-compose up -d db"
        exit 1
    fi

    # Экспорт с сжатием (gzip)
    log_info "Выполняем pg_dump (это может занять несколько минут)..."
    docker exec "${CONTAINER}" pg_dump \
        -U "${DB_USER}" \
        -d "${DB_NAME}" \
        --no-owner \
        --no-acl \
        --verbose \
        2>/dev/null | gzip > "${BACKUP_FILE}"

    # Проверяем размер файла
    BACKUP_SIZE=$(du -sh "${BACKUP_FILE}" | cut -f1)
    log_success "Экспорт завершён!"
    log_success "Файл: ${BACKUP_FILE}"
    log_success "Размер: ${BACKUP_SIZE}"

    # Показываем последние 5 бэкапов
    log_info "Последние бэкапы в ${BACKUP_DIR}:"
    ls -lht "${BACKUP_DIR}"/dominion_*.sql.gz 2>/dev/null | head -5 || true
}

# ── Функция: импорт БД ────────────────────────────────────────
do_import() {
    local IMPORT_FILE="${1:-}"

    if [ -z "${IMPORT_FILE}" ]; then
        log_error "Укажите файл для импорта!"
        echo "Использование: $0 import /path/to/backup.sql.gz"
        exit 1
    fi

    if [ ! -f "${IMPORT_FILE}" ]; then
        log_error "Файл не найден: ${IMPORT_FILE}"
        exit 1
    fi

    log_warn "⚠️  ВНИМАНИЕ: Импорт ПЕРЕЗАПИШЕТ текущую базу данных '${DB_NAME}'!"
    log_warn "Файл: ${IMPORT_FILE}"
    read -p "Продолжить? (yes/no): " CONFIRM
    if [ "${CONFIRM}" != "yes" ]; then
        log_info "Импорт отменён."
        exit 0
    fi

    # Проверяем что контейнер запущен
    if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
        log_error "Контейнер '${CONTAINER}' не запущен!"
        exit 1
    fi

    log_info "Начинаем импорт из ${IMPORT_FILE}..."

    # Создаём БД если не существует (на случай первого деплоя)
    docker exec "${CONTAINER}" psql -U "${DB_USER}" -c \
        "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1 || \
        docker exec "${CONTAINER}" psql -U "${DB_USER}" -c \
        "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};" 2>/dev/null || true

    # Импорт (распаковываем gzip на лету)
    log_info "Выполняем psql restore (это может занять несколько минут)..."
    gunzip -c "${IMPORT_FILE}" | docker exec -i "${CONTAINER}" psql \
        -U "${DB_USER}" \
        -d "${DB_NAME}" \
        --quiet \
        2>&1 | grep -v "^$" | grep -v "^SET$" | grep -v "^COMMIT$" | head -50 || true

    log_success "Импорт завершён!"
    log_info "Проверьте данные: docker exec ${CONTAINER} psql -U ${DB_USER} -d ${DB_NAME} -c '\\dt'"
}

# ── Функция: полный деплой (экспорт + загрузка + импорт) ─────
do_deploy() {
    local REMOTE_HOST="${1:-}"

    if [ -z "${REMOTE_HOST}" ]; then
        log_error "Укажите IP/хост сервера!"
        echo "Использование: $0 deploy 89.169.39.111"
        exit 1
    fi

    log_info "=== ПОЛНЫЙ ЦИКЛ ДЕПЛОЯ БД ==="
    log_info "Источник: localhost"
    log_info "Назначение: ${REMOTE_USER}@${REMOTE_HOST}"

    # Шаг 1: Экспорт
    log_info "--- ШАГ 1: Экспорт локальной БД ---"
    do_export

    # Шаг 2: Загрузка на сервер
    log_info "--- ШАГ 2: Загрузка на сервер ${REMOTE_HOST} ---"
    ssh "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p ${REMOTE_DIR}"
    log_info "Копируем ${BACKUP_FILE} → ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"
    scp "${BACKUP_FILE}" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"
    REMOTE_FILE="${REMOTE_DIR}/$(basename ${BACKUP_FILE})"
    log_success "Файл загружен: ${REMOTE_FILE}"

    # Шаг 3: Импорт на сервере
    log_info "--- ШАГ 3: Импорт на сервере ---"
    log_warn "Выполняем импорт на ${REMOTE_HOST}..."
    ssh "${REMOTE_USER}@${REMOTE_HOST}" "
        cd /root/dominion
        echo 'yes' | POSTGRES_USER=${DB_USER} POSTGRES_DB=${DB_NAME} \
            bash scripts/dump_db.sh import ${REMOTE_FILE}
    "

    log_success "=== ДЕПЛОЙ БД ЗАВЕРШЁН ==="
    log_success "База данных успешно перенесена на ${REMOTE_HOST}"
}

# ── Функция: создание бэкапа для cron ────────────────────────
do_cron_backup() {
    # Тихий режим для cron — без интерактивных запросов
    mkdir -p "${BACKUP_DIR}"

    docker exec "${CONTAINER}" pg_dump \
        -U "${DB_USER}" \
        -d "${DB_NAME}" \
        --no-owner \
        --no-acl \
        2>/dev/null | gzip > "${BACKUP_FILE}"

    # Удаляем бэкапы старше 7 дней
    find "${BACKUP_DIR}" -name "dominion_*.sql.gz" -mtime +7 -delete 2>/dev/null || true

    echo "[$(date)] Бэкап создан: ${BACKUP_FILE} ($(du -sh ${BACKUP_FILE} | cut -f1))"
}

# ── Главная логика ────────────────────────────────────────────
COMMAND="${1:-help}"

case "${COMMAND}" in
    export)
        do_export
        ;;
    import)
        do_import "${2:-}"
        ;;
    deploy)
        do_deploy "${2:-}"
        ;;
    cron)
        do_cron_backup
        ;;
    help|--help|-h)
        echo ""
        echo "S-GLOBAL DOMINION — Утилита управления базой данных"
        echo "Протокол: VERSHINA v200.17"
        echo ""
        echo "Использование:"
        echo "  $0 export                    — Экспорт БД в ${BACKUP_DIR}/"
        echo "  $0 import <file.sql.gz>      — Импорт БД из файла"
        echo "  $0 deploy <server_ip>        — Полный цикл: экспорт + загрузка + импорт"
        echo "  $0 cron                      — Тихий бэкап для cron (без интерактива)"
        echo ""
        echo "Переменные окружения:"
        echo "  POSTGRES_USER  — пользователь БД (по умолчанию: dominion_user)"
        echo "  POSTGRES_DB    — имя БД (по умолчанию: dominion_db)"
        echo "  BACKUP_DIR     — директория бэкапов (по умолчанию: /root/backups)"
        echo "  REMOTE_USER    — SSH пользователь (по умолчанию: root)"
        echo ""
        echo "Примеры:"
        echo "  ./scripts/dump_db.sh export"
        echo "  ./scripts/dump_db.sh import /root/backups/dominion_20260314_120000.sql.gz"
        echo "  ./scripts/dump_db.sh deploy 89.169.39.111"
        echo ""
        echo "Настройка автобэкапа (cron):"
        echo "  # Бэкап каждый день в 03:00:"
        echo "  0 3 * * * cd /root/dominion && ./scripts/dump_db.sh cron >> /var/log/dominion_backup.log 2>&1"
        echo ""
        ;;
    *)
        log_error "Неизвестная команда: ${COMMAND}"
        echo "Запустите '$0 help' для справки."
        exit 1
        ;;
esac
