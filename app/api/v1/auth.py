# -*- coding: utf-8 -*-
# app/api/v1/auth.py

import asyncio
import logging
import os
import secrets
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.models.all_models import User
from app.services.auth import verify_password, create_access_token, hash_password
from app.services.security import get_current_user_from_cookie

# Настройка логгера Врат
logger = logging.getLogger("AuthModule")

router = APIRouter(tags=["Security: Врата"])

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/login")
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """
    ВРАТА ЦИТАДЕЛИ: Процедура идентификации Мастера или Воина.
    """
    try:
        # 1. ПОИСК ПОЛЬЗОВАТЕЛЯ В РЕЕСТРЕ
        stmt = select(User).where(User.username == payload.username)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        # 2. АВТО-БУТСТРАП МАСТЕРА (если не найден)
        if not user:
            master_username = os.getenv("MASTER_BOOTSTRAP_USERNAME", "master")
            master_password = os.getenv("MASTER_BOOTSTRAP_PASSWORD")
            master_full_name = os.getenv("MASTER_BOOTSTRAP_NAME", "Master Spartak")
            if not master_password:
                logger.critical("SECURITY: MASTER_BOOTSTRAP_PASSWORD не задан в .env! Авто-бутстрап отключён.")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Доступ отклонен: Ключ не подходит"
                )
            if payload.username == master_username and secrets.compare_digest(
                payload.password.encode("utf-8"),
                master_password.encode("utf-8")
            ):
                user = User(
                    username=master_username,
                    hashed_password=hash_password(master_password),
                    full_name=master_full_name,
                    role="master",
                    is_active=True,
                    can_see_treasury=True,
                    can_see_fleet=True,
                    can_see_analytics=True,
                    can_see_logistics=True,
                    can_see_hr=True,
                    can_edit_users=True,
                )
                db.add(user)
                await db.commit()
                await db.refresh(user)

        # 3. ПРОВЕРКА КЛЮЧА (Пароля)
        if not user or not verify_password(payload.password, user.hashed_password):
            await asyncio.sleep(0.3)  # Нивелирует timing side-channel
            logger.warning(f"SECURITY ALERT: Неудачная попытка входа для пользователя: {payload.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Доступ отклонен: Ключ не подходит"
            )
        
        # 4. ГЕНЕРАЦИЯ JWT (Магический Знак)
        token = create_access_token(data={"sub": user.username})
        
        # 5. УСТАНОВКА COOKIE (Память Цитадели)
        is_production = os.getenv("ENVIRONMENT") == "production"
        response.set_cookie(
            key="access_token",
            value=token,
            httponly=True,   # Защита от XSS
            max_age=86400,   # 24 часа мощи
            samesite="lax",
            path="/",
            secure=is_production  # True только в продакшне (HTTPS), False для localhost
        )
        
        # 6. РЕГИСТРАЦИЯ ВХОДА (Для истории Оракула)
        logger.info(f"ACCESS GRANTED: {user.full_name} ({user.role}) вошел в систему.")

        # 7. ВОЗВРАТ ПРАВ И ДАННЫХ (токен передаётся только через httpOnly cookie)
        return {
            "status": "success",
            "token_type": "cookie",
            "user": {
                "id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "role": str(user.role) if user.role else "manager",
                "permissions": {
                    "treasury": user.can_see_treasury,
                    "fleet": user.can_see_fleet,
                    "analytics": user.can_see_analytics,
                    "logistics": user.can_see_logistics
                }
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"SYSTEM AUTH ERROR: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Сбой магических контуров Врат"
        )

@router.get("/me")
async def get_me(user: User = Depends(get_current_user_from_cookie)):
    """
    Проверка текущего статуса сессии.
    Валидирует httpOnly cookie → возвращает данные пользователя.
    Используется React SPA для восстановления сессии при перезагрузке.
    """
    return {
        "status": "active",
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role": str(user.role) if user.role else "manager",
        },
        "timestamp": datetime.now().isoformat(),
    }
