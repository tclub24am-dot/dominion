# -*- coding: utf-8 -*-
# app/routes/logistics.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.services.advantum import advantum_service
from app.core.config import settings
from app.models.all_models import Vehicle, OwnershipType

router = APIRouter(prefix="/api/v1/logistics", tags=["Logistics"])

# =================================================================
# 1. ТАРИФНАЯ СЕТКА ВКУСВИЛЛ (Константы из Матрицы)
# =================================================================
VKUSVILL_PRICES = {
    "darkstore": settings.VV_PRICE_DARKSTORE, # 6599.0
    "store": settings.VV_PRICE_STORE,         # 5883.0
    "shmel": settings.VV_PRICE_SHMEL,         # 3882.0
    "zhuk": settings.VV_PRICE_ZHUK            # 2107.0
}

# =================================================================
# 2. МОНИТОРИНГ ТЕМПЕРАТУРЫ (Advantum API)
# =================================================================
@router.get("/temperature")
async def get_fleet_temperature():
    """Получение данных о температуре рефрижераторов из Advantum"""
    try:
        data = await advantum_service.get_realtime_sensors()
        return {
            "status": "online",
            "sync_time": "LIVE",
            "sensors": data 
        }
    except Exception as e:
        return {"status": "error", "message": f"Advantum Sync Failed: {e}"}

# =================================================================
# 3. АКТИВНЫЕ МАРШРУТЫ И ГРАФИК (ВкусВилл ЮГ)
# =================================================================
@router.get("/vkusvill/active-trips")
async def get_vkusvill_trips():
    """
    Текущие активные маршруты согласно твоей ведомости:
    807 ТС, 426 ТС, 221 ТС, 115 ТС
    """
    return {
        "warehouse": "Домодедово (Юг)",
        "fleet_status": "Active",
        "trips": [
            {
                "vehicle": "807 ТС", 
                "driver": "Артур", 
                "trips": ["8464ДС_БольшаяЧеремушкинская2", "9107ДС_Николо-Хованская7"],
                "profit_potential": VKUSVILL_PRICES["darkstore"] * 2
            },
            {
                "vehicle": "426 ТС", 
                "driver": "Зариф", 
                "trips": ["9107ДС_Николо-Хованская7", "7341М_Люсиновская4", "8500Ш_Мичуринский16"],
                "profit_potential": VKUSVILL_PRICES["darkstore"] + VKUSVILL_PRICES["store"] + VKUSVILL_PRICES["shmel"]
            },
            {
                "vehicle": "221 ТС", 
                "driver": "Шахзод", 
                "trips": ["8464ДС_БольшаяЧеремушкинская2", "6956Ш_1йГрайвороновский13", "7627Ж_Сколковское40"],
                "profit_potential": VKUSVILL_PRICES["darkstore"] + VKUSVILL_PRICES["shmel"] + VKUSVILL_PRICES["zhuk"]
            },
            {
                "vehicle": "115 ТС", 
                "driver": "Арман", 
                "trips": ["4537М_Миклухо-Маклая43", "6736М_Стремянный2", "8171Ж_Зворыкина14"],
                "profit_potential": VKUSVILL_PRICES["store"] * 2 + VKUSVILL_PRICES["zhuk"]
            }
        ]
    }

# =================================================================
# 4. ФИНАНСОВЫЙ ПУЛЬС ЛОГИСТИКИ (Nexus Widget)
# =================================================================
@router.get("/vkusvill/stats")
async def get_vkusvill_stats(db: AsyncSession = Depends(get_db)):
    """
    Статистика прибыли для виджета: 
    Собственный 5т (1/4 прибыли) и партнерские Газели.
    """
    # Здесь в будущем будет запрос к Transactions
    # Пока считаем прогноз на основе тарифов
    daily_revenue_5t = VKUSVILL_PRICES["darkstore"] * 2 # Пример 2 рейса в день
    driver_pay = settings.VV_DRIVER_PAY # 2000
    fuel = settings.VV_FUEL_DAILY # 5000
    
    clean_profit_5t = daily_revenue_5t - (driver_pay * 2) - fuel
    master_share = clean_profit_5t / 4 # Твоя доля
    
    return {
        "daily_gross": daily_revenue_5t,
        "master_net_profit": master_share,
        "expenses": {
            "driver": driver_pay * 2,
            "fuel": fuel
        },
        "target": "ВкусВилл ЮГ"
    }
