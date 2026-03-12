# -*- coding: utf-8 -*-
# app/routes/consulting_crm.py
# CRM СИСТЕМА ДЛЯ ЭКСПЕРТНЫХ УСЛУГ (v22.6 КОМБАЙН)

import logging
from typing import Optional
from datetime import datetime, date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel

from app.database import get_db
from app.models.consulting import ConsultingClient, ConsultingService, ServiceType, ServiceStatus
from app.models.all_models import Transaction, User
from app.services.auth import get_current_user

logger = logging.getLogger("ConsultingCRM")
router = APIRouter(tags=["Consulting CRM"])

templates = Jinja2Templates(directory="app/templates")

# =================================================================
# SCHEMAS
# =================================================================

class ClientCreate(BaseModel):
    name: str
    contact_person: str
    phone: str
    email: Optional[str] = None
    client_type: str = "company"

class ServiceCreate(BaseModel):
    client_id: int
    service_type: ServiceType
    service_name: str
    description: Optional[str] = None
    price: float
    license_expires_at: Optional[str] = None  # Для лицензий

# =================================================================
# КЛИЕНТЫ
# =================================================================

@router.post("/clients/create")
async def create_client(
    client: ClientCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Создание нового клиента"""
    try:
        new_client = ConsultingClient(
            name=client.name,
            contact_person=client.contact_person,
            phone=client.phone,
            email=client.email,
            client_type=client.client_type,
            created_at=datetime.now()
        )
        
        db.add(new_client)
        await db.commit()
        await db.refresh(new_client)
        
        logger.info(f"✓ Client created: {client.name}")
        
        return {
            "status": "success",
            "client_id": new_client.id,
            "name": new_client.name
        }
        
    except Exception as e:
        logger.error(f"Create client error: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/clients/list")
async def list_clients(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Список всех клиентов"""
    try:
        stmt = select(ConsultingClient).where(ConsultingClient.is_active == True)
        result = await db.execute(stmt)
        clients = result.scalars().all()
        
        return {
            "clients": [
                {
                    "id": c.id,
                    "name": c.name,
                    "contact": c.contact_person,
                    "phone": c.phone,
                    "type": c.client_type
                }
                for c in clients
            ],
            "count": len(clients)
        }
        
    except Exception as e:
        logger.error(f"List clients error: {e}")
        return {"clients": [], "count": 0}

# =================================================================
# УСЛУГИ (ВОРОНКА ПРОДАЖ)
# =================================================================

@router.post("/services/create")
async def create_service(
    service: ServiceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Создание услуги (запись в воронке продаж)
    
    Автоматически:
    - Создаёт услугу со статусом LEAD
    - Если указан license_expires_at - настраивает напоминание
    """
    try:
        license_date = None
        if service.license_expires_at:
            license_date = date.fromisoformat(service.license_expires_at)
        
        new_service = ConsultingService(
            client_id=service.client_id,
            service_type=service.service_type,
            service_name=service.service_name,
            description=service.description,
            price=service.price,
            status=ServiceStatus.LEAD,
            license_expires_at=license_date,
            manager_id=current_user.id,
            created_at=datetime.now()
        )
        
        db.add(new_service)
        await db.commit()
        await db.refresh(new_service)
        
        logger.info(f"✓ Service created: {service.service_name} for client {service.client_id}")
        
        return {
            "status": "success",
            "service_id": new_service.id,
            "service_name": new_service.service_name
        }
        
    except Exception as e:
        logger.error(f"Create service error: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/services/{service_id}/status")
async def update_service_status(
    service_id: int,
    new_status: ServiceStatus,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Обновление статуса услуги в воронке
    
    При переходе в "paid":
    - Создаётся Transaction для Казны
    - Доход автоматически суммируется
    """
    try:
        service = await db.get(ConsultingService, service_id)
        if not service:
            raise HTTPException(status_code=404, detail="Услуга не найдена")
        
        old_status = service.status
        service.status = new_status
        
        # Обновляем временные метки
        if new_status == ServiceStatus.DOCUMENTS:
            service.documents_collected_at = datetime.now()
        elif new_status == ServiceStatus.IN_PROGRESS:
            service.started_at = datetime.now()
        elif new_status == ServiceStatus.COMPLETED:
            service.completed_at = datetime.now()
        elif new_status == ServiceStatus.PAID:
            service.paid_at = datetime.now()
            service.paid_amount = service.price
            
            # ФИНАНСОВАЯ СТЫКОВКА: Создаём транзакцию для Казны
            transaction = Transaction(
                category="Consulting_Income",
                contractor=service.service_name,
                description=f"Консалтинг: {service.service_name}",
                amount=service.price,  # Положительная
                tx_type="income",
                date=datetime.now(),
                responsibility="Consulting"
            )
            db.add(transaction)
            
            logger.info(f"💰 Consulting income added to Kazna: {service.price:,.0f}₽")
        
        await db.commit()
        
        logger.info(f"✓ Service {service_id} status: {old_status} → {new_status}")
        
        return {
            "status": "success",
            "service_id": service_id,
            "old_status": old_status,
            "new_status": new_status,
            "message": "Статус обновлён" + (" | Доход добавлен в Казну" if new_status == ServiceStatus.PAID else "")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update service status error: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/services/expiring-licenses")
async def get_expiring_licenses(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Получить лицензии истекающие в ближайшие N дней
    
    Используется для авто-напоминаний
    """
    try:
        cutoff_date = date.today() + timedelta(days=days)
        
        stmt = select(ConsultingService).where(
            and_(
                ConsultingService.license_expires_at <= cutoff_date,
                ConsultingService.license_expires_at >= date.today(),
                ConsultingService.status.in_([ServiceStatus.IN_PROGRESS, ServiceStatus.COMPLETED, ServiceStatus.PAID])
            )
        )
        
        result = await db.execute(stmt)
        services = result.scalars().all()
        
        expiring = []
        
        for s in services:
            # Получаем клиента
            client = await db.get(ConsultingClient, s.client_id)
            
            days_left = (s.license_expires_at - date.today()).days
            
            expiring.append({
                "service_id": s.id,
                "client_name": client.name if client else "N/A",
                "client_phone": client.phone if client else "N/A",
                "service_name": s.service_name,
                "expires_at": s.license_expires_at.isoformat(),
                "days_left": days_left,
                "urgency": "critical" if days_left <= 7 else "warning"
            })
        
        # Отправляем уведомление если есть критические
        critical = [e for e in expiring if e["urgency"] == "critical"]
        
        if critical:
            try:
                from app.services.telegram_bot import send_master_msg
                
                message = "⚠️ <b>ИСТЕКАЮЩИЕ ЛИЦЕНЗИИ</b>\n\n"
                
                for item in critical:
                    message += f"🏢 <b>{item['client_name']}</b>\n"
                    message += f"📋 {item['service_name']}\n"
                    message += f"⏰ Осталось: <b>{item['days_left']} дн.</b>\n"
                    message += f"📞 {item['client_phone']}\n\n"
                
                message += "💡 Мастер, пора продлевать лицензии!"
                
                await send_master_msg(message)
                
            except Exception as notify_error:
                logger.warning(f"Failed to send expiring licenses notification: {notify_error}")
        
        logger.info(f"✓ Found {len(expiring)} expiring licenses ({len(critical)} critical)")
        
        return {
            "expiring": expiring,
            "count": len(expiring),
            "critical_count": len(critical)
        }
        
    except Exception as e:
        logger.error(f"Expiring licenses error: {e}")
        return {"expiring": [], "count": 0}


@router.get("/stats/income")
async def get_consulting_income(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Доход от консалтинга за период
    
    Для графика в Казне
    """
    try:
        from sqlalchemy import func
        
        cutoff = datetime.now() - timedelta(days=days)
        
        # Доход из транзакций
        stmt = select(func.sum(Transaction.amount)).where(
            and_(
                Transaction.category == "Consulting_Income",
                Transaction.date >= cutoff.date(),
                Transaction.amount > 0
            )
        )
        
        result = await db.execute(stmt)
        total_income = float(result.scalar() or 0)
        
        # По типам услуг
        stmt = select(ConsultingService).where(
            and_(
                ConsultingService.status == ServiceStatus.PAID,
                ConsultingService.paid_at >= cutoff
            )
        )
        
        result = await db.execute(stmt)
        services = result.scalars().all()
        
        by_type = {}
        for s in services:
            service_type = s.service_type.value
            if service_type not in by_type:
                by_type[service_type] = 0
            by_type[service_type] += s.paid_amount
        
        return {
            "total_income": round(total_income, 2),
            "period_days": days,
            "by_type": by_type,
            "services_count": len(services)
        }
        
    except Exception as e:
        logger.error(f"Consulting income error: {e}")
        return {
            "total_income": 0.0,
            "period_days": days,
            "by_type": {},
            "services_count": 0
        }
