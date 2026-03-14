# -*- coding: utf-8 -*-
# app/core/permissions.py
# ═══════════════════════════════════════════════════════════════════════════════
# S-GLOBAL DOMINION — RBAC (Role-Based Access Control)
# Протокол VERSHINA v200.11 | Штатное расписание ООО «С-ГЛОБАЛ»
# ═══════════════════════════════════════════════════════════════════════════════

from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Set
from fastapi import Depends, HTTPException, Request, status
from app.services.security import get_current_user_from_cookie, get_current_user_optional
from app.core.modules import get_enabled_modules, module_access
from app.core.config import settings
from app.models.all_models import User


# ───────────────────────────────────────────────────────────────────────────────
# КОНСТАНТЫ РАЗРЕШЕНИЙ (Permissions)
# Гранулярные права доступа к модулям Империи S-GLOBAL
# ───────────────────────────────────────────────────────────────────────────────

# Флот
PERM_FLEET_READ   = "fleet:read"    # Просмотр флота, автомобилей, водителей
PERM_FLEET_WRITE  = "fleet:write"   # Управление флотом, назначение, редактирование

# Финансы (Казна)
PERM_FINANCE_READ  = "finance:read"   # Просмотр финансовых отчётов и транзакций
PERM_FINANCE_WRITE = "finance:write"  # Создание транзакций, управление казной

# Безопасность
PERM_SECURITY_READ = "security:read"  # Доступ к протоколам безопасности и аудиту

# GPS / Телематика
PERM_GPS_READ = "gps:read"  # Просмотр GPS-треков и телематики

# HR / Кадры
PERM_HR_READ  = "hr:read"   # Просмотр кадровых данных, скоринга водителей
PERM_HR_WRITE = "hr:write"  # Управление кадрами, расчёт ЗП, чёрный список

# Партнёры
PERM_PARTNER_READ = "partner:read"  # Доступ к партнёрским отчётам и данным

# Суперадмин
PERM_ADMIN_ALL = "admin:all"  # Мастер-доступ ко всем ресурсам (только Owner)

# T-CLUB24
PERM_TCLUB_OPS = "tclub:ops"  # Операционный доступ к T-CLUB24


# ───────────────────────────────────────────────────────────────────────────────
# РОЛИ СОТРУДНИКОВ ООО «С-ГЛОБАЛ»
# Штатное расписание — Протокол VERSHINA v200.11
# ───────────────────────────────────────────────────────────────────────────────

class DominionRole(str, Enum):
    """
    Роли сотрудников Империи S-GLOBAL DOMINION.
    Наследует str для совместимости с JWT-токенами и БД.
    """
    # Спартак — Мастер-Владелец, верховная власть
    OWNER = "owner"

    # Афунц Алик Арменович — Заместитель руководителя
    DEPUTY = "deputy"

    # Волков Михаил Юрьевич — Финансовая безопасность
    FINANCE_SECURITY = "finance_security"

    # Геворгян Левон Гагикович — Начальник флота
    FLEET_CHIEF = "fleet_chief"

    # Белякова Екатерина Александровна — Администратор T-CLUB24
    ADMIN_T_CLUB = "admin_t_club"

    # Системная роль — мастер (обратная совместимость с существующим кодом)
    MASTER = "master"


# ───────────────────────────────────────────────────────────────────────────────
# МАППИНГ РОЛЕЙ → РАЗРЕШЕНИЙ
# Каждая роль получает строго определённый набор прав
# ───────────────────────────────────────────────────────────────────────────────

ROLE_PERMISSIONS: dict[str, Set[str]] = {

    # ══════════════════════════════════════════════════════════════════
    # OWNER — Спартак (Мастер-Владелец)
    # Мастер-доступ ко всем ресурсам ООО С-ГЛОБАЛ и партнёрским отчётам
    # ══════════════════════════════════════════════════════════════════
    DominionRole.OWNER: {
        PERM_ADMIN_ALL,
        PERM_FLEET_READ, PERM_FLEET_WRITE,
        PERM_FINANCE_READ, PERM_FINANCE_WRITE,
        PERM_SECURITY_READ,
        PERM_GPS_READ,
        PERM_HR_READ, PERM_HR_WRITE,
        PERM_PARTNER_READ,
        PERM_TCLUB_OPS,
    },

    # ══════════════════════════════════════════════════════════════════
    # MASTER — системная роль (обратная совместимость)
    # Эквивалент Owner для legacy-кода
    # ══════════════════════════════════════════════════════════════════
    DominionRole.MASTER: {
        PERM_ADMIN_ALL,
        PERM_FLEET_READ, PERM_FLEET_WRITE,
        PERM_FINANCE_READ, PERM_FINANCE_WRITE,
        PERM_SECURITY_READ,
        PERM_GPS_READ,
        PERM_HR_READ, PERM_HR_WRITE,
        PERM_PARTNER_READ,
        PERM_TCLUB_OPS,
    },

    # ══════════════════════════════════════════════════════════════════
    # DEPUTY — Афунц Алик Арменович (Заместитель руководителя)
    # Полные права управления, кроме суперадмин-операций
    # ══════════════════════════════════════════════════════════════════
    DominionRole.DEPUTY: {
        PERM_FLEET_READ, PERM_FLEET_WRITE,
        PERM_FINANCE_READ, PERM_FINANCE_WRITE,
        PERM_SECURITY_READ,
        PERM_GPS_READ,
        PERM_HR_READ, PERM_HR_WRITE,
        PERM_PARTNER_READ,
        PERM_TCLUB_OPS,
    },

    # ══════════════════════════════════════════════════════════════════
    # FINANCE_SECURITY — Волков Михаил Юрьевич
    # Доступ к финансовому аудиту и протоколам безопасности
    # ══════════════════════════════════════════════════════════════════
    DominionRole.FINANCE_SECURITY: {
        PERM_FINANCE_READ, PERM_FINANCE_WRITE,
        PERM_SECURITY_READ,
        PERM_HR_READ,
        PERM_PARTNER_READ,
    },

    # ══════════════════════════════════════════════════════════════════
    # FLEET_CHIEF — Геворгян Левон Гагикович (Начальник флота)
    # Доступ к флоту, сервису, GPS и расчёту ЗП
    # ══════════════════════════════════════════════════════════════════
    DominionRole.FLEET_CHIEF: {
        PERM_FLEET_READ, PERM_FLEET_WRITE,
        PERM_GPS_READ,
        PERM_HR_READ, PERM_HR_WRITE,
        PERM_FINANCE_READ,
    },

    # ══════════════════════════════════════════════════════════════════
    # ADMIN_T_CLUB — Белякова Екатерина Александровна
    # Операционный доступ к T-CLUB24
    # ══════════════════════════════════════════════════════════════════
    DominionRole.ADMIN_T_CLUB: {
        PERM_TCLUB_OPS,
        PERM_FLEET_READ,
        PERM_HR_READ,
    },
}


# ───────────────────────────────────────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ RBAC
# ───────────────────────────────────────────────────────────────────────────────

def has_permission(role: str, permission: str) -> bool:
    """
    Проверяет, имеет ли роль указанное разрешение.

    Args:
        role: Строковое значение роли (из DominionRole или legacy-строка)
        permission: Константа разрешения (например, PERM_FLEET_READ)

    Returns:
        True если роль имеет разрешение, False иначе
    """
    if not role:
        return False

    # Нормализуем роль к нижнему регистру для совместимости
    role_lower = role.lower()

    # Ищем в маппинге (поддержка как enum-значений, так и строк)
    for role_key, perms in ROLE_PERMISSIONS.items():
        if role_key.value == role_lower or role_key == role_lower:
            # Owner и Master имеют PERM_ADMIN_ALL — доступ ко всему
            if PERM_ADMIN_ALL in perms:
                return True
            return permission in perms

    return False


def get_role_permissions(role: str) -> Set[str]:
    """
    Возвращает полный набор разрешений для указанной роли.

    Args:
        role: Строковое значение роли

    Returns:
        Множество строк-разрешений
    """
    if not role:
        return set()

    role_lower = role.lower()
    for role_key, perms in ROLE_PERMISSIONS.items():
        if role_key.value == role_lower or role_key == role_lower:
            return perms

    return set()


# ───────────────────────────────────────────────────────────────────────────────
# FASTAPI DEPENDENCY: require_role
# Проверяет роль пользователя из JWT/cookie
# ───────────────────────────────────────────────────────────────────────────────

def require_role(*roles: str):
    """
    FastAPI Dependency — проверяет, что текущий пользователь имеет одну из
    указанных ролей. Используется как зависимость в роутерах.

    Пример использования:
        @router.get("/finance", dependencies=[Depends(require_role(DominionRole.OWNER, DominionRole.FINANCE_SECURITY))])
        async def get_finance(): ...

    Args:
        *roles: Одна или несколько допустимых ролей (DominionRole или строки)

    Returns:
        Dependency-функция для FastAPI
    """
    # Нормализуем переданные роли к нижнему регистру
    allowed_roles = {
        (r.value if isinstance(r, DominionRole) else str(r)).lower()
        for r in roles
    }

    async def _dependency(
        request: Request,
        current_user: Optional[User] = Depends(get_current_user_optional),
    ) -> Optional[User]:
        # При YANDEX_ALLOW_SYNC_NOAUTH — пропускаем без авторизации (только для тестов)
        if current_user is None:
            if getattr(settings, "YANDEX_ALLOW_SYNC_NOAUTH", False):
                return None
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Требуется авторизация. Войдите в систему S-GLOBAL DOMINION."
            )

        user_role = (current_user.role or "").lower()

        # Owner и Master имеют доступ везде
        if user_role in (DominionRole.OWNER.value, DominionRole.MASTER.value):
            return current_user

        # Проверяем вхождение роли в список допустимых
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Доступ запрещён. Требуется одна из ролей: "
                    f"{', '.join(sorted(allowed_roles))}. "
                    f"Ваша роль: {user_role or 'не определена'}."
                )
            )

        return current_user

    return _dependency


def require_permission(permission: str):
    """
    FastAPI Dependency — проверяет наличие конкретного разрешения у пользователя,
    независимо от роли. Более гранулярный контроль, чем require_role.

    Пример использования:
        @router.get("/gps", dependencies=[Depends(require_permission(PERM_GPS_READ))])
        async def get_gps(): ...

    Args:
        permission: Константа разрешения (например, PERM_GPS_READ)

    Returns:
        Dependency-функция для FastAPI
    """
    async def _dependency(
        request: Request,
        current_user: Optional[User] = Depends(get_current_user_optional),
    ) -> Optional[User]:
        # При YANDEX_ALLOW_SYNC_NOAUTH — пропускаем без авторизации (только для тестов)
        if current_user is None:
            if getattr(settings, "YANDEX_ALLOW_SYNC_NOAUTH", False):
                return None
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Требуется авторизация. Войдите в систему S-GLOBAL DOMINION."
            )

        user_role = (current_user.role or "").lower()

        if not has_permission(user_role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Доступ запрещён. Требуется разрешение: {permission}. "
                    f"Обратитесь к Мастеру для расширения прав."
                )
            )

        return current_user

    return _dependency


# ───────────────────────────────────────────────────────────────────────────────
# LEGACY-ФУНКЦИИ (обратная совместимость)
# Сохранены без изменений для работы существующего кода
# ───────────────────────────────────────────────────────────────────────────────

def has_module_access(user: User, module_id: str) -> bool:
    """
    Проверяет доступ пользователя к модулю системы.
    Legacy-функция — сохранена для обратной совместимости.
    """
    if not user:
        return False
    enabled_modules = set(get_enabled_modules())
    if module_id not in enabled_modules:
        return False
    if (user.role or "").lower() in (DominionRole.MASTER.value, DominionRole.OWNER.value):
        return True

    base_modules = {m.strip() for m in settings.TRIAL_BASE_MODULES.split(",") if m.strip()}
    if not is_trial_active(user) and module_id not in base_modules:
        return False

    return module_access(user.role, module_id)


def is_trial_active(user: User) -> bool:
    """
    Проверяет, активен ли пробный период для пользователя.
    Legacy-функция — сохранена для обратной совместимости.
    """
    if not user or not user.created_at:
        return False
    start = user.created_at
    if isinstance(start, datetime):
        trial_end = start + timedelta(days=settings.TRIAL_DAYS)
        return datetime.now() <= trial_end
    return False


def require_module(module_id: str):
    """
    FastAPI Dependency — проверяет доступ к модулю системы.
    Legacy-функция — сохранена для обратной совместимости.
    """
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
