# -*- coding: utf-8 -*-
# app/api/v1/auth.py

import logging
import os
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.models.all_models import User
from app.services.auth import verify_password, create_access_token, hash_password

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
            master_password = os.getenv("MASTER_BOOTSTRAP_PASSWORD", "MasterSpartak777!")
            master_full_name = os.getenv("MASTER_BOOTSTRAP_NAME", "Master Spartak")
            if payload.username == master_username and payload.password == master_password:
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
            logger.warning(f"SECURITY ALERT: Неудачная попытка входа для пользователя: {payload.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Доступ отклонен: Ключ не подходит"
            )
        
        # 4. ГЕНЕРАЦИЯ JWT (Магический Знак)
        token = create_access_token(data={"sub": user.username})
        
        # 4. УСТАНОВКА COOKIE (Память Цитадели)
        response.set_cookie(
            key="access_token",
            value=token,
            httponly=True,  # Защита от XSS
            max_age=86400,  # 24 часа мощи
            samesite="lax",
            path="/",
            secure=False  # True только для HTTPS
        )
        
        # 5. РЕГИСТРАЦИЯ ВХОДА (Для истории Оракула)
        logger.info(f"ACCESS GRANTED: {user.full_name} ({user.role}) вошел в систему.")

        # 6. ВОЗВРАТ ПРАВ И ДАННЫХ
        return {
            "status": "success",
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "full_name": user.full_name,
                "role": user.role,
                "permissions": {
                    "treasury": user.can_see_treasury,
                    "fleet": user.can_see_fleet,
                    "analytics": user.can_see_analytics,
                    "logistics": user.can_see_logistics
                }
            }
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"SYSTEM AUTH ERROR: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Сбой магических контуров Врат"
        )

@router.get("/me")
async def get_me(user: User = Depends(User)): # Здесь в будущем будет зависимость get_current_user
    """Проверка текущего статуса сессии"""
    return {"status": "active", "timestamp": datetime.now()}
