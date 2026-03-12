#!/bin/bash

# S-GLOBAL DOMINION - Скрипт запуска и проверки системы
# v200.10 - Восхождение

echo "🏛️ S-GLOBAL DOMINION - ЗАПУСК СИСТЕМЫ"
echo "========================================"

# Проверка наличия Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker не установлен. Установите Docker для продолжения."
    exit 1
fi

# Проверка наличия Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose не установлен. Установите Docker Compose для продолжения."
    exit 1
fi

# Остановка существующих контейнеров (если есть)
echo "🔄 Останавливаем существующие контейнеры..."
docker-compose down

# Проверка наличия резервной копии
if [ -f "dominion_backup_feb2026.tar" ]; then
    echo "💾 Найдена резервная копия базы данных. Хотите восстановить данные? (y/n)"
    read -r restore_backup
    
    if [ "$restore_backup" = "y" ]; then
        echo "🔄 Восстанавливаем данные из резервной копии..."
        # Запускаем только базу данных
        docker-compose up -d db
        
        # Ждем, пока база данных запустится
        echo "⏳ Ожидаем запуска базы данных..."
        sleep 10
        
        # Восстанавливаем данные
        docker exec -i dominion_db pg_restore -U dominion_user -d dominion_db < dominion_backup_feb2026.tar
        
        echo "✅ Данные восстановлены!"
    fi
fi

# Запуск контейнеров
echo "🚀 Запускаем S-GLOBAL DOMINION..."
docker-compose up -d

# Проверка статуса контейнеров
echo "🔍 Проверка статуса контейнеров..."
sleep 5
docker-compose ps

echo ""
echo "✨ S-GLOBAL DOMINION запущен!"
echo "🌐 Доступ к системе: https://s-global.space (или http://89.169.39.111:8001)"
echo "👑 Логин: master"
echo "🔑 Пароль: см. MASTER_BOOTSTRAP_PASSWORD в .env"
echo ""
echo "📊 Мониторинг логов: docker-compose logs -f"