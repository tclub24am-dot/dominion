# -*- coding: utf-8 -*-
# app/services/security.py
# CITADEL SECURITY - Защита Цитадели

import logging
from typing import Optional
from fastapi import Cookie, HTTPException, status, Request
from jose import JWTError, jwt
from sqlalchemy import select

from app.core.config import settings
from app.models.all_models import User
from app.database import AsyncSessionLocal

logger = logging.getLogger("CitadelSecurity")

async def get_current_user_from_cookie(
    request: Request,
    access_token: Optional[str] = Cookie(None)
) -> User:
    """
    ВРАТА ЦИТАДЕЛИ: Проверка токена из Cookie
    """
    if not access_token:
        logger.warning(f"Access denied: No token for {request.url.path}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Токен не найден. Требуется авторизация."
        )

    try:
        payload = jwt.decode(
            access_token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )

        username: str = payload.get("sub")

        if username is None:
            logger.warning("Token payload invalid: no 'sub' field")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Токен повреждён: отсутствует поле 'sub'."
            )

        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.username == username)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

        if user is None:
            logger.warning(f"User not found: {username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Пользователь не найден."
            )

        if not user.is_active:
            logger.warning(f"User inactive: {username}, role: {user.role}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Пользователь деактивирован. Аккаунт '{username}' заблокирован (is_active=False). Обратитесь к Мастеру или используйте команду восстановления."
            )

        logger.info(f"✓ Access granted: {user.username} ({user.role})")
        return user

    except JWTError as e:
        logger.warning(f"JWT decode error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Токен недействителен или истёк."
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Auth error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ошибка авторизации."
        )

async def get_current_user_optional(
    request: Request,
    access_token: Optional[str] = Cookie(None)
) -> Optional[User]:
    """
    Получить текущего пользователя (опционально, без редиректа)
    """
    if not access_token:
        return None

    try:
        payload = jwt.decode(
            access_token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        username = payload.get("sub")

        if username:
            async with AsyncSessionLocal() as session:
                stmt = select(User).where(User.username == username)
                result = await session.execute(stmt)
                return result.scalar_one_or_none()

    except Exception as e:
        logger.debug(f"Optional auth failed: {e}")
        return None

    return None

async def get_current_user_from_ws(access_token: Optional[str]) -> Optional[User]:
    """
    Получить пользователя из токена WebSocket (cookie access_token).
    """
    if not access_token:
        return None
    try:
        payload = jwt.decode(
            access_token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        username = payload.get("sub")
        if not username:
            return None
        async with AsyncSessionLocal() as session:
            stmt = select(User).where(User.username == username)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
    except Exception:
        return None
