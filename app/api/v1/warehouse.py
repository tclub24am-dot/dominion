# -*- coding: utf-8 -*-
# app/routes/warehouse.py
# СКЛАД РЕСУРСОВ — Управление запчастями

import pandas as pd
import io
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, desc
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models.all_models import WarehouseItem, WarehouseLog, User, Vehicle
from app.services.auth import get_current_user

# Импорт Голоса Цитадели
try:
    from app.services.telegram_bot import send_master_msg
except ImportError:
    send_master_msg = None

logger = logging.getLogger("Dominion.Warehouse")
# v22.1: Prefix добавляется в main.py!
router = APIRouter(tags=["Склад: Ресурсы Цитадели"])

# =================================================================
# 1. ИНВЕНТАРИЗАЦИЯ
# =================================================================

@router.get("/inventory", response_class=HTMLResponse)
async def get_inventory(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Полный реестр запчастей — HTML для HTMX (v22.5)"""
    try:
        result = await db.execute(select(WarehouseItem).order_by(WarehouseItem.category, WarehouseItem.name))
        items = result.scalars().all()
        
        rows = []
        for item in items:
            rows.append(
                f"<tr><td>{item.sku}</td><td>{item.name}</td><td>{item.category}</td>"
                f"<td>{item.quantity}</td><td>{item.min_threshold}</td><td>{item.price}</td></tr>"
            )
        return HTMLResponse("".join(rows) or "<tr><td colspan='6'>Пусто</td></tr>", status_code=200)
    except Exception as e:
        logger.error(f"Warehouse inventory error: {e}")
        return HTMLResponse("<tr><td colspan='8'>Ошибка загрузки</td></tr>", status_code=200)

@router.post("/add-item")
async def add_new_item(
    name: str, sku: str, category: str, quantity: int, 
    min_threshold: int, price: float, 
    db: AsyncSession = Depends(get_db)
):
    """Ручное добавление новой позиции в арсенал"""
    existing = await db.execute(select(WarehouseItem).where(WarehouseItem.sku == sku))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Артикул {sku} уже существует в базе")
    
    item = WarehouseItem(
        name=name, sku=sku, category=category, 
        quantity=quantity, min_threshold=min_threshold, price_unit=price
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return {"status": "success", "item": item}

# =================================================================
# 2. МАССОВАЯ ЭКСПАНСИЯ (Загрузка файлов)
# =================================================================

@router.post("/upload-file")
async def upload_warehouse_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """Массовый импорт склада из CSV/Excel (name, sku, category, quantity, min_threshold, price_unit)"""
    contents = await file.read()
    filename = file.filename.lower()

    try:
        if filename.endswith('.csv'):
            try:
                # Сначала пробуем стандарт (UTF-8), затем Windows-1251 для русских файлов
                df = pd.read_csv(io.BytesIO(contents), sep=None, engine='python', encoding='utf-8')
            except:
                df = pd.read_csv(io.BytesIO(contents), sep=None, engine='python', encoding='cp1251')
        elif filename.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(io.BytesIO(contents))
        else:
            raise HTTPException(status_code=400, detail="Поддерживаются только форматы CSV и Excel")
    except Exception as e:
        logger.error(f"FILE READ ERROR: {e}")
        raise HTTPException(status_code=400, detail=f"Ошибка чтения файла: {str(e)}")

    required_columns = ['name', 'sku', 'category', 'quantity', 'min_threshold', 'price_unit']
    for col in required_columns:
        if col not in df.columns:
            raise HTTPException(status_code=400, detail=f"В файле отсутствует обязательная колонка: {col}")

    imported_count = 0
    for _, row in df.iterrows():
        sku_str = str(row['sku']).strip()
        # Проверка на дубликат, чтобы не плодить хаос
        existing = await db.execute(select(WarehouseItem).where(WarehouseItem.sku == sku_str))
        if existing.scalar_one_or_none():
            continue

        new_item = WarehouseItem(
            name=str(row['name']),
            sku=sku_str,
            category=str(row['category']),
            quantity=int(row['quantity']),
            min_threshold=int(row['min_threshold']),
            price_unit=float(row['price_unit'])
        )
        db.add(new_item)
        imported_count += 1

    await db.commit()
    logger.info(f"SUCCESS: Склад пополнен на {imported_count} позиций.")
    return {"status": "success", "imported_count": imported_count}

# =================================================================
# 3. ОКУЛЯР АНАЛИТИКА (Stats)
# =================================================================

@router.get("/stats")
async def get_warehouse_stats(db: AsyncSession = Depends(get_db)):
    """Сводка состояния ресурсов для Дашборда"""
    # Считаем дефицит
    low_stock_query = await db.execute(
        select(WarehouseItem).where(WarehouseItem.quantity <= WarehouseItem.min_threshold)
    )
    low_stock_items = low_stock_query.scalars().all()
    
    # Очередь на выдачу
    pending_count = await db.execute(
        select(func.count(WarehouseLog.id)).where(WarehouseLog.status == "pending")
    )
    
    return {
        "pending_issuance": pending_count.scalar() or 0,
        "low_stock_count": len(low_stock_items),
        "critical_items": [{"name": i.name, "qty": i.quantity, "sku": i.sku} for i in low_stock_items]
    }

# =================================================================
# 4. ОПЕРАЦИОННЫЙ ЦИКЛ (Выдача)
# =================================================================

@router.post("/request")
async def request_part(
    item_id: int, quantity: int, vehicle_id: int, master_id: int, 
    db: AsyncSession = Depends(get_db)
):
    """ЗАПРОС МАСТЕРА: Резервирование детали для ремонта"""
    item = await db.get(WarehouseItem, item_id)
    if not item or item.quantity < quantity:
        raise HTTPException(status_code=400, detail="Недостаточно ресурса на складе")
    
    new_log = WarehouseLog(
        item_id=item_id, change=-quantity, vehicle_id=vehicle_id,
        master_id=master_id
    )
    db.add(new_log)
    await db.commit()
    await db.refresh(new_log)
    return {"status": "success", "message": "Запрос создан.", "log_id": new_log.id}

@router.post("/issue/{log_id}")
async def issue_part(log_id: int, master_id: int, db: AsyncSession = Depends(get_db)):
    """ВЫДАЧА КЛАДОВЩИКОМ: Физическое списание со склада"""
    log = await db.get(WarehouseLog, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Запрос не найден")
    
    item = await db.get(WarehouseItem, log.item_id)
    
    # Списание
    item.quantity += log.change # log.change отрицательный
    log.master_id = master_id
    
    try:
        await db.commit()
        
        # УВЕДОМЛЕНИЕ МАСТЕРА
        if send_master_msg:
            await send_master_msg(
                f"📦 <b>СКЛАД: ВЫДАЧА РЕСУРСА</b>\n"
                f"🔹 Деталь: {item.name} ({item.sku})\n"
                f"🔹 Кол-во: {abs(log.change)} шт.\n"
                f"📉 Осаток на складе: <b>{item.quantity}</b>"
            )
        
        return {"status": "success", "remaining": item.quantity}
    except Exception as e:
        await db.rollback()
        logger.error(f"ISSUE ERROR: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при списании")

# =================================================================
# 5. ИСТОРИЯ
# =================================================================

@router.get("/history")
async def get_history(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """Архив всех движений ресурсов"""
    result = await db.execute(
        select(WarehouseLog)
        .options(joinedload(WarehouseLog.item)) # Если в модели прописан relationship
        .order_by(desc(WarehouseLog.timestamp))
        .limit(limit)
    )
    return result.scalars().all()
