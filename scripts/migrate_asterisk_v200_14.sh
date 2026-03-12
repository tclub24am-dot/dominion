#!/bin/bash
# ============================================================
# S-GLOBAL DOMINION — Миграция v200.14: S-АТС Asterisk
# Добавляет поле asterisk_unique_id в таблицу call_logs
# Запуск: bash scripts/migrate_asterisk_v200_14.sh
# ============================================================

set -e

echo "=== S-GLOBAL DOMINION: Миграция v200.14 (S-АТС Asterisk) ==="
echo "Время: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Проверяем, что контейнер БД запущен
if ! docker ps | grep -q dominion_db; then
    echo "❌ ОШИБКА: Контейнер dominion_db не запущен!"
    echo "   Запустите: docker-compose up -d db"
    exit 1
fi

echo "✅ Контейнер dominion_db найден"
echo ""

# Проверяем, существует ли уже колонка (идемпотентность)
echo "🔍 Проверяем наличие колонки asterisk_unique_id..."
COLUMN_EXISTS=$(docker exec dominion_db psql -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-dominion}" -tAc \
    "SELECT COUNT(*) FROM information_schema.columns \
     WHERE table_name='call_logs' AND column_name='asterisk_unique_id';" 2>/dev/null || echo "0")

if [ "$COLUMN_EXISTS" = "1" ]; then
    echo "ℹ️  Колонка asterisk_unique_id уже существует — пропускаем"
else
    echo "➕ Добавляем колонку asterisk_unique_id..."
    docker exec dominion_db psql -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-dominion}" -c \
        "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS asterisk_unique_id VARCHAR(64);"
    echo "✅ Колонка добавлена"
fi

# Создаём UNIQUE индекс (идемпотентно и совместимо с legacy non-unique индексом)
echo "📊 Проверяем индекс ix_call_logs_asterisk_uid..."
IS_UNIQUE=$(docker exec dominion_db psql -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-dominion}" -tAc \
    "SELECT COALESCE((SELECT indisunique FROM pg_indexes i JOIN pg_class c ON c.relname = i.indexname JOIN pg_index pi ON pi.indexrelid = c.oid WHERE i.schemaname = 'public' AND i.tablename = 'call_logs' AND i.indexname = 'ix_call_logs_asterisk_uid' LIMIT 1)::int, 0);" 2>/dev/null || echo "0")

if [ "$IS_UNIQUE" = "1" ]; then
    echo "✅ UNIQUE индекс ix_call_logs_asterisk_uid уже существует"
else
    echo "⚠️  Индекс ix_call_logs_asterisk_uid отсутствует или не UNIQUE — пересоздаём"
    docker exec dominion_db psql -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-dominion}" -c \
        "DROP INDEX IF EXISTS ix_call_logs_asterisk_uid;"
    docker exec dominion_db psql -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-dominion}" -c \
        "CREATE UNIQUE INDEX ix_call_logs_asterisk_uid ON call_logs(asterisk_unique_id) WHERE asterisk_unique_id IS NOT NULL;"
    echo "✅ UNIQUE индекс создан"
fi

echo ""
echo "=== ✅ Миграция v200.14 завершена успешно ==="
echo ""
echo "Следующие шаги:"
echo "  1. Убедитесь, что ATS_WEBHOOK_SECRET задан в .env"
echo "  2. Запустите S-АТС: docker-compose up -d asterisk"
echo "  3. Проверьте логи: docker logs dominion_asterisk -f"
