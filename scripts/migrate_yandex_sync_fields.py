#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
S-GLOBAL DOMINION — Миграция для синхронизации с Яндекс.Диспетчерской
================================================================================
Версия: 1.2 (isolated transactions)
Дата: 2026-02-14
Автор: Chief AI Architect

Добавляет недостающие поля для полной синхронизации с Яндекс.Диспетчерской.

Запуск:
    python scripts/migrate_yandex_sync_fields.py
"""

import sys
import os
import asyncio
from pathlib import Path
from datetime import datetime

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.database import engine, AsyncSessionLocal


# Список SQL-команд для выполнения (каждая в отдельной транзакции)
MIGRATION_COMMANDS = [
    # === VEHICLES ===
    ("vehicles: yandex_status", "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS yandex_status VARCHAR(50) DEFAULT NULL"),
    ("vehicles: yandex_rental", "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS yandex_rental BOOLEAN DEFAULT NULL"),
    ("vehicles: yandex_last_sync_at", "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS yandex_last_sync_at TIMESTAMP DEFAULT NULL"),
    ("vehicles: yandex_park_id", "ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS yandex_park_id VARCHAR(100) DEFAULT NULL"),
    ("vehicles: idx yandex_status", "CREATE INDEX IF NOT EXISTS idx_vehicles_yandex_status ON vehicles(yandex_status)"),
    ("vehicles: idx yandex_park_id", "CREATE INDEX IF NOT EXISTS idx_vehicles_yandex_park_id ON vehicles(yandex_park_id)"),
    ("vehicles: idx yandex_last_sync", "CREATE INDEX IF NOT EXISTS idx_vehicles_yandex_last_sync ON vehicles(yandex_last_sync_at)"),
    
    # === USERS ===
    ("users: yandex_work_status", "ALTER TABLE users ADD COLUMN IF NOT EXISTS yandex_work_status VARCHAR(50) DEFAULT NULL"),
    ("users: yandex_balance_updated_at", "ALTER TABLE users ADD COLUMN IF NOT EXISTS yandex_balance_updated_at TIMESTAMP DEFAULT NULL"),
    ("users: yandex_rating", "ALTER TABLE users ADD COLUMN IF NOT EXISTS yandex_rating FLOAT DEFAULT NULL"),
    ("users: yandex_phones", "ALTER TABLE users ADD COLUMN IF NOT EXISTS yandex_phones JSONB DEFAULT '[]'::jsonb"),
    ("users: yandex_names", "ALTER TABLE users ADD COLUMN IF NOT EXISTS yandex_names JSONB DEFAULT '{}'::jsonb"),
    ("users: yandex_current_car", "ALTER TABLE users ADD COLUMN IF NOT EXISTS yandex_current_car JSONB DEFAULT '{}'::jsonb"),
    ("users: yandex_last_sync_at", "ALTER TABLE users ADD COLUMN IF NOT EXISTS yandex_last_sync_at TIMESTAMP DEFAULT NULL"),
    ("users: idx yandex_work_status", "CREATE INDEX IF NOT EXISTS idx_users_yandex_work_status ON users(yandex_work_status)"),
    ("users: idx yandex_rating", "CREATE INDEX IF NOT EXISTS idx_users_yandex_rating ON users(yandex_rating)"),
    ("users: idx yandex_last_sync", "CREATE INDEX IF NOT EXISTS idx_users_yandex_last_sync ON users(yandex_last_sync_at)"),
    
    # === DRIVER_PROFILES ===
    ("driver_profiles: yandex_balance", "ALTER TABLE driver_profiles ADD COLUMN IF NOT EXISTS yandex_balance FLOAT DEFAULT 0.0"),
    ("driver_profiles: yandex_rating", "ALTER TABLE driver_profiles ADD COLUMN IF NOT EXISTS yandex_rating FLOAT DEFAULT NULL"),
    ("driver_profiles: yandex_work_status", "ALTER TABLE driver_profiles ADD COLUMN IF NOT EXISTS yandex_work_status VARCHAR(50) DEFAULT NULL"),
    ("driver_profiles: yandex_last_sync_at", "ALTER TABLE driver_profiles ADD COLUMN IF NOT EXISTS yandex_last_sync_at TIMESTAMP DEFAULT NULL"),
    ("driver_profiles: idx yandex_balance", "CREATE INDEX IF NOT EXISTS idx_driver_profiles_yandex_balance ON driver_profiles(yandex_balance)"),
    ("driver_profiles: idx yandex_work_status", "CREATE INDEX IF NOT EXISTS idx_driver_profiles_yandex_work_status ON driver_profiles(yandex_work_status)"),
    
    # === YANDEX_SYNC_LOG TABLE ===
    ("yandex_sync_log: create table", """
        CREATE TABLE IF NOT EXISTS yandex_sync_log (
            id SERIAL PRIMARY KEY,
            sync_type VARCHAR(50) NOT NULL,
            park_id VARCHAR(100) NOT NULL,
            records_processed INTEGER DEFAULT 0,
            records_created INTEGER DEFAULT 0,
            records_updated INTEGER DEFAULT 0,
            errors_count INTEGER DEFAULT 0,
            error_details JSONB DEFAULT '[]'::jsonb,
            started_at TIMESTAMP NOT NULL,
            finished_at TIMESTAMP DEFAULT NULL,
            duration_seconds FLOAT DEFAULT NULL
        )
    """),
    ("yandex_sync_log: idx park", "CREATE INDEX IF NOT EXISTS idx_yandex_sync_log_park ON yandex_sync_log(park_id)"),
    ("yandex_sync_log: idx started", "CREATE INDEX IF NOT EXISTS idx_yandex_sync_log_started ON yandex_sync_log(started_at)"),
]


async def run_single_command(db, name: str, sql: str) -> tuple:
    """
    Выполняет одну SQL-команду в отдельной транзакции.
    Возвращает (success: bool, skipped: bool, error: str)
    """
    try:
        await db.execute(text(sql))
        await db.commit()
        return True, False, None
    except Exception as e:
        await db.rollback()
        error_msg = str(e)
        
        # Проверяем, является ли ошибка "already exists"
        if 'already exists' in error_msg.lower() or 'duplicate' in error_msg.lower():
            return True, True, None  # Считаем успехом, просто пропустили
        
        return False, False, error_msg


async def run_migration():
    """Выполняет миграцию базы данных (асинхронно)"""
    print("=" * 80)
    print("S-GLOBAL DOMINION — Миграция для синхронизации с Яндекс.Диспетчерской")
    print("=" * 80)
    print(f"Время запуска: {datetime.now().isoformat()}")
    print(f"Всего команд: {len(MIGRATION_COMMANDS)}")
    print()
    
    success_count = 0
    skip_count = 0
    error_count = 0
    errors = []
    
    for i, (name, sql) in enumerate(MIGRATION_COMMANDS, 1):
        # Каждая команда в своей сессии/транзакции
        async with AsyncSessionLocal() as db:
            print(f"[{i:02d}/{len(MIGRATION_COMMANDS)}] {name}...", end=" ")
            
            success, skipped, error = await run_single_command(db, name, sql)
            
            if success:
                if skipped:
                    print("⚠ Уже существует")
                    skip_count += 1
                else:
                    print("✓ OK")
                    success_count += 1
            else:
                print(f"✗ ОШИБКА")
                error_count += 1
                errors.append((name, error))
                print(f"         {error}")
    
    print()
    print("=" * 80)
    print("РЕЗУЛЬТАТ МИГРАЦИИ")
    print("=" * 80)
    print(f"Успешно выполнено: {success_count}")
    print(f"Пропущено (уже существует): {skip_count}")
    print(f"Ошибок: {error_count}")
    print(f"Время завершения: {datetime.now().isoformat()}")
    
    if errors:
        print()
        print("ДЕТАЛИ ОШИБОК:")
        for name, error in errors:
            print(f"  - {name}: {error[:100]}")
    
    return error_count == 0


async def verify_migration():
    """Проверяет, что все поля добавлены (асинхронно)"""
    print()
    print("=" * 80)
    print("ПРОВЕРКА МИГРАЦИИ")
    print("=" * 80)
    
    async with AsyncSessionLocal() as db:
        try:
            # Проверяем vehicles
            result = await db.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'vehicles' 
                AND column_name LIKE 'yandex_%'
                ORDER BY column_name
            """))
            vehicle_cols = result.fetchall()
            print(f"\nVEHICLES — найдено {len(vehicle_cols)} полей yandex_*:")
            for col in vehicle_cols:
                print(f"  - {col[0]}: {col[1]}")
            
            # Проверяем users
            result = await db.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                AND column_name LIKE 'yandex_%'
                ORDER BY column_name
            """))
            user_cols = result.fetchall()
            print(f"\nUSERS — найдено {len(user_cols)} полей yandex_*:")
            for col in user_cols:
                print(f"  - {col[0]}: {col[1]}")
            
            # Проверяем driver_profiles
            result = await db.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'driver_profiles' 
                AND column_name LIKE 'yandex_%'
                ORDER BY column_name
            """))
            driver_cols = result.fetchall()
            print(f"\nDRIVER_PROFILES — найдено {len(driver_cols)} полей yandex_*:")
            for col in driver_cols:
                print(f"  - {col[0]}: {col[1]}")
            
            # Проверяем yandex_sync_log
            result = await db.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'yandex_sync_log'
                )
            """))
            sync_log_exists = result.scalar()
            print(f"\nYANDEX_SYNC_LOG — таблица существует: {'Да' if sync_log_exists else 'Нет'}")
            
            # Итого
            total_fields = len(vehicle_cols) + len(user_cols) + len(driver_cols)
            print()
            print(f"ИТОГО: {total_fields} полей yandex_* в базе")
            
            return True
            
        except Exception as e:
            print(f"Ошибка проверки: {e}")
            return False


async def main():
    """Главная асинхронная функция"""
    print()
    
    # Запускаем миграцию
    migration_success = await run_migration()
    
    # Всегда проверяем результат
    await verify_migration()
    
    print()
    if migration_success:
        print("✓ Миграция завершена успешно!")
    else:
        print("⚠ Миграция завершена с ошибками. См. лог выше.")
    print()
    
    return migration_success


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
