# -*- coding: utf-8 -*-
# app/routes/hr_center.py
# ГЛУБИННЫЙ HR-ЦЕНТР (v22.6 СУПЕРПОЗИЦИЯ)

import logging
from typing import Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from pathlib import Path

from app.database import get_db
from app.models.all_models import User, Transaction, FineInstallment, DriverTensionHistory, DriverProfile
from app.services.auth import get_current_user
from app.services.driver_scoring import driver_scoring

logger = logging.getLogger("HRCenter")
router = APIRouter(tags=["HR Center: Глубинный"])

templates = Jinja2Templates(directory="app/templates")

@router.get("/driver/{driver_id}/profile", response_class=HTMLResponse)
async def get_driver_profile(
    driver_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    ЛИЧНОЕ ДЕЛО ВОДИТЕЛЯ 360° (v22.6 ГЛУБИНА)
    
    Показывает:
    - Архив документов
    - История инцидентов
    - Финансовая карта
    - AI-скоринг
    - Статус в чёрном списке
    """
    try:
        # Получаем водителя
        driver = await db.get(User, driver_id)
        if not driver:
            raise HTTPException(status_code=404, detail="Водитель не найден")
        
        # AI-СКОРИНГ
        scoring = await driver_scoring.calculate_reliability_score(driver_id, db)
        
        # ЧЁРНЫЙ СПИСОК
        blacklist = await driver_scoring.check_blacklist_status(driver_id, db)
        
        # ДОКУМЕНТЫ (из DriverProfile)
        stmt = select(DriverProfile).where(DriverProfile.driver_id == driver_id)
        result = await db.execute(stmt)
        profile = result.scalar_one_or_none()
        
        documents = {
            "passport": {"status": "active", "expires": None},
            "license": {"status": "active", "expires": profile.license_expiry if profile else None},
            "contract": {"status": "active", "signed": None}
        }
        
        # Проверка сроков
        green_status = True
        if profile and profile.license_expiry:
            days_until = (profile.license_expiry - datetime.now().date()).days
            if days_until < 30:
                documents["license"]["status"] = "expiring_soon"
                green_status = False
            elif days_until < 0:
                documents["license"]["status"] = "expired"
                green_status = False
        
        # ИСТОРИЯ ИНЦИДЕНТОВ (последние 90 дней)
        cutoff = datetime.now() - timedelta(days=90)
        
        # Штрафы
        stmt = select(Transaction).where(
            and_(
                Transaction.contractor == driver.full_name,
                Transaction.category.like("%Штраф%"),
                Transaction.date >= cutoff.date()
            )
        ).order_by(desc(Transaction.date))
        
        result = await db.execute(stmt)
        fines = result.scalars().all()
        
        incidents = []
        for fine in fines:
            incidents.append({
                "type": "fine",
                "date": fine.date,
                "icon": "⚠️",
                "title": "Штраф",
                "description": fine.description or "Штраф",
                "amount": abs(fine.amount),
                "severity": "medium"
            })
        
        # ФИНАНСОВАЯ КАРТА
        stmt = select(FineInstallment).where(
            FineInstallment.driver_id == driver_id
        )
        result = await db.execute(stmt)
        debt_info = result.scalar_one_or_none()
        
        financial = {
            "total_debt": debt_info.total_debt_amount if debt_info else 0,
            "remaining_debt": debt_info.remaining_debt if debt_info else 0,
            "daily_deduction": debt_info.daily_deduction_default if debt_info else 0,
            "deposits": 0,  # TODO: интеграция
            "total_earnings": 0  # TODO: интеграция
        }
        
        data = {
            "driver": driver,
            "scoring": scoring,
            "blacklist": blacklist,
            "documents": documents,
            "green_status": green_status and not blacklist["blacklisted"],
            "incidents": incidents,
            "financial": financial
        }
        
        return templates.TemplateResponse(
            "driver_profile.html",
            {"request": request, "data": data}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Driver profile error: {e}", exc_info=True)
        return HTMLResponse(
            content=f'<div style="padding: 20px; color: #ff5252;">⚠️ Ошибка загрузки профиля: {str(e)}</div>',
            status_code=200
        )


@router.post("/driver/{driver_id}/upload-document")
async def upload_driver_document(
    driver_id: int,
    file: UploadFile = File(...),
    doc_type: str = "other",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Загрузка документа водителя
    
    Типы: passport, license, contract, medical, other
    """
    try:
        # Создаём папку для документов
        docs_dir = Path(f"/root/dominion/storage/driver_documents/{driver_id}")
        docs_dir.mkdir(parents=True, exist_ok=True)
        
        # Сохраняем файл
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{doc_type}_{timestamp}_{file.filename}"
        filepath = docs_dir / filename
        
        content = await file.read()
        filepath.write_bytes(content)
        
        logger.info(f"✓ Document uploaded: {filename} for driver {driver_id}")
        
        return {
            "status": "success",
            "filename": filename,
            "doc_type": doc_type,
            "size": len(content),
            "path": str(filepath)
        }
        
    except Exception as e:
        logger.error(f"Document upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/driver/{driver_id}/blacklist")
async def add_to_blacklist(
    driver_id: int,
    reason: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Добавление в чёрный список
    
    Блокирует возможность привязки к машинам
    """
    try:
        driver = await db.get(User, driver_id)
        if not driver:
            raise HTTPException(status_code=404, detail="Водитель не найден")
        
        # Деактивируем аккаунт
        driver.is_active = False
        
        await db.commit()
        
        # УВЕДОМЛЕНИЕ ОРАКУЛА
        try:
            from app.services.telegram_bot import send_master_msg
            
            message = f"🚨 <b>ЧЁРНЫЙ СПИСОК</b>\n\n"
            message += f"👤 Водитель: <b>{driver.full_name}</b>\n"
            message += f"📞 Телефон: {driver.username}\n"
            message += f"⚠️ Причина: {reason}\n\n"
            message += f"🔒 Аккаунт деактивирован\n"
            message += f"🚫 Блокировка привязки к машинам\n\n"
            message += f"👤 Заблокировал: {current_user.full_name}\n"
            message += f"⏰ Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            
            await send_master_msg(message)
            
        except Exception as notify_error:
            logger.warning(f"Failed to send blacklist notification: {notify_error}")
        
        logger.warning(f"⚠️ Driver {driver_id} ({driver.full_name}) added to BLACKLIST: {reason}")
        
        return {
            "status": "success",
            "message": "Водитель добавлен в чёрный список",
            "driver": driver.full_name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Blacklist error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/drivers/list-with-scoring")
async def list_drivers_with_scoring(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Список водителей с AI-скорингом
    
    Для каждого водителя вычисляет:
    - Коэффициент надёжности
    - Звёзды лояльности (1-5)
    - Статус (excellent/good/warning/critical)
    """
    try:
        # Получаем всех водителей
        stmt = select(User).where(User.role == "Driver")
        result = await db.execute(stmt)
        drivers = result.scalars().all()
        
        drivers_with_scoring = []
        
        for driver in drivers:
            scoring = await driver_scoring.calculate_reliability_score(driver.id, db)
            blacklist = await driver_scoring.check_blacklist_status(driver.id, db)
            
            drivers_with_scoring.append({
                "id": driver.id,
                "name": driver.full_name,
                "phone": driver.username,
                "rating": driver.rating,
                "score": scoring["score"],
                "stars": scoring["stars"],
                "status": scoring["status"],
                "blacklisted": blacklist["blacklisted"],
                "is_active": driver.is_active
            })
        
        return {
            "drivers": drivers_with_scoring,
            "count": len(drivers_with_scoring)
        }
        
    except Exception as e:
        logger.error(f"Drivers list error: {e}")
        return {"drivers": [], "count": 0}


# ============================================================
# LOGIST-PAY: HR-Метрики для Dashboard (v200.16.6)
# ============================================================

@router.get("/salary-status")
async def salary_status(
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    /api/v1/hr/salary-status — Статус ЗП логиста для Dashboard.
    
    Возвращает:
    - base_salary: Оклад 130 000₽
    - m4_fines_count: Количество штрафов М4 за период
    - m4_fine_penalty_each: 2 000₽ за каждое опоздание
    - total_fines_penalty: Общая сумма штрафов
    - final_salary: Итоговая сумма к выплате
    - audit_entity: ИП Мкртчян
    
    Протокол: LOGIST-PAY v200.16.6
    """
    try:
        from app.services.hr_engine import calculate_logistic_salary
        
        now = datetime.now()
        y = year or now.year
        m = month or now.month
        
        report = await calculate_logistic_salary(db, current_user.id, y, m)
        return {"status": "success", "data": report}
    except Exception as e:
        logger.error(f"[HR] salary-status error: {e}")
        return {"status": "error", "detail": str(e)}

@router.get("/logist-pay/dashboard")
async def hr_dashboard_metrics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    HR-Метрики для Dashboard Мастера:
    - Текущая ЗП логиста (онлайн)
    - Счётчик штрафов М4 за сегодня
    - Статус возврата тары
    
    Аудит: ИП Мкртчян (IT Service Fee Controller)
    """
    try:
        from app.services.hr_engine import get_hr_dashboard_metrics
        metrics = await get_hr_dashboard_metrics(db, current_user.id)
        return {"status": "success", "data": metrics}
    except Exception as e:
        logger.error(f"[LOGIST-PAY] Dashboard metrics error: {e}")
        return {"status": "error", "detail": str(e)}


@router.get("/logist-pay/salary/{user_id}")
async def calculate_salary(
    user_id: int,
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Расчёт ЗП логиста по формуле LOGIST-PAY:
    Salary = Base + Margin_Bonus - M4_Fines_Penalties
    
    IDOR FIX v200.16.4: только свои данные или master/admin.
    Аудит: ИП Мкртчян
    """
    # IDOR FIX: пользователь может видеть только свою ЗП, master/admin — любую
    user_role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    if current_user.id != user_id and user_role not in ("master", "admin"):
        raise HTTPException(
            status_code=403,
            detail="Доступ к чужим данным ЗП запрещён. Только master/admin могут просматривать ЗП других сотрудников."
        )
    try:
        from app.services.hr_engine import calculate_logistic_salary
        
        now = datetime.now()
        y = year or now.year
        m = month or now.month
        
        report = await calculate_logistic_salary(db, user_id, y, m)
        return {"status": "success", "data": report}
    except Exception as e:
        logger.error(f"[LOGIST-PAY] Salary calc error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
