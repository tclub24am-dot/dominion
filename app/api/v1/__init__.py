# -*- coding: utf-8 -*-
# app/api/v1/__init__.py

from .auth import router as auth
from .fleet import router as fleet
# Хребет экономики:
from .kazna import router as kazna
# Нервная система ВкусВилл:
from .logistics import router as logistics
# Арсенал запчастей:
from .warehouse import router as warehouse
# Око Оракула:
from .analytics import router as analytics
from .messenger import router as messenger
from .partner import router as partners
from .neural_core import router as neural_core
from .cashflow import router as investments
from .realtime import router as gps

# Экспортируем ВСЕ модули для центрального процессора main.py
__all__ = [
    "auth",
    "fleet",
    "kazna",
    "logistics",
    "warehouse",
    "analytics",
    "messenger",
    "partners",
    "neural_core",
    "investments",
    "gps"
]
