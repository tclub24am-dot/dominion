# -*- coding: utf-8 -*-
# app/create_db.py
# VERSHINA v200.16.3: Горячая миграция + создание таблиц
#
# Выполняет безопасную миграцию существующих таблиц (IF EXISTS / IF NOT EXISTS),
# затем создаёт недостающие таблицы через SQLAlchemy metadata.create_all.

import asyncio
import logging

from sqlalchemy import text

from app.database import Base, engine
import app.models.all_models  # noqa: F401 — регистрация всех моделей

logger = logging.getLogger("Dominion.Migration")


async def migrate_call_logs(conn):
    """
    Горячая миграция таблицы call_logs: v200.15 → v200.16.3
    
    Операции (все идемпотентные — безопасно запускать повторно):
    1. Переименование phone_number → caller_phone
    2. Добавление новых колонок (callee_phone, call_status, duration, recording_url, asterisk_unique_id)
    3. Добавление tenant_id для SaaS-изоляции
    4. Удаление дублирующего индекса ix_call_logs_asterisk_uid (unique остаётся на колонке)
    """
    migrations = [
        # 1. Переименование phone_number → caller_phone (если старая колонка существует)
        """
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
        """,

        # 2. Новые колонки
        "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS callee_phone VARCHAR(20);",
        "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS call_status VARCHAR(20) DEFAULT 'unknown';",
        "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS duration INTEGER DEFAULT 0;",
        "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS recording_url TEXT;",
        "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS asterisk_unique_id VARCHAR(64);",

        # 3. Tenant ID для SaaS-изоляции (NOT NULL — соответствует ORM nullable=False)
        "ALTER TABLE call_logs ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(100) NOT NULL DEFAULT 's-global';",

        # 4. Удаление дублирующего индекса (unique constraint остаётся на колонке через ORM)
        "DROP INDEX IF EXISTS ix_call_logs_asterisk_uid;",

        # 5. Составные индексы (IF NOT EXISTS через DO-блок)
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'ix_call_logs_tenant_caller') THEN
                CREATE INDEX ix_call_logs_tenant_caller ON call_logs (tenant_id, caller_phone);
            END IF;
        END $$;
        """,
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'ix_call_logs_timestamp') THEN
                CREATE INDEX ix_call_logs_timestamp ON call_logs (timestamp);
            END IF;
        END $$;
        """,
    ]

    for sql in migrations:
        try:
            await conn.execute(text(sql))
        except Exception as e:
            # Логируем, но не прерываем — миграция идемпотентная
            logger.warning(f"Migration step warning: {e}")


async def create_all_tables():
    """
    Основная точка входа: миграция + создание таблиц.
    Безопасно для повторного запуска (идемпотентность).
    """
    async with engine.begin() as conn:
        # Шаг 1: Горячая миграция существующих таблиц
        # Проверяем, существует ли таблица call_logs (миграция только для существующих БД)
        result = await conn.execute(text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.tables "
            "  WHERE table_name = 'call_logs'"
            ")"
        ))
        call_logs_exists = result.scalar()

        if call_logs_exists:
            logger.info("🔄 Запуск горячей миграции call_logs v200.16.3...")
            await migrate_call_logs(conn)
            logger.info("✅ Миграция call_logs завершена")
        else:
            logger.info("📋 Таблица call_logs не найдена — будет создана через create_all")

        # Шаг 2: Создание недостающих таблиц (SQLAlchemy create_all — идемпотентно)
        await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Все таблицы синхронизированы с ORM")


if __name__ == "__main__":
    asyncio.run(create_all_tables())
