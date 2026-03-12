# -*- coding: utf-8 -*-
# app/core/modules.py

from typing import Dict, List, Optional
from app.core.config import settings

MODULES: Dict[str, Dict] = {
    "core": {
        "label": "ЯДРО",
        "roles": ["master", "director", "admin", "convoy_head", "manager"]
    },
    "kazna": {
        "label": "КАЗНА / БУХГАЛТЕРИЯ",
        "roles": ["master", "director"]
    },
    "fleet": {
        "label": "ТАКСОПАРК T-CLUB24",
        "roles": ["master", "admin", "convoy_head", "manager"]
    },
    "logistics": {
        "label": "ПЕРЕВОЗКИ И ЛОГИСТИКА",
        "roles": ["master", "director"]
    },
    "autoservice": {
        "label": "АВТОСЕРВИС",
        "roles": ["master", "admin", "convoy_head"]
    },
    "warehouse": {
        "label": "СКЛАД И ЗАПЧАСТИ",
        "roles": ["master", "admin"]
    },
    "consulting": {
        "label": "КОНСАЛТИНГ И IT",
        "roles": ["master", "director"]
    },
    "ai_analyst": {
        "label": "AI АНАЛИТИК",
        "roles": ["master", "director"]
    },
    "security": {
        "label": "БЕЗОПАСНОСТЬ",
        "roles": ["master", "admin"]
    },
    "messenger": {
        "label": "IMPERIAL MESSENGER",
        "roles": ["master", "director", "admin", "convoy_head", "manager"]
    },
    "gps": {
        "label": "GPS МОНИТОРИНГ",
        "roles": ["master", "admin", "convoy_head", "manager"]
    },
    "tasks": {
        "label": "AI ОТЧЕТЫ И ЗАДАЧИ",
        "roles": ["master", "director", "manager"]
    },
    "merit": {
        "label": "ГАРНИЗОН ПОЧЕТА",
        "roles": ["master", "director"]
    },
    "investments": {
        "label": "ИНВЕСТИЦИИ И БЛАГОТВОРИТЕЛЬНОСТЬ",
        "roles": ["master", "director"]
    },
    "partners": {
        "label": "ПАРТНЕРЫ И ВЫПЛАТЫ",
        "roles": ["master", "director", "admin"]
    },
    "academy": {
        "label": "S-GLOBAL ACADEMY & LEGAL",
        "roles": ["master", "director"]
    }
}


def _parse_list(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def get_enabled_modules() -> List[str]:
    enabled_raw = _parse_list(settings.MODULES_ENABLED)
    disabled_raw = _parse_list(settings.MODULES_DISABLED)

    if enabled_raw:
        enabled = {m for m in enabled_raw}
    else:
        enabled = set(MODULES.keys())

    if disabled_raw:
        enabled -= {m for m in disabled_raw}

    return list(enabled)


def module_access(role: str, module_id: str) -> bool:
    module = MODULES.get(module_id)
    if not module:
        return False
    allowed_roles = [r.lower() for r in module.get("roles", [])]
    role_norm = (role or "").lower()
    if role_norm == "master":
        return True
    return role_norm in allowed_roles
