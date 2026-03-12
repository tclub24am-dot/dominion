# -*- coding: utf-8 -*-
# app/routes/warehouse_ops.py
# ОПЕРАЦИИ СКЛАДА v22.5+ — Списание запчастей + Контроль остатков

import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel

from app.database import get_db
from app.models.all_models import WarehouseItem, WarehouseLog, Vehicle, PartnerLedger, User, Transaction
from app.services.auth import get_current_user

logger = logging.getLogger("WarehouseOps")
router = APIRouter(tags=["Warehouse Operations"])

# =================================================================
# КОНТРОЛЬ ОСТАТКОВ (v22.5+ IRON ORDER)
# =================================================================

CRITICAL_LEVEL = 2  # Критический уровень остатка (Оракул предупреждает)
LOW_LEVEL = 5      # Низкий уровень остатка (предупреждение)

async def check_low_stock(db: AsyncSession, item: WarehouseItem = None, level: str = "critical") -> List[dict]:
    """
    Проверка критических остатков на складе (IRON ORDER)
    
    Args:
        db: Сессия БД
        item: Конкретная позиция (опционально)
        level: "critical" (≤2) или "low" (≤5)
    
    Returns:
        List[dict]: Список позиций с критическими/низкими остатками
    """
    try:
        threshold = CRITICAL_LEVEL if level == "critical" else LOW_LEVEL
        
        if item:
            # Проверяем конкретную позицию
            items = [item] if item.quantity <= threshold else []
        else:
            # Проверяем весь склад
            stmt = select(WarehouseItem).where(WarehouseItem.quantity <= threshold)
            result = await db.execute(stmt)
            items = result.scalars().all()
        
        critical_items = []
        
        for warehouse_item in items:
            if warehouse_item.quantity <= threshold:
                # Определяем уровень критичности
                if warehouse_item.quantity == 0:
                    alert_level = "empty"
                elif warehouse_item.quantity <= CRITICAL_LEVEL:
                    alert_level = "critical"
                else:
                    alert_level = "low"
                
                critical_items.append({
                    "id": warehouse_item.id,
                    "name": warehouse_item.name,
                    "sku": warehouse_item.sku,
                    "quantity": warehouse_item.quantity,
                    "min_level": warehouse_item.min_threshold or CRITICAL_LEVEL,
                    "category": warehouse_item.category,
                    "alert_level": alert_level
                })
        
        return critical_items
        
    except Exception as e:
        logger.error(f"Low stock check error: {e}")
        return []

async def send_low_stock_alert(items: List[dict]):
    """
    Отправка уведомлений ОРАКУЛА о критических остатках (v22.6 ГЛУБИНА)
    
    Отправляет Мастеру через @info_SGbot
    + Автоматически предлагает поставщиков
    """
    if not items:
        return
    
    try:
        from app.services.telegram_bot import send_master_msg
        from app.api.v1.suppliers import SUPPLIERS_DB
        
        # Сортируем по уровню критичности
        empty_items = [i for i in items if i['alert_level'] == 'empty']
        critical_items = [i for i in items if i['alert_level'] == 'critical']
        low_items = [i for i in items if i['alert_level'] == 'low']
        
        message = "⚡ <b>ОРАКУЛ: КОНТРОЛЬ СКЛАДА</b>\n\n"
        
        if empty_items:
            message += "🔴 <b>НА ИСХОДЕ (0 ед.):</b>\n"
            for item in empty_items:
                message += f"   • {item['name']} ({item['sku']})\n"
            message += "\n"
        
        if critical_items:
            message += f"🚨 <b>КРИТИЧЕСКИЙ ОСТАТОК (≤{CRITICAL_LEVEL} ед.):</b>\n"
            for item in critical_items:
                message += f"   • {item['name']}: <b>{item['quantity']} ед.</b> ({item['sku']})\n"
            message += "\n"
        
        if low_items:
            message += f"⚠️ <b>НИЗКИЙ ОСТАТОК (≤{LOW_LEVEL} ед.):</b>\n"
            for item in low_items[:3]:  # Топ-3
                message += f"   • {item['name']}: {item['quantity']} ед.\n"
            if len(low_items) > 3:
                message += f"   ... и ещё {len(low_items) - 3}\n"
            message += "\n"
        
        message += f"📋 <b>Всего позиций с низким уровнем: {len(items)}</b>\n"
        message += f"⚠️ Мастер, ресурсы на исходе! Требуется закупка!\n\n"
        
        # АВТОМАТИЧЕСКОЕ ПРЕДЛОЖЕНИЕ ПОСТАВЩИКОВ (v22.6 ГЛУБИНА)
        if critical_items or empty_items:
            message += "🏢 <b>РЕКОМЕНДУЕМЫЕ ПОСТАВЩИКИ:</b>\n\n"
            
            suggested_suppliers = set()
            for item in (critical_items + empty_items)[:3]:  # Топ-3 критичных
                item_name = item['name']
                
                # Ищем поставщика
                for supplier in SUPPLIERS_DB:
                    for supplier_item in supplier['items']:
                        if item_name.lower() in supplier_item.lower() or supplier_item.lower() in item_name.lower():
                            suggested_suppliers.add((
                                supplier['name'],
                                supplier['phone'],
                                supplier['delivery_days']
                            ))
                            break
            
            for supplier_name, phone, days in list(suggested_suppliers)[:2]:
                message += f"   • {supplier_name}\n"
                message += f"     ☎️ {phone}\n"
                message += f"     🚚 Доставка: {days} дн.\n\n"
            
            message += f"💡 Используйте: POST /api/v1/suppliers/purchase/request\n\n"
        
        message += f"Проверка: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        
        await send_master_msg(message)
        
        logger.info(f"🚨 Oracle stock alert sent: {len(items)} items (empty: {len(empty_items)}, critical: {len(critical_items)}, low: {len(low_items)})")
        
    except Exception as e:
        logger.error(f"Failed to send Oracle stock alert: {e}")

# =================================================================
# SCHEMAS
# =================================================================

class PartsWriteoffRequest(BaseModel):
    """Запрос на списание запчасти"""
    item_id: int
    quantity: int
    vehicle_id: int
    reason: str  # "repair", "maintenance", "replacement"
    description: Optional[str] = None

class RepairRegistrationRequest(BaseModel):
    """Регистрация ремонта"""
    vehicle_id: int
    parts: list  # [{"item_id": 1, "quantity": 2}, ...]
    labor_cost: float
    mechanic_name: str
    description: str

class WarehousePriceUpdate(BaseModel):
    """Обновление цены закупки по артикулу"""
    sku: str
    price: float

# =================================================================
# ПОИСК ПО СКЛАДУ (для живого подбора)
# =================================================================

@router.get("/items/search")
async def search_items(
    q: str = "",
    limit: int = 15,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        stmt = select(WarehouseItem).where(
            WarehouseItem.sku.ilike(f"%{q}%") | WarehouseItem.name.ilike(f"%{q}%")
        ).order_by(WarehouseItem.name).limit(limit)
        result = await db.execute(stmt)
        items = result.scalars().all()
        payload = [
            {
                "id": i.id,
                "name": i.name,
                "sku": i.sku,
                "quantity": i.quantity,
                "price_unit": i.price_unit
            } for i in items
        ]
        # Если запрос из HTMX — вернем HTML для select/списка
        if request and request.headers.get("HX-Request"):
            options = "".join([f'<option value="{i["id"]}">{i["name"]} ({i["sku"]}) — {i["quantity"]} шт.</option>' for i in payload])
            return HTMLResponse(options)
        return payload
    except Exception as e:
        logger.error(f"Search items error: {e}")
        raise HTTPException(status_code=500, detail="Ошибка поиска по складу")

# =================================================================
# ОБНОВЛЕНИЕ ЦЕНЫ ЗАКУПКИ (Проценка)
# =================================================================

@router.post("/price/update")
async def update_item_price(
    payload: WarehousePriceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        stmt = select(WarehouseItem).where(WarehouseItem.sku == payload.sku)
        result = await db.execute(stmt)
        item = result.scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="Позиция не найдена")
        
        item.price_unit = payload.price
        await db.commit()
        return {"status": "success", "sku": payload.sku, "price": payload.price}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update price error: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Не удалось обновить цену")

# =================================================================
# СПИСАНИЕ ЗАПЧАСТЕЙ
# =================================================================

@router.post("/writeoff")
async def writeoff_parts(
    request: PartsWriteoffRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Списание запчасти со склада (v22.5)
    
    Автоматически:
    1. Уменьшает количество на складе
    2. Создаёт запись в WarehouseLog
    3. Добавляет расход в PartnerLedger (если машина партнёрская)
    """
    try:
        # 1. Проверяем наличие
        item = await db.get(WarehouseItem, request.item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Запчасть не найдена")
        
        if item.quantity < request.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Недостаточно на складе! Доступно: {item.quantity}, запрошено: {request.quantity}"
            )
        
        # 2. Получаем машину
        vehicle = await db.get(Vehicle, request.vehicle_id)
        if not vehicle:
            raise HTTPException(status_code=404, detail="Машина не найдена")
        
        # 3. Списание со склада
        item.quantity -= request.quantity
        
        # 4. Запись в лог
        log_entry = WarehouseLog(
            item_id=request.item_id,
            vehicle_id=request.vehicle_id,
            change=-request.quantity,
            master_id=current_user.id,
            timestamp=datetime.now()
        )
        
        db.add(log_entry)
        
        # 5. МГНОВЕННОЕ ОТРАЖЕНИЕ В ПАРТНЁРСКОМ ХАБЕ
        # Если у машины есть связь с партнёром через PartnerLedger
        cost = request.quantity * item.price_unit
        
        stmt = select(PartnerLedger).where(
            PartnerLedger.vehicle_id == request.vehicle_id
        ).order_by(PartnerLedger.date.desc()).limit(1)
        
        result = await db.execute(stmt)
        ledger = result.scalar_one_or_none()
        
        if ledger:
            # Добавляем расход партнёру
            ledger.outgoing += cost
            ledger.balance = ledger.incoming - ledger.outgoing
            
            logger.info(f"💸 Partner expense added: {cost:,.2f}₽ for vehicle {vehicle.license_plate}")
        else:
            logger.info(f"No partner ledger for vehicle {vehicle.license_plate}")
        
        await db.commit()
        
        logger.info(f"✓ Writeoff: {item.name} x{request.quantity} for {vehicle.license_plate}")
        
        # 6. Уведомление Мастера через Telegram (если настроен)
        try:
            from app.services.telegram_bot import send_master_msg
            await send_master_msg(
                f"📦 <b>СКЛАД: СПИСАНИЕ</b>\n"
                f"🔹 {item.name} x{request.quantity}\n"
                f"🚗 {vehicle.license_plate}\n"
                f"💰 Стоимость: {cost:,.2f}₽\n"
                f"📉 Остаток: {item.quantity}"
            )
        except:
            pass
        
        # 7. КОНТРОЛЬ ОСТАТКОВ (v22.5+)
        critical_items = await check_low_stock(db, item)
        if critical_items:
            await send_low_stock_alert(critical_items)
        
        return {
            "status": "success",
            "item_name": item.name,
            "quantity_written_off": request.quantity,
            "remaining": item.quantity,
            "cost": round(cost, 2),
            "partner_charged": ledger is not None,
            "low_stock_alert": len(critical_items) > 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Writeoff error: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# =================================================================
# РЕГИСТРАЦИЯ РЕМОНТА
# =================================================================

@router.post("/repair/register")
async def register_repair(
    request: RepairRegistrationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Регистрация ремонта (v22.5)
    
    Автоматически:
    1. Списывает все запчасти
    2. Добавляет стоимость работы
    3. Суммирует и списывает с партнёра (если применимо)
    4. Создаёт запись в VehicleRepairHistory
    """
    try:
        vehicle = await db.get(Vehicle, request.vehicle_id)
        if not vehicle:
            raise HTTPException(status_code=404, detail="Машина не найдена")
        
        total_parts_cost = 0.0
        parts_details = []
        
        # 1. Списываем запчасти
        for part in request.parts:
            item = await db.get(WarehouseItem, part["item_id"])
            
            if not item:
                raise HTTPException(
                    status_code=404,
                    detail=f"Запчасть ID {part['item_id']} не найдена"
                )
            
            qty = part["quantity"]
            
            if item.quantity < qty:
                raise HTTPException(
                    status_code=400,
                    detail=f"Недостаточно {item.name}! Доступно: {item.quantity}"
                )
            
            # Списываем
            item.quantity -= qty
            cost = qty * item.price_unit
            total_parts_cost += cost
            
            parts_details.append({
                "name": item.name,
                "sku": item.sku,
                "quantity": qty,
                "price_unit": item.price_unit,
                "total": cost
            })
            
            # Лог склада
            log_entry = WarehouseLog(
                item_id=item.id,
                vehicle_id=request.vehicle_id,
                change=-qty,
                master_id=current_user.id,
                timestamp=datetime.now()
            )
            db.add(log_entry)
        
        # 2. Общая стоимость ремонта
        total_repair_cost = total_parts_cost + request.labor_cost
        
        # 3. Запись в VehicleRepairHistory
        from app.models.all_models import VehicleRepairHistory
        
        repair = VehicleRepairHistory(
            vehicle_id=request.vehicle_id,
            description=request.description,
            repair_cost=total_repair_cost,
            parts_json=parts_details,
            status="completed",
            created_at=datetime.now()
        )
        
        db.add(repair)
        
        # 4. Транзакция для Казны (P&L: REPAIR_EXPENSE)
        tx = Transaction(
            category="REPAIR_EXPENSE",
            contractor=request.mechanic_name,
            description=f"{vehicle.license_plate}: {request.description}",
            plate_info=vehicle.license_plate,
            amount=-total_repair_cost,
            tx_type="expense",
            date=datetime.now(),
            responsibility="Maintenance"
        )
        db.add(tx)
        
        # 5. Списание с партнёра
        stmt = select(PartnerLedger).where(
            PartnerLedger.vehicle_id == request.vehicle_id
        ).order_by(PartnerLedger.date.desc()).limit(1)
        
        result = await db.execute(stmt)
        ledger = result.scalar_one_or_none()
        
        if ledger:
            ledger.outgoing += total_repair_cost
            ledger.balance = ledger.incoming - ledger.outgoing
            
            logger.info(f"💸 Partner charged: {total_repair_cost:,.2f}₽ for repair")
        
        await db.commit()
        
        logger.info(f"✓ Repair registered: {vehicle.license_plate} | Cost: {total_repair_cost:,.2f}₽")
        
        # 5. Уведомление
        try:
            from app.services.telegram_bot import send_master_msg
            await send_master_msg(
                f"🔧 <b>РЕМОНТ ЗАВЕРШЁН</b>\n"
                f"🚗 {vehicle.brand} {vehicle.model} ({vehicle.license_plate})\n"
                f"📦 Запчасти: {total_parts_cost:,.2f}₽\n"
                f"👨‍🔧 Работа: {request.labor_cost:,.2f}₽\n"
                f"💰 Итого: <b>{total_repair_cost:,.2f}₽</b>\n"
                f"Механик: {request.mechanic_name}"
            )
        except:
            pass
        
        # 6. КОНТРОЛЬ ОСТАТКОВ (проверяем все использованные запчасти)
        critical_items = await check_low_stock(db)
        if critical_items:
            await send_low_stock_alert(critical_items)
        
        return {
            "status": "success",
            "repair_id": repair.id,
            "vehicle": f"{vehicle.brand} {vehicle.model} ({vehicle.license_plate})",
            "parts_cost": round(total_parts_cost, 2),
            "labor_cost": round(request.labor_cost, 2),
            "total_cost": round(total_repair_cost, 2),
            "parts_used": len(request.parts),
            "partner_charged": ledger is not None,
            "low_stock_items": len(critical_items)
        }
        
    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Register repair error: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# =================================================================
# ПРОВЕРКА ОСТАТКОВ (ENDPOINT)
# =================================================================

@router.get("/stock/check")
async def check_stock_levels(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Проверка уровня остатков на складе (v22.5+)
    
    Возвращает список всех позиций с критическим остатком (≤ 5)
    """
    try:
        critical_items = await check_low_stock(db)
        
        if not critical_items:
            return {
                "status": "ok",
                "message": "Все позиции в норме",
                "critical_items": [],
                "total_items": 0
            }
        
        # Отправляем уведомление
        await send_low_stock_alert(critical_items)
        
        return {
            "status": "warning",
            "message": f"Обнаружено {len(critical_items)} позиций с критическим остатком",
            "critical_items": critical_items,
            "total_items": len(critical_items),
            "critical_level": CRITICAL_LEVEL
        }
        
    except Exception as e:
        logger.error(f"Stock check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =================================================================
# ВИДЖЕТЫ СКЛАДА (IRON ORDER)
# =================================================================

@router.get("/stats/total_value")
async def get_warehouse_total_value(
    db: AsyncSession = Depends(get_db)
):
    """
    Общая стоимость склада (IRON ORDER)
    
    Возвращает сумму всех остатков в рублях
    """
    try:
        stmt = select(
            func.sum(WarehouseItem.quantity * WarehouseItem.price_unit)
        )
        result = await db.execute(stmt)
        total_value = result.scalar() or 0.0
        
        # Статистика по категориям
        stmt = select(
            WarehouseItem.category,
            func.sum(WarehouseItem.quantity * WarehouseItem.price_unit)
        ).group_by(WarehouseItem.category)
        result = await db.execute(stmt)
        categories = result.all()
        
        return {
            "total_value": round(float(total_value), 2),
            "categories": [
                {"name": cat[0] or "Без категории", "value": round(float(cat[1] or 0), 2)}
                for cat in categories
            ]
        }
        
    except Exception as e:
        logger.error(f"Warehouse total value error: {e}")
        return {"total_value": 0.0, "categories": []}

@router.get("/stats/top_expenses")
async def get_top_expenses(
    db: AsyncSession = Depends(get_db),
    days: int = 30
):
    """
    Топ трат на ремонт (IRON ORDER)
    
    Возвращает машины с максимальными расходами за период
    """
    try:
        from datetime import datetime, timedelta
        from sqlalchemy import and_
        
        start_date = datetime.now() - timedelta(days=days)
        
        # Группируем расходы по машинам
        stmt = select(
            PartnerLedger.vehicle_id,
            func.sum(PartnerLedger.outgoing).label('total_expenses')
        ).where(
            and_(
                PartnerLedger.date >= start_date.date(),
                PartnerLedger.outgoing > 0
            )
        ).group_by(
            PartnerLedger.vehicle_id
        ).order_by(
            func.sum(PartnerLedger.outgoing).desc()
        ).limit(5)
        
        result = await db.execute(stmt)
        top_expenses = result.all()
        
        # Получаем детали машин
        top_list = []
        for vehicle_id, total in top_expenses:
            vehicle = await db.get(Vehicle, vehicle_id)
            if vehicle:
                top_list.append({
                    "vehicle_id": vehicle_id,
                    "plate": vehicle.license_plate,
                    "brand": vehicle.brand or "",
                    "model": vehicle.model,
                    "total_expenses": round(float(total), 2)
                })
        
        return {
            "period_days": days,
            "top_expenses": top_list,
            "total": len(top_list)
        }
        
    except Exception as e:
        logger.error(f"Top expenses error: {e}")
        return {"period_days": days, "top_expenses": [], "total": 0}

@router.get("/stats/service_schedule")
async def get_service_schedule(
    db: AsyncSession = Depends(get_db),
    days: int = 7
):
    """
    График обслуживания (IRON ORDER)
    
    Возвращает статистику ТО/ремонтов за период
    """
    try:
        from app.models.all_models import VehicleRepairHistory
        from datetime import datetime, timedelta
        
        start_date = datetime.now() - timedelta(days=days)
        
        # Считаем ремонты по дням
        stmt = select(
            func.date(VehicleRepairHistory.created_at).label('repair_date'),
            func.count(VehicleRepairHistory.id).label('count'),
            func.sum(VehicleRepairHistory.repair_cost).label('total_cost')
        ).where(
            VehicleRepairHistory.created_at >= start_date
        ).group_by(
            func.date(VehicleRepairHistory.created_at)
        ).order_by(
            func.date(VehicleRepairHistory.created_at)
        )
        
        result = await db.execute(stmt)
        daily_stats = result.all()
        
        # Общая статистика
        stmt_total = select(
            func.count(VehicleRepairHistory.id),
            func.sum(VehicleRepairHistory.repair_cost)
        ).where(
            VehicleRepairHistory.created_at >= start_date
        )
        
        result_total = await db.execute(stmt_total)
        total_repairs, total_cost = result_total.first()
        
        return {
            "period_days": days,
            "total_repairs": int(total_repairs or 0),
            "total_cost": round(float(total_cost or 0), 2),
            "daily_stats": [
                {
                    "date": str(stat[0]),
                    "count": int(stat[1]),
                    "cost": round(float(stat[2] or 0), 2)
                }
                for stat in daily_stats
            ]
        }
        
    except Exception as e:
        logger.error(f"Service schedule error: {e}")
        return {"period_days": days, "total_repairs": 0, "total_cost": 0.0, "daily_stats": []}
