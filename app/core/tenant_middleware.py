# -*- coding: utf-8 -*-
# app/core/tenant_middleware.py
# VERSHINA v200.14: Multi-Tenant Hard Isolation Middleware — JWT Expiry Fix
#
# Стратегия извлечения tenant_id (приоритет по убыванию):
#   1. JWT / Cookie -> извлекаем identity пользователя -> tenant_id только из БД.
#   2. Заголовок X-Tenant-ID — только для сервисных webhook/M2M вызовов.
#   3. DEFAULT_TENANT ("s-global") — fallback для публичных/legacy маршрутов.

import logging
import re
from typing import Optional

from jose import jwt, JWTError
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.database import AsyncSessionLocal
from app.models.all_models import User

# Флаг DEBUG: X-Tenant-ID виден в ответах только при DEBUG=True
# Конкуренты не должны видеть внутреннюю структуру тенантов в production
_DEBUG_MODE: bool = getattr(settings, "DEBUG", False)

logger = logging.getLogger("Dominion.Tenant")

DEFAULT_TENANT = "s-global"

# Предкомпилированный regex для валидации tenant_id
_TENANT_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')


def _extract_token(request: Request) -> Optional[str]:
    """
    Проверяет заголовок Authorization: Bearer <token>
    и cookie "access_token".

    Возвращает raw JWT/cookie token или None.
    """
    token: Optional[str] = None

    # 1. Authorization: Bearer <token>
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()

    # 2. Cookie (fallback для браузерных клиентов)
    if not token:
        token = request.cookies.get("access_token")

    if not token:
        return None

    return token


async def _extract_tenant_from_authenticated_user(request: Request) -> Optional[str]:
    """
    DB-driven tenant resolution: tenant_id извлекается только из пользователя в БД.
    JWT используется лишь как контейнер для user identity (sub / user_id), но не как
    источник tenant_id.
    """
    token = _extract_token(request)
    if not token:
        return None

    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        options={"verify_exp": True},
    )

    username = payload.get("sub")
    user_id = payload.get("user_id")
    if username is None and user_id is None:
        raise JWTError("JWT token does not contain user identity")

    async with AsyncSessionLocal() as session:
        stmt = select(User)
        if user_id is not None:
            stmt = stmt.where(User.id == user_id)
        else:
            stmt = stmt.where(User.username == username)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise JWTError("Authenticated user not found or inactive")

    tenant_id = (user.tenant_id or DEFAULT_TENANT).strip()
    if not _is_valid_tenant_id(tenant_id):
        raise JWTError("User has invalid tenant_id in database")

    request.state.authenticated_user_id = user.id
    request.state.authenticated_username = user.username
    return tenant_id


def _is_service_request(request: Request) -> bool:
    """
    Определяет, является ли запрос сервисным (M2M / webhook).
    FIX v200.16.4: Убрана проверка Authorization Bearer — она конфликтует с JWT
    обычных пользователей. Сервисные запросы идентифицируются только по
    X-Webhook-Token или X-Webhook-Signature.
    """
    return bool(
        request.url.path.startswith("/api/v1/telephony/webhook/")
        and (
            request.headers.get("X-Webhook-Token")
            or request.headers.get("X-Webhook-Signature")
        )
    )


def _is_valid_tenant_id(tenant_id: str) -> bool:
    """Валидация tenant_id: только безопасные символы, длина 1-64."""
    return bool(_TENANT_ID_PATTERN.match(tenant_id))


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Middleware для мультитенантной изоляции данных.

    Устанавливает request.state.tenant_id для каждого запроса.
    Для аутентифицированных пользователей tenant_id берётся только из БД.
    X-Tenant-ID допускается только для сервисных webhook/M2M вызовов.

    VERSHINA v200.16.3: Публичные маршруты (Swagger, health, auth, webhooks)
    не блокируются при отсутствии/невалидности JWT — получают DEFAULT_TENANT.
    """

    # Публичные маршруты, для которых JWT не обязателен
    PUBLIC_PREFIXES = (
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/api/v1/auth/login",
        "/api/v1/auth/token",
        "/api/v1/telephony/webhook/",
    )

    def _is_public_path(self, path: str) -> bool:
        """Проверяет, является ли маршрут публичным (JWT не требуется)."""
        return any(path.startswith(prefix) for prefix in self.PUBLIC_PREFIXES)

    async def dispatch(self, request: Request, call_next) -> Response:
        tenant_id: Optional[str] = None
        path = request.url.path

        # Приоритет 1: аутентифицированный пользователь -> tenant_id только из БД
        try:
            tenant_id = await _extract_tenant_from_authenticated_user(request)
        except JWTError:
            # VERSHINA v200.16.3: На публичных маршрутах невалидный JWT не блокирует запрос —
            # устанавливаем DEFAULT_TENANT и пропускаем дальше.
            if self._is_public_path(path) or _is_service_request(request):
                logger.debug(
                    "Public/service path with invalid JWT — using DEFAULT_TENANT",
                    extra={"path": path, "method": request.method},
                )
                tenant_id = DEFAULT_TENANT
            else:
                logger.warning(
                    "Rejected request with invalid or expired JWT while resolving tenant",
                    extra={"path": path, "method": request.method},
                )
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Unauthorized"},
                )

        # Приоритет 2: сервисный X-Tenant-ID только для M2M / webhook вызовов
        if not tenant_id:
            header_tenant = request.headers.get("X-Tenant-ID", "").strip()
            if header_tenant and _is_service_request(request) and _is_valid_tenant_id(header_tenant):
                tenant_id = header_tenant
            elif header_tenant:
                logger.warning(
                    "Rejected X-Tenant-ID header outside verified service flow",
                    extra={"path": str(request.url.path), "method": request.method},
                )
                return JSONResponse(status_code=403, content={"detail": "Forbidden tenant override"})

        # Приоритет 3: Default fallback
        if not tenant_id:
            tenant_id = DEFAULT_TENANT

        request.state.tenant_id = tenant_id

        response = await call_next(request)
        # SECURITY: X-Tenant-ID виден только в DEBUG-режиме.
        # В production конкуренты не должны видеть внутреннюю структуру тенантов.
        if _DEBUG_MODE:
            response.headers["X-Tenant-ID"] = tenant_id
        return response


def get_current_tenant(request: Request) -> str:
    """
    FastAPI Dependency: возвращает tenant_id текущего запроса.
    Использовать в Depends() для эндпоинтов.
    """
    return getattr(request.state, "tenant_id", DEFAULT_TENANT)


def require_tenant(tenant_id: str = DEFAULT_TENANT) -> str:
    """Утилита для принудительного указания tenant в запросах."""
    return tenant_id
