# -*- coding: utf-8 -*-
# app/services/invest_forecast.py
# Investment Forecast Service

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.all_models import Vehicle, Transaction, User

logger = logging.getLogger("InvestForecast")


class InvestForecastService:
    """
    Сервис прогнозирования окупаемости инвестиций
    """
    
    async def calculate_payback_period(
        self, 
        vehicle_id: int, 
        db: AsyncSession
    ) -> Dict:
        """
        Расчёт прогноза окупаемости для конкретного автомобиля
        
        Args:
            vehicle_id: ID автомобиля
            db: Сессия базы данных
        
        Returns:
            Dict с прогнозом окупаемости
        """
        try:
            # Получаем автомобиль
            vehicle = await db.get(Vehicle, vehicle_id)
            if not vehicle:
                return {"error": "Автомобиль не найден", "vehicle_id": vehicle_id}
            
            # Получаем транзакции за последние 30 дней
            since = datetime.now() - timedelta(days=30)
            
            stmt = select(Transaction).where(
                and_(
                    Transaction.date >= since,
                    or_(
                        Transaction.plate_info == vehicle.license_plate,
                        Transaction.description.ilike(f"%{vehicle.license_plate}%")
                    )
                )
            )
            
            result = await db.execute(stmt)
            transactions = result.scalars().all()
            
            # Расчёт среднего дохода
            total_revenue = sum(
                float(tx.amount or 0) 
                for tx in transactions 
                if float(tx.amount or 0) > 0
            )
            avg_monthly_revenue = total_revenue  # За 30 дней
            
            # Оценочная стоимость автомобиля
            estimated_value = 1500000  # Базовая оценка
            
            # Прогноз окупаемости
            if avg_monthly_revenue > 0:
                months_to_payback = estimated_value / avg_monthly_revenue
            else:
                months_to_payback = None
            
            return {
                "vehicle_id": vehicle_id,
                "license_plate": vehicle.license_plate,
                "avg_monthly_revenue": round(avg_monthly_revenue, 2),
                "estimated_value": estimated_value,
                "months_to_payback": round(months_to_payback, 1) if months_to_payback else None,
                "transactions_analyzed": len(transactions),
                "calculated_at": datetime.now().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Payback calculation error: {e}")
            return {
                "vehicle_id": vehicle_id,
                "error": str(e),
                "calculated_at": datetime.now().isoformat(),
            }
    
    async def generate_fleet_forecast(self, db: AsyncSession) -> Dict:
        """
        Генерация прогноза по всему автопарку
        
        Args:
            db: Сессия базы данных
        
        Returns:
            Dict с прогнозом по автопарку
        """
        try:
            # Получаем все активные автомобили
            stmt = select(Vehicle).where(Vehicle.is_archived == False)
            result = await db.execute(stmt)
            vehicles = result.scalars().all()
            
            fleet_forecast = []
            total_value = 0
            total_monthly_revenue = 0
            
            for vehicle in vehicles:
                forecast = await self.calculate_payback_period(vehicle.id, db)
                if "error" not in forecast or forecast.get("avg_monthly_revenue", 0) > 0:
                    fleet_forecast.append(forecast)
                    total_value += forecast.get("estimated_value", 0)
                    total_monthly_revenue += forecast.get("avg_monthly_revenue", 0)
            
            if total_monthly_revenue > 0:
                fleet_months_to_payback = total_value / total_monthly_revenue
            else:
                fleet_months_to_payback = None
            
            return {
                "total_vehicles": len(vehicles),
                "active_vehicles": len(fleet_forecast),
                "total_fleet_value": round(total_value, 2),
                "total_monthly_revenue": round(total_monthly_revenue, 2),
                "fleet_months_to_payback": round(fleet_months_to_payback, 1) if fleet_months_to_payback else None,
                "vehicles": fleet_forecast[:10],  # Топ 10 для отображения
                "calculated_at": datetime.now().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Fleet forecast error: {e}")
            return {
                "total_vehicles": 0,
                "active_vehicles": 0,
                "total_fleet_value": 0,
                "total_monthly_revenue": 0,
                "error": str(e),
                "calculated_at": datetime.now().isoformat(),
            }


# Singleton instance
invest_forecast = InvestForecastService()
