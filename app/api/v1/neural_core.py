# -*- coding: utf-8 -*-
# app/routes/neural_core.py

from datetime import datetime
import logging
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.all_models import (
    User,
)
from typing import Optional
from app.services.security import get_current_user_from_cookie, get_current_user_optional
from app.core.modules import MODULES, get_enabled_modules, module_access
from app.services.analytics_engine import AnalyticsEngine

logger = logging.getLogger("NeuralCore")
router = APIRouter(tags=["Neural Core"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/neural-core", response_class=HTMLResponse)
async def neural_core_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie)
):
    response = templates.TemplateResponse(
        "neural_core.html",
        {"request": request, "current_user": current_user}
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@router.get("/api/v1/neural/graph")
async def neural_graph_data(
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Данные для MindMap Command Center.
    """
    try:
        from app.services.yandex_sync_service import yandex_sync
        metrics = await AnalyticsEngine.get_overlay_metrics(
            db, yandex_sync=yandex_sync
        )
    except Exception as e:
        logger.error("Neural graph metrics error: %s", e, exc_info=True)
        metrics = {}  # Продолжаем с пустыми метриками, виджеты всё равно показываем

    if not metrics:
        metrics = {}  # Пустой dict вместо return — виджеты показываем всегда

    try:
        now = datetime.fromisoformat(metrics.get("timestamp") or datetime.now().isoformat())
    except Exception:
        now = datetime.now()
    vehicles_total = metrics.get("vehicles_total", 0)
    vehicles_working = metrics.get("vehicles_working", 0)
    vehicles_repair = metrics.get("vehicles_repair", 0)
    drivers_active = metrics.get("drivers_active", 0)
    drivers_online = metrics.get("drivers_online", 0)
    drivers_free = metrics.get("drivers_free", 0)
    drivers_in_order = metrics.get("drivers_in_order", 0)
    drivers_busy = metrics.get("drivers_busy", 0)
    tx_count = metrics.get("transactions_7d", 0)
    revenue_7d = metrics.get("revenue_7d", 0)
    gross_revenue_7d = metrics.get("gross_revenue_7d", 0)
    park_commission_7d = metrics.get("park_commission_7d", 0)
    expenses_7d = metrics.get("expenses_7d", 0)
    payouts_7d = metrics.get("payouts_7d", 0)
    revenue_today = metrics.get("revenue_today", 0)
    low_stock = metrics.get("low_stock", 0)
    service_in_progress = metrics.get("service_in_progress", 0)
    trips_total = metrics.get("trips_total", 0)
    park_counts = metrics.get("fleet_parks") or {
        "PRO": {"vehicles_total": 0},
        "GO": {"vehicles_total": 0},
        "PLUS": {"vehicles_total": 0},
        "EXPRESS": {"vehicles_total": 0},
    }

    enabled_modules = set(get_enabled_modules())
    role = getattr(current_user.role, "value", current_user.role) if current_user else "Guest"

    def module_state(module_id: str) -> dict:
        is_enabled = module_id in enabled_modules
        is_allowed = module_access(role, module_id)
        return {"enabled": is_enabled, "allowed": is_allowed}

    nodes = [
        {"id": "fleet", "label": "ТАКСОПАРК T-CLUB24", "group": "fleet", "size": 22, **module_state("fleet")},
        {"id": "logistics", "label": "ЛОГИСТИКА И МАРШРУТЫ", "group": "logistics", "size": 20, **module_state("logistics")},
        {"id": "consulting", "label": "КОНСАЛТИНГ И IT", "group": "consulting", "size": 20, **module_state("consulting")},
        {"id": "warehouse", "label": "АВТОСЕРВИС И СКЛАД", "group": "warehouse", "size": 20, **module_state("warehouse")},
        {"id": "ai_analyst", "label": "AI АНАЛИТИК", "group": "ai", "size": 20, **module_state("ai_analyst")},
        {"id": "messenger", "label": "IMPERIAL MESSENGER", "group": "messenger", "size": 18, **module_state("messenger")},
        {"id": "gps", "label": "GPS МОНИТОРИНГ", "group": "gps", "size": 18, **module_state("gps")},
        {"id": "tasks", "label": "AI ОТЧЕТЫ И ЗАДАЧИ", "group": "tasks", "size": 18, **module_state("tasks")},
        {"id": "merit", "label": "ГАРНИЗОН ПОЧЕТА", "group": "merit", "size": 18, **module_state("merit")},
        {"id": "investments", "label": "ИНВЕСТИЦИИ И БЛАГОТВОРИТЕЛЬНОСТЬ", "group": "investments", "size": 18, **module_state("investments")},
        {"id": "partners", "label": "ПАРТНЕРЫ И ВЫПЛАТЫ", "group": "partners", "size": 18, **module_state("partners")},
        {"id": "academy", "label": "S-GLOBAL ACADEMY & LEGAL", "group": "academy", "size": 18, **module_state("academy")},
    ]

    links = [
        {"source": "fleet", "target": "warehouse"},
        {"source": "fleet", "target": "gps"},
        {"source": "fleet", "target": "investments"},
        {"source": "fleet", "target": "partners"},
        {"source": "logistics", "target": "gps"},
        {"source": "logistics", "target": "fleet"},
        {"source": "consulting", "target": "academy"},
        {"source": "ai_analyst", "target": "tasks"},
        {"source": "messenger", "target": "ai_analyst"},
        {"source": "merit", "target": "fleet"},
    ]
    if service_in_progress > 0:
        links.append({"source": "warehouse", "target": "fleet", "type": "bridge"})

    children = {
        "fleet": [
            {"id": "fleet_pro", "label": f"PRO ({park_counts['PRO']['vehicles_total']})", "group": "fleet"},
            {"id": "fleet_go", "label": f"GO ({park_counts['GO']['vehicles_total']})", "group": "fleet"},
            {"id": "fleet_plus", "label": f"PLUS ({park_counts['PLUS']['vehicles_total']})", "group": "fleet"},
            {"id": "fleet_express", "label": f"EXPRESS ({park_counts['EXPRESS']['vehicles_total']})", "group": "fleet"},
            {"id": "fleet_vehicles", "label": f"База {vehicles_total} борт", "group": "fleet"},
            {"id": "fleet_working", "label": f"В работе {vehicles_working}", "group": "fleet"},
            {"id": "fleet_drivers", "label": f"{drivers_active} водителей", "group": "fleet"},
        ],
        "logistics": [
            {"id": "t24_cargo", "label": "T24-CARGO", "group": "logistics"},
            {"id": "vkusvill", "label": "ВкусВилл", "group": "logistics"},
            {"id": "routing", "label": f"Маршрутизация ({trips_total})", "group": "logistics"},
        ],
        "warehouse": [
            {"id": "stock", "label": f"Наличие ({low_stock} дефицит)", "group": "warehouse"},
            {"id": "purchases", "label": "Закупки", "group": "warehouse"},
            {"id": "inventory", "label": "Инвентаризация", "group": "warehouse"},
            {"id": "deficit", "label": "Дефицит", "group": "warehouse"},
            {"id": "service_current", "label": f"Ремонт ({vehicles_repair})", "group": "warehouse"},
        ],
        "consulting": [
            {"id": "dev", "label": "Разработки", "group": "consulting"},
            {"id": "clients", "label": "Клиенты", "group": "consulting"},
            {"id": "projects", "label": "Проекты v30.6+", "group": "consulting"},
        ],
        "ai_analyst": [
            {"id": "forecast", "label": "Прогнозы", "group": "ai"},
            {"id": "anomalies", "label": "Аномалии", "group": "ai"},
            {"id": "profit_opt", "label": "Оптимизация прибыли", "group": "ai"},
        ],
        "messenger": [
            {"id": "channels", "label": "Каналы по секторам", "group": "messenger"},
            {"id": "threads", "label": "Треды и объекты", "group": "messenger"},
            {"id": "attachments", "label": "Вложения", "group": "messenger"},
        ],
        "gps": [
            {"id": "radar", "label": "Радар активности", "group": "gps"},
            {"id": "zones", "label": "Гео-зоны", "group": "gps"},
            {"id": "heat", "label": "Плотность заказов", "group": "gps"},
        ],
        "tasks": [
            {"id": "plans", "label": "Планы и отчеты", "group": "tasks"},
            {"id": "pl_report", "label": f"P&L (7д) {int(park_commission_7d):,}₽", "group": "tasks"},
            {"id": "tx_7d", "label": f"Транзакции (7д) {tx_count}", "group": "tasks"},
        ],
        "merit": [
            {"id": "gold5", "label": "Золотая пятерка", "group": "merit"},
            {"id": "rating", "label": f"Рейтинг водителей ({drivers_active})", "group": "merit"},
            {"id": "badges", "label": "Награды и ауры", "group": "merit"},
        ],
        "investments": [
            {"id": "capital", "label": f"Капитал (7д) {int(gross_revenue_7d):,}₽", "group": "investments"},
            {"id": "fund", "label": "Фонд и гранты", "group": "investments"},
            {"id": "impact", "label": "Социальный эффект", "group": "investments"},
        ],
        "partners": [
            {"id": "b2b", "label": "B2B кабинеты", "group": "partners"},
            {"id": "firepay", "label": f"Выплаты (7д) {int(payouts_7d):,}₽", "group": "partners"},
            {"id": "banks", "label": "Банковские шлюзы", "group": "partners"},
        ],
        "academy": [
            {"id": "learning", "label": "Обучение и курсы", "group": "academy"},
            {"id": "legal", "label": "Юр. щит", "group": "academy"},
            {"id": "cert", "label": "Сертификация", "group": "academy"},
        ]
    }

    # Помечаем листья состоянием модулей
    for module_id, items in children.items():
        state = module_state(module_id)
        for item in items:
            item.update(state)

    return {
        "nodes": nodes,
        "links": links,
        "children": children,
        "meta": {
            "vehicles_total": vehicles_total,
            "vehicles_working": vehicles_working,
            "vehicles_repair": vehicles_repair,
            "drivers_active": drivers_active,
            "drivers_online": drivers_online,
            "drivers_free": drivers_free,
            "drivers_in_order": drivers_in_order,
            "drivers_busy": drivers_busy,
            "live_300": metrics.get("live_300", 0),
            "transactions_7d": tx_count,
            "revenue_7d": float(revenue_7d or 0),
            "gross_revenue_7d": float(gross_revenue_7d or 0),
            "park_commission_7d": float(park_commission_7d or 0),
            "revenue_today": float(revenue_today or 0),
            "expenses_7d": float(expenses_7d or 0),
            "payouts_7d": float(payouts_7d or 0),
            "kazna_profit_7d": float(metrics.get("kazna_profit_7d") or 0),
            "low_stock": low_stock,
            "service_in_progress": service_in_progress,
            "trips_total": trips_total,
            "ai_insight": "Поток стабилен. Аномалий не обнаружено.",
            "timestamp": now.isoformat(),
            "has_kazna_data": metrics.get("has_kazna_data", False),
            "has_fleet_data": metrics.get("has_fleet_data", False),
            "fleet_parks": metrics.get("fleet_parks") or {},
            "fleet_totals": metrics.get("fleet_totals") or {},
            "fleet_archived_drivers": metrics.get("fleet_archived_drivers", 0),
            "modules_enabled": list(enabled_modules),
            "modules_disabled": [m for m in MODULES.keys() if m not in enabled_modules],
            "role": role
        }
    }
