#!/bin/bash
# ============================================================
# S-GLOBAL DOMINION — entrypoint.sh
# Протокол: VERSHINA v200.14
# ============================================================
set -euo pipefail

echo "🏛️ S-GLOBAL DOMINION — ЗАПУСК v200.14"

# ============================================================
# ПРОВЕРКА ОБЯЗАТЕЛЬНЫХ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ
# Если переменная не задана — система не стартует (fail-fast)
# ============================================================
REQUIRED_VARS=(
    "POSTGRES_USER"
    "POSTGRES_PASSWORD"
    "POSTGRES_DB"
    "SECRET_KEY"
    "ATS_WEBHOOK_SECRET"
)

MISSING=0
for VAR in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!VAR:-}" ]; then
        echo "❌ FATAL: Переменная окружения '${VAR}' не задана!" >&2
        MISSING=1
    fi
done

if [ "$MISSING" -eq 1 ]; then
    echo "❌ FATAL: Система не может стартовать без обязательных переменных." >&2
    echo "   Задайте все переменные в файле .env и перезапустите контейнер." >&2
    exit 1
fi

# ============================================================
# ОЖИДАНИЕ ГОТОВНОСТИ POSTGRESQL (pg_isready — надёжнее sleep)
# ============================================================
DB_HOST="${POSTGRES_HOST:-db}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_USER="${POSTGRES_USER}"
DB_NAME="${POSTGRES_DB}"

echo "⏳ Ожидание готовности PostgreSQL (${DB_HOST}:${DB_PORT})..."

MAX_RETRIES=30
RETRY_INTERVAL=2
RETRIES=0

until pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -q; do
    RETRIES=$((RETRIES + 1))
    if [ "$RETRIES" -ge "$MAX_RETRIES" ]; then
        echo "❌ FATAL: PostgreSQL не ответил за $((MAX_RETRIES * RETRY_INTERVAL)) секунд. Аварийный стоп." >&2
        exit 1
    fi
    echo "   PostgreSQL не готов (попытка ${RETRIES}/${MAX_RETRIES}). Повтор через ${RETRY_INTERVAL}с..."
    sleep "${RETRY_INTERVAL}"
done

echo "✅ PostgreSQL готов!"

# ============================================================
# ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ
# ============================================================
echo "📦 Создание таблиц в базе данных..."
python -m app.create_db

echo "👤 Инициализация мастер-пользователя..."
python -m app.create_master_user

# ============================================================
# ЗАПУСК ПРИЛОЖЕНИЯ
# VERSHINA v200.15: --workers 1 — один воркер исключает дублирование
# фоновых задач lifespan (двойные уведомления, конфликты в БД).
# ============================================================
echo "🚀 Запуск FastAPI приложения на порту 8001 (1 воркер)..."
exec uvicorn main:app --host 0.0.0.0 --port 8001 --workers 1 --log-level info
