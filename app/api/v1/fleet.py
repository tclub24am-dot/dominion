# -*- coding: utf-8 -*-
# app/routes/fleet.py

import pandas as pd
import io
import logging
import re
import uuid
import asyncio
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, distinct, text
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta, date

from app.database import get_db
from app.core.config import settings
from app.models.all_models import (
    Vehicle,
    VehicleRepairHistory,
    User,
    OwnershipType,
    ContractTerm,
    ContractTermHistory,
    DriverProfile,
    Transaction,
)
from app.services.auth import get_current_user, hash_password
from app.services.security import get_current_user_from_cookie, get_current_user_optional
from app.core.permissions import has_module_access
from app.services.yandex_fleet import yandex_provider
from app.services.analytics_engine import AnalyticsEngine

# Попытка импорта уведомлений бота
try:
    from app.services.telegram_bot import send_master_msg
except ImportError:
    send_master_msg = None

logger = logging.getLogger("FleetModule")
router = APIRouter(tags=["ФЛОТ И СЕРВИС"])  # Prefix добавляется в main.py!
pages_router = APIRouter(tags=["Fleet Pages"])
templates = Jinja2Templates(directory="app/templates")

def _is_master(user: User) -> bool:
    role = getattr(user, "role", "")
    if hasattr(role, "value"):
        role = role.value
    return str(role).lower() == "master"

# =================================================================
# 1. СХЕМЫ ДАННЫХ (Schemas)
# =================================================================

class VehicleOut(BaseModel):
    id: int
    license_plate: str
    model: str
    brand: Optional[str] # Класс: economy, comfort, business
    ownership_type: OwnershipType
    daily_rent_price: float
    status: str

    class Config:
        from_attributes = True

class RepairLogSchema(BaseModel):
    license_plate: str
    description: str
    parts_cost: float
    labor_cost: float
    parts_list: Optional[list] = [] 

class ContractTermsUpdate(BaseModel):
    partner_daily_rent: Optional[float] = None
    driver_daily_rent: Optional[float] = None
    commission_rate: Optional[float] = None
    day_off_rate: Optional[float] = None
    is_repair: Optional[bool] = None
    is_day_off: Optional[bool] = None
    is_idle: Optional[bool] = None
    note: Optional[str] = None

class DriverCreatePayload(BaseModel):
    park_name: str
    first_name: str
    last_name: str
    middle_name: Optional[str] = None
    phone: str
    email: Optional[str] = None
    address: Optional[str] = None
    birth_date: str
    license_number: str
    license_issue_date: str
    license_expiry_date: str
    license_country: str = "rus"
    driver_license_experience_since: str
    tax_identification_number: Optional[str] = None
    employment_type: str  # selfemployed | park_employee | individual_entrepreneur
    profession: str = "taxi/driver"
    car_id: Optional[str] = None

class VehicleCreatePayload(BaseModel):
    park_name: str
    license_plate: str
    vin: str
    brand: str
    model: str
    year: int
    color: str
    sts_number: str
    callsign: Optional[str] = None
    ownership_type: str
    is_park_property: Optional[bool] = None
    ownership_type_external: Optional[str] = None  # park | leasing

def _normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")

def _normalize_plate(plate: str) -> str:
    return (plate or "").replace(" ", "").upper()

def _extract_car_number(user) -> Optional[str]:
    """Извлечь госномер из yandex_current_car JSONB если нет привязки через current_vehicle_id.
    EXORCISM v200.11: Поддержка ключей car_number, number, plate + fallback по car_id."""
    yc = getattr(user, "yandex_current_car", None)
    if not yc or not isinstance(yc, dict):
        return None
    # Прямой поиск по номеру
    plate = yc.get("car_number") or yc.get("number") or yc.get("plate")
    if plate:
        normalized = _normalize_plate(plate)
        if normalized and not normalized.startswith("UNKNOWN"):
            return normalized
    return None

def _validate_vin(vin: str) -> None:
    vin_clean = (vin or "").upper()
    if len(vin_clean) != 17 or not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin_clean):
        raise HTTPException(status_code=400, detail="VIN должен быть из 17 символов (латиница/цифры)")

def _validate_plate(plate: str) -> None:
    plate_clean = _normalize_plate(plate)
    if not plate_clean:
        raise HTTPException(status_code=400, detail="Госномер обязателен")
    if not re.fullmatch(r"[A-ZА-Я]{1}\d{3}[A-ZА-Я]{2}\d{2,3}", plate_clean):
        logger.warning("Plate format not standard: %s", plate_clean)

PARK_DEFAULTS = {
    "PRO": {"commission_rate": 0.04},
    "GO": {"commission_rate": 0.035},
    "PLUS": {"commission_rate": 0.03},
    "EXPRESS": {"commission_rate": 0.03},
}

def _moscow_iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S+03:00")

async def _ensure_default_terms(db: AsyncSession, park_name: str) -> ContractTerm:
    park = (park_name or "PRO").upper()
    stmt = select(ContractTerm).where(
        and_(ContractTerm.is_default == True, ContractTerm.park_name == park)
    )
    term = (await db.execute(stmt)).scalar_one_or_none()
    if term:
        return term
    defaults = PARK_DEFAULTS.get(park, PARK_DEFAULTS["PRO"])
    term = ContractTerm(
        park_name=park,
        is_default=True,
        partner_daily_rent=0.0,
        driver_daily_rent=0.0,
        commission_rate=defaults.get("commission_rate", 0.03),
        day_off_rate=0.0,
        is_repair=False,
        is_day_off=False,
        is_idle=False,
    )
    db.add(term)
    await db.commit()
    await db.refresh(term)
    return term

def _get_park_cfg(park_name: str) -> dict:
    park = (park_name or "PRO").upper()
    cfg = settings.PARKS.get(park, {})
    if not all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")]):
        raise HTTPException(status_code=400, detail=f"Нет ключей API для парка {park}")
    return cfg

def _yandex_recent_activity(profile: dict, hours: int = 48) -> bool:
    if not profile:
        return False
    keys = [
        "last_order_at",
        "last_order_date",
        "last_ride_at",
        "last_transaction_at",
        "last_activity_at",
    ]
    cutoff = datetime.now() - timedelta(hours=hours)
    for key in keys:
        value = profile.get(key) or (profile.get("profile") or {}).get(key)
        if not value:
            continue
        try:
            ts = datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            continue
        if ts >= cutoff:
            return True
    return False

def _extract_profile_ids(profile: dict) -> set:
    if not profile:
        return set()
    candidates = []
    for key in ["contractor_profile_id", "driver_profile_id", "id", "driver_id", "profile_id"]:
        value = profile.get(key)
        if value:
            candidates.append(str(value))
    for block_key in ["driver_profile", "profile", "contractor", "driver"]:
        block = profile.get(block_key) or {}
        if not isinstance(block, dict):
            continue
        for key in ["contractor_profile_id", "driver_profile_id", "id", "driver_id"]:
            value = block.get(key)
            if value:
                candidates.append(str(value))
    return set(candidates)

def _ensure_fleet_access(user: User) -> None:
    if not has_module_access(user, "fleet"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Модуль отключен, нет доступа по роли или истек пробный период. Продлите Золотую Лицензию.",
        )

# =================================================================
# PAGES: Реестр и профили
# =================================================================

@pages_router.get("/fleet/drivers", response_class=HTMLResponse)
async def fleet_drivers_registry(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    if current_user:
        _ensure_fleet_access(current_user)
    elif not settings.YANDEX_ALLOW_SYNC_NOAUTH:
        raise HTTPException(status_code=403, detail="Требуется авторизация")
    parks = ["PRO", "GO", "PLUS", "EXPRESS"]
    yandex_failed = False

    # ─── ТРОЙНАЯ ЛОГИКА СЧЁТЧИКОВ v200.11 ───────────────────────
    # 1) Всего: Все водители со статусом working
    total_working_stmt = select(func.count(User.id)).where(
        and_(
            User.is_active == True,
            User.is_archived == False,
            or_(
                User.yandex_driver_id.isnot(None),
                User.yandex_contractor_id.isnot(None),
            ),
            or_(
                User.work_status == "working",
                User.yandex_work_status == "working",
            ),
        )
    )
    total_working = (await db.execute(total_working_stmt)).scalar() or 0

    # 2) Активные 30д: Уникальные водители с транзакциями за 30 дней
    cutoff_30d = datetime.now() - timedelta(days=30)
    active_30d_stmt = select(func.count(distinct(Transaction.yandex_driver_id))).where(
        and_(
            Transaction.yandex_driver_id.isnot(None),
            Transaction.date >= cutoff_30d,
        )
    )
    active_30d = (await db.execute(active_30d_stmt)).scalar() or 0

    # 3) Дневная активность: Уникальные водители с транзакциями СЕГОДНЯ
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    daily_active_stmt = select(func.count(distinct(Transaction.yandex_driver_id))).where(
        and_(
            Transaction.yandex_driver_id.isnot(None),
            Transaction.date >= today_start,
        )
    )
    daily_active = (await db.execute(daily_active_stmt)).scalar() or 0

    # ─── ОСНОВНОЙ ЗАПРОС: Все working водители ───────────────────
    stmt = (
        select(User, Vehicle.license_plate)
        .outerjoin(Vehicle, Vehicle.id == User.current_vehicle_id)
        .where(
            and_(
                User.is_active == True,
                User.is_archived == False,
                or_(
                    User.yandex_driver_id.isnot(None),
                    User.yandex_contractor_id.isnot(None),
                ),
                or_(
                    User.work_status == "working",
                    User.yandex_work_status == "working",
                ),
            )
        )
        .order_by(User.full_name)
    )

    rows = (await db.execute(stmt)).all()
    drivers = []
    park_counts = {park: 0 for park in parks}

    # ─── АВТОПРИВЯЗКА АВТО: yandex_current_car → vehicles ────────
    car_fix_count = 0
    for user, plate in rows:
        park = (user.park_name or "PRO").upper()
        if park in park_counts:
            park_counts[park] += 1

        # Автоматическая привязка через yandex_current_car
        effective_plate = plate
        if not plate and user.yandex_current_car:
            yandex_car = user.yandex_current_car if isinstance(user.yandex_current_car, dict) else {}
            yx_car_id = yandex_car.get("car_id") or yandex_car.get("id")
            yx_car_number = yandex_car.get("car_number") or yandex_car.get("number")

            if yx_car_id or yx_car_number:
                # Ищем по yandex_car_id или по госномеру
                v_stmt = select(Vehicle)
                if yx_car_id:
                    v_stmt = v_stmt.where(
                        and_(Vehicle.yandex_car_id == yx_car_id, Vehicle.park_name == park)
                    )
                elif yx_car_number:
                    v_stmt = v_stmt.where(
                        Vehicle.license_plate == _normalize_plate(yx_car_number)
                    )
                found_vehicle = (await db.execute(v_stmt)).scalar_one_or_none()
                if found_vehicle:
                    user.current_vehicle_id = found_vehicle.id
                    effective_plate = found_vehicle.license_plate
                    car_fix_count += 1
                elif yx_car_number:
                    effective_plate = yx_car_number

        drivers.append(
            {
                "id": user.id,
                "full_name": user.full_name or "—",
                "phone": user.username or "—",
                "park_name": park,
                "balance": float(user.driver_balance or 0.0),
                "last_active_at": user.last_active_at.isoformat() if user.last_active_at else None,
                "vehicle_plate": effective_plate,
                "yandex_driver_id": user.yandex_driver_id,
                "yandex_contractor_id": user.yandex_contractor_id,
                "work_status": user.yandex_work_status or user.work_status or "not_working",
            }
        )

    if car_fix_count > 0:
        try:
            await db.commit()
            logger.info(f"Автопривязка: обновлено {car_fix_count} связей водитель → авто")
        except Exception as e:
            logger.warning(f"Автопривязка — ошибка commit: {e}")
            await db.rollback()

    return templates.TemplateResponse(
        "modules/drivers_registry.html",
        {
            "request": request,
            "current_user": current_user,
            "drivers": drivers,
            "parks": parks,
            "park_counts": park_counts,
            "yandex_failed": yandex_failed,
            "total_working": total_working,
            "active_30d": active_30d,
            "daily_active": daily_active,
        },
    )


@pages_router.get("/fleet/driver/{driver_id}", response_class=HTMLResponse)
async def fleet_driver_page(
    driver_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_cookie),
):
    _ensure_fleet_access(current_user)
    from app.services.yandex_sync_service import yandex_sync

    user = await db.get(User, driver_id)
    if not user:
        raise HTTPException(status_code=404, detail="Водитель не найден")

    contractor_id = user.yandex_contractor_id or user.yandex_driver_id
    yandex_profile = {}
    if contractor_id:
        try:
            yandex_profile = await yandex_sync.fetch_driver_profile(user.park_name or "PRO", str(contractor_id))
        except Exception:
            yandex_profile = {}

    # ─── АВТОПРИВЯЗКА АВТО в профиле ─────────────────────────────
    vehicle = None
    if user.current_vehicle_id:
        vehicle = await db.get(Vehicle, user.current_vehicle_id)

    # Если нет привязки — ищем через yandex_current_car
    if not vehicle and user.yandex_current_car:
        yandex_car = user.yandex_current_car if isinstance(user.yandex_current_car, dict) else {}
        yx_car_id = yandex_car.get("car_id") or yandex_car.get("id")
        yx_car_number = yandex_car.get("car_number") or yandex_car.get("number")
        park = (user.park_name or "PRO").upper()
        if yx_car_id:
            v_stmt = select(Vehicle).where(
                and_(Vehicle.yandex_car_id == yx_car_id, Vehicle.park_name == park)
            )
            vehicle = (await db.execute(v_stmt)).scalar_one_or_none()
        if not vehicle and yx_car_number:
            v_stmt = select(Vehicle).where(
                Vehicle.license_plate == _normalize_plate(yx_car_number)
            )
            vehicle = (await db.execute(v_stmt)).scalar_one_or_none()
        if vehicle:
            user.current_vehicle_id = vehicle.id
            try:
                await db.commit()
            except Exception:
                await db.rollback()

    reserve_stmt = select(Vehicle).where(
        and_(Vehicle.is_free == True, Vehicle.park_name == (user.park_name or "PRO").upper())
    ).order_by(Vehicle.license_plate)
    reserve_vehicles = (await db.execute(reserve_stmt)).scalars().all()

    # ─── ТРАНЗАКЦИИ: 10 последних из таблицы transactions ────────
    driver_ids = [user.yandex_driver_id]
    if user.yandex_contractor_id:
        driver_ids.append(user.yandex_contractor_id)
    driver_ids = [d for d in driver_ids if d]
    
    transactions = []
    if driver_ids:
        tx_stmt = select(Transaction).where(
            Transaction.yandex_driver_id.in_(driver_ids)
        ).order_by(Transaction.date.desc()).limit(10)
        transactions = (await db.execute(tx_stmt)).scalars().all()
    
    # Фоллбэк: FinancialLog по driver_id (исправлен баг user_id → driver_id)
    financial_logs = []
    if not transactions:
        from app.models.all_models import FinancialLog
        fl_stmt = select(FinancialLog).where(
            FinancialLog.driver_id == user.id
        ).order_by(FinancialLog.created_at.desc()).limit(10)
        financial_logs = (await db.execute(fl_stmt)).scalars().all()

    return templates.TemplateResponse(
        "modules/driver_profile.html",
        {
            "request": request,
            "current_user": current_user,
            "driver": user,
            "vehicle": vehicle,
            "yandex_profile": yandex_profile,
            "transactions": transactions,
            "financial_logs": financial_logs,
            "reserve_vehicles": reserve_vehicles,
            "today": date.today(),  # v35.1: для расчёта срока ВУ
        },
    )


@pages_router.get("/fleet/vehicle/{vehicle_id}", response_class=HTMLResponse)
async def fleet_vehicle_page(
    vehicle_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_cookie),
):
    _ensure_fleet_access(current_user)
    vehicle = await db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Автомобиль не найден")

    repairs_stmt = select(VehicleRepairHistory).where(
        VehicleRepairHistory.vehicle_id == vehicle.id
    ).order_by(VehicleRepairHistory.created_at.desc())
    repairs = (await db.execute(repairs_stmt)).scalars().all()

    plate = (vehicle.license_plate or "").upper()
    history_stmt = (
        select(
            Transaction.yandex_driver_id,
            func.max(Transaction.date),
        )
        .where(
            and_(
                Transaction.yandex_driver_id.isnot(None),
                or_(
                    Transaction.plate_info == plate,
                    Transaction.description.ilike(f"%{plate}%"),
                ),
            )
        )
        .group_by(Transaction.yandex_driver_id)
        .order_by(func.max(Transaction.date).desc())
        .limit(10)
    )
    driver_rows = (await db.execute(history_stmt)).all()
    driver_ids = [row[0] for row in driver_rows if row[0]]
    users_stmt = select(User).where(
        or_(
            User.yandex_driver_id.in_(driver_ids),
            User.yandex_contractor_id.in_(driver_ids),
        )
    )
    users = {u.yandex_driver_id or u.yandex_contractor_id: u for u in (await db.execute(users_stmt)).scalars().all()}
    driver_history = [
        {"driver_id": driver_id, "last_seen": last_seen, "driver": users.get(driver_id)}
        for driver_id, last_seen in driver_rows
    ]

    return templates.TemplateResponse(
        "modules/vehicle_profile.html",
        {
            "request": request,
            "current_user": current_user,
            "vehicle": vehicle,
            "repairs": repairs,
            "driver_history": driver_history,
        },
    )

# =================================================================
# 1.5. СИНХРОНИЗАЦИЯ ДОКУМЕНТОВ И РЕЙТИНГА ВОДИТЕЛЕЙ
# =================================================================

async def _run_sync_documents(background_tasks: BackgroundTasks, current_user: User):
    """Общая логика синхронизации документов для GET и POST."""
    if not _is_master(current_user):
        raise HTTPException(status_code=403, detail="Только Мастер может запустить Deep Sync")

    async def _sync_docs_background():
        from app.services.yandex_sync_service import yandex_sync
        from app.database import async_session_factory
        
        async with async_session_factory() as session:
            # v35.2: Берём АКТИВНЫХ водителей = последний заказ ≤ 30 дней
            # Категории доходных транзакций (поездки)
            _rev_cats = [
                "Оплата картой", "Наличные", "Корпоративная оплата",
                "Оплата через терминал", "Оплата электронным кошельком",
                "Оплата промокодом", "Компенсация оплаты поездки",
                "Оплата картой, поездка партнёра", "Наличные, поездка партнёра",
            ]
            since_30d = datetime.now() - timedelta(days=30)
            
            # Subquery: водители с заказами за последние 30 дней
            active_drivers_sub = (
                select(Transaction.yandex_driver_id)
                .where(
                    Transaction.amount > 0,
                    Transaction.category.in_(_rev_cats),
                    Transaction.date >= since_30d,
                )
                .group_by(Transaction.yandex_driver_id)
            ).subquery()
            
            stmt = (
                select(User)
                .where(
                    and_(
                        User.is_active == True,
                        User.is_archived == False,
                        or_(
                            User.yandex_contractor_id.isnot(None),
                            User.yandex_driver_id.isnot(None),
                        ),
                        or_(
                            User.yandex_driver_id.in_(select(active_drivers_sub.c.yandex_driver_id)),
                            User.yandex_contractor_id.in_(select(active_drivers_sub.c.yandex_driver_id)),
                        ),
                    )
                )
            )
            drivers = (await session.execute(stmt)).scalars().all()
            updated = 0
            errors = 0

            for driver in drivers:
                try:
                    park = (driver.park_name or "PRO").upper()
                    cid = driver.yandex_contractor_id or driver.yandex_driver_id
                    if not cid:
                        continue
                    
                    profile = await yandex_sync.fetch_driver_profile(park, str(cid))
                    if not profile:
                        continue

                    # Извлекаем данные ВУ
                    dp = profile.get("driver_profile") or profile.get("profile") or profile
                    dl = dp.get("driver_license") or {}
                    
                    if dl.get("number") and not driver.license_number:
                        driver.license_number = dl["number"]
                    if dl.get("expiry_date") and not driver.license_expiry_date:
                        try:
                            driver.license_expiry_date = date.fromisoformat(dl["expiry_date"][:10])
                        except Exception:
                            pass
                    if dl.get("issue_date") and not driver.license_issue_date:
                        try:
                            driver.license_issue_date = date.fromisoformat(dl["issue_date"][:10])
                        except Exception:
                            pass
                    if dl.get("country") and not driver.license_country:
                        driver.license_country = dl["country"]
                    if dl.get("experience") and not driver.driving_experience_from:
                        try:
                            exp = dl.get("experience", {})
                            if isinstance(exp, dict) and exp.get("since"):
                                driver.driving_experience_from = date.fromisoformat(exp["since"][:10])
                            elif isinstance(exp, str):
                                driver.driving_experience_from = date.fromisoformat(exp[:10])
                        except Exception:
                            pass

                    # Рейтинг
                    rating = dp.get("rating") or profile.get("rating")
                    if rating:
                        try:
                            driver.yandex_rating = float(rating)
                        except Exception:
                            pass

                    # Привязка авто
                    car_info = profile.get("car") or dp.get("car") or {}
                    if car_info:
                        car_id = car_info.get("id")
                        car_number = car_info.get("number")
                        yandex_car_data = {}
                        if car_id:
                            yandex_car_data["car_id"] = car_id
                        if car_number:
                            yandex_car_data["car_number"] = car_number
                        if yandex_car_data:
                            driver.yandex_current_car = yandex_car_data

                    driver.yandex_last_sync_at = datetime.now()
                    updated += 1
                except Exception as e:
                    errors += 1
                    logger.warning(f"Sync docs error for driver {driver.id}: {e}")
                
                # Rate limit: 100ms между запросами
                await asyncio.sleep(0.1)

            try:
                await session.commit()
                logger.info(f"Deep Sync Documents: обновлено {updated}, ошибок {errors}")
            except Exception as e:
                await session.rollback()
                logger.error(f"Deep Sync Documents commit error: {e}")

    background_tasks.add_task(_sync_docs_background)
    return JSONResponse({"status": "started", "message": "Синхронизация документов запущена в фоне"})


@router.get("/drivers/sync-documents")
async def sync_driver_documents_get(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    return await _run_sync_documents(background_tasks, current_user)


@router.post("/drivers/sync-documents")
async def sync_driver_documents_post(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    return await _run_sync_documents(background_tasks, current_user)


# Дублирование на pages_router для доступа без require_module
@pages_router.get("/fleet/sync-documents")
async def sync_driver_documents_page(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user_from_cookie),
):
    return await _run_sync_documents(background_tasks, current_user)


async def _run_sync_cars(background_tasks: BackgroundTasks, current_user: User):
    """Общая логика привязки авто для GET и POST."""
    if not _is_master(current_user):
        raise HTTPException(status_code=403, detail="Только Мастер может запустить привязку авто")

    async def _sync_cars_background():
        from app.database import async_session_factory
        
        async with async_session_factory() as session:
            stmt = select(User).where(
                and_(
                    User.is_active == True,
                    User.is_archived == False,
                    User.current_vehicle_id.is_(None),
                    User.yandex_current_car.isnot(None),
                )
            )
            drivers = (await session.execute(stmt)).scalars().all()
            linked = 0

            for driver in drivers:
                yandex_car = driver.yandex_current_car if isinstance(driver.yandex_current_car, dict) else {}
                yx_car_id = yandex_car.get("car_id") or yandex_car.get("id")
                yx_car_number = yandex_car.get("car_number") or yandex_car.get("number")
                park = (driver.park_name or "PRO").upper()

                vehicle = None
                if yx_car_id:
                    v_stmt = select(Vehicle).where(
                        and_(Vehicle.yandex_car_id == yx_car_id, Vehicle.park_name == park)
                    )
                    vehicle = (await session.execute(v_stmt)).scalar_one_or_none()
                if not vehicle and yx_car_number:
                    v_stmt = select(Vehicle).where(
                        Vehicle.license_plate == _normalize_plate(yx_car_number)
                    )
                    vehicle = (await session.execute(v_stmt)).scalar_one_or_none()
                if vehicle:
                    driver.current_vehicle_id = vehicle.id
                    linked += 1

            try:
                await session.commit()
                logger.info(f"Тотальная привязка авто: связано {linked} водителей")
            except Exception as e:
                await session.rollback()
                logger.error(f"Привязка авто commit error: {e}")

    background_tasks.add_task(_sync_cars_background)
    return JSONResponse({"status": "started", "message": "Привязка авто запущена в фоне"})


@router.get("/drivers/sync-cars")
async def sync_driver_cars_get(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    return await _run_sync_cars(background_tasks, current_user)


@router.post("/drivers/sync-cars")
async def sync_driver_cars_post(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    return await _run_sync_cars(background_tasks, current_user)


# Дублирование на pages_router для доступа без require_module
@pages_router.get("/fleet/sync-cars")
async def sync_driver_cars_page(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user_from_cookie),
):
    return await _run_sync_cars(background_tasks, current_user)


# =================================================================
# 2. МЕНЕДЖМЕНТ ТРАНСПОРТА
# =================================================================

@router.get("/vehicles/active")
async def get_active_vehicles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Список всех боевых единиц (42 субаренда + 78 подключки + 5т)
    
    Возвращает: HTML карточки для HTMX загрузки (v22.6 FINAL)
    """
    try:
        # Проверка прав доступа
        if not current_user.can_see_fleet and current_user.role.lower() != "master":
            from fastapi.responses import HTMLResponse
            return HTMLResponse(
                content='<div style="padding: 40px; text-align: center; color: #ff5252;">⛔ Доступ к Флоту закрыт Мастером</div>',
                status_code=200
            )
        
        from fastapi.responses import HTMLResponse
        
        # Получаем машины
        result = await db.execute(select(Vehicle).order_by(Vehicle.license_plate))
        vehicles = result.scalars().all()
        
        logger.info(f"✓ Fleet query: found {len(vehicles)} vehicles")
        
        if len(vehicles) == 0:
            return HTMLResponse(
                content='<div style="padding: 40px; text-align: center; color: var(--text-muted);">📭 Автопарк пуст</div>',
                status_code=200
            )
        
        # Генерируем HTML карточки
        html_cards = ""
        
        for v in vehicles:
            try:
                # Безопасное определение статуса
                status = str(v.status) if v.status else "unknown"
                status_class = "status-working" if status == "working" else "status-service" if status in ["maintenance", "service"] else "status-offline"
                status_text = "На линии" if status == "working" else "Сервис" if status in ["maintenance", "service"] else "Оффлайн"
                
                # ПРОВЕРКА TENSION INDEX для водителя (v22.6 FINAL)
                card_class = "vehicle-card"
                try:
                    # Если у машины есть водитель - проверяем его Tension
                    from app.models.all_models import DriverTensionHistory
                    # Упрощённая проверка без дополнительного запроса
                    # В продакшене можно добавить джойн или кэш
                    card_class = "vehicle-card"  # По умолчанию
                except:
                    card_class = "vehicle-card"
                
                # Безопасное определение типа владения
                ownership_type = str(v.ownership_type.value) if hasattr(v.ownership_type, 'value') else str(v.ownership_type)
                if ownership_type == "sublease" or "SUBLEASE" in ownership_type:
                    ownership = "Субаренда"
                elif ownership_type == "connected" or "CONNECTED" in ownership_type:
                    ownership = "Подключка"
                else:
                    ownership = "Собственная"
                
                # Безопасное форматирование
                brand = str(v.brand) if v.brand else ""
                model = str(v.model) if v.model else "Неизвестная"
                plate = str(v.license_plate) if v.license_plate else "N/A"
                mileage = int(v.current_mileage) if v.current_mileage else 0
                year = str(v.year) if hasattr(v, 'year') and v.year else "N/A"
                
                html_cards += f'''
        <div class="{card_class}" data-filter="{ownership_type}">
            <div class="vehicle-header">
                <span class="vehicle-plate">{plate}</span>
                <span class="vehicle-status {status_class}">{status_text}</span>
            </div>
            <div class="vehicle-model">{brand} {model}</div>
            <div class="vehicle-type">{ownership} • {brand if brand else 'N/A'}</div>
            <div class="vehicle-stats">
                <div class="stat-item">
                    <div class="stat-value">{mileage:,} км</div>
                    <div class="stat-label">Пробег</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">{year}</div>
                    <div class="stat-label">Год</div>
                </div>
            </div>
            <div class="vehicle-actions">
                <button class="btn-manage" onclick="openVehicleModal({v.id})">
                    <i class="fa-solid fa-sliders"></i> Управление
                </button>
                <button class="btn-secondary" onclick="window.location.href='/logbook'">
                    <i class="fa-solid fa-file-lines"></i>
                </button>
            </div>
        </div>
        '''
            except Exception as card_error:
                logger.error(f"Error generating card for vehicle {v.id}: {card_error}")
                continue
        
        logger.info(f"✓ Fleet loaded: {len(vehicles)} vehicles, generated {len(html_cards)} chars of HTML")
        
        return HTMLResponse(content=html_cards, status_code=200)
        
    except Exception as e:
        logger.error(f"Fleet vehicles/active error: {e}", exc_info=True)
        from fastapi.responses import HTMLResponse
        return HTMLResponse(
            content=f'<div style="padding: 40px; text-align: center; color: #ff5252;">⚠️ Ошибка загрузки автопарка: {str(e)}</div>',
            status_code=200
        )

@router.get("/command-data")
async def get_fleet_command_data(
    show_archive: bool = False,  # True = показать все машины (включая неактивные)
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Данные для Command Dashboard.
    По умолчанию: только "Живые 300" (is_active_dominion=True).
    ?show_archive=true: все машины для вкладки АРХИВ.
    """
    if not current_user.can_see_fleet and current_user.role.lower() != "master":
        return JSONResponse(
            status_code=403,
            content={"status": "forbidden"}
        )
    data = await AnalyticsEngine.get_fleet_command_data(db, include_all=show_archive)
    driver_id_expr = func.coalesce(User.yandex_driver_id, User.yandex_contractor_id)
    on_line_stmt = (
        select(func.count(distinct(driver_id_expr)))
        .select_from(Vehicle)
        .join(User, Vehicle.current_driver_id == User.id)
        .where(
            and_(
                Vehicle.status == "working",
                Vehicle.current_driver_id.isnot(None),
                driver_id_expr.isnot(None),
            )
        )
    )
    drivers_on_line = (await db.execute(on_line_stmt)).scalar() or 0
    data["drivers_on_line"] = int(drivers_on_line)

    # ── PARK CAR COUNTS (is_park_car=True) ── реальные данные для кнопок PRO/GO/PLUS ──
    park_car_stmt = (
        select(Vehicle.park_name, func.count(Vehicle.id))
        .where(
            and_(
                Vehicle.is_active == True,
                Vehicle.is_park_car == True,
            )
        )
        .group_by(Vehicle.park_name)
    )
    park_car_rows = (await db.execute(park_car_stmt)).all()
    park_car_counts = {row[0]: row[1] for row in park_car_rows if row[0]}
    # Гарантируем ключи PRO/GO/PLUS/EXPRESS даже если 0
    for p in ("PRO", "GO", "PLUS", "EXPRESS"):
        park_car_counts.setdefault(p, 0)
    data["park_car_counts"] = park_car_counts

    return JSONResponse(content=data)

    # triad-data перенесён на pages_router (без require_module), см. ниже


@router.post("/driver/{driver_id}/photo")
async def upload_driver_photo(
    driver_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not _is_master(current_user):
        raise HTTPException(status_code=403, detail="Только Мастер может загружать фото")
    driver = await db.get(User, driver_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Водитель не найден")
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Разрешены только изображения")
    ext = Path(file.filename or "").suffix.lower() or ".jpg"
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        raise HTTPException(status_code=400, detail="Неподдерживаемый формат")
    storage_dir = Path("/root/dominion/storage/drivers")
    storage_dir.mkdir(parents=True, exist_ok=True)
    filename = f"driver_{driver_id}_{uuid.uuid4().hex}{ext}"
    file_path = storage_dir / filename
    contents = await file.read()
    with open(file_path, "wb") as f:
        f.write(contents)
    driver.photo_url = f"/storage/drivers/{filename}"
    await db.commit()
    return {"status": "ok", "photo_url": driver.photo_url}

@router.post("/upload-vehicles")
async def upload_vehicles(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Массовая загрузка машин.
    Ожидаемые колонки: license_plate, model, brand, vin, ownership_type, daily_rent
    """
    if not _is_master(current_user):
        raise HTTPException(status_code=403, detail="Только Мастер может расширять Флот")

    contents = await file.read()
    try:
        if file.filename.endswith('.xlsx'):
            df = pd.read_excel(io.BytesIO(contents))
        else:
            df = pd.read_csv(io.BytesIO(contents), sep=None, engine='python', encoding='cp1251')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Ошибка файла: {e}")

    imported = 0
    for _, row in df.iterrows():
        plate = str(row['license_plate']).upper().strip()

        # Проверка на дубликат
        exist = await db.execute(select(Vehicle).where(Vehicle.license_plate == plate))
        if exist.scalar_one_or_none():
            continue

        # Логика определения типа владения
        raw_type = str(row.get('ownership_type', 'connected')).lower()
        v_type = OwnershipType.SUBLEASE if 'sub' in raw_type else OwnershipType.CONNECTED
        if '5t' in raw_type:
            v_type = OwnershipType.OWNED_5T

        v = Vehicle(
            license_plate=plate,
            model=row.get('model', 'Unknown'),
            brand=row.get('brand', 'economy'),
            vin=row.get('vin', ''),
            ownership_type=v_type,
            daily_rent_price=float(row.get('daily_rent', 450.0)),
            status='working'
        )
        db.add(v)
        imported += 1

    await db.commit()
    return {"status": "success", "imported_vehicles": imported}

# =================================================================
# 3. МЕНЕДЖМЕНТ ВОДИТЕЛЕЙ
# =================================================================

@router.post("/upload-drivers")
async def upload_drivers(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Массовая загрузка водителей (full_name, phone)"""
    if not _is_master(current_user):
        raise HTTPException(status_code=403, detail="Только Мастер может нанимать воинов")

    contents = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(contents), sep=None, engine='python', encoding='cp1251')
    except:
        df = pd.read_csv(io.BytesIO(contents), sep=None, engine='python', encoding='utf-8')

    imported = 0
    for _, row in df.iterrows():
        phone = str(row['phone']).replace(".0", "").replace("+", "").strip()
        name = str(row['full_name']).strip()

        exist = await db.execute(select(User).where(User.username == phone))
        if exist.scalar_one_or_none():
            continue

        new_driver = User(
            username=phone,
            full_name=name,
            hashed_password=hash_password("driver123"),
            role="Driver",
            can_see_fleet=True
        )
        db.add(new_driver)
        imported += 1

    await db.commit()
    return {"status": "success", "imported_drivers": imported}

# =================================================================
# 4. СЕРВИС И РЕМОНТ
# =================================================================

@router.post("/repair-log")
async def create_repair_log(
    log: RepairLogSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Фиксация ремонта и уведомление Мастера"""
    if not current_user.can_see_fleet and current_user.role.lower() != "master":
        raise HTTPException(status_code=403, detail="Нет прав на запись сервиса")

    res = await db.execute(select(Vehicle).where(Vehicle.license_plate == log.license_plate))
    vehicle = res.scalar_one_or_none()
    
    if not vehicle:
        raise HTTPException(status_code=404, detail="Машина не найдена")

    total_cost = log.parts_cost + log.labor_cost

    new_repair = VehicleRepairHistory(
        vehicle_id=vehicle.id,
        description=log.description,
        repair_cost=total_cost,
        parts_json=log.parts_list,
        status="completed",
        created_at=datetime.utcnow()
    )
    
    db.add(new_repair)
    vehicle.status = 'working' # Возвращаем в строй
    
    await db.commit()
    
    # ГОЛОС ЦИТАДЕЛИ
    if send_master_msg:
        try:
            await send_master_msg(
                f"🔧 <b>РЕМОНТ ЗАВЕРШЕН</b>\n"
                f"🚗 Авто: <code>{vehicle.license_plate}</code>\n"
                f"🛠 Описание: {log.description}\n"
                f"💰 Итого: <b>{total_cost:,.2f} ₽</b>"
            )
        except Exception as e:
            logger.error(f"TG Notify Error: {e}")
    
    return {"repair_id": new_repair.id, "status": "success"}

# =================================================================
# 5. GARAGE v30.1 - ПРОФЕССИОНАЛЬНАЯ ТАБЛИЦА ФЛОТА
# =================================================================

@router.get("/vehicles/table")
async def get_vehicles_table(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Таблица автопарка (HTML для Garage v30.1)
    """
    try:
        from fastapi.responses import HTMLResponse
        from fastapi.templating import Jinja2Templates
        from fastapi import Request
        from sqlalchemy import func, and_
        from datetime import timedelta
        
        templates = Jinja2Templates(directory="app/templates")
        
        # Получаем все активные машины
        stmt = select(Vehicle).where(Vehicle.is_active == True).order_by(Vehicle.license_plate)
        result = await db.execute(stmt)
        vehicles = result.scalars().all()
        
        # Для каждой машины считаем профит за месяц
        vehicles_data = []
        
        for vehicle in vehicles:
            # Считаем доход и расход за 30 дней
            month_ago = datetime.now() - timedelta(days=30)
            
            from app.models.all_models import Transaction
            
            # Доход машины (по госномеру в описании)
            income_stmt = select(func.sum(Transaction.amount)).where(
                and_(
                    Transaction.amount > 0,
                    Transaction.description.like(f"%{vehicle.license_plate}%"),
                    Transaction.date >= month_ago.date()
                )
            )
            income_result = await db.execute(income_stmt)
            income = float(income_result.scalar() or 0)
            
            # Расход на ремонт
            repair_stmt = select(func.sum(VehicleRepairHistory.repair_cost)).where(
                and_(
                    VehicleRepairHistory.vehicle_id == vehicle.id,
                    VehicleRepairHistory.created_at >= month_ago
                )
            )
            repair_result = await db.execute(repair_stmt)
            repair_cost = float(repair_result.scalar() or 0)
            
            # Профит = Доход - Расход на ремонт
            profit = income - repair_cost
            
            vehicles_data.append({
                "id": vehicle.id,
                "license_plate": vehicle.license_plate,
                "brand": vehicle.brand or "—",
                "model": vehicle.model or "—",
                "year": vehicle.year or "—",
                "color": vehicle.color or "—",
                "vin": vehicle.vin or "—",
                "sts_number": vehicle.sts_number or "—",
                "callsign": vehicle.callsign or "—",
                "status": vehicle.status,
                "ownership_type": vehicle.ownership_type.value if vehicle.ownership_type else "connected",
                "profit_month": round(profit, 2)
            })
        
        logger.info(f"✓ Fleet table: {len(vehicles_data)} vehicles")
        
        # Возвращаем HTML строки
        html_rows = []
        for v in vehicles_data:
            status_class = {
                "working": "status-working",
                "service": "status-service",
                "preparing": "status-preparing",
                "debt_lock": "status-offline",
                "offline": "status-offline"
            }.get(v["status"], "status-offline")
            
            status_text = {
                "working": "Работает",
                "service": "Сервис",
                "preparing": "Подготовка",
                "debt_lock": "Заблокирован",
                "offline": "Не работает"
            }.get(v["status"], "—")
            
            ownership_text = {
                "sublease": "Субаренда (4% + 450₽)",
                "connected": "Подключенная (3%)",
                "owned_5t": "Собственная (5т)",
                "partner": "Партнёрская"
            }.get(v["ownership_type"], "Подключенная")
            
            profit_class = "profit-positive" if v["profit_month"] >= 0 else "profit-negative"
            
            html_rows.append(f"""
                <tr data-vehicle-id="{v['id']}">
                    <td style="text-align: center;">
                        <i class="fa-solid fa-car" style="color: var(--gold-dark); font-size: 16px;"></i>
                    </td>
                    <td>
                        <div class="vehicle-name luxury-text-contrast">{v['brand']} {v['model']}</div>
                        <div class="vehicle-plate">{v['license_plate']}</div>
                        <div style="font-size: 10px; color: var(--text-muted); margin-top: 2px;">{v['year']} • {v['color']}</div>
                    </td>
                    <td>
                        <span class="status-badge {status_class}">{status_text}</span>
                    </td>
                    <td>
                        <div class="vehicle-callsign luxury-text-contrast">{v['callsign']}</div>
                    </td>
                    <td>
                        <div class="vin-text luxury-text-contrast">{v['sts_number']}</div>
                    </td>
                    <td>
                        <div class="vin-text luxury-text-contrast" style="font-size:12px;font-family:monospace;word-break:break-all;">{v['vin']}</div>
                    </td>
                    <td>
                        <div style="font-size: 12px; color: var(--text-secondary);">Таксопарк</div>
                    </td>
                    <td>
                        <div style="font-size: 11px; color: var(--text-secondary);">{ownership_text}</div>
                    </td>
                    <td style="text-align: right;">
                        <div class="profit-cell {profit_class}">{v['profit_month']:+,.0f}₽</div>
                    </td>
                </tr>
            """)
        
        return HTMLResponse(content=''.join(html_rows), status_code=200)
        
    except Exception as e:
        logger.error(f"Fleet table error: {e}", exc_info=True)
        return HTMLResponse(
            content=f'<tr><td colspan="9" style="padding: 20px; color: #ff5252; text-align: center;">⚠️ Ошибка загрузки: {str(e)}</td></tr>',
            status_code=200
        )

@router.get("/vehicles/list")
async def get_vehicles_list_json(
    show_archive: bool = False,  # True = показать все машины (архив)
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Список автопарка (JSON для Alpine.js) v30.1 + PROTOCOL "THE LIVE 300"
    
    По умолчанию показывает только "Живые" борты (is_active_dominion=True).
    Для просмотра всех машин: ?show_archive=true
    """
    try:
        from app.models.all_models import Transaction
        
        # PROTOCOL "THE LIVE 300": Фильтрация по is_active_dominion
        if show_archive:
            # Архив: все машины
            where_clause = Vehicle.is_active == True
        else:
            # Боевой режим: только "Живые 300"
            where_clause = and_(
                Vehicle.is_active == True,
                Vehicle.is_active_dominion == True
            )
        
        stmt = (
            select(Vehicle, User)
            .outerjoin(User, Vehicle.current_driver_id == User.id)
            .where(where_clause)
            .order_by(Vehicle.license_plate)
        )
        result = await db.execute(stmt)
        rows = result.all()
        
        # Счётчики для UI
        total_count = (await db.execute(
            select(func.count(Vehicle.id)).where(Vehicle.is_active == True)
        )).scalar() or 0
        active_count = (await db.execute(
            select(func.count(Vehicle.id)).where(
                and_(Vehicle.is_active == True, Vehicle.is_active_dominion == True)
            )
        )).scalar() or 0
        
        # Для каждой машины считаем профит
        vehicles_data = []
        month_ago = datetime.now() - timedelta(days=30)
        
        for v, driver in rows:
            # Доход за месяц
            income_stmt = select(func.sum(Transaction.amount)).where(
                and_(
                    Transaction.amount > 0,
                    Transaction.description.like(f"%{v.license_plate}%"),
                    Transaction.date >= month_ago.date()
                )
            )
            income_result = await db.execute(income_stmt)
            income = float(income_result.scalar() or 0)
            
            # Расходы по транзакциям (штрафы/прочее)
            expense_stmt = select(func.sum(Transaction.amount)).where(
                and_(
                    Transaction.amount < 0,
                    Transaction.description.like(f"%{v.license_plate}%"),
                    Transaction.date >= month_ago.date()
                )
            )
            expense_result = await db.execute(expense_stmt)
            expense = float(expense_result.scalar() or 0)  # отрицательное число
            
            # Расход на ремонт
            repair_stmt = select(func.sum(VehicleRepairHistory.repair_cost)).where(
                and_(
                    VehicleRepairHistory.vehicle_id == v.id,
                    VehicleRepairHistory.created_at >= month_ago
                )
            )
            repair_result = await db.execute(repair_stmt)
            repair_cost = float(repair_result.scalar() or 0)
            
            profit = income + expense - repair_cost
            
            vehicles_data.append({
                "id": v.id,
                "license_plate": v.license_plate,
                "plate": v.license_plate,  # Алиас для фронтенда
                "brand": v.brand or "—",
                "model": v.model or "—",
                "year": v.year,
                "color": v.color,
                "current_mileage": getattr(v, "current_mileage", None),
                "vin": v.vin or "—",
            "sts_number": getattr(v, "sts_number", None) or "—",
                "sts_number": v.sts_number or "Внешнее авто",
                "callsign": v.callsign or "—",
                "status": v.status,
                "park": (v.park_name or "PRO").upper(),  # DEEP MAPPING v200.1
                "park_name": (v.park_name or "PRO").upper(),
                "ownership_type": v.ownership_type.value if v.ownership_type else "connected",
                "is_park_car": getattr(v, "is_park_car", False),  # DEEP MAPPING v200.1
                "driver_name": driver.full_name if driver else None,  # DEEP MAPPING v200.1
                "driver_id": driver.id if driver else None,
                "created_at": v.created_at.isoformat() if hasattr(v, 'created_at') and v.created_at else v.last_update.isoformat() if v.last_update else None,
                "profit_month": round(profit, 2),
                "income_month": round(income, 2),
                "expense_month": round(abs(expense), 2),
                "repair_month": round(repair_cost, 2)
            })
        
        logger.info(f"✓ Fleet list JSON: {len(vehicles_data)} vehicles (active: {active_count}, total: {total_count})")
        
        return {
            "status": "success",
            "vehicles": vehicles_data,
            "total": len(vehicles_data),
            # PROTOCOL "THE LIVE 300": Счётчики
            "active_dominion": active_count,  # "Живые" борты
            "total_fleet": total_count,  # Всего в системе
            "is_archive_mode": show_archive,
        }
        
    except Exception as e:
        logger.error(f"Fleet list JSON error: {e}", exc_info=True)
        return {
            "status": "error",
            "vehicles": [],
            "message": str(e)
        }

class StatusUpdate(BaseModel):
    status: str
    reason: Optional[str] = None

class VehicleCreate(BaseModel):
    brand: str
    model: str
    year: int
    color: str
    license_plate: str
    vin: str
    sts_number: str
    callsign: Optional[str] = None
    ownership_type: str = "connected"

@router.patch("/vehicles/{vehicle_id}/status")
async def update_vehicle_status(
    vehicle_id: int,
    payload: StatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Обновление статуса автомобиля с логированием (v30.1 FINANCE HOOK)
    """
    try:
        vehicle = await db.get(Vehicle, vehicle_id)
        if not vehicle:
            raise HTTPException(status_code=404, detail="Машина не найдена")
        
        # Сохраняем старый статус
        old_status = vehicle.status
        
        # ЛОГИРУЕМ ИЗМЕНЕНИЕ СТАТУСА (для финансового анализа!)
        from app.models.all_models import VehicleStatusHistory
        
        status_log = VehicleStatusHistory(
            vehicle_id=vehicle_id,
            old_status=old_status,
            new_status=payload.status,
            changed_by=current_user.username if current_user else "System",
            changed_at=datetime.now(),
            reason=payload.reason
        )
        
        db.add(status_log)
        
        # Обновляем статус
        vehicle.status = payload.status
        vehicle.last_update = datetime.now()
        
        await db.commit()
        
        logger.info(f"💰 STATUS CHANGE (Finance Impact): {vehicle.license_plate}")
        logger.info(f"   {old_status} → {payload.status}")
        logger.info(f"   Changed by: {current_user.username if current_user else 'System'}")
        
        # Если машина ушла в ремонт/простой - логируем для P&L
        if payload.status in ['service', 'offline', 'debt_lock']:
            logger.warning(f"⚠️ Vehicle offline: {vehicle.license_plate} | Revenue impact for P&L!")
        
        return {
            "status": "success",
            "vehicle_id": vehicle_id,
            "old_status": old_status,
            "new_status": payload.status,
            "finance_impact": payload.status in ['service', 'offline', 'debt_lock']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Status update error: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/vehicles/{vehicle_id}/contract-terms")
async def get_contract_terms(
    vehicle_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.can_see_fleet and current_user.role.lower() != "master":
        raise HTTPException(status_code=403, detail="Нет доступа к Флоту")
    vehicle = await db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Машина не найдена")
    driver = await db.get(User, vehicle.current_driver_id) if vehicle.current_driver_id else None

    term_stmt = select(ContractTerm).where(ContractTerm.vehicle_id == vehicle_id)
    term = (await db.execute(term_stmt)).scalar_one_or_none()
    source = "vehicle"
    if not term and driver:
        driver_stmt = select(ContractTerm).where(ContractTerm.driver_id == driver.id)
        term = (await db.execute(driver_stmt)).scalar_one_or_none()
        source = "driver"
    if not term:
        term = await _ensure_default_terms(db, vehicle.park_name or "PRO")
        source = "default"

    history_stmt = select(ContractTermHistory).where(
        ContractTermHistory.vehicle_id == vehicle_id
    ).order_by(ContractTermHistory.changed_at.desc()).limit(20)
    history = (await db.execute(history_stmt)).scalars().all()
    history_items = [
        {
            "id": h.id,
            "changed_by": h.changed_by,
            "changed_at": h.changed_at.isoformat() if h.changed_at else None,
            "changes": h.changes or {},
            "note": h.note,
        }
        for h in history
    ]

    return {
        "status": "success",
        "source": source,
        "term": {
            "id": term.id,
            "vehicle_id": vehicle_id,
            "driver_id": term.driver_id,
            "park_name": term.park_name,
            "partner_daily_rent": float(term.partner_daily_rent or 0.0),
            "driver_daily_rent": float(term.driver_daily_rent or 0.0),
            "commission_rate": float(term.commission_rate or 0.0),
            "day_off_rate": float(term.day_off_rate or 0.0),
            "is_repair": bool(term.is_repair),
            "is_day_off": bool(term.is_day_off),
            "is_idle": bool(term.is_idle),
            "updated_at": term.updated_at.isoformat() if term.updated_at else None,
        },
        "history": history_items,
    }

@router.patch("/vehicles/{vehicle_id}/contract-terms")
async def update_contract_terms(
    vehicle_id: int,
    payload: ContractTermsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.can_see_fleet and current_user.role.lower() != "master":
        raise HTTPException(status_code=403, detail="Нет доступа к Флоту")
    vehicle = await db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Машина не найдена")
    driver = await db.get(User, vehicle.current_driver_id) if vehicle.current_driver_id else None

    term_stmt = select(ContractTerm).where(ContractTerm.vehicle_id == vehicle_id)
    term = (await db.execute(term_stmt)).scalar_one_or_none()
    if not term:
        defaults = await _ensure_default_terms(db, vehicle.park_name or "PRO")
        term = ContractTerm(
            vehicle_id=vehicle_id,
            driver_id=driver.id if driver else None,
            park_name=(vehicle.park_name or "PRO").upper(),
            is_default=False,
            partner_daily_rent=defaults.partner_daily_rent,
            driver_daily_rent=float(driver.daily_rent or 0.0) if driver else defaults.driver_daily_rent,
            commission_rate=vehicle.commission_rate or defaults.commission_rate,
            day_off_rate=defaults.day_off_rate,
            is_repair=False,
            is_day_off=False,
            is_idle=False,
        )
        db.add(term)
        await db.commit()
        await db.refresh(term)

    changes = {}
    for field in [
        "partner_daily_rent",
        "driver_daily_rent",
        "commission_rate",
        "day_off_rate",
        "is_repair",
        "is_day_off",
        "is_idle",
    ]:
        value = getattr(payload, field)
        if value is None:
            continue
        old_value = getattr(term, field)
        if old_value != value:
            changes[field] = {"from": old_value, "to": value}
            setattr(term, field, value)

    if changes:
        term.updated_at = datetime.now()
        history = ContractTermHistory(
            contract_term_id=term.id,
            vehicle_id=vehicle_id,
            changed_by_user_id=current_user.id if current_user else None,
            changed_by=current_user.username if current_user else "System",
            changes=changes,
            note=payload.note,
            changed_at=datetime.now()
        )
        db.add(history)

        if payload.is_repair is True:
            vehicle.status = "service"
        elif payload.is_idle is True:
            vehicle.status = "offline"
        elif payload.is_day_off is True and vehicle.status == "service":
            vehicle.status = "offline"

        vehicle.last_update = datetime.now()
        await db.commit()
        await db.refresh(term)

    return {
        "status": "success",
        "vehicle_id": vehicle_id,
        "changes": changes,
        "term": {
            "id": term.id,
            "partner_daily_rent": float(term.partner_daily_rent or 0.0),
            "driver_daily_rent": float(term.driver_daily_rent or 0.0),
            "commission_rate": float(term.commission_rate or 0.0),
            "day_off_rate": float(term.day_off_rate or 0.0),
            "is_repair": bool(term.is_repair),
            "is_day_off": bool(term.is_day_off),
            "is_idle": bool(term.is_idle),
            "updated_at": term.updated_at.isoformat() if term.updated_at else None,
        },
    }

@router.get("/contract-terms/defaults")
async def get_default_contract_terms(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role.lower() != "master":
        raise HTTPException(status_code=403, detail="Только Мастер")
    parks = ["PRO", "GO", "PLUS", "EXPRESS"]
    result = {}
    for park in parks:
        term = await _ensure_default_terms(db, park)
        result[park] = {
            "id": term.id,
            "partner_daily_rent": float(term.partner_daily_rent or 0.0),
            "driver_daily_rent": float(term.driver_daily_rent or 0.0),
            "commission_rate": float(term.commission_rate or 0.0),
            "day_off_rate": float(term.day_off_rate or 0.0),
        }
    return {"status": "success", "defaults": result}

@router.patch("/contract-terms/defaults")
async def update_default_contract_terms(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role.lower() != "master":
        raise HTTPException(status_code=403, detail="Только Мастер")
    park = (payload.get("park") or "PRO").upper()
    term = await _ensure_default_terms(db, park)
    changes = {}
    for field in ["partner_daily_rent", "driver_daily_rent", "commission_rate", "day_off_rate"]:
        if field in payload and payload[field] is not None:
            old_value = getattr(term, field)
            new_value = payload[field]
            if old_value != new_value:
                changes[field] = {"from": old_value, "to": new_value}
                setattr(term, field, new_value)
    if changes:
        term.updated_at = datetime.now()
        history = ContractTermHistory(
            contract_term_id=term.id,
            vehicle_id=None,
            changed_by_user_id=current_user.id if current_user else None,
            changed_by=current_user.username if current_user else "System",
            changes=changes,
            note=f"Default update for {park}",
            changed_at=datetime.now()
        )
        db.add(history)
        await db.commit()
        await db.refresh(term)
    return {"status": "success", "park": park, "changes": changes}

@router.get("/vehicles/lookup")
async def lookup_vehicle(
    vin: Optional[str] = None,
    plate: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    vin_value = (vin or "").upper()
    plate_value = _normalize_plate(plate or "")
    if not vin_value and not plate_value:
        return {"exists": False, "matches": []}
    stmt = select(Vehicle)
    if vin_value and plate_value:
        stmt = stmt.where(or_(Vehicle.vin == vin_value, Vehicle.license_plate == plate_value))
    elif vin_value:
        stmt = stmt.where(Vehicle.vin == vin_value)
    else:
        stmt = stmt.where(Vehicle.license_plate == plate_value)
    rows = (await db.execute(stmt.limit(10))).scalars().all()
    matches = [
        {
            "id": v.id,
            "license_plate": v.license_plate,
            "vin": v.vin,
            "park_name": v.park_name,
            "yandex_car_id": v.yandex_car_id,
        }
        for v in rows
    ]
    return {"exists": bool(matches), "matches": matches}

@router.get("/drivers/lookup")
async def lookup_driver(
    phone: Optional[str] = None,
    name: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    phone_value = _normalize_phone(phone or "")
    name_value = (name or "").strip()
    if not phone_value and not name_value:
        return {"exists": False, "matches": []}
    stmt = select(User)
    if phone_value and name_value:
        stmt = stmt.where(
            or_(
                User.username == phone_value,
                User.full_name.ilike(f"%{name_value}%"),
            )
        )
    elif phone_value:
        stmt = stmt.where(User.username == phone_value)
    else:
        stmt = stmt.where(User.full_name.ilike(f"%{name_value}%"))
    rows = (await db.execute(stmt.limit(10))).scalars().all()
    matches = [
        {
            "id": u.id,
            "full_name": u.full_name,
            "phone": u.username,
            "park_name": u.park_name,
            "yandex_driver_id": u.yandex_driver_id,
            "yandex_contractor_id": u.yandex_contractor_id,
        }
        for u in rows
    ]
    return {"exists": bool(matches), "matches": matches}

@router.post("/drivers/add")
async def add_driver(
    payload: DriverCreatePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from app.services.yandex_sync_service import yandex_sync
    park = (payload.park_name or "PRO").upper()
    cfg = _get_park_cfg(park)
    phone_clean = _normalize_phone(payload.phone)
    if not phone_clean:
        raise HTTPException(status_code=400, detail="Телефон обязателен")
    exists_stmt = select(User).where(User.username == phone_clean)
    existing = (await db.execute(exists_stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Водитель с таким телефоном уже существует")

    yandex_payload = {
        "contractor": {
            "person": {
                "full_name": {
                    "first_name": payload.first_name,
                    "middle_name": payload.middle_name,
                    "last_name": payload.last_name,
                },
                "contact_info": {
                    "phone": f"+{phone_clean}" if not payload.phone.startswith("+") else payload.phone,
                },
                "driver_license": {
                    "birth_date": payload.birth_date,
                    "country": payload.license_country,
                    "expiry_date": payload.license_expiry_date,
                    "issue_date": payload.license_issue_date,
                    "number": payload.license_number,
                },
                "driver_license_experience": {
                    "total_since_date": payload.driver_license_experience_since
                },
            },
            "profile": {
                "hire_date": datetime.now().date().isoformat()
            },
            "order_provider": {"platform": True, "partner": True},
        },
        "profession": payload.profession,
        "employment": {"type": payload.employment_type},
    }
    if payload.email:
        yandex_payload["contractor"]["person"]["contact_info"]["email"] = payload.email
    if payload.address:
        yandex_payload["contractor"]["person"]["contact_info"]["address"] = payload.address
    if payload.tax_identification_number:
        yandex_payload["contractor"]["person"]["tax_identification_number"] = payload.tax_identification_number
    headers = yandex_sync._get_headers_for_park(cfg)
    if payload.car_id:
        v2_details = await yandex_sync._request_raw(
            "GET",
            f"{yandex_sync.base_url}/v2/parks/vehicles/car",
            headers,
            params={"vehicle_id": str(payload.car_id)},
        )
        if not v2_details:
            raise HTTPException(status_code=502, detail="Не удалось проверить car_id через Yandex V2")
        yandex_payload["contractor"]["car_id"] = payload.car_id

    headers["X-Idempotency-Token"] = uuid.uuid4().hex
    url = f"{yandex_sync.base_url}/v1/parks/contractors/profile"
    response = await yandex_sync._request_raw("POST", url, headers, payload=yandex_payload)
    contractor_profile_id = response.get("contractor_profile_id") or response.get("id")
    if not contractor_profile_id:
        raise HTTPException(status_code=502, detail="Не удалось создать профиль в Яндексе")

    user = User(
        username=phone_clean,
        hashed_password=hash_password("driver123"),
        full_name=" ".join([p for p in [payload.last_name, payload.first_name, payload.middle_name] if p]).strip(),
        is_active=True,
        can_see_fleet=True,
        yandex_driver_id=str(contractor_profile_id),
        yandex_contractor_id=str(contractor_profile_id),
        park_name=park,
    )
    db.add(user)
    await db.flush()

    driver_profile = DriverProfile(
        user_id=user.id,
        license_number=payload.license_number,
    )
    db.add(driver_profile)

    default_term = await _ensure_default_terms(db, park)
    term_stmt = select(ContractTerm).where(ContractTerm.driver_id == user.id)
    existing_term = (await db.execute(term_stmt)).scalar_one_or_none()
    if not existing_term:
        term = ContractTerm(
            driver_id=user.id,
            park_name=park,
            is_default=False,
            partner_daily_rent=default_term.partner_daily_rent,
            driver_daily_rent=default_term.driver_daily_rent,
            commission_rate=default_term.commission_rate,
            day_off_rate=default_term.day_off_rate,
            is_repair=False,
            is_day_off=False,
            is_idle=False,
        )
        db.add(term)

    await db.commit()
    await db.refresh(user)
    return {"status": "success", "driver_id": user.id, "contractor_profile_id": contractor_profile_id}

@router.post("/vehicles/add")
async def add_vehicle(
    payload: VehicleCreatePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from app.services.yandex_sync_service import yandex_sync
    park = (payload.park_name or "PRO").upper()
    cfg = _get_park_cfg(park)
    _validate_vin(payload.vin)
    _validate_plate(payload.license_plate)

    plate_clean = _normalize_plate(payload.license_plate)
    vin_clean = payload.vin.upper()

    exists_stmt = select(Vehicle).where(
        or_(Vehicle.license_plate == plate_clean, Vehicle.vin == vin_clean)
    )
    existing = (await db.execute(exists_stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Машина с таким VIN или госномером уже существует")

    ownership_type = payload.ownership_type.lower()
    if ownership_type not in ["sublease", "connected", "owned_5t", "partner"]:
        raise HTTPException(status_code=400, detail="Неверный тип владения")
    is_park_property = payload.is_park_property
    if is_park_property is None:
        is_park_property = ownership_type in ["sublease", "owned_5t"]
    ownership_external = payload.ownership_type_external or ("park" if is_park_property else "leasing")

    yandex_payload = {
        "vehicle_specifications": {
            "model": payload.model,
            "brand": payload.brand,
            "color": payload.color,
            "year": payload.year,
            "vin": vin_clean,
        },
        "vehicle_licenses": {
            "licence_plate_number": plate_clean,
            "registration_certificate": payload.sts_number,
        },
        "park_profile": {
            "callsign": payload.callsign or "",
            "status": "working",
            "is_park_property": bool(is_park_property),
            "ownership_type": ownership_external,
        },
    }

    headers = yandex_sync._get_headers_for_park(cfg)
    headers["X-Idempotency-Token"] = uuid.uuid4().hex
    url = f"{yandex_sync.base_url}/v2/parks/vehicles/car"
    response = await yandex_sync._request_raw("POST", url, headers, payload=yandex_payload)
    yandex_car_id = response.get("vehicle_id") or response.get("car_id") or response.get("id")
    if not yandex_car_id:
        raise HTTPException(status_code=502, detail="Не удалось создать авто в Яндексе")

    vehicle = Vehicle(
        brand=payload.brand,
        model=payload.model,
        year=payload.year,
        color=payload.color,
        license_plate=plate_clean,
        vin=vin_clean,
        sts_number=payload.sts_number,
        callsign=payload.callsign,
        ownership_type=OwnershipType(ownership_type),
        status="working",
        is_active=True,
        is_free=True,
        park_name=park,
        yandex_car_id=str(yandex_car_id),
        created_at=datetime.now(),
        last_update=datetime.now(),
    )
    db.add(vehicle)
    await db.flush()

    default_term = await _ensure_default_terms(db, park)
    term_stmt = select(ContractTerm).where(ContractTerm.vehicle_id == vehicle.id)
    existing_term = (await db.execute(term_stmt)).scalar_one_or_none()
    if not existing_term:
        term = ContractTerm(
            vehicle_id=vehicle.id,
            park_name=park,
            is_default=False,
            partner_daily_rent=default_term.partner_daily_rent,
            driver_daily_rent=default_term.driver_daily_rent,
            commission_rate=default_term.commission_rate,
            day_off_rate=default_term.day_off_rate,
            is_repair=False,
            is_day_off=False,
            is_idle=False,
        )
        db.add(term)

    await db.commit()
    await db.refresh(vehicle)
    return {"status": "success", "vehicle_id": vehicle.id, "yandex_car_id": yandex_car_id}

@router.post("/drivers/{driver_id}/action")
async def driver_action(
    driver_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from app.services.yandex_sync_service import yandex_sync
    action = (payload.get("action") or "").lower()
    if action not in {"fire", "block", "unblock"}:
        raise HTTPException(status_code=400, detail="Неверное действие")
    user = await db.get(User, driver_id)
    if not user:
        raise HTTPException(status_code=404, detail="Водитель не найден")
    contractor_id = user.yandex_contractor_id or user.yandex_driver_id
    if not contractor_id:
        raise HTTPException(status_code=400, detail="Нет contractor_profile_id для Яндекс API")
    park = (user.park_name or "PRO").upper()
    cfg = _get_park_cfg(park)

    if action == "fire":
        update_payload = {
            "contractor_profile_id": str(contractor_id),
            "contractor": {"profile": {"work_status": "fired"}},
        }
    else:
        update_payload = {
            "contractor_profile_id": str(contractor_id),
            "contractor": {"account": {"block_orders_on_balance_below_limit": action == "block"}},
        }
    headers = yandex_sync._get_headers_for_park(cfg)
    headers["X-Idempotency-Token"] = uuid.uuid4().hex
    url = f"{yandex_sync.base_url}/v1/parks/contractors/profile"
    response = await yandex_sync._request_raw("PUT", url, headers, payload=update_payload)
    if response.get("code") and response.get("message"):
        raise HTTPException(status_code=502, detail=response.get("message"))

    if action == "fire":
        user.is_active = False
    elif action == "unblock":
        user.is_active = True
    await db.commit()
    return {"status": "success", "action": action}

@router.post("/drivers/{driver_id}/bind-vehicle")
async def bind_vehicle_to_driver(
    driver_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from app.services.yandex_sync_service import yandex_sync
    vehicle_id = payload.get("vehicle_id")
    if not vehicle_id:
        raise HTTPException(status_code=400, detail="vehicle_id обязателен")
    user = await db.get(User, driver_id)
    if not user:
        raise HTTPException(status_code=404, detail="Водитель не найден")
    vehicle = await db.get(Vehicle, int(vehicle_id))
    if not vehicle:
        raise HTTPException(status_code=404, detail="Авто не найдено")
    if not vehicle.yandex_car_id:
        raise HTTPException(status_code=400, detail="У авто нет yandex_car_id")

    driver_profile_id = user.yandex_driver_id or user.yandex_contractor_id
    if not driver_profile_id:
        raise HTTPException(status_code=400, detail="Нет ID водителя для Яндекс API")

    response = await yandex_sync.bind_driver_to_car(
        user.park_name or "PRO",
        str(driver_profile_id),
        str(vehicle.yandex_car_id),
    )
    if response.get("code") and response.get("message"):
        raise HTTPException(status_code=502, detail=response.get("message"))

    if user.current_vehicle_id and user.current_vehicle_id != vehicle.id:
        prev_vehicle = await db.get(Vehicle, user.current_vehicle_id)
        if prev_vehicle:
            prev_vehicle.current_driver_id = None
            prev_vehicle.yandex_driver_id = None
            prev_vehicle.is_free = True
            prev_vehicle.last_update = datetime.now()
    user.current_vehicle_id = vehicle.id
    vehicle.current_driver_id = user.id
    vehicle.yandex_driver_id = str(user.yandex_driver_id or user.yandex_contractor_id)
    vehicle.is_free = False
    vehicle.last_update = datetime.now()
    await db.commit()
    return {"status": "success", "vehicle_id": vehicle.id}

@router.post("/vehicles/create")
async def create_vehicle(
    payload: VehicleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Ручное добавление автомобиля (v30.1)
    """
    try:
        # Валидация VIN
        if len(payload.vin) != 17:
            raise HTTPException(status_code=400, detail="VIN должен содержать ровно 17 символов")
        
        # Проверка на дубликат
        stmt = select(Vehicle).where(Vehicle.license_plate == payload.license_plate.upper())
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            # Запрещаем ручное перезаписывание данных, пришедших из Яндекс API
            if existing.yandex_car_id:
                raise HTTPException(status_code=400, detail="Эта машина синхронизируется с Яндекс. API запись защищена.")
            raise HTTPException(status_code=400, detail=f"Машина с госномером {payload.license_plate} уже существует")
        
        # Создаем машину
        new_vehicle = Vehicle(
            brand=payload.brand,
            model=payload.model,
            year=payload.year,
            color=payload.color,
            license_plate=payload.license_plate.upper(),
            vin=payload.vin.upper(),
            sts_number=payload.sts_number,
            callsign=payload.callsign,
            ownership_type=OwnershipType(payload.ownership_type) if payload.ownership_type in ['sublease', 'connected', 'owned_5t', 'partner'] else OwnershipType.CONNECTED,
            status='preparing',  # Новая машина в подготовке
            is_active=True,
            created_at=datetime.now(),
            last_update=datetime.now()
        )
        
        db.add(new_vehicle)
        await db.commit()
        await db.refresh(new_vehicle)
        
        logger.info(f"✓ Vehicle created manually: {new_vehicle.license_plate} | ID: {new_vehicle.id}")
        
        return {
            "status": "success",
            "vehicle_id": new_vehicle.id,
            "license_plate": new_vehicle.license_plate,
            "message": "Автомобиль успешно добавлен"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create vehicle error: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/vehicles/create")
async def create_vehicle_manual(
    payload: VehicleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Ручное добавление автомобиля (v30.1)
    """
    try:
        # Валидация VIN
        if len(payload.vin) != 17:
            raise HTTPException(status_code=400, detail="VIN должен содержать ровно 17 символов")
        
        # Проверка на дубликат
        stmt = select(Vehicle).where(Vehicle.license_plate == payload.license_plate.upper())
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            if existing.yandex_car_id:
                raise HTTPException(status_code=400, detail="Эта машина синхронизируется с Яндекс. API запись защищена.")
            raise HTTPException(status_code=400, detail=f"Машина с госномером {payload.license_plate} уже существует")
        
        # Создаем машину
        new_vehicle = Vehicle(
            brand=payload.brand,
            model=payload.model,
            year=payload.year,
            color=payload.color,
            license_plate=payload.license_plate.upper(),
            vin=payload.vin.upper(),
            sts_number=payload.sts_number,
            callsign=payload.callsign,
            ownership_type=OwnershipType(payload.ownership_type) if payload.ownership_type in ['sublease', 'connected', 'owned_5t', 'partner'] else OwnershipType.CONNECTED,
            status='preparing',
            is_active=True,
            created_at=datetime.now(),
            last_update=datetime.now()
        )
        
        db.add(new_vehicle)
        await db.commit()
        await db.refresh(new_vehicle)
        
        logger.info(f"✓ Vehicle created manually: {new_vehicle.license_plate} | ID: {new_vehicle.id}")
        
        return {
            "status": "success",
            "vehicle_id": new_vehicle.id,
            "license_plate": new_vehicle.license_plate,
            "message": "Автомобиль успешно добавлен"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create vehicle error: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/vehicles/{vehicle_id}/ownership")
async def update_vehicle_ownership(
    vehicle_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Обновление условий аренды (v30.1 FINANCE HOOK)
    """
    try:
        vehicle = await db.get(Vehicle, vehicle_id)
        if not vehicle:
            raise HTTPException(status_code=404, detail="Машина не найдена")
        
        new_ownership = payload.get("ownership_type")
        old_ownership = vehicle.ownership_type.value if vehicle.ownership_type else "connected"
        
        # Обновляем тип собственности
        vehicle.ownership_type = OwnershipType(new_ownership)
        
        # Устанавливаем комиссии
        if new_ownership == "sublease":
            vehicle.commission_rate = 0.04
            vehicle.fixed_fee = 450.0
        elif new_ownership == "connected":
            vehicle.commission_rate = 0.03
            vehicle.fixed_fee = 0.0
        
        vehicle.last_update = datetime.now()
        
        await db.commit()
        
        logger.info(f"💰 OWNERSHIP CHANGE (Finance Impact): {vehicle.license_plate}")
        logger.info(f"   {old_ownership} → {new_ownership}")
        logger.info(f"   Commission: {vehicle.commission_rate*100}%, Fixed: {vehicle.fixed_fee}₽")
        
        return {
            "status": "success",
            "vehicle_id": vehicle_id,
            "old_ownership": old_ownership,
            "new_ownership": new_ownership,
            "finance_impact": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ownership update error: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sync/vehicles")
async def sync_vehicles_from_yandex(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Синхронизация автопарка с Яндекс.Такси API (v30.1)
    """
    try:
        from app.services.yandex_sync_service import yandex_sync
        
        logger.info("🔄 Starting fleet sync with Yandex API...")
        
        result = await yandex_sync.sync_vehicles()
        
        logger.info(f"✓ Fleet sync completed: {result}")
        
        return {
            "status": "success",
            "message": f"Синхронизировано: {result.get('synced', 0)} машин",
            "details": result
        }
        
    except Exception as e:
        logger.error(f"Fleet sync error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sync/drivers")
async def sync_drivers_from_yandex(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Синхронизация водителей с Яндекс.Такси API и авто-распределение по паркам.
    """
    if not _is_master(current_user):
        raise HTTPException(status_code=403, detail="Только Мастер может синхронизировать водителей")
    try:
        from app.services.yandex_sync_service import yandex_sync
        result = await yandex_sync.sync_driver_profiles_multi_park()
        return {
            "status": "success",
            "result": result,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Driver sync error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# Глобальный статус синхронизации для real-time отображения
_sync_status = {
    "is_running": False,
    "started_at": None,
    "finished_at": None,
    "last_result": None,
    "error": None
}

async def _run_sync_background():
    """Фоновая задача синхронизации."""
    global _sync_status
    _sync_status["is_running"] = True
    _sync_status["started_at"] = datetime.now().isoformat()
    _sync_status["error"] = None
    try:
        from app.services.yandex_sync_service import yandex_sync
        result = await yandex_sync.sync_all_parks()
        _sync_status["last_result"] = result
        _sync_status["finished_at"] = datetime.now().isoformat()
        logger.info(f"Background sync completed: {result}")
    except Exception as e:
        _sync_status["error"] = str(e)
        _sync_status["finished_at"] = datetime.now().isoformat()
        logger.error(f"Background sync error: {e}", exc_info=True)
    finally:
        _sync_status["is_running"] = False

@router.post("/sync/full")
async def sync_full_from_yandex(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """
    Полная многопоточная синхронизация 4 парков: водители, авто, транзакции.
    Запускается в фоновом режиме — мгновенный ответ 200 OK.
    """
    global _sync_status
    if not _is_master(current_user) and not settings.YANDEX_ALLOW_SYNC_NOAUTH:
        raise HTTPException(status_code=403, detail="Только Мастер")
    
    if _sync_status["is_running"]:
        return {
            "status": "already_running",
            "message": "Синхронизация уже выполняется",
            "started_at": _sync_status["started_at"]
        }
    
    # Запускаем синхронизацию в фоне — браузер получит 200 OK мгновенно
    background_tasks.add_task(_run_sync_background)
    
    return {
        "status": "processing",
        "message": "Синхронизация запущена в фоне. Обновление данных через 30-60 секунд.",
        "timestamp": datetime.now().isoformat()
    }

@router.get("/sync/full")
async def sync_full_get(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """
    GET-версия полной синхронизации — для запуска из браузера или кнопки UI.
    Запускает тот же фоновый процесс, что и POST /sync/full.
    Выкачивает ВСЕ данные: водители (ВУ серия/номер, даты, стаж, рейтинг), авто, транзакции.
    """
    global _sync_status
    if not _is_master(current_user) and not settings.YANDEX_ALLOW_SYNC_NOAUTH:
        raise HTTPException(status_code=403, detail="Только Мастер")
    
    if _sync_status["is_running"]:
        return {
            "status": "already_running",
            "message": "Синхронизация уже выполняется",
            "started_at": _sync_status["started_at"]
        }
    
    background_tasks.add_task(_run_sync_background)
    
    return {
        "status": "processing",
        "message": "Синхронизация запущена в фоновом режиме",
        "timestamp": datetime.now().isoformat()
    }

@router.get("/sync/status")
async def get_sync_status(
    current_user: User = Depends(get_current_user)
):
    """Получить текущий статус фоновой синхронизации."""
    return {
        "status": "ok",
        "sync": _sync_status
    }

@router.post("/sync/start")
async def sync_start_initial(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """
    ПЕРВИЧНАЯ ЗАГРУЗКА ДАННЫХ ИЗ ЯНДЕКСА
    
    Запускает полную синхронизацию:
    - Водители (все парки)
    - Машины (все парки)
    - Транзакции (последние 48 часов)
    - Привязки водитель-машина
    
    Требует настроенных API ключей в .env:
    - PRO_YANDEX_PARK_ID, PRO_YANDEX_CLIENT_ID, PRO_YANDEX_API_KEY
    - GO_YANDEX_PARK_ID, GO_YANDEX_CLIENT_ID, GO_YANDEX_API_KEY
    - и т.д.
    """
    global _sync_status
    
    # Проверка прав
    if not _is_master(current_user) and not settings.YANDEX_ALLOW_SYNC_NOAUTH:
        raise HTTPException(status_code=403, detail="Только Мастер может запускать синхронизацию")
    
    # Импорт сервиса синхронизации
    from app.services.yandex_sync_service import yandex_sync
    
    # Проверка конфигурации API ключей
    if not yandex_sync.enabled:
        active_parks = []
        missing_parks = []
        
        for park_name, cfg in settings.PARKS.items():
            if all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")]):
                active_parks.append(park_name)
            else:
                missing_parks.append(park_name)
        
        return {
            "status": "error",
            "message": "API ключи Яндекса не настроены",
            "active_parks": active_parks,
            "missing_parks": missing_parks,
            "hint": "Добавьте в .env файл ключи для каждого парка:\n" +
                    "PRO_YANDEX_PARK_ID=...\nPRO_YANDEX_CLIENT_ID=...\nPRO_YANDEX_API_KEY=...\n" +
                    "и перезапустите сервер."
        }
    
    # Проверка на уже запущенную синхронизацию
    if _sync_status["is_running"]:
        return {
            "status": "already_running",
            "message": "Синхронизация уже выполняется",
            "started_at": _sync_status["started_at"],
            "hint": "Используйте GET /api/v1/fleet/sync/status для мониторинга"
        }
    
    # Запуск фоновой синхронизации
    background_tasks.add_task(_run_sync_background)
    
    return {
        "status": "started",
        "message": f"Первичная загрузка запущена для {len(yandex_sync.active_parks)} парков",
        "active_parks": list(yandex_sync.active_parks.keys()),
        "timestamp": datetime.now().isoformat(),
        "hint": "Используйте GET /api/v1/fleet/sync/status для мониторинга прогресса"
    }


@router.get("/parks/health")
async def parks_health(
    current_user: User = Depends(get_current_user)
):
    """
    Быстрый статус API Яндекс по каждому парку.
    200 -> ok, 401/403 -> error.
    """
    try:
        from app.services.yandex_sync_service import yandex_sync
        results = await yandex_sync.check_parks_health()
        return {"status": "ok", "parks": results}
    except Exception as e:
        logger.error("Health check error: %s", e)
        return {"status": "error", "parks": {}}

@router.get("/debug/driver-profiles")
async def debug_driver_profiles(
    park: str = "PRO",
    name: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Debug: получить driver-profiles по парку и фильтру имени.
    Возвращает сокращенные поля без секретов.
    """
    if not _is_master(current_user):
        raise HTTPException(status_code=403, detail="Только Мастер")
    from app.services.yandex_sync_service import yandex_sync
    profiles = await yandex_sync.fetch_driver_profiles(park)
    if name:
        needle = name.strip().lower()
        filtered = []
        for p in profiles:
            person = p.get("person") or {}
            full = p.get("full_name")
            if not full:
                full_name = person.get("full_name") or {}
                full = " ".join(
                    [v for v in [full_name.get("last_name"), full_name.get("first_name"), full_name.get("middle_name")] if v]
                )
            if needle and needle in (full or "").lower():
                filtered.append(p)
        profiles = filtered
    results = []
    for p in profiles:
        person = p.get("person") or {}
        full_name = person.get("full_name") or {}
        full = p.get("full_name") or " ".join(
            [v for v in [full_name.get("last_name"), full_name.get("first_name"), full_name.get("middle_name")] if v]
        )
        results.append({
            "contractor_profile_id": p.get("contractor_profile_id"),
            "driver_profile_id": p.get("driver_profile_id"),
            "id": p.get("id"),
            "park_id": p.get("park_id") or (p.get("park") or {}).get("id"),
            "status": p.get("status"),
            "work_status": p.get("work_status"),
            "full_name": full,
        })
    return {"status": "ok", "park": park.upper(), "count": len(results), "items": results}

@router.get("/debug/driver-profile")
async def debug_driver_profile(
    park: str = "PRO",
    contractor_profile_id: str = "",
    current_user: User = Depends(get_current_user)
):
    if not _is_master(current_user):
        raise HTTPException(status_code=403, detail="Только Мастер")
    if not contractor_profile_id:
        raise HTTPException(status_code=400, detail="contractor_profile_id обязателен")
    from app.services.yandex_sync_service import yandex_sync
    data = await yandex_sync.fetch_driver_profile(park, contractor_profile_id)
    return {"status": "ok", "park": park.upper(), "contractor_profile_id": contractor_profile_id, "data": data}

@router.get("/debug/driver-supply-hours")
async def debug_driver_supply_hours(
    park: str = "PRO",
    contractor_profile_id: str = "",
    period_from: Optional[str] = None,
    period_to: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    if not _is_master(current_user):
        raise HTTPException(status_code=403, detail="Только Мастер")
    if not contractor_profile_id:
        raise HTTPException(status_code=400, detail="contractor_profile_id обязателен")
    if not period_from or not period_to:
        now = datetime.now()
        period_to = _moscow_iso(now)
        period_from = _moscow_iso(now - timedelta(hours=24))
    from app.services.yandex_sync_service import yandex_sync
    data = await yandex_sync.fetch_supply_hours(park, contractor_profile_id, period_from, period_to)
    return {
        "status": "ok",
        "park": park.upper(),
        "contractor_profile_id": contractor_profile_id,
        "period_from": period_from,
        "period_to": period_to,
        "data": data,
    }

@router.get("/debug/driver-work-rules")
async def debug_driver_work_rules(
    park: str = "PRO",
    current_user: User = Depends(get_current_user)
):
    if not _is_master(current_user):
        raise HTTPException(status_code=403, detail="Только Мастер")
    from app.services.yandex_sync_service import yandex_sync
    data = await yandex_sync.fetch_driver_work_rules(park)
    return {"status": "ok", "park": park.upper(), "data": data}

@router.get("/debug/yandex-profile/{driver_id}")
async def debug_yandex_profile(
    driver_id: str,
    park: str = "PRO",
    current_user: User = Depends(get_current_user)
):
    if not _is_master(current_user):
        raise HTTPException(status_code=403, detail="Только Мастер")
    from app.services.yandex_sync_service import yandex_sync
    data = await yandex_sync.fetch_driver_profile(park, driver_id)
    return data

@router.get("/debug/transactions")
async def debug_transactions(
    park: str = "PRO",
    window_minutes: int = 60,
    current_user: User = Depends(get_current_user)
):
    if current_user.role.lower() != "master":
        raise HTTPException(status_code=403, detail="Только Мастер")
    from app.services.yandex_sync_service import yandex_sync
    data = await yandex_sync.fetch_transactions_live(park, window_minutes=window_minutes)
    items = []
    for tx in data.get("transactions") or []:
        category_id = tx.get("category_id") or tx.get("category")
        category_name = tx.get("category_name") or tx.get("category_title")
        items.append({
            "id": tx.get("id"),
            "event_at": tx.get("event_at"),
            "amount": tx.get("amount"),
            "category_id": category_id,
            "category_name": category_name,
            "normalized_category": yandex_sync._normalize_tx_category(category_id, category_name),
            "driver_profile_id": tx.get("driver_profile_id") or (tx.get("driver") or {}).get("id"),
            "description": tx.get("description"),
        })
    return {
        "status": "ok",
        "park": park.upper(),
        "window_minutes": window_minutes,
        "count": len(items),
        "items": items,
    }

@router.post("/deep-binding")
async def run_deep_binding(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """
    Принудительный Deep Binding для всех активных водителей.
    Запускается в фоновом режиме.
    """
    if not _is_master(current_user):
        raise HTTPException(status_code=403, detail="Только Мастер")
    
    async def _run_deep_binding():
        try:
            from app.services.yandex_sync_service import yandex_sync
            result = await yandex_sync.deep_pull_driver_bindings(
                window_hours=None,  # Все водители, не только 48ч
                concurrency=15,
                include_unlinked=True
            )
            logger.info(f"Deep Binding completed: {result}")
        except Exception as e:
            logger.error(f"Deep Binding error: {e}", exc_info=True)
    
    background_tasks.add_task(_run_deep_binding)
    
    return {
        "status": "processing",
        "message": "Deep Binding запущен в фоновом режиме. Привязка водителей к авто выполняется.",
        "timestamp": datetime.now().isoformat()
    }


# РЕЕСТРЫ (vehicles-list, drivers-list, calendar, periodic-charges, legion) зарегистрированы в main.py
# явно ДО /fleet/vehicles/{id} и /fleet/drivers/{id}, иначе /fleet/vehicles-list матчится как vehicle_id="list"

# API: Legion — элита: пилоты с доходом за 30 дней (только активные парки)
@router.get("/legion-data")
async def get_legion_data(
    park: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    if current_user and not current_user.can_see_fleet and getattr(current_user, "role", "").lower() != "master":
        return JSONResponse(status_code=403, content={"error": "forbidden"})

    _active_parks = [
        p for p, cfg in settings.PARKS.items()
        if all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")])
    ]

    since = datetime.now() - timedelta(days=30)

    # Грязный оборот — полный список категорий доходных поездок
    _revenue_cats = [
        "Оплата картой", "Наличные", "Корпоративная оплата",
        "Оплата через терминал", "Оплата электронным кошельком",
        "Оплата промокодом", "Компенсация оплаты поездки",
        "Компенсация скидки по промокоду",
        "Компенсация за увеличенное время в пути",
        "Оплата картой проезда по платной дороге",
        "Оплата картой, поездка партнёра", "Наличные, поездка партнёра",
    ]

    stmt = (
        select(
            User.id,
            User.full_name,
            User.username,
            User.work_status,
            User.realtime_status,
            User.park_name,
            User.driver_balance,
            User.photo_url,
            func.count(Transaction.id).label("trips_count"),
            func.max(Transaction.date).label("last_order"),
            func.sum(Transaction.amount).label("revenue_month"),
        )
        .join(
            Transaction,
            or_(
                User.yandex_driver_id == Transaction.yandex_driver_id,
                User.yandex_contractor_id == Transaction.yandex_driver_id,
            ),
        )
        .where(
            and_(
                Transaction.date >= since,
                Transaction.amount > 0,
                Transaction.category.in_(_revenue_cats),
                User.is_archived == False,
            )
        )
        .group_by(
            User.id, User.full_name, User.username,
            User.work_status, User.realtime_status,
            User.park_name, User.driver_balance,
            User.photo_url,
        )
    )
    if _active_parks:
        stmt = stmt.where(User.park_name.in_(_active_parks))
    if park and park.upper() != "ALL":
        stmt = stmt.where(User.park_name == park.upper())

    rows = (await db.execute(stmt)).all()

    # Get vehicle plates: User.current_vehicle_id → Vehicle.license_plate (raw SQL, ORM join unreliable)
    user_ids = [int(r.id) for r in rows]
    plate_map = {}
    if user_ids:
        plate_q = text("""
            SELECT u.id, v.license_plate
            FROM users u JOIN vehicles v ON u.current_vehicle_id = v.id
            WHERE u.id = ANY(:ids)
        """)
        plate_rows = (await db.execute(plate_q, {"ids": user_ids})).all()
        for uid, plate in plate_rows:
            if plate:
                plate_map[int(uid)] = plate

    pilots = []
    for r in rows:
        pilots.append({
            "id": r.id,
            "full_name": r.full_name or "—",
            "phone": r.username or "—",
            "park_name": (r.park_name or "PRO").upper(),
            "photo_url": r.photo_url,
            "vehicle_plate": plate_map.get(r.id, "—"),
            "last_order": r.last_order.isoformat() if r.last_order else None,
            "trips_count": int(r.trips_count or 0),
            "revenue_month": round(float(r.revenue_month or 0), 2),
            "balance": round(float(r.driver_balance or 0), 2),
            "status": (r.realtime_status or r.work_status or "offline").lower(),
        })

    pilots.sort(key=lambda p: p["revenue_month"], reverse=True)

    # Assign ranks
    for i, p in enumerate(pilots):
        p["rank"] = i + 1

    # KPI summary
    total_revenue = sum(p["revenue_month"] for p in pilots)
    total_trips = sum(p["trips_count"] for p in pilots)
    online_count = sum(1 for p in pilots if p["status"] in ("online", "busy", "working"))
    avg_revenue = total_revenue / len(pilots) if pilots else 0

    # Counts per park
    _leg_park_col = func.coalesce(User.park_name, "PRO")
    counts_stmt = (
        select(_leg_park_col.label("park"), func.count(distinct(User.id)))
        .join(
            Transaction,
            or_(
                User.yandex_driver_id == Transaction.yandex_driver_id,
                User.yandex_contractor_id == Transaction.yandex_driver_id,
            ),
        )
        .where(
            and_(
                Transaction.date >= since,
                Transaction.amount > 0,
                Transaction.category.in_(_revenue_cats),
                User.is_archived == False,
            )
        )
        .group_by(_leg_park_col)
    )
    if _active_parks:
        counts_stmt = counts_stmt.where(User.park_name.in_(_active_parks))
    count_rows = (await db.execute(counts_stmt)).all()
    counts = {"ALL": sum(c[1] for c in count_rows)}
    for row in count_rows:
        counts[row[0]] = row[1]

    return JSONResponse(content={
        "pilots": pilots,
        "counts": counts,
        "kpi": {
            "total_revenue": round(total_revenue, 2),
            "total_trips": total_trips,
            "avg_revenue": round(avg_revenue, 2),
            "pilots_total": len(pilots),
            "pilots_online": online_count,
        },
    })


# API: Oracle Search — подсказки для перехода на карточку авто/водителя
@router.get("/oracle-search")
async def oracle_search(
    q: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.can_see_fleet and getattr(current_user, "role", "").lower() != "master":
        return JSONResponse(status_code=403, content={"results": []})
    q = (q or "").strip()[:80]
    if not q or len(q) < 2:
        return JSONResponse(content={"results": []})
    q_lower = q.lower().replace(" ", "%")
    q_pattern = f"%{q_lower}%"
    vehicles_stmt = (
        select(Vehicle.id, Vehicle.license_plate, Vehicle.brand, Vehicle.model, Vehicle.park_name)
        .where(
            and_(
                Vehicle.is_active == True,
                or_(
                    Vehicle.license_plate.ilike(q_pattern),
                    func.coalesce(Vehicle.vin, "").ilike(q_pattern),
                ),
            )
        )
        .limit(10)
    )
    vehicles = (await db.execute(vehicles_stmt)).scalars().all()
    users_stmt = (
        select(User.id, User.full_name, User.username, User.park_name)
        .where(
            and_(
                or_(
                    User.yandex_driver_id.isnot(None),
                    User.yandex_contractor_id.isnot(None),
                ),
                User.is_archived == False,
                or_(
                    User.full_name.ilike(q_pattern),
                    User.username.ilike(q_pattern),
                ),
            )
        )
        .limit(10)
    )
    users = (await db.execute(users_stmt)).scalars().all()
    results = []
    for v in vehicles:
        park_label = (v[4] or "PRO").upper() if len(v) > 4 else "PRO"
        label = f"{v[1]} — {v[2] or ''} {v[3] or ''}".strip() or str(v[1])
        results.append({
            "type": "vehicle",
            "id": v[0],
            "label": f"{label} • {park_label}",
            "url": f"/fleet/vehicles/{v[0]}",
        })
    for u in users:
        park_label = (u[3] or "PRO").upper() if len(u) > 3 else "PRO"
        results.append({
            "type": "driver",
            "id": u[0],
            "label": f"{u[1] or 'Водитель'} ({u[2] or ''}) • {park_label}",
            "url": f"/fleet/drivers/{u[0]}",
        })
    return JSONResponse(content={"results": results[:15]})


# API: Vehicles list data — Активный флот с фильтрацией
# v33.0 PROTOCOL: Активность = поездки/статус за 24ч, Парковый в топе, Архив
@router.get("/vehicles-list-data")
async def get_vehicles_list_data(
    owner: Optional[str] = None,
    park: Optional[str] = None,
    include_archive: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Реестр автомобилей PRO v33.0
    
    Параметры:
    - owner: "park" | "private" | None — фильтр по типу владения
    - park: "PRO" | "GO" | "PLUS" | "EXPRESS" | "ALL" — фильтр по парку
    - include_archive: bool — если True, показать все 1127 машин, иначе только активные
    
    Логика АКТИВНОСТИ (24 часа):
    - Машина активна если были поездки ИЛИ обновление статуса за последние 24 часа
    - По умолчанию показываем только активные (~90 машин)
    
    Маркировка ПАРКОВЫЙ:
    - is_park_car=True (субаренда) — всегда в топе списка с меткой "ПАРКОВЫЙ"
    """
    if current_user and not current_user.can_see_fleet and getattr(current_user, "role", "").lower() != "master":
        return JSONResponse(status_code=403, content={"error": "forbidden"})

    # Определяем активные парки (только те, у которых есть API-ключи)
    _active_parks = [
        p for p, cfg in settings.PARKS.items()
        if all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")])
    ]

    # Subquery: revenue per vehicle's driver in last 7 days
    _vrev_cats = [
        "Оплата картой", "Наличные", "Корпоративная оплата",
        "Оплата через терминал", "Оплата электронным кошельком",
        "Оплата промокодом", "Компенсация оплаты поездки",
        "Оплата картой, поездка партнёра", "Наличные, поездка партнёра",
    ]
    since_7d = datetime.now() - timedelta(days=7)
    vrev_sub = (
        select(
            Transaction.yandex_driver_id,
            func.sum(Transaction.amount).label("vrev7"),
            func.count(Transaction.id).label("vtrips7"),
        )
        .where(
            Transaction.date >= since_7d,
            Transaction.amount > 0,
            Transaction.category.in_(_vrev_cats),
        )
        .group_by(Transaction.yandex_driver_id)
    ).subquery()

    # Subquery: активность за 24 часа (поездки или транзакции)
    since_24h = datetime.now() - timedelta(hours=24)
    activity_sub = (
        select(
            Transaction.yandex_driver_id,
            func.count(Transaction.id).label("trips_24h"),
        )
        .where(
            Transaction.date >= since_24h,
            Transaction.amount != 0,  # Любые транзакции = активность
        )
        .group_by(Transaction.yandex_driver_id)
    ).subquery()

    # Базовый запрос: наш флот + driver data + revenue + activity
    stmt = (
        select(
            Vehicle,
            User.full_name.label("driver_name"),
            User.username.label("driver_phone"),
            User.realtime_status.label("driver_status"),
            User.yandex_rating.label("driver_yandex_rating"),
            User.created_at.label("driver_updated_at"),
            func.coalesce(vrev_sub.c.vrev7, 0).label("vrev7"),
            func.coalesce(vrev_sub.c.vtrips7, 0).label("vtrips7"),
            func.coalesce(activity_sub.c.trips_24h, 0).label("trips_24h"),
        )
        .outerjoin(User, or_(
            Vehicle.current_driver_id == User.id,
            User.current_vehicle_id == Vehicle.id,
        ))
        .outerjoin(
            vrev_sub,
            or_(
                User.yandex_driver_id == vrev_sub.c.yandex_driver_id,
                User.yandex_contractor_id == vrev_sub.c.yandex_driver_id,
            ),
        )
        .outerjoin(
            activity_sub,
            or_(
                User.yandex_driver_id == activity_sub.c.yandex_driver_id,
                User.yandex_contractor_id == activity_sub.c.yandex_driver_id,
            ),
        )
    )
    
    # Фильтр: Активные (по умолчанию) или Все (архив)
    if not include_archive:
        # АКТИВНЫЕ: is_active_dominion=True (наш флот)
        stmt = stmt.where(Vehicle.is_active_dominion == True)
    else:
        # АРХИВ: все машины с is_active=True
        stmt = stmt.where(Vehicle.is_active == True)
    
    if _active_parks:
        stmt = stmt.where(Vehicle.park_name.in_(_active_parks))

    if owner == "park":
        stmt = stmt.where(Vehicle.is_park_car == True)
    elif owner == "private":
        stmt = stmt.where(Vehicle.is_park_car == False)
    if park and park.upper() != "ALL":
        stmt = stmt.where(Vehicle.park_name == park.upper())

    rows = (await db.execute(stmt)).all()
    seen_ids = set()
    items = []
    for v, driver_name, driver_phone, driver_status, driver_yandex_rating, driver_updated_at, vrev7, vtrips7, trips_24h in rows:
        if v.id in seen_ids:
            continue
        seen_ids.add(v.id)
        
        # v33.0: Определяем АКТИВНОСТЬ за 24 часа
        is_active_24h = False
        vehicle_updated = getattr(v, "updated_at", None)
        
        # Проверяем поездки за 24 часа
        if trips_24h and trips_24h > 0:
            is_active_24h = True
        # Проверяем обновление статуса машины за 24 часа
        elif vehicle_updated:
            try:
                if hasattr(vehicle_updated, 'tzinfo') and vehicle_updated.tzinfo:
                    vehicle_updated = vehicle_updated.replace(tzinfo=None)
                if vehicle_updated >= since_24h:
                    is_active_24h = True
            except Exception:
                pass
        # Проверяем обновление водителя за 24 часа
        elif driver_updated_at:
            try:
                if hasattr(driver_updated_at, 'tzinfo') and driver_updated_at.tzinfo:
                    driver_updated_at = driver_updated_at.replace(tzinfo=None)
                if driver_updated_at >= since_24h:
                    is_active_24h = True
            except Exception:
                pass
        
        # v35.1: Статус СТРОГО из Яндекс API (§2 Библии)
        # ЗАКОН: yandex_status → vehicle.status → fallback
        # Если Яндекс говорит working — РАБОТАЕТ, точка. Без проверки водителя.
        yandex_status = getattr(v, "yandex_status", None) or None
        local_status = (v.status or "").strip().lower()
        
        # Приоритет 1: yandex_status напрямую из Яндекс API
        if yandex_status == "working":
            detail_status = "working"
        elif yandex_status == "not_working":
            detail_status = "no_driver"
        elif yandex_status in ("blocked", "repairing"):
            detail_status = "service"
        # Приоритет 2: vehicle.status из БД (заполняется при синхронизации v35.1)
        elif local_status == "working":
            detail_status = "working"
        elif local_status == "not_working":
            detail_status = "no_driver"
        elif local_status in ("service", "maintenance", "offline", "debt_lock", "blocked", "repairing"):
            detail_status = "service"
        elif local_status == "preparing":
            detail_status = "preparing"
        elif local_status == "no_driver":
            detail_status = "no_driver"
        # Приоритет 3: fallback
        else:
            detail_status = "other"
        
        # v33.0: Парковый признак для топа списка
        is_park_car = bool(v.is_park_car)
        
        items.append({
            "id": v.id,
            "license_plate": v.license_plate or "—",
            "brand": v.brand or "",
            "model": v.model or "",
            "year": getattr(v, "year", None) or "",
            "status": detail_status,
            "yandex_status": yandex_status,
            "callsign": v.callsign or "—",
            "vin": v.vin or "—",
            "sts_number": getattr(v, "sts_number", None) or "—",
            "park_name": (v.park_name or "PRO").upper(),
            "is_park_car": is_park_car,
            "ownership_type": str(v.ownership_type.value if v.ownership_type else "connected"),
            "driver_name": driver_name or "—",
            "driver_phone": driver_phone or "—",
            "yandex_rating": driver_yandex_rating,
            "revenue_7d": round(float(vrev7 or 0), 0),
            "trips_7d": int(vtrips7 or 0),
            "trips_24h": int(trips_24h or 0),
            "is_active_24h": is_active_24h,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        })

    # v33.0: СОРТИРОВКА — Парковый в топе, потом по госномеру
    items.sort(key=lambda x: (0 if x["is_park_car"] else 1, x["license_plate"]))

    # Счётчики по паркам
    if not include_archive:
        counts_base = Vehicle.is_active_dominion == True
    else:
        counts_base = Vehicle.is_active == True
    if _active_parks:
        counts_base = and_(counts_base, Vehicle.park_name.in_(_active_parks))
    _park_col = func.upper(func.coalesce(Vehicle.park_name, "PRO"))
    counts_stmt = (
        select(_park_col.label("park"), func.count(Vehicle.id))
        .where(counts_base)
    )
    if owner == "park":
        counts_stmt = counts_stmt.where(Vehicle.is_park_car == True)
    elif owner == "private":
        counts_stmt = counts_stmt.where(Vehicle.is_park_car == False)
    counts_stmt = counts_stmt.group_by(_park_col)
    count_rows = (await db.execute(counts_stmt)).all()
    
    # Подсчёт активных за 24 часа
    active_24h_count = sum(1 for item in items if item["is_active_24h"])
    park_cars_count = sum(1 for item in items if item["is_park_car"])
    
    counts = {
        "ALL": sum(c[1] for c in count_rows),
        "active_24h": active_24h_count,
        "park_cars": park_cars_count,
    }
    for row in count_rows:
        counts[row[0]] = row[1]
    
    return JSONResponse(content={
        "vehicles": items, 
        "counts": counts,
        "include_archive": include_archive,
    })


# API: Drivers list data — ТОЛЬКО активные парки + привязка к машинам
@router.get("/drivers-list-data")
async def get_drivers_list_data(
    filter_type: Optional[str] = None,
    q: Optional[str] = None,
    park: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    if current_user and not current_user.can_see_fleet and getattr(current_user, "role", "").lower() != "master":
        return JSONResponse(status_code=403, content={"error": "forbidden"})

    # Определяем активные парки
    _active_parks = [
        p for p, cfg in settings.PARKS.items()
        if all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")])
    ]

    # Категории доходных транзакций (поездки)
    _rev7_cats = [
        "Оплата картой", "Наличные", "Корпоративная оплата",
        "Оплата через терминал", "Оплата электронным кошельком",
        "Оплата промокодом", "Компенсация оплаты поездки",
        "Оплата картой, поездка партнёра", "Наличные, поездка партнёра",
    ]
    since_7d = datetime.now() - timedelta(days=7)
    since_30d = datetime.now() - timedelta(days=30)

    # Subquery: revenue & trips per driver in last 7 days
    rev_sub = (
        select(
            Transaction.yandex_driver_id,
            func.sum(Transaction.amount).label("rev7"),
            func.count(Transaction.id).label("trips7"),
        )
        .where(
            Transaction.date >= since_7d,
            Transaction.amount > 0,
            Transaction.category.in_(_rev7_cats),
        )
        .group_by(Transaction.yandex_driver_id)
    ).subquery()

    # Subquery: last order date per driver (для фильтра «Активные 30 дней»)
    last_order_sub = (
        select(
            Transaction.yandex_driver_id,
            func.max(Transaction.date).label("last_order_date"),
        )
        .where(
            Transaction.amount > 0,
            Transaction.category.in_(_rev7_cats),
        )
        .group_by(Transaction.yandex_driver_id)
    ).subquery()

    stmt = (
        select(
            User,
            Vehicle.license_plate.label("vehicle_plate"),
            func.coalesce(rev_sub.c.rev7, 0).label("rev7"),
            func.coalesce(rev_sub.c.trips7, 0).label("trips7"),
            last_order_sub.c.last_order_date.label("last_order_date"),
        )
        .outerjoin(Vehicle, User.current_vehicle_id == Vehicle.id)
        .outerjoin(
            rev_sub,
            or_(
                User.yandex_driver_id == rev_sub.c.yandex_driver_id,
                User.yandex_contractor_id == rev_sub.c.yandex_driver_id,
            ),
        )
        .outerjoin(
            last_order_sub,
            or_(
                User.yandex_driver_id == last_order_sub.c.yandex_driver_id,
                User.yandex_contractor_id == last_order_sub.c.yandex_driver_id,
            ),
        )
        .where(
            or_(
                User.yandex_driver_id.isnot(None),
                User.yandex_contractor_id.isnot(None),
            )
        )
        .order_by(User.full_name)
    )
    if _active_parks:
        stmt = stmt.where(User.park_name.in_(_active_parks))

    if filter_type == "archive":
        stmt = stmt.where(User.is_archived == True)
    elif filter_type == "active":
        # АКТИВНЫЕ = последний заказ не старше 30 дней (цель ~89)
        stmt = stmt.where(
            User.is_archived == False,
            last_order_sub.c.last_order_date >= since_30d,
        )
    elif filter_type == "warnings":
        # ДОЛГ = баланс строго < 0 (исключить нули)
        stmt = stmt.where(User.is_archived == False, User.driver_balance < 0)
    else:
        stmt = stmt.where(User.is_archived == False)
    if q and q.strip():
        q_p = f"%{(q or '').strip().lower().replace(' ', '%')}%"
        stmt = stmt.where(or_(User.full_name.ilike(q_p), User.username.ilike(q_p)))
    if park and park.upper() != "ALL":
        stmt = stmt.where(User.park_name == park.upper())

    rows = (await db.execute(stmt)).all()
    drivers = []
    for u, vehicle_plate, rev7, trips7, last_order_date in rows:
        # v35.1: Статус как в Яндексе — work_status + realtime_status
        ws = (u.work_status or "not_working").lower()
        rs = (getattr(u, "realtime_status", None) or "offline").lower()
        
        # Маппинг статуса для отображения (зеркало Яндекса)
        if ws == "working":
            if rs in ("busy", "on_order"):
                display_status = "busy"
            elif rs == "online":
                display_status = "online"
            else:
                display_status = "online"  # working но не busy = онлайн
        elif ws == "fired":
            display_status = "fired"
        elif ws == "blocked":
            display_status = "blocked"
        else:
            display_status = "offline"
        
        # Баланс — как есть из Яндекса (может быть отрицательным)
        balance = round(float(getattr(u, "driver_balance", 0) or 0), 2)
        balance_limit = round(float(getattr(u, "balance_limit", 5) or 5), 0)
        
        # ВУ — срок действия
        license_expiry = None
        license_number = getattr(u, "license_number", None)
        if hasattr(u, "license_expiry_date") and u.license_expiry_date:
            license_expiry = u.license_expiry_date.isoformat()
        
        # Стаж
        experience_from = None
        if hasattr(u, "driving_experience_from") and u.driving_experience_from:
            experience_from = u.driving_experience_from.isoformat()
        
        # Дата принятия
        hire_date = None
        if hasattr(u, "hire_date") and u.hire_date:
            hire_date = u.hire_date.isoformat()
        
        drivers.append({
            "id": u.id,
            "full_name": u.full_name or "—",
            "phone": u.username or "—",
            "park_name": (u.park_name or "PRO").upper(),
            "photo_url": getattr(u, "photo_url", None),
            "driver_balance": balance,
            "balance_limit": balance_limit,
            "vehicle_plate": vehicle_plate or _extract_car_number(u) or "—",
            "revenue_7d": round(float(rev7 or 0), 0),
            "trips_7d": int(trips7 or 0),
            "work_status": ws,
            "realtime_status": rs,
            "status": display_status,
            "rating": round(float(getattr(u, "yandex_rating", None) or getattr(u, "rating", None) or 0), 2),
            "license_number": license_number,
            "license_expiry": license_expiry,
            "experience_from": experience_from,
            "hire_date": hire_date,
        })

    # Счётчики — текущий набор (уже отфильтрован)
    counts = {"ALL": len(drivers)}
    for d in drivers:
        pk = d["park_name"]
        counts[pk] = counts.get(pk, 0) + 1

    # EXORCISM v200.11: Реальный счётчик «Активные 30д» — водители с заказами за 30 дней
    active_30d_stmt = select(func.count(distinct(Transaction.yandex_driver_id))).where(
        and_(
            Transaction.yandex_driver_id.isnot(None),
            Transaction.date >= since_30d,
            Transaction.amount > 0,
            Transaction.category.in_(_rev7_cats),
        )
    )
    active_30d_count = (await db.execute(active_30d_stmt)).scalar() or 0

    return JSONResponse(content={
        "drivers": drivers,
        "counts": counts,
        "active_30d": active_30d_count,
    })


# API: Calendar — ЖИВОЙ календарь списаний по дням (привязка через yandex_driver_id)
# Связь: Vehicle.yandex_driver_id → Transaction.yandex_driver_id + Vehicle.license_plate → Transaction.plate_info
@router.get("/calendar-data")
async def get_calendar_data(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    park: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.can_see_fleet and getattr(current_user, "role", "").lower() != "master":
        return JSONResponse(status_code=403, content={"error": "forbidden"})

    # Активные парки
    _active_parks = [
        p for p, cfg in settings.PARKS.items()
        if all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")])
    ]

    from datetime import datetime as dt_parse
    try:
        fd = dt_parse.fromisoformat(from_date.replace("Z", "+00:00")).date() if from_date else (datetime.now().date() - timedelta(days=7))
        td = dt_parse.fromisoformat(to_date.replace("Z", "+00:00")).date() if to_date else datetime.now().date()
    except Exception:
        fd = datetime.now().date() - timedelta(days=7)
        td = datetime.now().date()

    # 1. Наш флот (is_active_dominion) + связанный водитель + его yandex_driver_id
    v_stmt = (
        select(
            Vehicle.id, Vehicle.license_plate, Vehicle.brand, Vehicle.model,
            User.yandex_driver_id.label("driver_yandex_id"),  # Yandex ID водителя для привязки транзакций
            Vehicle.park_name,
            User.full_name.label("driver_name"),
        )
        .outerjoin(User, Vehicle.current_driver_id == User.id)
        .where(Vehicle.is_active_dominion == True)
        .order_by(Vehicle.license_plate)
    )
    if _active_parks:
        v_stmt = v_stmt.where(Vehicle.park_name.in_(_active_parks))
    if park and park.upper() != "ALL":
        v_stmt = v_stmt.where(Vehicle.park_name == park.upper())
    vehicles = (await db.execute(v_stmt)).all()

    # 2. Собираем yandex_driver_id (водителя!) и plate для привязки транзакций
    yandex_ids = set()
    plate_map = {}  # normalized_plate -> vehicle_index
    for i, v in enumerate(vehicles):
        if v.driver_yandex_id:
            yandex_ids.add(v.driver_yandex_id)
        plate_norm = (v.license_plate or "").replace(" ", "").upper()
        if plate_norm:
            plate_map[plate_norm] = i

    # 3. Транзакции за период — привязка через yandex_driver_id ИЛИ plate_info
    tx_filters = and_(
        Transaction.date >= datetime.combine(fd, datetime.min.time()),
        Transaction.date <= datetime.combine(td, datetime.max.time()),
        Transaction.amount != 0,
    )
    if _active_parks:
        tx_filters = and_(tx_filters, Transaction.park_name.in_(_active_parks))
    if park and park.upper() != "ALL":
        tx_filters = and_(tx_filters, Transaction.park_name == park.upper())

    tx_stmt = (
        select(
            Transaction.yandex_driver_id,
            Transaction.plate_info,
            func.date(Transaction.date).label("tx_day"),
            func.sum(Transaction.amount).label("total"),
        )
        .where(tx_filters)
        .group_by(Transaction.yandex_driver_id, Transaction.plate_info, func.date(Transaction.date))
    )
    tx_rows = (await db.execute(tx_stmt)).all()

    # 4. Индекс: yandex_driver_id водителя -> [vehicle_indices]
    yid_to_vidx = {}
    for i, v in enumerate(vehicles):
        if v.driver_yandex_id:
            yid_to_vidx.setdefault(v.driver_yandex_id, []).append(i)

    # 5. Строим сетку
    days = []
    d = fd
    while d <= td:
        days.append(d.isoformat())
        d += timedelta(days=1)

    # Инициализируем суммы
    grid_data = [{} for _ in vehicles]  # day -> amount

    for tx in tx_rows:
        day_str = str(tx.tx_day) if tx.tx_day else ""
        amount = float(tx.total or 0)
        matched = False

        # Приоритет 1: по yandex_driver_id
        if tx.yandex_driver_id and tx.yandex_driver_id in yid_to_vidx:
            for idx in yid_to_vidx[tx.yandex_driver_id]:
                grid_data[idx][day_str] = grid_data[idx].get(day_str, 0) + amount
            matched = True

        # Приоритет 2: по plate_info
        if not matched and tx.plate_info:
            plate_norm = str(tx.plate_info).replace(" ", "").upper()
            if plate_norm in plate_map:
                idx = plate_map[plate_norm]
                grid_data[idx][day_str] = grid_data[idx].get(day_str, 0) + amount

    grid = []
    for i, v in enumerate(vehicles):
        row = {
            "vehicle_id": v.id,
            "plate": v.license_plate or "—",
            "brand": v.brand or "",
            "model": v.model or "",
            "driver_name": v.driver_name or "—",
            "park_name": (v.park_name or "PRO").upper(),
            "days": {},
        }
        for day in days:
            row["days"][day] = round(grid_data[i].get(day, 0), 2)
        grid.append(row)

    # 6. Итоги по дням (для нижней строки)
    totals = {}
    for day in days:
        totals[day] = round(sum(g["days"].get(day, 0) for g in grid), 2)

    return JSONResponse(content={"vehicles": grid, "days": days, "totals": totals})


# API: Periodic charges — финансовые правила (ContractTerm + rent-terms из Яндекса)
# Только для нашего активного флота (is_active_dominion=True)
@router.get("/periodic-charges-data")
async def get_periodic_charges_data(
    park: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    МАТРИЦА ЗАКОНОВ v3.1 — Единый Источник Истины.
    Начинаем от 41 борта (is_active_dominion + SUBLEASE),
    через User.current_vehicle_id находим текущего водителя,
    через ContractTerm получаем тариф.
    """
    if not current_user.can_see_fleet and getattr(current_user, "role", "").lower() != "master":
        return JSONResponse(status_code=403, content={"error": "forbidden"})

    from sqlalchemy import literal_column

    # ── 1. Все «живые» борты Dominion ──
    # Начинаем от Vehicle → User (current_vehicle_id) → ContractTerm
    # DISTINCT ON (v.id) — один борт = одна строка (последний CT)
    v_stmt = text("""
        SELECT DISTINCT ON (v.id)
            v.id AS vehicle_id,
            v.license_plate,
            v.brand,
            v.model,
            v.ownership_type,
            v.park_name AS v_park,
            v.is_active_dominion,
            u.id AS driver_id,
            u.full_name AS driver_name,
            u.work_status,
            ct.id AS ct_id,
            ct.driver_daily_rent,
            ct.partner_daily_rent,
            ct.commission_rate,
            ct.day_off_rate,
            ct.is_repair,
            ct.is_day_off,
            ct.is_idle,
            ct.created_at AS ct_created,
            ct.updated_at AS ct_updated
        FROM vehicles v
        LEFT JOIN users u
            ON u.current_vehicle_id = v.id AND u.is_active = true
        LEFT JOIN contract_terms ct
            ON ct.driver_id = u.id AND ct.driver_daily_rent > 0
        WHERE v.is_active_dominion = true
        ORDER BY v.id, ct.updated_at DESC NULLS LAST
    """)
    rows = (await db.execute(v_stmt)).all()

    charges = []
    for r in rows:
        has_driver = r.driver_id is not None
        has_ct = r.ct_id is not None

        # Статус определяем по реальному состоянию борта
        if has_ct and r.is_repair:
            charge_status = "repair"
        elif has_ct and r.is_day_off:
            charge_status = "day_off"
        elif has_ct and r.is_idle:
            charge_status = "idle"
        elif has_driver and has_ct:
            charge_status = "active"
        elif has_driver and not has_ct:
            charge_status = "active"  # Водитель есть, но нет ContractTerm (тариф по умолчанию)
        else:
            charge_status = "no_driver"

        ownership = (r.ownership_type or "CONNECTED").upper()
        daily_rent = float(r.driver_daily_rent or 0)

        charges.append({
            "id": r.vehicle_id,   # Используем vehicle_id как основной ID
            "ct_id": r.ct_id,
            "status": charge_status,
            "park_name": (r.v_park or "PRO").upper(),
            "created_at": r.ct_created.isoformat() if r.ct_created else None,
            "updated_at": r.ct_updated.isoformat() if r.ct_updated else None,
            "driver_name": r.driver_name or "—",
            "vehicle_plate": r.license_plate or "—",
            "vehicle_info": f"{r.brand or ''} {r.model or ''}".strip() or "—",
            "ownership": ownership,
            "partner_rent": round(float(r.partner_daily_rent or 0), 2),
            "driver_rent": round(daily_rent, 2),
            "commission_rate": round(float(r.commission_rate or 0) * 100, 1),
            "day_off_rate": round(float(r.day_off_rate or 0), 2),
            "is_repair": bool(r.is_repair) if r.is_repair is not None else False,
            "is_day_off": bool(r.is_day_off) if r.is_day_off is not None else False,
            "is_idle": bool(r.is_idle) if r.is_idle is not None else False,
            "meta": {},
        })

    # Счётчики
    total = len(charges)
    sublease = sum(1 for c in charges if c["ownership"] == "SUBLEASE")
    connected = sum(1 for c in charges if c["ownership"] == "CONNECTED")
    counts = {"ALL": total, "SUBLEASE": sublease, "CONNECTED": connected}

    return JSONResponse(content={"charges": charges, "counts": counts})


# ──────────────────────────────────────────────────────────
# ДВОРЕЦ «КАЛЕНДАРЬ РЕНТЫ» — Сетка Времени v3.0
# ──────────────────────────────────────────────────────────

@router.get("/rent-calendar-data")
async def get_rent_calendar_data(
    year: Optional[int] = None,
    month: Optional[int] = None,
    ownership: Optional[str] = None,   # sublease | connected | all
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    КАЛЕНДАРЬ РЕНТЫ v3.1 — Единый Источник Истины.
    Начинаем от Vehicles (is_active_dominion) → User (current_vehicle_id) → ContractTerm.
    Для списаний: FinancialLog + Яндекс «Платежи по расписанию».
    """
    if not current_user.can_see_fleet and getattr(current_user, "role", "").lower() != "master":
        return JSONResponse(status_code=403, content={"error": "forbidden"})

    import calendar as cal_mod
    from app.models.all_models import FinancialLog
    from datetime import date as date_type

    now = datetime.now()
    y = year or now.year
    m = month or now.month
    _, days_in_month = cal_mod.monthrange(y, m)
    today = now.date()

    month_start = datetime(y, m, 1)
    month_end = datetime(y, m, days_in_month, 23, 59, 59)

    # ── 1. Выбираем борты + связь через User.current_vehicle_id ──
    # OwnershipType хранится как VARCHAR → сравниваем строками
    ownership_where = ""
    if ownership == "sublease":
        ownership_where = "AND v.ownership_type = 'SUBLEASE'"
    elif ownership == "connected":
        ownership_where = "AND v.ownership_type = 'CONNECTED'"

    v_sql = text(f"""
        SELECT DISTINCT ON (v.id)
            v.id,
            v.license_plate,
            v.brand,
            v.model,
            v.ownership_type,
            v.park_name,
            u.id AS driver_id,
            u.full_name AS driver_name,
            u.yandex_driver_id,
            ct.driver_daily_rent,
            ct.is_repair,
            ct.is_day_off,
            ct.is_idle
        FROM vehicles v
        LEFT JOIN users u
            ON u.current_vehicle_id = v.id AND u.is_active = true
        LEFT JOIN contract_terms ct
            ON ct.driver_id = u.id AND ct.driver_daily_rent > 0
        WHERE v.is_active_dominion = true {ownership_where}
        ORDER BY v.id, ct.updated_at DESC NULLS LAST
    """)
    vehicles = (await db.execute(v_sql)).all()

    if not vehicles:
        return JSONResponse(content={
            "vehicles": [], "days": [], "month": m, "year": y,
            "totals": {}, "summary": {}
        })

    vehicle_ids = [v.id for v in vehicles]

    # ── 2. FinancialLog (auto_deduction) за месяц ──
    fl_stmt = (
        select(
            FinancialLog.vehicle_id,
            func.date(FinancialLog.created_at).label("log_day"),
            func.sum(FinancialLog.amount).label("charged"),
            func.count(FinancialLog.id).label("cnt"),
        )
        .where(
            FinancialLog.vehicle_id.in_(vehicle_ids),
            FinancialLog.entry_type == "auto_deduction",
            FinancialLog.created_at >= month_start,
            FinancialLog.created_at <= month_end,
        )
        .group_by(FinancialLog.vehicle_id, func.date(FinancialLog.created_at))
    )
    fl_rows = (await db.execute(fl_stmt)).all()

    charge_map = {}
    for row in fl_rows:
        key = (row.vehicle_id, str(row.log_day))
        charge_map[key] = {
            "amount": round(float(row.charged or 0), 2),
            "count": int(row.cnt or 0),
        }

    # ── 3. Яндекс «Платежи по расписанию» (аренда) через yandex_driver_id ──
    yandex_driver_ids = [v.yandex_driver_id for v in vehicles if v.yandex_driver_id]
    ydid_to_vid = {}
    for v in vehicles:
        if v.yandex_driver_id:
            ydid_to_vid[v.yandex_driver_id] = v.id

    yandex_charge_map = {}
    if yandex_driver_ids:
        yandex_tx_stmt = (
            select(
                Transaction.yandex_driver_id,
                func.date(Transaction.date).label("tx_day"),
                func.sum(func.abs(Transaction.amount)).label("charged"),
            )
            .where(
                Transaction.yandex_driver_id.in_(yandex_driver_ids),
                Transaction.category == "Платежи по расписанию",
                Transaction.date >= month_start,
                Transaction.date <= month_end,
            )
            .group_by(Transaction.yandex_driver_id, func.date(Transaction.date))
        )
        ytx_rows = (await db.execute(yandex_tx_stmt)).all()
        for row in ytx_rows:
            vid = ydid_to_vid.get(row.yandex_driver_id)
            if vid:
                key = (vid, str(row.tx_day))
                yandex_charge_map[key] = round(float(row.charged or 0), 2)

    # ── 4. Строим сетку ──
    days = []
    for d in range(1, days_in_month + 1):
        days.append(date_type(y, m, d).isoformat())

    grid = []
    summary_paid = 0
    summary_debt = 0
    summary_total_expected = 0
    day_totals = {day: {"paid": 0, "debt": 0, "expected": 0} for day in days}

    for v in vehicles:
        daily_rent = float(v.driver_daily_rent or 0)
        is_repair = bool(v.is_repair) if v.is_repair is not None else False
        is_day_off = bool(v.is_day_off) if v.is_day_off is not None else False
        is_idle = bool(v.is_idle) if v.is_idle is not None else False
        row_days = {}

        for day in days:
            day_date = date_type.fromisoformat(day)
            is_future = day_date > today

            # Ищем списание: сначала FinancialLog, потом Яндекс «Платежи по расписанию»
            fl_entry = charge_map.get((v.id, day))
            yx_entry = yandex_charge_map.get((v.id, day), 0)
            charged = fl_entry["amount"] if fl_entry else yx_entry

            if is_future:
                status = "future"
                expected = daily_rent
            elif is_repair:
                status = "repair"
                expected = 0
            elif is_day_off:
                status = "day_off"
                expected = 0
            elif is_idle:
                status = "idle"
                expected = 0
            elif charged > 0:
                status = "paid"
                expected = daily_rent
                summary_paid += charged
                day_totals[day]["paid"] += charged
            else:
                if daily_rent > 0:
                    status = "debt"
                    summary_debt += daily_rent
                    day_totals[day]["debt"] += daily_rent
                else:
                    status = "no_rent"
                expected = daily_rent

            if not is_future:
                summary_total_expected += expected
                day_totals[day]["expected"] += expected

            row_days[day] = {
                "status": status,
                "charged": round(charged, 2),
                "expected": round(daily_rent, 2),
            }

        ownership_str = (v.ownership_type or "CONNECTED").upper()

        grid.append({
            "vehicle_id": v.id,
            "plate": v.license_plate or "—",
            "brand": v.brand or "",
            "model": v.model or "",
            "driver_id": v.driver_id,
            "driver_name": v.driver_name or "—",
            "ownership": ownership_str,
            "park_name": (v.park_name or "PRO").upper(),
            "daily_rent": round(daily_rent, 2),
            "is_repair": is_repair,
            "is_day_off": is_day_off,
            "is_idle": is_idle,
            "days": row_days,
        })

    return JSONResponse(content={
        "vehicles": grid,
        "days": days,
        "month": m,
        "year": y,
        "totals": day_totals,
        "summary": {
            "total_vehicles": len(grid),
            "sublease_count": sum(1 for v in grid if v["ownership"] == "SUBLEASE"),
            "connected_count": sum(1 for v in grid if v["ownership"] == "CONNECTED"),
            "total_paid": round(summary_paid, 2),
            "total_debt": round(summary_debt, 2),
            "total_expected": round(summary_total_expected, 2),
            "collection_rate": round(
                (summary_paid / summary_total_expected * 100) if summary_total_expected > 0 else 0, 1
            ),
        },
    })


# ──────────────────────────────────────────────────────────
# УПРАВЛЕНИЕ ТАРИФАМИ — Матрица Законов v3.0
# ──────────────────────────────────────────────────────────

class TariffUpdateRequest(BaseModel):
    vehicle_id: int
    driver_daily_rent: Optional[float] = None
    partner_daily_rent: Optional[float] = None
    commission_rate: Optional[float] = None
    day_off_rate: Optional[float] = None
    is_repair: Optional[bool] = None
    is_day_off: Optional[bool] = None
    is_idle: Optional[bool] = None


class BulkTariffRequest(BaseModel):
    vehicle_ids: List[int]
    driver_daily_rent: Optional[float] = None
    partner_daily_rent: Optional[float] = None


@router.post("/tariff/update")
async def update_vehicle_tariff(
    req: TariffUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Обновить тариф для конкретного борта."""
    if getattr(current_user, "role", "").lower() != "master":
        return JSONResponse(status_code=403, content={"error": "Только Мастер может менять тарифы"})

    # Найдём или создадим ContractTerm для этого борта
    stmt = select(ContractTerm).where(
        ContractTerm.vehicle_id == req.vehicle_id,
        ContractTerm.is_default == False,
    ).order_by(ContractTerm.updated_at.desc())
    ct = (await db.execute(stmt)).scalar_one_or_none()

    if not ct:
        vehicle = await db.get(Vehicle, req.vehicle_id)
        if not vehicle:
            return JSONResponse(status_code=404, content={"error": "Борт не найден"})
        ct = ContractTerm(
            vehicle_id=req.vehicle_id,
            driver_id=vehicle.current_driver_id,
            park_name=vehicle.park_name or "PRO",
        )
        db.add(ct)

    if req.driver_daily_rent is not None:
        ct.driver_daily_rent = req.driver_daily_rent
    if req.partner_daily_rent is not None:
        ct.partner_daily_rent = req.partner_daily_rent
    if req.commission_rate is not None:
        ct.commission_rate = req.commission_rate
    if req.day_off_rate is not None:
        ct.day_off_rate = req.day_off_rate
    if req.is_repair is not None:
        ct.is_repair = req.is_repair
    if req.is_day_off is not None:
        ct.is_day_off = req.is_day_off
    if req.is_idle is not None:
        ct.is_idle = req.is_idle
    ct.updated_at = datetime.now()

    await db.commit()
    return JSONResponse(content={"status": "ok", "contract_id": ct.id})


@router.post("/tariff/bulk-update")
async def bulk_update_tariffs(
    req: BulkTariffRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Массовое обновление тарифов для группы машин."""
    if getattr(current_user, "role", "").lower() != "master":
        return JSONResponse(status_code=403, content={"error": "Только Мастер"})

    updated = 0
    for vid in req.vehicle_ids:
        stmt = select(ContractTerm).where(
            ContractTerm.vehicle_id == vid,
            ContractTerm.is_default == False,
        ).order_by(ContractTerm.updated_at.desc())
        ct = (await db.execute(stmt)).scalar_one_or_none()

        if not ct:
            vehicle = await db.get(Vehicle, vid)
            if not vehicle:
                continue
            ct = ContractTerm(
                vehicle_id=vid,
                driver_id=vehicle.current_driver_id,
                park_name=vehicle.park_name or "PRO",
            )
            db.add(ct)

        if req.driver_daily_rent is not None:
            ct.driver_daily_rent = req.driver_daily_rent
        if req.partner_daily_rent is not None:
            ct.partner_daily_rent = req.partner_daily_rent
        ct.updated_at = datetime.now()
        updated += 1

    await db.commit()
    return JSONResponse(content={"status": "ok", "updated": updated})


@router.post("/tariff/trigger-deduction")
async def trigger_manual_deduction(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ручной запуск суточного списания (по приказу Мастера)."""
    if getattr(current_user, "role", "").lower() != "master":
        return JSONResponse(status_code=403, content={"error": "Только Мастер"})

    from app.services.ledger_engine import LedgerEngine
    result = await LedgerEngine.run_daily_deductions()
    return JSONResponse(content=result)
