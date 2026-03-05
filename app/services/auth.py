# -*- coding: utf-8 -*-
# app/services/auth.py

import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.all_models import User

# --- 1. КОНФИГУРАЦИЯ ---
from app.core.config import settings
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 часа

# --- 2. КРИПТОГРАФИЯ ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверяет пароль. Без лишних условий, только честный bcrypt."""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False

# --- 3. ТОКЕНЫ ---
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# --- 4. ГЛАВНЫЙ ЗАЩИТНИК ---
async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Универсальный поиск токена:
    1. Сначала ищем в Header (Authorization: Bearer ...)
    2. Если нет, ищем в Cookies (access_token)
    """
    token = None

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]

    if not token:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ключ доступа не найден. Войдите в Цитадель."
        )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Искаженный токен")
    except JWTError:
        raise HTTPException(status_code=401, detail="Срок действия ключа истек")

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    
    if not user.is_active:
        raise HTTPException(
            status_code=403, 
            detail=f"Аккаунт '{username}' деактивирован (is_active=False). Синхронизация могла его заблокировать. Используйте команду восстановления."
        )

    return user
