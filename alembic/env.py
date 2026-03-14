# -*- coding: utf-8 -*-
# alembic/env.py
# S-GLOBAL DOMINION — Alembic Environment (Sync для autogenerate)

import os
import sys
from pathlib import Path
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Добавляем корень проекта в sys.path для импорта app.*
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Загружаем .env
from dotenv import load_dotenv
load_dotenv()

# Импортируем Base и все модели для autogenerate
from app.database import Base
import app.models.all_models  # noqa: F401 — регистрирует все модели в Base.metadata

# Конфигурация Alembic
config = context.config

# Настройка логирования из alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Метаданные для autogenerate
target_metadata = Base.metadata


def get_sync_url():
    """Возвращает синхронный URL для Alembic (psycopg2)."""
    url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://dominion_user:MasterSpartak777!@db/dominion_db"
    )
    # asyncpg → psycopg2 для синхронного Alembic
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")


def run_migrations_offline() -> None:
    """Запуск миграций в offline-режиме (без подключения к БД)."""
    url = get_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Запуск миграций в online-режиме (синхронный psycopg2)."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_sync_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
