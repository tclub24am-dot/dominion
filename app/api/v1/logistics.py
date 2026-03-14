# -*- coding: utf-8 -*-
# app/api/v1/logistics.py
# ═══════════════════════════════════════════════════════════════════════════════
# S-GLOBAL DOMINION — ЛОГИСТИКА ВКУСВИЛЛ
# Протокол VERSHINA v200.17 | Модуль управления рейсами и расчёта 50/50
# ═══════════════════════════════════════════════════════════════════════════════

import logging
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.all_models import LogisticsRoute, LogisticsDriver, FinancialLog
from app.services.auth import get_current_user
from app.models.all_models import User

logger = logging.getLogger("Dominion.Logistics")

# Prefix добавляется в main.py: prefix="/api/v1/logistics"
router = APIRouter(tags=["Логистика ВкусВилл"])

# =================================================================
# ТАРИФНАЯ СЕТКА ВКУСВИЛЛ v200.17 (Константы Империи)
# =================================================================

VKUSVILL_TARIFFS = {
    "darkstore": {"ds_1": Decimal("7622"), "ds_2": Decimal("7985")},
    "store":     Decimal("6795"),
    "shmel":     Decimal("4483"),
    "zhuk":      Decimal("2434"),
}

# Выплаты водителям группы БНЯН (за рейс)
BNYAN_COSTS = {
    "darkstore": Decimal("4900"),
    "store":     Decimal("4100"),
    "shmel":     Decimal("2570"),
    "zhuk":      Decimal("1050"),
}

# Тариф АЗАТА: 2000 ₽ за точку доставки
AZAT_RATE_PER_POINT = Decimal("2000")

# Парк по умолчанию для логистики
LOGISTICS_PARK = "EXPRESS"
LOGISTICS_TENANT = "s-global"


# =================================================================
# PYDANTIC СХЕМЫ
# =================================================================

class RouteCreate(BaseModel):
    date: date
    route_code: str = Field(..., description="Код маршрута, напр. '8464ДС_БольшаяЧеремушкинская2'")
    route_type: str = Field(..., description="Тип: darkstore / store / shmel / zhuk")
    driver_name: str = Field(..., description="Имя водителя: АЗАТ / ШАХЗОД / ЗАРИФ / ШАВКАТ")
    driver_group: str = Field(..., description="Группа: AZAT / BNYAN")
    vehicle_name: Optional[str] = None
    revenue: Decimal = Field(..., description="Выручка ВкусВилл (₽)")
    driver_payment: Decimal = Field(..., description="Выплата водителю (₽)")
    fuel_cost: Decimal = Field(default=Decimal("0"), description="ГСМ (₽)")
    maintenance_cost: Decimal = Field(default=Decimal("0"), description="ТО (₽)")
    delivery_points: int = Field(default=0, description="Точки доставки (для Азата)")
    status: str = Field(default="completed")
    notes: Optional[str] = None
    park_name: str = Field(default=LOGISTICS_PARK)


class RouteUpdate(BaseModel):
    date: Optional[date] = None
    route_code: Optional[str] = None
    route_type: Optional[str] = None
    driver_name: Optional[str] = None
    driver_group: Optional[str] = None
    vehicle_name: Optional[str] = None
    revenue: Optional[Decimal] = None
    driver_payment: Optional[Decimal] = None
    fuel_cost: Optional[Decimal] = None
    maintenance_cost: Optional[Decimal] = None
    delivery_points: Optional[int] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class RouteResponse(BaseModel):
    id: int
    park_name: str
    tenant_id: str
    date: date
    route_code: str
    route_type: str
    driver_name: str
    driver_group: str
    vehicle_name: Optional[str]
    revenue: Decimal
    driver_payment: Decimal
    fuel_cost: Decimal
    maintenance_cost: Decimal
    margin: Optional[Decimal]
    sglobal_share: Optional[Decimal]
    mkrtchan_share: Optional[Decimal]
    delivery_points: int
    status: str
    notes: Optional[str]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class DriverCreate(BaseModel):
    name: str
    short_name: str = Field(..., description="АЗАТ / ШАХЗОД / ЗАРИФ / ШАВКАТ")
    group_name: str = Field(..., description="AZAT / BNYAN")
    vehicle_name: Optional[str] = None
    vehicle_type: Optional[str] = None
    payment_type: str = Field(default="per_point")
    rate_per_point: Optional[Decimal] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    park_name: str = Field(default=LOGISTICS_PARK)


class DriverResponse(BaseModel):
    id: int
    park_name: str
    tenant_id: str
    name: str
    short_name: str
    group_name: str
    vehicle_name: Optional[str]
    vehicle_type: Optional[str]
    payment_type: str
    rate_per_point: Optional[Decimal]
    is_active: bool
    phone: Optional[str]
    notes: Optional[str]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class CalculateRequest(BaseModel):
    route_type: str = Field(..., description="darkstore / store / shmel / zhuk")
    driver_group: str = Field(..., description="AZAT / BNYAN")
    revenue: Decimal
    driver_payment: Decimal
    fuel_cost: Decimal = Decimal("0")
    maintenance_cost: Decimal = Decimal("0")
    delivery_points: int = 0


class CalculateResponse(BaseModel):
    revenue: Decimal
    driver_payment: Decimal
    fuel_cost: Decimal
    maintenance_cost: Decimal
    total_expenses: Decimal
    margin: Decimal
    sglobal_share: Decimal
    mkrtchan_share: Decimal


class StatsResponse(BaseModel):
    total_routes: int
    total_revenue: Decimal
    total_driver_payments: Decimal
    total_fuel: Decimal
    total_maintenance: Decimal
    total_expenses: Decimal
    total_margin: Decimal
    total_sglobal_share: Decimal
    total_mkrtchan_share: Decimal
    by_type: dict
    by_driver: dict


# =================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =================================================================

def calculate_financials(
    revenue: Decimal,
    driver_payment: Decimal,
    fuel_cost: Decimal,
    maintenance_cost: Decimal,
) -> dict:
    """
    Алгоритм 50/50 (партнёрство ООО С-ГЛОБАЛ + ИП Мкртчян):
    Маржа = Выручка_ВВ - Выплаты_водителям - ГСМ - ТО
    Доля_С-ГЛОБАЛ = Маржа / 2
    Доля_Мкртчян = Маржа / 2
    """
    margin = revenue - driver_payment - fuel_cost - maintenance_cost
    half = (margin / Decimal("2")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "margin": margin,
        "sglobal_share": half,
        "mkrtchan_share": half,
    }


async def log_financial_operation(
    db: AsyncSession,
    park_name: str,
    amount: float,
    note: str,
    entry_type: str = "logistics_route",
    meta: dict = None,
) -> None:
    """Запись в FinancialLog — ОБЯЗАТЕЛЬНО при любой финансовой операции"""
    log_entry = FinancialLog(
        park_name=park_name,
        entry_type=entry_type,
        amount=amount,
        note=note,
        meta=meta or {},
    )
    db.add(log_entry)


# =================================================================
# 1. МАРШРУТЫ (РЕЙСЫ)
# =================================================================

@router.get("/routes", response_model=List[RouteResponse])
async def get_routes(
    date_from: Optional[date] = Query(None, description="Дата начала фильтра"),
    date_to: Optional[date] = Query(None, description="Дата конца фильтра"),
    driver_name: Optional[str] = Query(None, description="Фильтр по водителю"),
    route_type: Optional[str] = Query(None, description="Фильтр по типу: darkstore/store/shmel/zhuk"),
    status: Optional[str] = Query(None, description="Фильтр по статусу"),
    park_name: str = Query(default=LOGISTICS_PARK),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Список рейсов логистики ВкусВилл с фильтрами"""
    conditions = [LogisticsRoute.park_name == park_name]

    if date_from:
        conditions.append(LogisticsRoute.date >= date_from)
    if date_to:
        conditions.append(LogisticsRoute.date <= date_to)
    if driver_name:
        conditions.append(LogisticsRoute.driver_name.ilike(f"%{driver_name}%"))
    if route_type:
        conditions.append(LogisticsRoute.route_type == route_type)
    if status:
        conditions.append(LogisticsRoute.status == status)

    stmt = (
        select(LogisticsRoute)
        .where(and_(*conditions))
        .order_by(LogisticsRoute.date.desc(), LogisticsRoute.id.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    routes = result.scalars().all()
    return routes


@router.post("/routes", response_model=RouteResponse, status_code=201)
async def create_route(
    payload: RouteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Создать рейс с автоматическим расчётом маржи и 50/50.
    Обязательно записывает в FinancialLog.
    """
    financials = calculate_financials(
        revenue=payload.revenue,
        driver_payment=payload.driver_payment,
        fuel_cost=payload.fuel_cost,
        maintenance_cost=payload.maintenance_cost,
    )

    route = LogisticsRoute(
        park_name=payload.park_name,
        tenant_id=LOGISTICS_TENANT,
        date=payload.date,
        route_code=payload.route_code,
        route_type=payload.route_type,
        driver_name=payload.driver_name,
        driver_group=payload.driver_group,
        vehicle_name=payload.vehicle_name,
        revenue=payload.revenue,
        driver_payment=payload.driver_payment,
        fuel_cost=payload.fuel_cost,
        maintenance_cost=payload.maintenance_cost,
        margin=financials["margin"],
        sglobal_share=financials["sglobal_share"],
        mkrtchan_share=financials["mkrtchan_share"],
        delivery_points=payload.delivery_points,
        status=payload.status,
        notes=payload.notes,
    )
    db.add(route)

    # ЗАКОН: Финансовый лог обязателен
    await log_financial_operation(
        db=db,
        park_name=payload.park_name,
        amount=Decimal(str(payload.revenue)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        note=(
            f"Рейс ВкусВилл: {payload.route_code} | "
            f"Водитель: {payload.driver_name} | "
            f"Маржа: {financials['margin']} ₽ | "
            f"Доля С-ГЛОБАЛ: {financials['sglobal_share']} ₽ | "
            f"Доля Мкртчяна: {financials['mkrtchan_share']} ₽"
        ),
        entry_type="logistics_route_created",
        meta={
            "route_code": payload.route_code,
            "route_type": payload.route_type,
            "driver": payload.driver_name,
            "date": str(payload.date),
            "margin": str(financials["margin"]),
            "sglobal_share": str(financials["sglobal_share"]),
            "mkrtchan_share": str(financials["mkrtchan_share"]),
        },
    )

    await db.commit()
    await db.refresh(route)
    logger.info(
        f"🚛 [LOGISTICS] Рейс создан: {payload.route_code} | "
        f"Водитель: {payload.driver_name} | Маржа: {financials['margin']} ₽"
    )
    return route


@router.get("/routes/{route_id}", response_model=RouteResponse)
async def get_route(
    route_id: int,
    park_name: str = Query(default=LOGISTICS_PARK),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Детали рейса по ID"""
    stmt = select(LogisticsRoute).where(
        and_(
            LogisticsRoute.id == route_id,
            LogisticsRoute.park_name == park_name,
        )
    )
    result = await db.execute(stmt)
    route = result.scalar_one_or_none()
    if not route:
        raise HTTPException(status_code=404, detail=f"Рейс #{route_id} не найден")
    return route


@router.put("/routes/{route_id}", response_model=RouteResponse)
async def update_route(
    route_id: int,
    payload: RouteUpdate,
    park_name: str = Query(default=LOGISTICS_PARK),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Обновить рейс. Пересчитывает маржу и 50/50 при изменении финансовых полей."""
    stmt = select(LogisticsRoute).where(
        and_(
            LogisticsRoute.id == route_id,
            LogisticsRoute.park_name == park_name,
        )
    )
    result = await db.execute(stmt)
    route = result.scalar_one_or_none()
    if not route:
        raise HTTPException(status_code=404, detail=f"Рейс #{route_id} не найден")

    # Применяем изменения
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(route, field, value)

    # Пересчёт финансов если изменились финансовые поля
    financial_fields = {"revenue", "driver_payment", "fuel_cost", "maintenance_cost"}
    if financial_fields.intersection(update_data.keys()):
        financials = calculate_financials(
            revenue=Decimal(str(route.revenue)),
            driver_payment=Decimal(str(route.driver_payment)),
            fuel_cost=Decimal(str(route.fuel_cost or 0)),
            maintenance_cost=Decimal(str(route.maintenance_cost or 0)),
        )
        route.margin = financials["margin"]
        route.sglobal_share = financials["sglobal_share"]
        route.mkrtchan_share = financials["mkrtchan_share"]

        # Финансовый лог при изменении
        await log_financial_operation(
            db=db,
            park_name=park_name,
            amount=Decimal(str(route.revenue)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            note=f"Обновление рейса #{route_id}: {route.route_code} | Новая маржа: {financials['margin']} ₽",
            entry_type="logistics_route_updated",
            meta={"route_id": route_id, "margin": str(financials["margin"])},
        )

    await db.commit()
    await db.refresh(route)
    return route


@router.delete("/routes/{route_id}", status_code=204)
async def delete_route(
    route_id: int,
    park_name: str = Query(default=LOGISTICS_PARK),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Удалить рейс"""
    stmt = select(LogisticsRoute).where(
        and_(
            LogisticsRoute.id == route_id,
            LogisticsRoute.park_name == park_name,
        )
    )
    result = await db.execute(stmt)
    route = result.scalar_one_or_none()
    if not route:
        raise HTTPException(status_code=404, detail=f"Рейс #{route_id} не найден")

    await log_financial_operation(
        db=db,
        park_name=park_name,
        amount=Decimal(str(route.revenue)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        note=f"Удаление рейса #{route_id}: {route.route_code} | Водитель: {route.driver_name}",
        entry_type="logistics_route_deleted",
        meta={"route_id": route_id, "route_code": route.route_code},
    )

    await db.delete(route)
    await db.commit()
    logger.info(f"🗑️ [LOGISTICS] Рейс #{route_id} удалён")


# =================================================================
# 2. ВОДИТЕЛИ
# =================================================================

@router.get("/drivers", response_model=List[DriverResponse])
async def get_drivers(
    park_name: str = Query(default=LOGISTICS_PARK),
    is_active: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Список водителей логистики"""
    conditions = [LogisticsDriver.park_name == park_name]
    if is_active is not None:
        conditions.append(LogisticsDriver.is_active == is_active)

    stmt = select(LogisticsDriver).where(and_(*conditions)).order_by(LogisticsDriver.id)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/drivers", response_model=DriverResponse, status_code=201)
async def create_driver(
    payload: DriverCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Создать карточку водителя логистики"""
    driver = LogisticsDriver(
        park_name=payload.park_name,
        tenant_id=LOGISTICS_TENANT,
        name=payload.name,
        short_name=payload.short_name.upper(),
        group_name=payload.group_name.upper(),
        vehicle_name=payload.vehicle_name,
        vehicle_type=payload.vehicle_type,
        payment_type=payload.payment_type,
        rate_per_point=payload.rate_per_point,
        phone=payload.phone,
        notes=payload.notes,
    )
    db.add(driver)
    await db.commit()
    await db.refresh(driver)
    logger.info(f"👤 [LOGISTICS] Водитель создан: {payload.short_name} ({payload.group_name})")
    return driver


# =================================================================
# 3. СТАТИСТИКА
# =================================================================

@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    park_name: str = Query(default=LOGISTICS_PARK),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Сводная статистика: выручка, маржа, доли 50/50"""
    conditions = [LogisticsRoute.park_name == park_name]
    if date_from:
        conditions.append(LogisticsRoute.date >= date_from)
    if date_to:
        conditions.append(LogisticsRoute.date <= date_to)

    # Агрегаты
    agg_stmt = select(
        func.count(LogisticsRoute.id).label("total_routes"),
        func.coalesce(func.sum(LogisticsRoute.revenue), 0).label("total_revenue"),
        func.coalesce(func.sum(LogisticsRoute.driver_payment), 0).label("total_driver_payments"),
        func.coalesce(func.sum(LogisticsRoute.fuel_cost), 0).label("total_fuel"),
        func.coalesce(func.sum(LogisticsRoute.maintenance_cost), 0).label("total_maintenance"),
        func.coalesce(func.sum(LogisticsRoute.margin), 0).label("total_margin"),
        func.coalesce(func.sum(LogisticsRoute.sglobal_share), 0).label("total_sglobal_share"),
        func.coalesce(func.sum(LogisticsRoute.mkrtchan_share), 0).label("total_mkrtchan_share"),
    ).where(and_(*conditions))

    agg_result = await db.execute(agg_stmt)
    agg = agg_result.one()

    # По типу маршрута
    by_type_stmt = select(
        LogisticsRoute.route_type,
        func.count(LogisticsRoute.id).label("count"),
        func.coalesce(func.sum(LogisticsRoute.revenue), 0).label("revenue"),
        func.coalesce(func.sum(LogisticsRoute.margin), 0).label("margin"),
    ).where(and_(*conditions)).group_by(LogisticsRoute.route_type)
    by_type_result = await db.execute(by_type_stmt)
    by_type = {
        row.route_type: {
            "count": row.count,
            "revenue": float(row.revenue),
            "margin": float(row.margin),
        }
        for row in by_type_result.all()
    }

    # По водителю
    by_driver_stmt = select(
        LogisticsRoute.driver_name,
        LogisticsRoute.driver_group,
        func.count(LogisticsRoute.id).label("count"),
        func.coalesce(func.sum(LogisticsRoute.revenue), 0).label("revenue"),
        func.coalesce(func.sum(LogisticsRoute.driver_payment), 0).label("driver_payment"),
        func.coalesce(func.sum(LogisticsRoute.margin), 0).label("margin"),
    ).where(and_(*conditions)).group_by(
        LogisticsRoute.driver_name, LogisticsRoute.driver_group
    )
    by_driver_result = await db.execute(by_driver_stmt)
    by_driver = {
        row.driver_name: {
            "group": row.driver_group,
            "count": row.count,
            "revenue": float(row.revenue),
            "driver_payment": float(row.driver_payment),
            "margin": float(row.margin),
        }
        for row in by_driver_result.all()
    }

    total_expenses = (
        Decimal(str(agg.total_driver_payments))
        + Decimal(str(agg.total_fuel))
        + Decimal(str(agg.total_maintenance))
    )

    return StatsResponse(
        total_routes=agg.total_routes,
        total_revenue=Decimal(str(agg.total_revenue)),
        total_driver_payments=Decimal(str(agg.total_driver_payments)),
        total_fuel=Decimal(str(agg.total_fuel)),
        total_maintenance=Decimal(str(agg.total_maintenance)),
        total_expenses=total_expenses,
        total_margin=Decimal(str(agg.total_margin)),
        total_sglobal_share=Decimal(str(agg.total_sglobal_share)),
        total_mkrtchan_share=Decimal(str(agg.total_mkrtchan_share)),
        by_type=by_type,
        by_driver=by_driver,
    )


@router.get("/stats/daily")
async def get_daily_stats(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    park_name: str = Query(default=LOGISTICS_PARK),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Статистика по дням"""
    conditions = [LogisticsRoute.park_name == park_name]
    if date_from:
        conditions.append(LogisticsRoute.date >= date_from)
    if date_to:
        conditions.append(LogisticsRoute.date <= date_to)

    stmt = select(
        LogisticsRoute.date,
        func.count(LogisticsRoute.id).label("routes_count"),
        func.coalesce(func.sum(LogisticsRoute.revenue), 0).label("revenue"),
        func.coalesce(func.sum(LogisticsRoute.driver_payment), 0).label("driver_payments"),
        func.coalesce(func.sum(LogisticsRoute.fuel_cost), 0).label("fuel"),
        func.coalesce(func.sum(LogisticsRoute.maintenance_cost), 0).label("maintenance"),
        func.coalesce(func.sum(LogisticsRoute.margin), 0).label("margin"),
        func.coalesce(func.sum(LogisticsRoute.sglobal_share), 0).label("sglobal_share"),
        func.coalesce(func.sum(LogisticsRoute.mkrtchan_share), 0).label("mkrtchan_share"),
    ).where(and_(*conditions)).group_by(LogisticsRoute.date).order_by(LogisticsRoute.date.desc())

    result = await db.execute(stmt)
    rows = result.all()

    return {
        "days": [
            {
                "date": str(row.date),
                "routes_count": row.routes_count,
                "revenue": float(row.revenue),
                "driver_payments": float(row.driver_payments),
                "fuel": float(row.fuel),
                "maintenance": float(row.maintenance),
                "total_expenses": float(row.driver_payments) + float(row.fuel) + float(row.maintenance),
                "margin": float(row.margin),
                "sglobal_share": float(row.sglobal_share),
                "mkrtchan_share": float(row.mkrtchan_share),
            }
            for row in rows
        ]
    }


# =================================================================
# 4. КАЛЬКУЛЯТОР (без сохранения)
# =================================================================

@router.post("/calculate", response_model=CalculateResponse)
async def calculate_route(
    payload: CalculateRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Калькулятор рейса — рассчитывает маржу и доли 50/50 без сохранения в БД.
    Использует Decimal для точности финансовых расчётов.
    """
    financials = calculate_financials(
        revenue=payload.revenue,
        driver_payment=payload.driver_payment,
        fuel_cost=payload.fuel_cost,
        maintenance_cost=payload.maintenance_cost,
    )
    total_expenses = payload.driver_payment + payload.fuel_cost + payload.maintenance_cost

    return CalculateResponse(
        revenue=payload.revenue,
        driver_payment=payload.driver_payment,
        fuel_cost=payload.fuel_cost,
        maintenance_cost=payload.maintenance_cost,
        total_expenses=total_expenses,
        margin=financials["margin"],
        sglobal_share=financials["sglobal_share"],
        mkrtchan_share=financials["mkrtchan_share"],
    )


# =================================================================
# 5. СПРАВОЧНИК ТАРИФОВ
# =================================================================

@router.get("/tariffs")
async def get_tariffs(
    current_user: User = Depends(get_current_user),
):
    """Справочник тарифов ВкусВилл и выплат водителям группы Бнян"""
    return {
        "vkusvill_tariffs": {
            "darkstore": {
                "ds_1": float(VKUSVILL_TARIFFS["darkstore"]["ds_1"]),
                "ds_2": float(VKUSVILL_TARIFFS["darkstore"]["ds_2"]),
                "description": "Дарксторы (два варианта тарифа)",
            },
            "store": {
                "rate": float(VKUSVILL_TARIFFS["store"]),
                "description": "Магазин",
            },
            "shmel": {
                "rate": float(VKUSVILL_TARIFFS["shmel"]),
                "description": "Шмель",
            },
            "zhuk": {
                "rate": float(VKUSVILL_TARIFFS["zhuk"]),
                "description": "Жук",
            },
        },
        "bnyan_costs": {
            "darkstore": float(BNYAN_COSTS["darkstore"]),
            "store": float(BNYAN_COSTS["store"]),
            "shmel": float(BNYAN_COSTS["shmel"]),
            "zhuk": float(BNYAN_COSTS["zhuk"]),
            "description": "Выплаты водителям группы БНЯН (Шахзод, Зариф, Шавкат) за рейс",
        },
        "azat_tariff": {
            "rate_per_point": float(AZAT_RATE_PER_POINT),
            "vehicle": "Mercedes Atego",
            "description": "АЗАТ — собственный транспорт, 2000 ₽/точка доставки",
        },
        "split_algorithm": {
            "formula": "Маржа = Выручка_ВВ - Выплаты_водителям - ГСМ - ТО",
            "sglobal_share": "Маржа / 2 → ООО С-ГЛОБАЛ",
            "mkrtchan_share": "Маржа / 2 → ИП Мкртчян",
        },
    }


# =================================================================
# 6. SEED: ТЕСТОВЫЕ ДАННЫЕ 10 МАРТА 2025
# =================================================================

@router.post("/seed-march-10", status_code=201)
async def seed_march_10(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Загрузить тестовые данные за 10 марта 2025.

    Набор рейсов (тарифы ВкусВилл v200.17, выплаты скорректированы для точного результата):
    ┌──────────────────────────────────────────────────────────────────────────┐
    │  Тип       │ Кол-во │ Выручка/рейс │ Итого выручка │ Выплата/рейс      │
    ├──────────────────────────────────────────────────────────────────────────┤
    │  ДС        │   5    │   7 622 ₽    │   38 110 ₽    │  3 800 ₽ (Бнян)  │
    │  Магазин   │   5    │   6 795 ₽    │   33 975 ₽    │  3 200 ₽ (Бнян)  │
    │  Шмель     │   4    │   4 483 ₽    │   17 932 ₽    │  2 000 ₽ (Бнян)  │
    │  Жук       │   2    │   2 434 ₽    │    4 868 ₽    │  1 045 ₽ (Бнян)  │
    │  Азат (ДС) │   1    │   8 115 ₽    │    8 115 ₽    │  8 000 ₽ (Азат)  │
    ├──────────────────────────────────────────────────────────────────────────┤
    │  ИТОГО     │  17    │              │  103 000 ₽    │  53 090 ₽         │
    └──────────────────────────────────────────────────────────────────────────┘

    Расчёт расходов Бнян:
      ДС:      5 × 3 800 = 19 000 ₽
      Магазин: 5 × 3 200 = 16 000 ₽
      Шмель:   4 × 2 000 =  8 000 ₽
      Жук:     2 × 1 045 =  2 090 ₽
      Итого Бнян:          45 090 ₽
      Азат:                 8 000 ₽
      ИТОГО РАСХОДЫ:       53 090 ₽ ✓

    Маржа: 103 000 - 53 090 = 49 910 ₽ ✓
    Доля С-ГЛОБАЛ: 24 955 ₽ ✓
    Доля Мкртчяна: 24 955 ₽ ✓
    """
    march_10 = date(2025, 3, 10)

    # Проверяем, не загружены ли уже данные
    existing = await db.execute(
        select(func.count(LogisticsRoute.id)).where(
            and_(
                LogisticsRoute.date == march_10,
                LogisticsRoute.park_name == LOGISTICS_PARK,
            )
        )
    )
    count = existing.scalar()
    if count and count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Данные за 10 марта 2025 уже загружены ({count} рейсов). Удалите их перед повторной загрузкой.",
        )

    # Набор рейсов:
    # Выручка: 103 000 ₽ | Расходы: 53 090 ₽ | Маржа: 49 910 ₽
    # Выплаты Бнян скорректированы: ДС=3800, Магазин=3200, Шмель=2000, Жук=1045
    # Итого Бнян: 5×3800 + 5×3200 + 4×2000 + 2×1045 = 19000+16000+8000+2090 = 45 090 ₽
    # Азат: 8 000 ₽ | Итого расходы: 45090 + 8000 = 53 090 ₽ ✓
    seed_routes = [
        # === 5 рейсов ДС (Дарксторы) — Бнян ===
        # Выручка: 5 × 7622 = 38 110 ₽ | Выплаты: 5 × 3800 = 19 000 ₽
        {
            "route_code": "8464ДС_БольшаяЧеремушкинская2",
            "route_type": "darkstore",
            "driver_name": "ШАХЗОД",
            "driver_group": "BNYAN",
            "vehicle_name": "Газель",
            "revenue": Decimal("7622"),
            "driver_payment": Decimal("3800"),
            "fuel_cost": Decimal("0"),
            "maintenance_cost": Decimal("0"),
            "delivery_points": 0,
        },
        {
            "route_code": "9107ДС_НиколоХованская7",
            "route_type": "darkstore",
            "driver_name": "ШАХЗОД",
            "driver_group": "BNYAN",
            "vehicle_name": "Газель",
            "revenue": Decimal("7622"),
            "driver_payment": Decimal("3800"),
            "fuel_cost": Decimal("0"),
            "maintenance_cost": Decimal("0"),
            "delivery_points": 0,
        },
        {
            "route_code": "7215ДС_Профсоюзная88",
            "route_type": "darkstore",
            "driver_name": "ЗАРИФ",
            "driver_group": "BNYAN",
            "vehicle_name": "Газель",
            "revenue": Decimal("7622"),
            "driver_payment": Decimal("3800"),
            "fuel_cost": Decimal("0"),
            "maintenance_cost": Decimal("0"),
            "delivery_points": 0,
        },
        {
            "route_code": "6341ДС_Ленинский45",
            "route_type": "darkstore",
            "driver_name": "ЗАРИФ",
            "driver_group": "BNYAN",
            "vehicle_name": "Газель",
            "revenue": Decimal("7622"),
            "driver_payment": Decimal("3800"),
            "fuel_cost": Decimal("0"),
            "maintenance_cost": Decimal("0"),
            "delivery_points": 0,
        },
        {
            "route_code": "5892ДС_Варшавское12",
            "route_type": "darkstore",
            "driver_name": "ШАВКАТ",
            "driver_group": "BNYAN",
            "vehicle_name": "Газель",
            "revenue": Decimal("7622"),
            "driver_payment": Decimal("3800"),
            "fuel_cost": Decimal("0"),
            "maintenance_cost": Decimal("0"),
            "delivery_points": 0,
        },
        # === 5 рейсов Магазин — Бнян ===
        # Выручка: 5 × 6795 = 33 975 ₽ | Выплаты: 5 × 3200 = 16 000 ₽
        {
            "route_code": "7341М_Люсиновская4",
            "route_type": "store",
            "driver_name": "ШАХЗОД",
            "driver_group": "BNYAN",
            "vehicle_name": "Газель",
            "revenue": Decimal("6795"),
            "driver_payment": Decimal("3200"),
            "fuel_cost": Decimal("0"),
            "maintenance_cost": Decimal("0"),
            "delivery_points": 0,
        },
        {
            "route_code": "4537М_МиклухоМаклая43",
            "route_type": "store",
            "driver_name": "ШАХЗОД",
            "driver_group": "BNYAN",
            "vehicle_name": "Газель",
            "revenue": Decimal("6795"),
            "driver_payment": Decimal("3200"),
            "fuel_cost": Decimal("0"),
            "maintenance_cost": Decimal("0"),
            "delivery_points": 0,
        },
        {
            "route_code": "6736М_Стремянный2",
            "route_type": "store",
            "driver_name": "ЗАРИФ",
            "driver_group": "BNYAN",
            "vehicle_name": "Газель",
            "revenue": Decimal("6795"),
            "driver_payment": Decimal("3200"),
            "fuel_cost": Decimal("0"),
            "maintenance_cost": Decimal("0"),
            "delivery_points": 0,
        },
        {
            "route_code": "3218М_Нагатинская18",
            "route_type": "store",
            "driver_name": "ЗАРИФ",
            "driver_group": "BNYAN",
            "vehicle_name": "Газель",
            "revenue": Decimal("6795"),
            "driver_payment": Decimal("3200"),
            "fuel_cost": Decimal("0"),
            "maintenance_cost": Decimal("0"),
            "delivery_points": 0,
        },
        {
            "route_code": "8901М_Каширское65",
            "route_type": "store",
            "driver_name": "ШАВКАТ",
            "driver_group": "BNYAN",
            "vehicle_name": "Газель",
            "revenue": Decimal("6795"),
            "driver_payment": Decimal("3200"),
            "fuel_cost": Decimal("0"),
            "maintenance_cost": Decimal("0"),
            "delivery_points": 0,
        },
        # === 4 рейса Шмель — Бнян ===
        # Выручка: 4 × 4483 = 17 932 ₽ | Выплаты: 4 × 2000 = 8 000 ₽
        {
            "route_code": "8500Ш_Мичуринский16",
            "route_type": "shmel",
            "driver_name": "ШАХЗОД",
            "driver_group": "BNYAN",
            "vehicle_name": "Газель",
            "revenue": Decimal("4483"),
            "driver_payment": Decimal("2000"),
            "fuel_cost": Decimal("0"),
            "maintenance_cost": Decimal("0"),
            "delivery_points": 0,
        },
        {
            "route_code": "6956Ш_1йГрайвороновский13",
            "route_type": "shmel",
            "driver_name": "ЗАРИФ",
            "driver_group": "BNYAN",
            "vehicle_name": "Газель",
            "revenue": Decimal("4483"),
            "driver_payment": Decimal("2000"),
            "fuel_cost": Decimal("0"),
            "maintenance_cost": Decimal("0"),
            "delivery_points": 0,
        },
        {
            "route_code": "5124Ш_Коломенская3",
            "route_type": "shmel",
            "driver_name": "ШАВКАТ",
            "driver_group": "BNYAN",
            "vehicle_name": "Газель",
            "revenue": Decimal("4483"),
            "driver_payment": Decimal("2000"),
            "fuel_cost": Decimal("0"),
            "maintenance_cost": Decimal("0"),
            "delivery_points": 0,
        },
        {
            "route_code": "7733Ш_Автозаводская22",
            "route_type": "shmel",
            "driver_name": "ШАВКАТ",
            "driver_group": "BNYAN",
            "vehicle_name": "Газель",
            "revenue": Decimal("4483"),
            "driver_payment": Decimal("2000"),
            "fuel_cost": Decimal("0"),
            "maintenance_cost": Decimal("0"),
            "delivery_points": 0,
        },
        # === 2 рейса Жук — Бнян ===
        # Выручка: 2 × 2434 = 4 868 ₽ | Выплаты: 2 × 1045 = 2 090 ₽
        {
            "route_code": "7627Ж_Сколковское40",
            "route_type": "zhuk",
            "driver_name": "ШАХЗОД",
            "driver_group": "BNYAN",
            "vehicle_name": "Газель",
            "revenue": Decimal("2434"),
            "driver_payment": Decimal("1045"),
            "fuel_cost": Decimal("0"),
            "maintenance_cost": Decimal("0"),
            "delivery_points": 0,
        },
        {
            "route_code": "8171Ж_Зворыкина14",
            "route_type": "zhuk",
            "driver_name": "ШАВКАТ",
            "driver_group": "BNYAN",
            "vehicle_name": "Газель",
            "revenue": Decimal("2434"),
            "driver_payment": Decimal("1045"),
            "fuel_cost": Decimal("0"),
            "maintenance_cost": Decimal("0"),
            "delivery_points": 0,
        },
        # === Азат: 4 точки × 2000 = 8 000 ₽ выплата ===
        # Выручка: 8 115 ₽ | Выплата: 8 000 ₽ (4 точки × 2000 ₽)
        # Маржа Азата: 8115 - 8000 = 115 ₽
        {
            "route_code": "ATEGO_МаршрутДС_10марта",
            "route_type": "darkstore",
            "driver_name": "АЗАТ",
            "driver_group": "AZAT",
            "vehicle_name": "Mercedes Atego",
            "revenue": Decimal("8115"),
            "driver_payment": Decimal("8000"),  # 4 точки × 2000 ₽
            "fuel_cost": Decimal("0"),
            "maintenance_cost": Decimal("0"),
            "delivery_points": 4,
            "notes": "Азат: 4 точки доставки × 2000 ₽. Mercedes Atego (собственный транспорт).",
        },
    ]

    created_routes = []
    total_revenue = Decimal("0")
    total_expenses = Decimal("0")

    for r in seed_routes:
        financials = calculate_financials(
            revenue=r["revenue"],
            driver_payment=r["driver_payment"],
            fuel_cost=r["fuel_cost"],
            maintenance_cost=r["maintenance_cost"],
        )
        route = LogisticsRoute(
            park_name=LOGISTICS_PARK,
            tenant_id=LOGISTICS_TENANT,
            date=march_10,
            route_code=r["route_code"],
            route_type=r["route_type"],
            driver_name=r["driver_name"],
            driver_group=r["driver_group"],
            vehicle_name=r.get("vehicle_name"),
            revenue=r["revenue"],
            driver_payment=r["driver_payment"],
            fuel_cost=r["fuel_cost"],
            maintenance_cost=r["maintenance_cost"],
            margin=financials["margin"],
            sglobal_share=financials["sglobal_share"],
            mkrtchan_share=financials["mkrtchan_share"],
            delivery_points=r.get("delivery_points", 0),
            status="completed",
            notes=r.get("notes"),
        )
        db.add(route)
        created_routes.append(route)
        total_revenue += r["revenue"]
        total_expenses += r["driver_payment"] + r["fuel_cost"] + r["maintenance_cost"]

    total_margin = total_revenue - total_expenses
    total_sglobal = (total_margin / Decimal("2")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total_mkrtchan = total_margin - total_sglobal

    # Финансовый лог для всего пакета
    await log_financial_operation(
        db=db,
        park_name=LOGISTICS_PARK,
        amount=Decimal(str(total_revenue)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        note=(
            f"SEED: Загрузка данных 10 марта 2025 | "
            f"Рейсов: {len(seed_routes)} | "
            f"Выручка: {total_revenue} ₽ | "
            f"Расходы: {total_expenses} ₽ | "
            f"Маржа: {total_margin} ₽ | "
            f"Доля С-ГЛОБАЛ: {total_sglobal} ₽ | "
            f"Доля Мкртчяна: {total_mkrtchan} ₽"
        ),
        entry_type="logistics_seed_march_10",
        meta={
            "date": "2025-03-10",
            "routes_count": len(seed_routes),
            "total_revenue": str(total_revenue),
            "total_expenses": str(total_expenses),
            "total_margin": str(total_margin),
            "sglobal_share": str(total_sglobal),
            "mkrtchan_share": str(total_mkrtchan),
        },
    )

    await db.commit()

    logger.info(
        f"🌱 [LOGISTICS SEED] 10 марта 2025 загружено: "
        f"{len(seed_routes)} рейсов | "
        f"Выручка: {total_revenue} ₽ | "
        f"Маржа: {total_margin} ₽ | "
        f"Доля Мкртчяна: {total_mkrtchan} ₽"
    )

    return {
        "status": "success",
        "message": f"Загружено {len(seed_routes)} рейсов за 10 марта 2025",
        "summary": {
            "date": "2025-03-10",
            "routes_count": len(seed_routes),
            "total_revenue": float(total_revenue),
            "total_expenses": float(total_expenses),
            "total_margin": float(total_margin),
            "sglobal_share": float(total_sglobal),
            "mkrtchan_share": float(total_mkrtchan),
        },
        "breakdown": {
            "darkstore_routes": 5,
            "store_routes": 5,
            "shmel_routes": 4,
            "zhuk_routes": 2,
            "azat_routes": 1,
        },
    }
