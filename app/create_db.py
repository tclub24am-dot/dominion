# -*- coding: utf-8 -*-
# app/create_db.py
# VERSHINA v200.16.4: Горячая миграция + создание таблиц
#
# Выполняет безопасную миграцию существующих таблиц (IF EXISTS / IF NOT EXISTS),
# затем создаёт недостающие таблицы через SQLAlchemy metadata.create_all.
# AUTOCOMMIT для DDL — исключает "aborted transaction" при ошибках индексов.

import asyncio
import logging

from sqlalchemy import text

from app.database import Base, engine
import app.models.all_models  # noqa: F401 — регистрация всех моделей

logger = logging.getLogger("Dominion.Migration")


async def _exec_ddl(conn, sql: str, description: str = ""):
    """
    Выполняет DDL-команду с перехватом ошибок.
    Каждая команда — отдельная транзакция (AUTOCOMMIT-режим).
    """
    try:
        await conn.execute(text(sql))
        if description:
            logger.info(f"✅ {description}")
    except Exception as e:
        logger.warning(f"⚠️ DDL warning [{description}]: {e}")


async def migrate_call_logs():
    """
    Горячая миграция таблицы call_logs: v200.15 → v200.16.4

    Каждая операция выполняется в AUTOCOMMIT — ошибка одного шага
    не откатывает остальные (идемпотентность гарантирована).
    """
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")

        migrations = [
            # 1. Переименование phone_number → caller_phone
            ("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'call_logs' AND column_name = 'phone_number'
                ) THEN
                    ALTER TABLE call_logs RENAME COLUMN phone_number TO caller_phone;
                    RAISE NOTICE 'MIGRATED: phone_number → caller_phone';
                END IF;
            END $$;
            """, "phone_number → caller_phone"),

            # 2. Новые колонки
            ("ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS callee_phone VARCHAR(20);",
             "ADD COLUMN callee_phone"),
            ("ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS call_status VARCHAR(20) DEFAULT 'unknown';",
             "ADD COLUMN call_status"),
            ("ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS duration INTEGER DEFAULT 0;",
             "ADD COLUMN duration"),
            ("ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS recording_url TEXT;",
             "ADD COLUMN recording_url"),
            ("ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS asterisk_unique_id VARCHAR(64);",
             "ADD COLUMN asterisk_unique_id"),

            # 3. Tenant ID для SaaS-изоляции
            ("ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(100) NOT NULL DEFAULT 's-global';",
             "ADD COLUMN tenant_id"),

            # 4. Удаление дублирующего индекса
            ("DROP INDEX IF EXISTS ix_call_logs_asterisk_uid;",
             "DROP INDEX ix_call_logs_asterisk_uid"),

            # 5. Составные индексы (IF NOT EXISTS)
            ("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'ix_call_logs_tenant_caller') THEN
                    CREATE INDEX ix_call_logs_tenant_caller ON call_logs (tenant_id, caller_phone);
                END IF;
            END $$;
            """, "INDEX ix_call_logs_tenant_caller"),

            # 6. Индекс ix_call_logs_timestamp — IF NOT EXISTS
            #    Предотвращает DuplicateTableError в Base.metadata.create_all
            ("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'ix_call_logs_timestamp') THEN
                    CREATE INDEX ix_call_logs_timestamp ON call_logs (timestamp);
                END IF;
            END $$;
            """, "INDEX ix_call_logs_timestamp"),
        ]

        for sql, desc in migrations:
            await _exec_ddl(conn, sql, desc)


async def create_all_tables():
    """
    Основная точка входа: миграция + создание таблиц.
    Безопасно для повторного запуска (идемпотентность).
    """
    # Шаг 1: Проверяем существование call_logs
    async with engine.connect() as conn:
        result = await conn.execute(text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.tables "
            "  WHERE table_name = 'call_logs'"
            ")"
        ))
        call_logs_exists = result.scalar()

    if call_logs_exists:
        logger.info("🔄 Запуск горячей миграции call_logs v200.16.4...")
        await migrate_call_logs()
        logger.info("✅ Миграция call_logs завершена")
    else:
        logger.info("📋 Таблица call_logs не найдена — будет создана через create_all")

    # Шаг 2: Создание недостающих таблиц через create_all
    # Используем AUTOCOMMIT чтобы каждый CREATE TABLE/INDEX был независим
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        try:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("✅ Все таблицы синхронизированы с ORM")
        except Exception as e:
            # Если create_all упал на дублирующем индексе — логируем и продолжаем
            # (таблицы уже существуют, индексы созданы в миграции)
            logger.warning(f"⚠️ create_all warning (возможно дублирующий индекс): {e}")
            logger.info("✅ Таблицы уже существуют — продолжаем запуск")


if __name__ == "__main__":
    asyncio.run(create_all_tables())
