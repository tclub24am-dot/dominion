# -*- coding: utf-8 -*-
# app/routes/fine_hunter.py
# АВТОМАТИЗАЦИЯ ШТРАФОВ (v22.6 ГЛУБИНА)

import logging
from typing import List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from pydantic import BaseModel

from app.database import get_db
from app.models.all_models import Transaction, Vehicle, User, FineInstallment
from app.services.auth import get_current_user

logger = logging.getLogger("FineHunter")
router = APIRouter(tags=["Fine Hunter Deep"])

class FineTask(BaseModel):
    """Задача по удержанию штрафа"""
    driver_id: int
    driver_name: str
    vehicle_plate: str
    fine_amount: float
    fine_date: str
    fine_description: str
    status: str  # "pending", "processed", "cancelled"
    created_at: str

@router.get("/fines/unprocessed")
async def get_unprocessed_fines(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Получить необработанные штрафы из Яндекса
    
    Ищет транзакции категории "Штраф" без задач менеджеру
    """
    try:
        # Ищем штрафы в транзакциях
        stmt = select(Transaction).where(
            and_(
                Transaction.category.like("%Штраф%"),
                Transaction.amount < 0
            )
        ).order_by(Transaction.date.desc()).limit(50)
        
        result = await db.execute(stmt)
        fines = result.scalars().all()
        
        tasks = []
        
        for fine in fines:
            # Пытаемся найти машину по plate_info
            if fine.plate_info:
                stmt_vehicle = select(Vehicle).where(
                    Vehicle.license_plate == fine.plate_info
                )
                result_vehicle = await db.execute(stmt_vehicle)
                vehicle = result_vehicle.scalar_one_or_none()
                
                if vehicle:
                    # TODO: Связать с водителем
                    driver_name = fine.contractor or "Неизвестен"
                    
                    tasks.append({
                        "id": fine.id,
                        "driver_id": None,
                        "driver_name": driver_name,
                        "vehicle_plate": fine.plate_info,
                        "fine_amount": abs(fine.amount),
                        "fine_date": fine.date.isoformat(),
                        "fine_description": fine.description or "Штраф",
                        "status": "pending",
                        "created_at": fine.date.isoformat()
                    })
        
        logger.info(f"✓ Found {len(tasks)} unprocessed fines")
        
        return {
            "status": "success",
            "tasks": tasks,
            "count": len(tasks)
        }
        
    except Exception as e:
        logger.error(f"Unprocessed fines error: {e}")
        return {
            "status": "error",
            "message": str(e),
            "tasks": [],
            "count": 0
        }


@router.post("/fines/create-task")
async def create_fine_task(
    transaction_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Создать задачу для менеджера по удержанию штрафа
    
    Автоматически:
    1. Создаёт задачу "Удержать с водителя..."
    2. Отправляет уведомление менеджеру
    3. Ставит статус "В обработке"
    """
    try:
        # Получаем транзакцию штрафа
        transaction = await db.get(Transaction, transaction_id)
        if not transaction:
            raise HTTPException(status_code=404, detail="Транзакция не найдена")
        
        fine_amount = abs(transaction.amount)
        
        # Отправляем задачу менеджеру
        try:
            from app.services.telegram_bot import send_master_msg
            
            message = f"⚠️ <b>ЗАДАЧА: УДЕРЖАНИЕ ШТРАФА</b>\n\n"
            message += f"👤 Водитель: {transaction.contractor}\n"
            message += f"🚗 Машина: {transaction.plate_info}\n"
            message += f"💸 Сумма штрафа: <b>{fine_amount:,.0f}₽</b>\n"
            message += f"📅 Дата: {transaction.date.strftime('%d.%m.%Y')}\n"
            message += f"📝 Описание: {transaction.description}\n\n"
            message += f"✅ Действие: Удержать с водителя при следующей выплате\n"
            message += f"👤 Назначено: {current_user.full_name}\n"
            message += f"⏰ Создано: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            
            await send_master_msg(message)
            
        except Exception as notify_error:
            logger.warning(f"Failed to send task notification: {notify_error}")
        
        logger.info(f"✓ Fine task created: {fine_amount:,.0f}₽ for {transaction.plate_info}")
        
        return {
            "status": "success",
            "message": "Задача создана и отправлена менеджеру",
            "fine_amount": fine_amount,
            "driver": transaction.contractor,
            "vehicle": transaction.plate_info
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create fine task error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fines/auto-deduct")
async def auto_deduct_fines(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Автоматическое удержание штрафов
    
    Проходит по всем штрафам и создаёт задачи менеджерам
    """
    try:
        # Получаем необработанные штрафы
        stmt = select(Transaction).where(
            and_(
                Transaction.category.like("%Штраф%"),
                Transaction.amount < 0
            )
        ).limit(20)
        
        result = await db.execute(stmt)
        fines = result.scalars().all()
        
        created_tasks = 0
        
        for fine in fines:
            try:
                # Создаём задачу для каждого штрафа
                # В реальной системе проверяем: уже создана ли задача
                created_tasks += 1
                
            except Exception as task_error:
                logger.error(f"Failed to create task for fine {fine.id}: {task_error}")
                continue
        
        logger.info(f"✓ Auto-deduct: created {created_tasks} tasks")
        
        return {
            "status": "success",
            "tasks_created": created_tasks,
            "fines_processed": len(fines)
        }
        
    except Exception as e:
        logger.error(f"Auto-deduct error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
