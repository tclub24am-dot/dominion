#!/usr/bin/env python3
"""
Миграция v35.1: Добавление полей документов водителя (ВУ) в таблицу users.
Запуск: python scripts/migrate_driver_documents.py

ФАЗА 1: ADD COLUMN (с коммитом)
ФАЗА 2: CREATE INDEX (каждый в отдельном try/except)
"""
import asyncio
import sys
sys.path.insert(0, ".")

from sqlalchemy import text
from app.database import engine

# ═══ ФАЗА 1: Добавление колонок ═══
COLUMNS_SQL = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS license_number VARCHAR(30)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS license_issue_date DATE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS license_expiry_date DATE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS license_country VARCHAR(10)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS driving_experience_from DATE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS birth_date DATE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS hire_date DATE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS first_order_date DATE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS balance_limit FLOAT DEFAULT 5.0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS driver_documents JSONB DEFAULT '{}'",
]

# ═══ ФАЗА 2: Создание индексов (после коммита колонок) ═══
INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_users_license_expiry ON users(license_expiry_date) WHERE license_expiry_date IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_users_license_number ON users(license_number) WHERE license_number IS NOT NULL",
]


async def migrate():
    # ── ФАЗА 1: Колонки ──
    print("═══ ФАЗА 1: Добавление колонок ═══")
    async with engine.begin() as conn:
        for stmt in COLUMNS_SQL:
            try:
                await conn.execute(text(stmt))
                print(f"  ✓ {stmt[:80]}")
            except Exception as e:
                print(f"  ✗ {stmt[:80]} → {e}")
    # conn.commit() выполняется автоматически при выходе из engine.begin()
    print("  ✅ Колонки закоммичены\n")

    # ── ФАЗА 2: Индексы (каждый отдельно) ──
    print("═══ ФАЗА 2: Создание индексов ═══")
    for stmt in INDEXES_SQL:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(stmt))
            print(f"  ✓ {stmt[:80]}")
        except Exception as e:
            print(f"  ⚠ Индекс пропущен: {stmt[:60]}... → {e}")

    print("\n✅ Миграция v35.1 завершена: поля документов водителя добавлены")


if __name__ == "__main__":
    asyncio.run(migrate())
