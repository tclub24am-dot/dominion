#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# app/services/ledger_engine.py

import logging
from datetime import datetime
from typing import Dict

from sqlalchemy import select, or_, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database import AsyncSessionLocal
from app.models.all_models import (
    FinancialLog,
    OwnershipType,
    Transaction,
    User,
    Vehicle,
)
from app.services.analytics_engine import AnalyticsEngine
from app.services.telegram_bot import send_master_msg

logger = logging.getLogger("LedgerEngine")


class LedgerEngine:
    """
    Автоматизированная бухгалтерия: автосписания в 00:00.
    """

    @staticmethod
    async def run_daily_deductions() -> Dict:
        now = datetime.now()
        processed = 0
        deducted = 0
        alerts = 0

        async with AsyncSessionLocal() as session:
            # PROTOCOL "THE LIVE 300": Только активные борты Dominion
            vehicles_stmt = select(Vehicle).where(
                Vehicle.is_active == True,
                Vehicle.is_active_dominion == True,  # Только "Живые 300"
                Vehicle.ownership_type.cast(String) == "SUBLEASE",
            )
            vehicles = (await session.execute(vehicles_stmt)).scalars().all()
            logger.info(f"[LEDGER] Smart Deduction for {len(vehicles)} active Dominion vehicles")

            for vehicle in vehicles:
                processed += 1
                result = await AnalyticsEngine.calculate_smart_deduction(
                    session, vehicle.id, on_date=now
                )
                if result.get("status") != "ok":
                    continue

                driver_id = result.get("driver_id")
                driver_charge = float(result.get("driver_charge") or 0.0)
                partner_charge = float(result.get("partner_charge") or 0.0)
                reason = result.get("reason")

                driver = await session.get(User, driver_id) if driver_id else None
                if driver and driver_charge:
                    driver.driver_balance = float(driver.driver_balance or 0.0) - driver_charge
                    deducted += 1

                if driver_charge > 0:
                    tx = Transaction(
                        park_name=vehicle.park_name or "PRO",
                        yandex_driver_id=driver.yandex_driver_id if driver else None,
                        category="AutoRent",
                        category_type="EXPENSES",
                        contractor=driver.full_name if driver else "Driver",
                        description="Автосписание: Аренда",
                        amount=-abs(driver_charge),
                        tx_type="expense",
                        date=now,
                        responsibility="driver",
                        plate_info=vehicle.license_plate,
                    )
                    session.add(tx)

                log = FinancialLog(
                    vehicle_id=vehicle.id,
                    driver_id=driver.id if driver else None,
                    park_name=vehicle.park_name or "PRO",
                    entry_type="auto_deduction",
                    amount=driver_charge,
                    note=f"Автосписание: Аренда ({reason})",
                    meta={
                        "driver_charge": driver_charge,
                        "partner_charge": partner_charge,
                        "commission_rate": result.get("commission_rate"),
                        "has_activity": result.get("has_activity"),
                        "reason": reason,
                    },
                    created_at=now,
                )
                session.add(log)

                if driver and driver.driver_balance is not None:
                    if driver.driver_balance < settings.DRIVER_NEGATIVE_LIMIT:
                        alerts += 1
                        try:
                            await send_master_msg(
                                "⚠️ Глубокий минус по балансу:\n"
                                f"Водитель: {driver.full_name}\n"
                                f"Авто: {vehicle.license_plate}\n"
                                f"Баланс: {driver.driver_balance:,.2f}₽"
                            )
                        except Exception:
                            logger.warning("Telegram alert failed", exc_info=True)

            await session.commit()

        return {
            "status": "ok",
            "processed": processed,
            "deducted": deducted,
            "alerts": alerts,
            "timestamp": now.isoformat(),
        }

    @staticmethod
    async def get_financial_rain(limit: int = 50, active_only: bool = True) -> Dict:
        async with AsyncSessionLocal() as session:
            stmt = (
                select(FinancialLog, User.full_name, Vehicle.license_plate)
                .outerjoin(User, User.id == FinancialLog.driver_id)
                .outerjoin(Vehicle, Vehicle.id == FinancialLog.vehicle_id)
            )
            
            # Фильтр только для активного флота (is_active_dominion)
            if active_only:
                stmt = stmt.where(
                    or_(
                        Vehicle.is_active_dominion == True,
                        FinancialLog.vehicle_id == None  # Также показываем записи без машины
                    )
                )
            
            stmt = stmt.order_by(FinancialLog.created_at.desc()).limit(limit)
            rows = (await session.execute(stmt)).all()
            items = [
                {
                    "id": r.id,
                    "vehicle_id": r.vehicle_id,
                    "driver_id": r.driver_id,
                    "park_name": r.park_name,
                    "entry_type": r.entry_type,
                    "amount": float(r.amount or 0.0),
                    "note": r.note,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "driver_name": driver_name,
                    "plate": plate,
                }
                for r, driver_name, plate in rows
            ]
        return {"status": "ok", "items": items}


ledger_engine = LedgerEngine()
