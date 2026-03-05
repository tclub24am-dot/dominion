# -*- coding: utf-8 -*-
# app/routes/analytics_strategic.py
# СТРАТЕГИЧЕСКАЯ АНАЛИТИКА (v22.6 МОЗГ КАЗНЫ)

import logging
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.all_models import User
from app.services.auth import get_current_user
from app.services.pl_report import pl_report
from app.services.invest_forecast import invest_forecast

logger = logging.getLogger("StrategicAnalytics")
router = APIRouter(tags=["Strategic Analytics"])

templates = Jinja2Templates(directory="app/templates")

@router.get("/pl", response_class=HTMLResponse)
async def pl_report_page(
    request: Request,
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Страница P&L отчёта (Прибыли и Убытки)
    
    Уровень: Совет директоров
    """
    try:
        report = await pl_report.generate_pl_report(db, days)
        
        response = templates.TemplateResponse(
            "analytics_pl.html",
            {"request": request, "data": report, "current_user": current_user}
        )
        if current_user and current_user.role == "master":
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response
        
    except Exception as e:
        logger.error(f"P&L page error: {e}")
        return HTMLResponse(
            content=f'<div style="padding: 20px; color: #ff5252;">⚠️ Ошибка: {str(e)}</div>',
            status_code=200
        )


@router.get("/pl/json")
async def pl_report_json(
    days: int = 30,
    park: str = None,
    start_date: str = None,
    end_date: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    P&L отчёт в JSON (для API/экспорта)
    park: фильтр по парку (PRO, GO, PLUS, EXPRESS, None=все)
    start_date: дата начала в формате YYYY-MM-DD (опционально)
    end_date: дата конца в формате YYYY-MM-DD (опционально)
    """
    try:
        # Если указаны конкретные даты, используем их вместо дней
        if start_date and end_date:
            from datetime import datetime as dt
            try:
                end = dt.strptime(end_date, "%Y-%m-%d")
                start = dt.strptime(start_date, "%Y-%m-%d")
                days = (end - start).days
                if days < 1:
                    days = 1
            except:
                pass  # Fallback на дни
        
        report = await pl_report.generate_pl_report(db, days, park_name=park)
        return report
    except Exception as e:
        logger.error(f"P&L JSON error: {e}")
        return {"error": str(e), "net_profit": 0}


@router.get("/forecast/vehicle/{vehicle_id}")
async def vehicle_forecast(
    vehicle_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Прогноз окупаемости конкретной машины
    """
    try:
        forecast = await invest_forecast.calculate_payback_period(vehicle_id, db)
        return forecast
    except Exception as e:
        logger.error(f"Vehicle forecast error: {e}")
        return {"error": str(e)}


@router.get("/forecast/fleet")
async def fleet_forecast(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Прогноз по всему автопарку
    """
    try:
        forecast = await invest_forecast.generate_fleet_forecast(db)
        return forecast
    except Exception as e:
        logger.error(f"Fleet forecast error: {e}")
        return {"error": str(e)}
