#!/bin/bash
# ============================================================
# S-GLOBAL DOMINION — Deploy Migration v200.13
# S-АТС: Применение миграции call_logs на сервере
# 
# Запуск: bash scripts/deploy_migration_v200_13.sh
# Сервер: 89.169.39.111
# ============================================================

set -e  # Остановить при любой ошибке

echo "============================================================"
echo "  S-GLOBAL DOMINION — Migration v200.13"
echo "  S-АТС: call_logs upgrade"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"

# Проверяем, что контейнер БД запущен
echo "[1/4] Проверка контейнера dominion_db..."
docker ps --filter "name=dominion_db" --format "{{.Names}}: {{.Status}}"

# Копируем SQL-скрипт в контейнер
echo "[2/4] Копирование миграционного скрипта..."
docker cp scripts/migration_v200_13_call_logs_s_ats.sql dominion_db:/tmp/migration_v200_13.sql

# Применяем миграцию
echo "[3/4] Применение миграции v200.13..."
docker exec dominion_db psql \
    -U dominion_user \
    -d dominion_db \
    -f /tmp/migration_v200_13.sql \
    -v ON_ERROR_STOP=1

# Верификация структуры
echo "[4/4] Верификация структуры таблицы call_logs..."
docker exec dominion_db psql \
    -U dominion_user \
    -d dominion_db \
    -c "\d call_logs"

echo ""
echo "============================================================"
echo "  ✅ S-OMEGA DATABASE UPGRADED TO v200.13"
echo "  База готова к приёму первого звонка через S-АТС!"
echo "============================================================"
