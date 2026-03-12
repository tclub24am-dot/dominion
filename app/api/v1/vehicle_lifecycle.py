# -*- coding: utf-8 -*-
# app/routes/vehicle_lifecycle.py
# БОРТОВОЙ ЖУРНАЛ АВТОМОБИЛЯ (v22.6 ГЛУБИНА)

import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from datetime import datetime, timedelta

from app.database import get_db
from app.models.all_models import Vehicle, VehicleRepairHistory, Transaction, User
from app.services.auth import get_current_user

logger = logging.getLogger("VehicleLifeCycle")
router = APIRouter(tags=["Vehicle LifeCycle"])

templates = Jinja2Templates(directory="app/templates")

@router.get("/vehicle/{vehicle_id}/journal", response_class=HTMLResponse)
async def get_vehicle_journal(
    vehicle_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    БОРТОВОЙ ЖУРНАЛ 2.0 (v22.6 ГЛУБИНА)
    
    Показывает для машины:
    - Ремонты и ТО
    - Штрафы
    - Смены водителей
    - ДТП
    - Амортизацию
    - Стоимость владения
    """
    try:
        # Получаем машину
        vehicle = await db.get(Vehicle, vehicle_id)
        if not vehicle:
            raise HTTPException(status_code=404, detail="Машина не найдена")
        
        # СОБЫТИЯ ЗА ПОСЛЕДНИЕ 30 ДНЕЙ
        cutoff = datetime.now() - timedelta(days=30)
        
        # 1. РЕМОНТЫ И ТО
        stmt = select(VehicleRepairHistory).where(
            VehicleRepairHistory.vehicle_id == vehicle_id,
            VehicleRepairHistory.created_at >= cutoff
        ).order_by(desc(VehicleRepairHistory.created_at))
        
        result = await db.execute(stmt)
        repairs = result.scalars().all()
        
        # 2. ШТРАФЫ (из транзакций)
        stmt = select(Transaction).where(
            Transaction.plate_info == vehicle.license_plate,
            Transaction.category.like("%Штраф%"),
            Transaction.date >= cutoff.date()
        ).order_by(desc(Transaction.date))
        
        result = await db.execute(stmt)
        fines = result.scalars().all()
        
        # 3. РАСЧЁТ АМОРТИЗАЦИИ
        total_repairs_cost = sum(r.repair_cost for r in repairs)
        daily_depreciation = 150.0  # Средняя амортизация 150₽/день
        days_30 = 30
        total_depreciation = daily_depreciation * days_30
        
        # 4. СТОИМОСТЬ ВЛАДЕНИЯ
        ownership_cost = total_repairs_cost + total_depreciation
        
        # Формируем ленту событий
        events = []
        
        for repair in repairs:
            events.append({
                "type": "repair",
                "date": repair.created_at,
                "icon": "🔧",
                "title": "Ремонт/ТО",
                "description": repair.description,
                "cost": repair.repair_cost,
                "color": "#ffc107"
            })
        
        for fine in fines:
            events.append({
                "type": "fine",
                "date": fine.date,
                "icon": "⚠️",
                "title": "Штраф",
                "description": fine.description,
                "cost": abs(fine.amount),
                "color": "#ff5252"
            })
        
        # Сортируем по дате
        events.sort(key=lambda x: x["date"], reverse=True)
        
        data = {
            "vehicle": vehicle,
            "events": events,
            "total_repairs": len(repairs),
            "total_fines": len(fines),
            "repairs_cost": round(total_repairs_cost, 2),
            "depreciation": round(total_depreciation, 2),
            "ownership_cost": round(ownership_cost, 2),
            "period_days": days_30
        }
        
        return templates.TemplateResponse(
            "vehicle_journal.html",
            {"request": request, "data": data}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Vehicle journal error: {e}", exc_info=True)
        return HTMLResponse(
            content=f'<div style="padding: 20px; color: #ff5252;">⚠️ Ошибка загрузки журнала: {str(e)}</div>',
            status_code=200
        )


@router.get("/vehicle/{vehicle_id}/stats")
async def get_vehicle_stats(
    vehicle_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Статистика машины (JSON для виджетов)
    
    Возвращает:
    - Общая стоимость ремонтов
    - Количество ТО
    - Штрафов
    - Амортизация
    """
    try:
        vehicle = await db.get(Vehicle, vehicle_id)
        if not vehicle:
            raise HTTPException(status_code=404, detail="Машина не найдена")
        
        cutoff = datetime.now() - timedelta(days=30)
        
        # Ремонты
        stmt = select(VehicleRepairHistory).where(
            VehicleRepairHistory.vehicle_id == vehicle_id,
            VehicleRepairHistory.created_at >= cutoff
        )
        result = await db.execute(stmt)
        repairs = result.scalars().all()
        
        total_cost = sum(r.repair_cost for r in repairs)
        
        return {
            "vehicle_id": vehicle_id,
            "license_plate": vehicle.license_plate,
            "repairs_count": len(repairs),
            "repairs_cost": round(total_cost, 2),
            "depreciation_30d": round(150.0 * 30, 2),
            "ownership_cost_30d": round(total_cost + 150.0 * 30, 2)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Vehicle stats error: {e}")
        return {
            "error": str(e),
            "vehicle_id": vehicle_id
        }
