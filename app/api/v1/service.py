# -*- coding: utf-8 -*-
# app/routes/service.py
# VECTOR B: Регистрация расходов (v22.6 IRON ORDER)

import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.models.all_models import Vehicle, WarehouseItem, WarehouseLog, PartnerLedger, Transaction, User
from app.services.auth import get_current_user

logger = logging.getLogger("ServiceRecord")
router = APIRouter(tags=["Service Record"])

# =================================================================
# SCHEMAS
# =================================================================

class ServiceRecordRequest(BaseModel):
    """Запрос на регистрацию расхода"""
    vehicle_id: int
    item_id: Optional[int] = None  # Опционально: запчасть со склада
    work_cost: float
    description: str
    mechanic_name: Optional[str] = None

# =================================================================
# РЕГИСТРАЦИЯ РАСХОДА (VECTOR B)
# =================================================================

@router.post("/record")
async def record_service(
    request: ServiceRecordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    VECTOR B: Регистрация расхода на обслуживание (v22.6)
    
    Автоматически:
    1. Списывает запчасть со склада (если указана)
    2. Создаёт запись в Partner Ledger
    3. Создаёт транзакцию для отражения в Казне
    4. Прибыль пересчитывается мгновенно
    """
    try:
        # 1. Получаем машину
        vehicle = await db.get(Vehicle, request.vehicle_id)
        if not vehicle:
            raise HTTPException(status_code=404, detail="Машина не найдена")
        
        total_cost = request.work_cost
        parts_info = ""
        
        # 2. Если указана запчасть — списываем со склада
        if request.item_id:
            item = await db.get(WarehouseItem, request.item_id)
            
            if not item:
                raise HTTPException(status_code=404, detail="Запчасть не найдена")
            
            if item.quantity < 1:
                raise HTTPException(
                    status_code=400,
                    detail=f"Недостаточно {item.name} на складе! Доступно: {item.quantity}"
                )
            
            # Списываем
            item.quantity -= 1
            parts_cost = item.price_unit
            total_cost += parts_cost
            
            parts_info = f"{item.name} (1 шт. × {parts_cost:,.0f}₽)"
            
            # Лог склада
            log_entry = WarehouseLog(
                item_id=item.id,
                vehicle_id=vehicle.id,
                change=-1,
                master_id=current_user.id,
                timestamp=datetime.now()
            )
            db.add(log_entry)
            
            logger.info(f"📦 Writeoff: {item.name} for {vehicle.license_plate}")
        
        # 3. Запись в Partner Ledger
        ledger_entry = PartnerLedger(
            partner_id=None,
            vehicle_id=vehicle.id,
            incoming=0.0,
            outgoing=total_cost,
            expense_type="Обслуживание",
            expense_description=f"{request.description} | {parts_info if parts_info else 'Только работа'}",
            date=datetime.now().date(),
            created_at=datetime.now()
        )
        db.add(ledger_entry)
        
        # 4. Создаём транзакцию для Казны (это влияет на прибыль!)
        transaction = Transaction(
            category="Расходы_Обслуживание",
            contractor=request.mechanic_name or current_user.full_name,
            description=f"{vehicle.license_plate}: {request.description}",
            plate_info=vehicle.license_plate,
            amount=-total_cost,  # Отрицательная для расхода
            tx_type="expense",
            date=datetime.now(),
            responsibility="Maintenance"
        )
        db.add(transaction)
        
        await db.commit()
        
        logger.info(f"✓ Service recorded: {vehicle.license_plate} | Total: {total_cost:,.2f}₽")
        
        # 5. Уведомление Мастера
        try:
            from app.services.telegram_bot import send_master_msg
            await send_master_msg(
                f"💰 <b>РАСХОД ЗАРЕГИСТРИРОВАН</b>\n"
                f"🚗 {vehicle.brand} {vehicle.model} ({vehicle.license_plate})\n"
                f"💸 Сумма: <b>{total_cost:,.0f}₽</b>\n"
                f"📝 {request.description}\n"
                f"{f'📦 {parts_info}' if parts_info else ''}\n\n"
                f"✓ Прибыль в Казне скорректирована"
            )
        except:
            pass
        
        return {
            "status": "success",
            "vehicle": f"{vehicle.brand} {vehicle.model} ({vehicle.license_plate})",
            "total_cost": round(total_cost, 2),
            "work_cost": round(request.work_cost, 2),
            "parts_cost": round(total_cost - request.work_cost, 2) if request.item_id else 0,
            "parts_info": parts_info,
            "message": "Расход занесён, прибыль скорректирована"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Service record error: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
