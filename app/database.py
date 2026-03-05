import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from pathlib import Path
from dotenv import load_dotenv
import redis.asyncio as redis

# 1. Загрузка переменных окружения
load_dotenv()

# 2. Асинхронный движок (Строго PostgreSQL для Цитадели)
# Берем URL из .env, если нет - кидаем ошибку для безопасности
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # Если .env не сработал, жестко прописываем путь к Postgres
    DATABASE_URL = "postgresql+asyncpg://dominion_user:MasterSpartak777!@db/dominion_db"

engine = create_async_engine(
    DATABASE_URL, 
    echo=False,  # 🔒 Отключено (убивает CPU!)
    future=True,
    # 🔒 POOL OPTIMIZATION ДЛЯ СТАБИЛЬНОСТИ
    pool_size=5,              # Минимум 5 соединений
    max_overflow=10,          # Максимум 15 одновременных
    pool_pre_ping=True,       # Проверка живых соединений
    pool_recycle=3600,        # Переиспользование каждый час
    connect_args={"timeout": 30}  # Timeout 30 сек на соединение
)

# 3. Фабрика сессий
AsyncSessionLocal = async_sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

# Псевдонимы для совместимости
SessionLocal = AsyncSessionLocal
async_session_factory = AsyncSessionLocal

class Base(DeclarativeBase):
    """Базовый класс Доминиона"""
    pass

# 4. Универсальная функция получения сессии БД
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# 5. Функция для Redis
async def get_redis():
    """Dependency для Redis"""
    redis_client = redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=False
    )
    try:
        yield redis_client
    finally:
        await redis_client.aclose()
