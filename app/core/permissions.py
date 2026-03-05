# -*- coding: utf-8 -*-
# app/core/permissions.py

from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from app.services.security import get_current_user_from_cookie, get_current_user_optional
from app.core.modules import get_enabled_modules, module_access
from app.core.config import settings
from app.models.all_models import User


def has_module_access(user: User, module_id: str) -> bool:
    if not user:
        return False
    enabled_modules = set(get_enabled_modules())
    if module_id not in enabled_modules:
        return False
    if (user.role or "").lower() == "master":
        return True

    base_modules = {m.strip() for m in settings.TRIAL_BASE_MODULES.split(",") if m.strip()}
    if not is_trial_active(user) and module_id not in base_modules:
        return False

    return module_access(user.role, module_id)


def is_trial_active(user: User) -> bool:
    if not user or not user.created_at:
        return False
    start = user.created_at
    if isinstance(start, datetime):
        trial_end = start + timedelta(days=settings.TRIAL_DAYS)
        return datetime.now() <= trial_end
    return False


def require_module(module_id: str):
    async def _dependency(
        request: Request,
        current_user: Optional[User] = Depends(get_current_user_optional),
    ):
        # При YANDEX_ALLOW_SYNC_NOAUTH — пропускаем без авторизации
        if current_user is None:
            if getattr(settings, "YANDEX_ALLOW_SYNC_NOAUTH", False):
                return None
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Требуется авторизация."
            )
        if not has_module_access(current_user, module_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Модуль отключен, нет доступа по роли или истек пробный период. Продлите Золотую Лицензию."
            )
        return current_user
    return _dependency
