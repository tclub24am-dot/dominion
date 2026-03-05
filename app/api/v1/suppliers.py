# -*- coding: utf-8 -*-
# app/routes/suppliers.py
# ПОСТАВЩИКИ И ЗАКУПКИ (v22.6 ГЛУБИНА)

import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.database import get_db
from app.models.all_models import User
from app.services.auth import get_current_user

logger = logging.getLogger("Suppliers")
router = APIRouter(tags=["Поставщики и Закупки"])

templates = Jinja2Templates(directory="app/templates")

# =================================================================
# МОДЕЛИ
# =================================================================

# Временное хранилище поставщиков (в продакшене - отдельная таблица)
SUPPLIERS_DB = [
    {
        "id": 1,
        "name": "ООО Автозапчасти Плюс",
        "contact": "Иванов И.И.",
        "phone": "+7 (495) 123-45-67",
        "items": ["Масло моторное", "Фильтры", "Тормозные колодки"],
        "delivery_days": 2,
        "min_order": 5000.0
    },
    {
        "id": 2,
        "name": "ИП Смирнов (Shell)",
        "contact": "Смирнов А.В.",
        "phone": "+7 (916) 234-56-78",
        "items": ["Масло Shell", "Антифриз", "Тормозная жидкость"],
        "delivery_days": 1,
        "min_order": 3000.0
    },
    {
        "id": 3,
        "name": "Автосервис Премиум",
        "contact": "Петров С.С.",
        "phone": "+7 (985) 345-67-89",
        "items": ["Свечи зажигания", "Аккумуляторы", "Лампы"],
        "delivery_days": 3,
        "min_order": 2000.0
    }
]

class PurchaseRequest(BaseModel):
    """Запрос на закупку"""
    supplier_id: int
    item_name: str
    quantity: int
    estimated_price: float
    urgency: str  # "normal", "urgent", "critical"
    notes: Optional[str] = None

# =================================================================
# ENDPOINTS
# =================================================================

@router.get("/suppliers/list")
async def get_suppliers(
    current_user: User = Depends(get_current_user)
):
    """
    Список поставщиков
    """
    return {
        "suppliers": SUPPLIERS_DB,
        "count": len(SUPPLIERS_DB)
    }


@router.get("/suppliers/{item_name}/suggest")
async def suggest_supplier(
    item_name: str,
    current_user: User = Depends(get_current_user)
):
    """
    Предложить поставщика для позиции
    
    Используется когда остаток критический
    """
    try:
        # Ищем поставщиков с этой позицией
        matches = []
        
        for supplier in SUPPLIERS_DB:
            # Fuzzy поиск
            for supplier_item in supplier["items"]:
                if item_name.lower() in supplier_item.lower() or supplier_item.lower() in item_name.lower():
                    matches.append({
                        "supplier_id": supplier["id"],
                        "supplier_name": supplier["name"],
                        "contact": supplier["contact"],
                        "phone": supplier["phone"],
                        "delivery_days": supplier["delivery_days"],
                        "min_order": supplier["min_order"]
                    })
                    break
        
        if len(matches) == 0:
            return {
                "found": False,
                "message": f"Поставщиков для '{item_name}' не найдено"
            }
        
        return {
            "found": True,
            "item": item_name,
            "suppliers": matches,
            "count": len(matches)
        }
        
    except Exception as e:
        logger.error(f"Supplier suggest error: {e}")
        return {"found": False, "error": str(e)}


@router.post("/purchase/request")
async def create_purchase_request(
    request: PurchaseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Создать запрос на закупку (v22.6 ГЛУБИНА)
    
    При критическом остатке:
    1. Создаётся заявка
    2. Уведомление менеджеру
    3. Кнопка "Заказать у [Поставщик]" в боте
    """
    try:
        # Находим поставщика
        supplier = next((s for s in SUPPLIERS_DB if s["id"] == request.supplier_id), None)
        
        if not supplier:
            raise HTTPException(status_code=404, detail="Поставщик не найден")
        
        # Создаём уведомление
        urgency_icon = "🚨" if request.urgency == "critical" else "⚠️" if request.urgency == "urgent" else "📝"
        
        try:
            from app.services.telegram_bot import send_master_msg
            
            message = f"{urgency_icon} <b>ЗАПРОС НА ЗАКУПКУ</b>\n\n"
            message += f"📦 <b>{request.item_name}</b>\n"
            message += f"🔢 Количество: {request.quantity} ед.\n"
            message += f"💰 Ориентировочная стоимость: {request.estimated_price:,.0f}₽\n\n"
            message += f"🏢 Поставщик: <b>{supplier['name']}</b>\n"
            message += f"📞 Контакт: {supplier['contact']}\n"
            message += f"☎️ Телефон: {supplier['phone']}\n"
            message += f"🚚 Доставка: {supplier['delivery_days']} дн.\n"
            message += f"💵 Мин. заказ: {supplier['min_order']:,.0f}₽\n\n"
            
            if request.notes:
                message += f"📝 Примечание: {request.notes}\n\n"
            
            message += f"👤 Запросил: {current_user.full_name}\n"
            message += f"⏰ Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            
            await send_master_msg(message)
            
            logger.info(f"✓ Purchase request sent: {request.item_name} x{request.quantity} from {supplier['name']}")
            
        except Exception as notify_error:
            logger.warning(f"Failed to send notification: {notify_error}")
        
        return {
            "status": "success",
            "message": "Запрос на закупку отправлен Мастеру",
            "supplier": supplier["name"],
            "item": request.item_name,
            "quantity": request.quantity,
            "estimated_total": round(request.estimated_price * request.quantity, 2)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Purchase request error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
