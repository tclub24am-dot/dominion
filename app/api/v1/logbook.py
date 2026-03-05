# -*- coding: utf-8 -*-
# app/routes/logbook.py

import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import joinedload
from pydantic import BaseModel

from app.database import get_db
from app.services.auth import get_current_user
# Если Redis пока не настроен в database.py, можно временно закомментировать зависимость
try:
    from app.database import get_redis
except ImportError:
    get_redis = lambda: None

from app.models.all_models import TripSheet, TripStatus, User, Vehicle, OwnershipType
from app.services.kis_art import KisArtService

logger = logging.getLogger("Dominion.Logbook")

# v22.1: Prefix добавляется в main.py, здесь не нужен!
router = APIRouter(tags=["Бортжурнал: Пульс Линии"])

# --- СХЕМЫ ДАННЫХ (Schemas) ---

class ReleaseResponse(BaseModel):
    trip_id: int
    trip_number: str
    status: str
    kis_art_id: Optional[str] = None
    message: str

# --- ЭНДПОИНТЫ ---

@router.post("/release/{trip_id}", response_model=ReleaseResponse)
async def release_to_line(
    trip_id: int, 
    use_kis_art: bool = Query(True, description="Включить/выключить передачу в КИС АРТ"), 
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis)
):
    """
    РИТУАЛ ВЫПУСКА: Проверка готовности и активация путевого листа.
    """
    try:
        # 1. ЗАГРУЗКА ПУТЕВОГО ЛИСТА С ПРОВЕРКАМИ
        stmt = (
            select(TripSheet)
            .options(
                joinedload(TripSheet.medical_check),
                joinedload(TripSheet.technical_check),
                joinedload(TripSheet.driver),
                joinedload(TripSheet.vehicle)
            )
            .where(TripSheet.id == trip_id)
        )
        result = await db.execute(stmt)
        trip = result.scalar_one_or_none()

        if not trip:
            raise HTTPException(status_code=404, detail="Путевой лист не найден в Цитадели")

        if trip.status == TripStatus.ACTIVE:
            raise HTTPException(status_code=400, detail="Воин уже находится на линии")

        # 2. ГВАРДЕЙСКИЕ ПРОВЕРКИ (Guard Clauses)
        if not trip.medical_check or not trip.medical_check.is_fit:
            logger.error(f"RELEASE DENIED: Воин {trip.driver.full_name} не прошел медосмотр")
            raise HTTPException(status_code=400, detail="Выпуск запрещен: Нет допуска медика!")
        
        if not trip.technical_check or not trip.technical_check.is_passed:
            logger.error(f"RELEASE DENIED: Колесница {trip.vehicle.license_plate} неисправна")
            raise HTTPException(status_code=400, detail="Выпуск запрещен: Нет допуска механика!")

        # 3. ИНТЕГРАЦИЯ КИС АРТ (Сервисный слой)
        kis_service = KisArtService(db=db, redis_client=redis)
        kis_result = await kis_service.sign_waybill(
            trip_id=trip.id, 
            use_kis_art=use_kis_art
        )
        
        if not kis_result.get("success"):
            logger.error(f"KIS ART REJECT: {kis_result.get('message')}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, 
                detail=f"Отказ КИС АРТ: {kis_result.get('message')}"
            )

        # 4. ОБНОВЛЕНИЕ СОСТОЯНИЯ (Запись в вечность)
        trip.status = TripStatus.ACTIVE
        trip.kis_art_sent = use_kis_art
        trip.kis_art_response = kis_result  # Ответ сервера КИС АРТ
        trip.start_time = datetime.now()
        
        await db.commit()
        logger.info(f"SUCCESS: Путевой {trip.trip_number} активирован для {trip.driver.full_name}")

        return ReleaseResponse(
            trip_id=trip.id,
            trip_number=trip.trip_number,
            status="ACTIVE",
            kis_art_id=kis_result.get("kis_art_id"),
            message=f"Воин выпущен. Статус КИС АРТ: {kis_result.get('message')}"
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        await db.rollback()
        logger.error(f"CRITICAL ERROR IN LOGBOOK: {e}")
        raise HTTPException(status_code=500, detail="Сбой внутренней логики выпуска")

@router.get("/data")
async def logbook_data(db: AsyncSession = Depends(get_db)):
    """
    Данные для генератора путевых листов (v22.1)
    Возвращает списки водителей и машин
    """
    try:
        # Получаем водителей
        stmt = select(User).where(User.role == "Driver").order_by(User.full_name)
        result = await db.execute(stmt)
        users = result.scalars().all()
        
        drivers = [{"id": u.id, "name": u.full_name} for u in users]
        
        # Получаем машины
        stmt = select(Vehicle).where(Vehicle.status == "working").order_by(Vehicle.license_plate)
        result = await db.execute(stmt)
        vehicles_list = result.scalars().all()
        
        vehicles = [
            {
                "id": v.id,
                "plate": v.license_plate,
                "brand": v.brand or "Unknown",
                "model": v.model
            }
            for v in vehicles_list
        ]
        
        logger.info(f"✓ Logbook data: {len(drivers)} drivers, {len(vehicles)} vehicles")
        
        return {
            "drivers": drivers,
            "vehicles": vehicles
        }
        
    except Exception as e:
        logger.error(f"Logbook data error: {e}")
        return {"drivers": [], "vehicles": []}

@router.get("/recent", response_class=HTMLResponse)
async def logbook_recent(
    request: Request,
    limit: int = 10,
    db: AsyncSession = Depends(get_db)
):
    """
    Последние путевые листы — HTML для HTMX (v22.5)
    """
    try:
        stmt = (
            select(TripSheet)
            .options(
                joinedload(TripSheet.driver),
                joinedload(TripSheet.vehicle)
            )
            .order_by(desc(TripSheet.created_at))
            .limit(limit)
        )
        
        result = await db.execute(stmt)
        trips_db = result.scalars().all()
        
        logger.info(f"✓ Recent trips: {len(trips_db)} records")
        
        trips = [
            {
                "id": t.id,
                "number": t.trip_number,
                "driver": t.driver.full_name if t.driver else "Unknown",
                "vehicle": f"{t.vehicle.license_plate} ({t.vehicle.model})" if t.vehicle else "N/A",
                "status": t.status.value if hasattr(t.status, 'value') else str(t.status),
                "time": t.created_at.strftime("%H:%M %d.%m")
            }
            for t in trips_db
        ]
        
        # Возвращаем HTML template
        from fastapi.templating import Jinja2Templates
        templates = Jinja2Templates(directory="app/templates")
        
        return templates.TemplateResponse(
            "logbook_recent.html",
            {"request": request, "trips": trips}
        )
        
    except Exception as e:
        logger.error(f"Recent trips error: {e}")
        return HTMLResponse(
            content="""
            <div style="text-align: center; padding: 40px; color: var(--text-muted);">
                <i class="fa-solid fa-exclamation-triangle" style="font-size: 32px; color: #ff5252;"></i>
                <p style="margin-top: 12px;">Ошибка загрузки</p>
            </div>
            """,
            status_code=200
        )

@router.post("/generate")
async def generate_trip_sheet(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Генерация путевого листа в PDF (v22.5 - упрощённая версия)
    
    Принимает JSON body напрямую (без Pydantic валидации)
    """
    try:
        from app.services.logbook_service import logbook_service
        
        # Читаем JSON body
        body = await request.json()
        
        driver_id = int(body.get('driver_id', 0))
        vehicle_id = int(body.get('vehicle_id', 0))
        force = bool(body.get('force', False))
        
        logger.info(f"Generate request: driver={driver_id}, vehicle={vehicle_id}, user={current_user.username}")
        
        if not driver_id or not vehicle_id:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "Не указан водитель или машина"}
            )
        
        # Только Мастер может пропускать валидацию
        if force and current_user.role not in ["Master", "Admin"]:
            raise HTTPException(
                status_code=403,
                detail="Только Мастер может пропустить валидацию"
            )
        
        # Генерация
        result = await logbook_service.generate_pdf(
            driver_id=driver_id,
            vehicle_id=vehicle_id,
            db=db,
            force=force
        )
        
        if result["status"] == "blocked":
            # Документы просрочены
            logger.warning(f"⚠ Trip sheet blocked: {result['errors']}")
            return JSONResponse(
                status_code=400,
                content={
                    "status": "blocked",
                    "message": "🛡 Мастер, выпуск данного авто опасен для Империи!",
                    "errors": result["errors"],
                    "hint": "Проверьте документы: ОСАГО, Диагностическую карту, ВУ"
                }
            )
        
        elif result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])
        
        else:
            return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Generate trip sheet error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/journal")
async def get_electronic_journal(
    ownership: Optional[OwnershipType] = None,
    limit: int = 50, 
    db: AsyncSession = Depends(get_db)
):
    """
    ОКО ОРАКУЛА: Электронный журнал путевых листов.
    Позволяет фильтровать по типу владения (субаренда/подключки).
    """
    stmt = (
        select(TripSheet)
        .options(
            joinedload(TripSheet.driver),
            joinedload(TripSheet.vehicle)
        )
        .order_by(desc(TripSheet.created_at))
    )

    # Фильтр для Мастера: смотреть только свои 42 машины или 78 подключек
    if ownership:
        stmt = stmt.join(Vehicle).where(Vehicle.ownership_type == ownership)

    result = await db.execute(stmt.limit(limit))
    trips = result.scalars().all()
    
    return [
        {
            "id": t.id,
            "number": t.trip_number,
            "driver": t.driver.full_name if t.driver else "Unknown",
            "vehicle": f"{t.vehicle.license_plate} ({t.vehicle.model})" if t.vehicle else "N/A",
            "ownership": t.vehicle.ownership_type if t.vehicle else "N/A",
            "status": t.status.value if hasattr(t.status, 'value') else str(t.status),
            "kis_art": "✅" if t.kis_art_sent else "❌",
            "time": t.created_at.strftime("%H:%M %d.%m")
        }
        for t in trips
    ]
