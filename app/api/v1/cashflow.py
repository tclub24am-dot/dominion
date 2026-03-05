# -*- coding: utf-8 -*-
# app/routes/cashflow.py
# CASHFLOW CALENDAR v30.0 EXTREME - Календарь будущих обязательств

import logging
from typing import List, Dict
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from datetime import datetime, timedelta, date

from app.database import get_db
from app.models.all_models import Vehicle, VehicleProfile, User
from app.services.auth import get_current_user

logger = logging.getLogger("CashFlow")
router = APIRouter(tags=["CashFlow"])

templates = Jinja2Templates(directory="app/templates")


@router.get("/calendar/json")
async def cashflow_calendar_json(
    days: int = 90,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Календарь будущих обязательств (JSON)
    
    Собирает даты:
    - ОСАГО expiry
    - КАСКО expiry
    - Диагностическая карта expiry
    - Права expiry
    - Плановые ТО
    """
    try:
        today = datetime.now().date()
        future_date = today + timedelta(days=days)
        
        # Получаем все vehicle profiles с датами
        stmt = select(VehicleProfile, Vehicle).join(
            Vehicle, VehicleProfile.vehicle_id == Vehicle.id
        ).where(
            or_(
                and_(
                    VehicleProfile.osago_expiry.isnot(None),
                    VehicleProfile.osago_expiry >= today,
                    VehicleProfile.osago_expiry <= future_date
                ),
                and_(
                    VehicleProfile.kasko_expiry.isnot(None),
                    VehicleProfile.kasko_expiry >= today,
                    VehicleProfile.kasko_expiry <= future_date
                ),
                and_(
                    VehicleProfile.diagnostic_card_expiry.isnot(None),
                    VehicleProfile.diagnostic_card_expiry >= today,
                    VehicleProfile.diagnostic_card_expiry <= future_date
                ),
                and_(
                    VehicleProfile.license_expiry.isnot(None),
                    VehicleProfile.license_expiry >= today,
                    VehicleProfile.license_expiry <= future_date
                )
            )
        )
        
        result = await db.execute(stmt)
        profiles_with_vehicles = result.all()
        
        # Собираем события
        events = []
        
        for profile, vehicle in profiles_with_vehicles:
            # ОСАГО
            if profile.osago_expiry and today <= profile.osago_expiry <= future_date:
                days_until = (profile.osago_expiry - today).days
                urgency = "critical" if days_until <= 7 else "warning" if days_until <= 30 else "normal"
                
                events.append({
                    "date": profile.osago_expiry.isoformat(),
                    "type": "osago",
                    "type_label": "ОСАГО",
                    "vehicle_id": vehicle.id,
                    "vehicle_plate": vehicle.license_plate,
                    "vehicle_brand": f"{vehicle.brand} {vehicle.model}",
                    "description": f"Истекает ОСАГО #{profile.osago_number or 'N/A'}",
                    "estimated_cost": 8000,  # Средняя стоимость ОСАГО
                    "urgency": urgency,
                    "days_until": days_until
                })
            
            # КАСКО
            if profile.kasko_expiry and today <= profile.kasko_expiry <= future_date:
                days_until = (profile.kasko_expiry - today).days
                urgency = "critical" if days_until <= 7 else "warning" if days_until <= 30 else "normal"
                
                events.append({
                    "date": profile.kasko_expiry.isoformat(),
                    "type": "kasko",
                    "type_label": "КАСКО",
                    "vehicle_id": vehicle.id,
                    "vehicle_plate": vehicle.license_plate,
                    "vehicle_brand": f"{vehicle.brand} {vehicle.model}",
                    "description": f"Истекает КАСКО #{profile.kasko_number or 'N/A'}",
                    "estimated_cost": 45000,  # Средняя стоимость КАСКО
                    "urgency": urgency,
                    "days_until": days_until
                })
            
            # Диагностическая карта
            if profile.diagnostic_card_expiry and today <= profile.diagnostic_card_expiry <= future_date:
                days_until = (profile.diagnostic_card_expiry - today).days
                urgency = "critical" if days_until <= 7 else "warning" if days_until <= 30 else "normal"
                
                events.append({
                    "date": profile.diagnostic_card_expiry.isoformat(),
                    "type": "diagnostic",
                    "type_label": "Диагностика",
                    "vehicle_id": vehicle.id,
                    "vehicle_plate": vehicle.license_plate,
                    "vehicle_brand": f"{vehicle.brand} {vehicle.model}",
                    "description": "Истекает диагностическая карта",
                    "estimated_cost": 1500,
                    "urgency": urgency,
                    "days_until": days_until
                })
            
            # Права
            if profile.license_expiry and today <= profile.license_expiry <= future_date:
                days_until = (profile.license_expiry - today).days
                urgency = "critical" if days_until <= 7 else "warning" if days_until <= 30 else "normal"
                
                events.append({
                    "date": profile.license_expiry.isoformat(),
                    "type": "license",
                    "type_label": "Права",
                    "vehicle_id": vehicle.id,
                    "vehicle_plate": vehicle.license_plate,
                    "vehicle_brand": f"{vehicle.brand} {vehicle.model}",
                    "description": "Истекают водительские права",
                    "estimated_cost": 3000,
                    "urgency": urgency,
                    "days_until": days_until
                })
        
        # Сортируем по дате
        events.sort(key=lambda x: x["date"])
        
        # Считаем общую сумму обязательств
        total_cost = sum(event["estimated_cost"] for event in events)
        
        # Группируем по месяцам
        monthly_breakdown = {}
        for event in events:
            month_key = event["date"][:7]  # YYYY-MM
            if month_key not in monthly_breakdown:
                monthly_breakdown[month_key] = {
                    "month": month_key,
                    "events": 0,
                    "total_cost": 0
                }
            monthly_breakdown[month_key]["events"] += 1
            monthly_breakdown[month_key]["total_cost"] += event["estimated_cost"]
        
        logger.info(f"✓ CashFlow calendar: {len(events)} events, {total_cost:,.0f}₽ total")
        
        return {
            "period_days": days,
            "from_date": today.isoformat(),
            "to_date": future_date.isoformat(),
            "events_count": len(events),
            "total_estimated_cost": round(total_cost, 2),
            "events": events,
            "monthly_breakdown": list(monthly_breakdown.values()),
            "urgency_counts": {
                "critical": len([e for e in events if e["urgency"] == "critical"]),
                "warning": len([e for e in events if e["urgency"] == "warning"]),
                "normal": len([e for e in events if e["urgency"] == "normal"])
            }
        }
        
    except Exception as e:
        logger.error(f"CashFlow calendar error: {e}", exc_info=True)
        return {"error": str(e), "events": []}


@router.get("/calendar/timeline", response_class=HTMLResponse)
async def cashflow_timeline_html(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Временная шкала обязательств (HTML для HTMX)
    """
    try:
        # Получаем данные
        data = await cashflow_calendar_json(90, current_user, db)
        
        if isinstance(data, dict) and "error" not in data:
            items = data.get("events", [])
            rows = [
                f"<div><strong>{e.get('date')}</strong> — {e.get('title')} ({e.get('amount')})</div>"
                for e in items
            ]
            return HTMLResponse("".join(rows) or "<div>Нет событий</div>", status_code=200)
        else:
            return HTMLResponse(
                content=f'<div style="padding: 20px; color: #ff5252;">⚠️ Ошибка: {data.get("error", "Unknown")}</div>',
                status_code=200
            )
            
    except Exception as e:
        logger.error(f"Timeline HTML error: {e}", exc_info=True)
        return HTMLResponse(
            content=f'<div style="padding: 20px; color: #ff5252;">⚠️ Ошибка: {str(e)}</div>',
            status_code=200
        )
