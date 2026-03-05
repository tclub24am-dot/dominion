# -*- coding: utf-8 -*-
# app/routes/partner.py
# PARTNER HUB v22.5 — Швейцарская прозрачность

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc
from datetime import datetime, timedelta, date
from pydantic import BaseModel
from decimal import Decimal

from app.database import get_db
from app.models.all_models import Partner, PartnerLedger, Vehicle, Transaction
from app.services.auth import get_current_user
from app.models.all_models import User
from app.services.analytics_engine import AnalyticsEngine
from app.services.telegram_bot import telegram_bot

logger = logging.getLogger("PartnerHub")
router = APIRouter(tags=["Partner Hub"])

templates = Jinja2Templates(directory="app/templates")

# =================================================================
# PARTNER DASHBOARD API (v30.0 EXTREME)
# =================================================================

@router.get("/list", response_class=HTMLResponse)
async def partners_list_html(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Список партнёров с карточками (HTML для HTMX)
    """
    try:
        # Получаем всех активных партнёров
        stmt = select(Partner).where(Partner.is_active == True).order_by(Partner.name)
        result = await db.execute(stmt)
        partners = result.scalars().all()
        
        # Для каждого партнёра получаем баланс
        partners_data = []
        
        for partner in partners:
            # Считаем incoming (доход от машин)
            stmt_incoming = select(func.sum(PartnerLedger.incoming)).where(
                PartnerLedger.partner_id == partner.id
            )
            result_incoming = await db.execute(stmt_incoming)
            total_incoming = float(result_incoming.scalar() or 0)
            
            # Считаем outgoing (расходы)
            stmt_outgoing = select(func.sum(PartnerLedger.outgoing)).where(
                PartnerLedger.partner_id == partner.id
            )
            result_outgoing = await db.execute(stmt_outgoing)
            total_outgoing = float(result_outgoing.scalar() or 0)
            
            # Считаем выплачено (пометка paid)
            stmt_paid = select(func.sum(PartnerLedger.outgoing)).where(
                and_(
                    PartnerLedger.partner_id == partner.id,
                    PartnerLedger.expense_type == "Payout"
                )
            )
            result_paid = await db.execute(stmt_paid)
            total_paid = float(result_paid.scalar() or 0)
            
            # Баланс = incoming - outgoing - paid
            balance = total_incoming - total_outgoing - total_paid
            
            # Получаем машины партнёра
            stmt_vehicles = select(Vehicle).where(
                Vehicle.owner_id == partner.id
            )
            result_vehicles = await db.execute(stmt_vehicles)
            vehicles = result_vehicles.scalars().all()
            
            partners_data.append({
                "id": partner.id,
                "name": partner.name,
                "phone": partner.phone,
                "balance": round(balance, 2),
                "total_incoming": round(total_incoming, 2),
                "total_outgoing": round(total_outgoing, 2),
                "vehicles_count": len(vehicles),
                "vehicles": [{"id": v.id, "plate": v.license_plate} for v in vehicles[:3]]  # Первые 3
            })
        
        logger.info(f"✓ Loaded {len(partners_data)} partners")
        
        cards = []
        for p in partners_data:
            cards.append(
                f"<div class='card'><div>{p['name']}</div><div>{p['balance']} ₽</div></div>"
            )
        return HTMLResponse("".join(cards) or "<div>Нет партнеров</div>", status_code=200)
        
    except Exception as e:
        logger.error(f"Partners list error: {e}", exc_info=True)
        return HTMLResponse(
            content=f'<div style="padding: 20px; color: #ff5252;">⚠️ Ошибка: {str(e)}</div>',
            status_code=200
        )


@router.get("/{partner_id}/ledger", response_class=HTMLResponse)
async def partner_ledger_modal(
    partner_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Личный Ledger партнёра (модальное окно)
    """
    try:
        # Получаем партнёра
        partner = await db.get(Partner, partner_id)
        if not partner:
            raise HTTPException(status_code=404, detail="Партнёр не найден")
        
        # Получаем все записи ledger за последние 30 дней
        cutoff = datetime.now() - timedelta(days=30)
        
        stmt = select(PartnerLedger).where(
            and_(
                PartnerLedger.partner_id == partner_id,
                PartnerLedger.date >= cutoff.date()
            )
        ).order_by(PartnerLedger.date.desc())
        
        result = await db.execute(stmt)
        ledger_entries = result.scalars().all()
        
        # Считаем баланс
        stmt_incoming = select(func.sum(PartnerLedger.incoming)).where(
            PartnerLedger.partner_id == partner_id
        )
        result_incoming = await db.execute(stmt_incoming)
        total_incoming = float(result_incoming.scalar() or 0)
        
        stmt_outgoing = select(func.sum(PartnerLedger.outgoing)).where(
            PartnerLedger.partner_id == partner_id
        )
        result_outgoing = await db.execute(stmt_outgoing)
        total_outgoing = float(result_outgoing.scalar() or 0)
        
        balance = total_incoming - total_outgoing
        
        # Получаем машины
        stmt_vehicles = select(Vehicle).where(Vehicle.owner_id == partner_id)
        result_vehicles = await db.execute(stmt_vehicles)
        vehicles = result_vehicles.scalars().all()
        
        rows = [
            f"<div>{l.date} • +{l.incoming} / -{l.outgoing} • {l.description}</div>"
            for l in ledger_entries
        ]
        html = (
            f"<div><strong>{partner.name}</strong></div>"
            f"<div>Баланс: {round(balance, 2)} ₽</div>"
            f"<div>Приход: {round(total_incoming, 2)} ₽</div>"
            f"<div>Расход: {round(total_outgoing, 2)} ₽</div>"
            + ("".join(rows) or "<div>Нет операций</div>")
        )
        return HTMLResponse(html, status_code=200)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Partner ledger error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class PayoutRequest(BaseModel):
    partner_id: int
    amount: float
    description: str = "Выплата партнёру"


@router.post("/{partner_id}/payout")
async def partner_payout(
    partner_id: int,
    payload: PayoutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Зафиксировать выплату партнёру
    """
    try:
        # Проверяем партнёра
        partner = await db.get(Partner, partner_id)
        if not partner:
            raise HTTPException(status_code=404, detail="Партнёр не найден")
        
        # Считаем текущий баланс
        stmt_incoming = select(func.sum(PartnerLedger.incoming)).where(
            PartnerLedger.partner_id == partner_id
        )
        result_incoming = await db.execute(stmt_incoming)
        total_incoming = float(result_incoming.scalar() or 0)
        
        stmt_outgoing = select(func.sum(PartnerLedger.outgoing)).where(
            PartnerLedger.partner_id == partner_id
        )
        result_outgoing = await db.execute(stmt_outgoing)
        total_outgoing = float(result_outgoing.scalar() or 0)
        
        current_balance = total_incoming - total_outgoing
        
        # Проверяем что хватает средств
        if current_balance < payload.amount:
            raise HTTPException(
                status_code=400,
                detail=f"Недостаточно средств. Баланс: {current_balance:,.2f}₽"
            )
        
        # Создаём запись о выплате
        payout_entry = PartnerLedger(
            partner_id=partner_id,
            vehicle_id=None,  # Выплата не привязана к конкретной машине
            incoming=0.0,
            outgoing=payload.amount,
            expense_type="Payout",
            expense_description=payload.description,
            date=datetime.now().date()
        )
        
        db.add(payout_entry)
        
        # Создаём транзакцию в общей бухгалтерии
        transaction = Transaction(
            category="Partner_Payout",
            contractor=partner.name,
            description=f"Выплата партнёру: {payload.description}",
            amount=-payload.amount,
            tx_type="expense",
            date=datetime.now(),
            responsibility="park"
        )
        
        db.add(transaction)
        
        await db.commit()
        
        new_balance = current_balance - payload.amount
        
        logger.info(f"✓ Payout recorded: {partner.name} - {payload.amount:,.2f}₽")
        
        return {
            "status": "success",
            "message": f"Выплата {payload.amount:,.2f}₽ зафиксирована",
            "partner_id": partner_id,
            "partner_name": partner.name,
            "amount": payload.amount,
            "new_balance": round(new_balance, 2),
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Payout error: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

class FirePayRequest(BaseModel):
    driver_id: int
    amount: Optional[float] = None
    description: str = "Моментальная выплата водителю"

@router.post("/fire-pay")
async def fire_pay_driver(
    payload: FirePayRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Моментальная выплата живому водителю (FIRE PAY)
    """
    driver = await db.get(User, payload.driver_id)
    if not driver or driver.role != "Driver":
        raise HTTPException(status_code=404, detail="Водитель не найден")
    is_live = await AnalyticsEngine.is_live_driver(db, driver)
    if not driver.is_active or not driver.yandex_driver_id or not is_live:
        raise HTTPException(status_code=400, detail="Водитель не активен")
    amount = float(payload.amount or driver.driver_balance or 0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Сумма выплаты должна быть больше 0")
    if driver.driver_balance is None or driver.driver_balance < amount:
        raise HTTPException(status_code=400, detail="Недостаточно средств на балансе водителя")

    driver.driver_balance = float(driver.driver_balance) - amount
    transaction = Transaction(
        category="Fire_Pay",
        category_type="PAYOUT",
        contractor=driver.full_name,
        description=f"Срочно: FIRE PAY водителю {driver.full_name}",
        amount=-amount,
        tx_type="expense",
        date=datetime.now(),
        responsibility="park"
    )
    db.add(transaction)
    await db.commit()
    await telegram_bot.send_to_user(
        driver.telegram_id,
        "Мастер Спартак одобрил моментальную выплату! ПОБЕДА и ВЕЗЕНИЕ!"
    )
    return {
        "status": "queued",
        "driver_id": driver.id,
        "driver_name": driver.full_name,
        "amount": amount,
        "is_live": True,
        "message": "Выплата зафиксирована и отправлена в очередь"
    }

# =================================================================
# PARTNER AUTH (SMS/Telegram Code)
# =================================================================

class PartnerLoginRequest(BaseModel):
    phone: str
    code: str

@router.post("/partner/login")
async def partner_login(
    payload: PartnerLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Вход партнёра по телефону + код
    """
    try:
        stmt = select(Partner).where(
            and_(
                Partner.phone == payload.phone,
                Partner.login_code == payload.code,
                Partner.is_active == True
            )
        )
        
        result = await db.execute(stmt)
        partner = result.scalar_one_or_none()
        
        if not partner:
            raise HTTPException(status_code=401, detail="Неверный код")
        
        # Обновляем last_login
        partner.last_login = datetime.now()
        await db.commit()
        
        # TODO: Создать JWT токен для партнёра
        
        return {
            "status": "success",
            "partner_id": partner.id,
            "name": partner.name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Partner login error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/partner/dashboard", response_class=HTMLResponse)
async def partner_dashboard(
    request: Request,
    partner_id: int,  # TODO: из JWT токена
    db: AsyncSession = Depends(get_db)
):
    """
    ПАРТНЁРСКИЙ КАБИНЕТ
    """
    try:
        # Получаем партнёра
        stmt = select(Partner).where(Partner.id == partner_id)
        result = await db.execute(stmt)
        partner = result.scalar_one_or_none()
        
        if not partner:
            raise HTTPException(status_code=404, detail="Партнёр не найден")
        
        # Получаем его машины
        stmt = select(Vehicle).join(
            # TODO: добавить partner_id в Vehicle
        ).limit(10)
        
        # Получаем финансы за месяц
        month_ago = datetime.now() - timedelta(days=30)
        
        stmt = select(
            func.sum(PartnerLedger.incoming),
            func.sum(PartnerLedger.outgoing)
        ).where(
            and_(
                PartnerLedger.partner_id == partner_id,
                PartnerLedger.date >= month_ago.date()
            )
        )
        
        result = await db.execute(stmt)
        incoming, outgoing = result.first()
        
        incoming = float(incoming) if incoming else 0.0
        outgoing = float(outgoing) if outgoing else 0.0
        profit = incoming - outgoing
        
        data = {
            "partner": partner,
            "vehicles_count": 0,  # TODO
            "incoming": incoming,
            "outgoing": outgoing,
            "profit": profit,
            "period": "30 дней"
        }
        
        html = (
            f"<div><strong>{partner.name}</strong></div>"
            f"<div>Приход: {incoming} ₽</div>"
            f"<div>Расход: {outgoing} ₽</div>"
            f"<div>Профит: {profit} ₽</div>"
        )
        return HTMLResponse(html, status_code=200)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Partner dashboard error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/partner/vehicles")
async def partner_vehicles(
    partner_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Мой Флот — список машин партнёра
    """
    try:
        # TODO: получить машины партнёра
        vehicles = []
        
        return {
            "status": "success",
            "vehicles": vehicles,
            "count": len(vehicles)
        }
        
    except Exception as e:
        logger.error(f"Partner vehicles error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =================================================================
# ADMIN ENDPOINTS (Для Мастера)
# =================================================================

@router.get("/list", response_class=HTMLResponse)
async def partners_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Список всех партнёров — возвращает HTML для HTMX (v22.5)
    """
    try:
        stmt = select(Partner).order_by(Partner.name)
        result = await db.execute(stmt)
        partners_db = result.scalars().all()
        
        # Для каждого партнёра считаем статистику
        partners = []
        
        for p in partners_db:
            # Считаем машины через PartnerLedger
            stmt_vehicles = select(func.count(func.distinct(PartnerLedger.vehicle_id))).where(
                PartnerLedger.partner_id == p.id
            )
            vehicles_result = await db.execute(stmt_vehicles)
            vehicles_count = vehicles_result.scalar() or 0
            
            # Считаем задолженность за текущий месяц
            month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            stmt_ledger = select(
                func.sum(PartnerLedger.incoming),
                func.sum(PartnerLedger.outgoing)
            ).where(
                and_(
                    PartnerLedger.partner_id == p.id,
                    PartnerLedger.date >= month_start.date()
                )
            )
            
            ledger_result = await db.execute(stmt_ledger)
            incoming, outgoing = ledger_result.first()
            
            incoming = float(incoming) if incoming else 0.0
            outgoing = float(outgoing) if outgoing else 0.0
            balance = incoming - outgoing
            
            partners.append({
                "id": p.id,
                "name": p.name,
                "phone": p.phone,
                "vehicles_count": vehicles_count,
                "balance_month": round(balance, 2),
                "is_active": p.is_active,
                "last_login": p.last_login.isoformat() if p.last_login else None
            })
        
        logger.info(f"✓ Partners list: {len(partners)} partners")
        
        cards = [
            f"<div><strong>{p['name']}</strong> — {p['balance_month']} ₽</div>"
            for p in partners
        ]
        return HTMLResponse("".join(cards) or "<div>Нет партнеров</div>", status_code=200)
        
    except Exception as e:
        logger.error(f"Partners list error: {e}")
        return HTMLResponse(
            content=f"""
            <div style="grid-column: 1 / -1; text-align: center; padding: 40px; color: var(--text-muted);">
                <i class="fa-solid fa-exclamation-triangle" style="font-size: 48px; color: #ff5252;"></i>
                <p>Ошибка загрузки партнёров</p>
            </div>
            """,
            status_code=200
        )

@router.post("/create")
async def create_partner(
    name: str,
    phone: str,
    telegram_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Создание нового партнёра (только для Мастера)
    """
    if current_user.role not in ["Master", "Admin"]:
        raise HTTPException(status_code=403, detail="Только Мастер может добавлять партнёров")
    
    try:
        # Проверка на дубликат
        stmt = select(Partner).where(Partner.phone == phone)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            raise HTTPException(status_code=400, detail=f"Партнёр с телефоном {phone} уже существует")
        
        # Генерация login кода
        import random
        login_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        
        new_partner = Partner(
            name=name,
            phone=phone,
            telegram_id=telegram_id,
            login_code=login_code,
            is_active=True,
            created_at=datetime.now()
        )
        
        db.add(new_partner)
        await db.commit()
        await db.refresh(new_partner)
        
        logger.info(f"✓ Partner created: {name} | Code: {login_code}")
        
        return {
            "status": "success",
            "partner_id": new_partner.id,
            "name": new_partner.name,
            "login_code": login_code,
            "message": "Партнёр создан. Отправьте ему код для входа."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create partner error: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/payouts/calculate", response_class=HTMLResponse)
async def calculate_payouts(
    request: Request,
    period_days: int = 30,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Расчёт выплат всем партнёрам за период (v22.5)
    Возвращает HTML fragment для HTMX
    
    Логика:
    1. Берём PartnerLedger за период
    2. Для каждого партнёра: incoming - outgoing = к выплате
    3. Суммируем total_payable
    """
    try:
        cutoff_date = datetime.now() - timedelta(days=period_days)
        
        # Получаем всех активных партнёров
        stmt = select(Partner).where(Partner.is_active == True)
        result = await db.execute(stmt)
        partners = result.scalars().all()
        
        payouts = []
        total_payable = 0.0
        vehicles_count = 0
        
        for partner in partners:
            # Расчёт для партнёра
            stmt_ledger = select(
                func.sum(PartnerLedger.incoming),
                func.sum(PartnerLedger.outgoing)
            ).where(
                and_(
                    PartnerLedger.partner_id == partner.id,
                    PartnerLedger.date >= cutoff_date.date()
                )
            )
            
            ledger_result = await db.execute(stmt_ledger)
            incoming, outgoing = ledger_result.first()
            
            incoming = float(incoming) if incoming else 0.0
            outgoing = float(outgoing) if outgoing else 0.0
            payable = incoming - outgoing
            
            if payable > 0:
                total_payable += payable
                
            # Считаем машины
            stmt_vehicles = select(func.count(func.distinct(PartnerLedger.vehicle_id))).where(
                PartnerLedger.partner_id == partner.id
            )
            v_result = await db.execute(stmt_vehicles)
            vehicles_count += v_result.scalar() or 0
        
        logger.info(f"✓ Payouts calculated: {len(partners)} partners, {total_payable:,.2f}₽ total")
        
        html = (
            f"<div>Партнеров: {len(partners)}</div>"
            f"<div>К выплате: {round(total_payable, 2)} ₽</div>"
            f"<div>Машин: {vehicles_count}</div>"
        )
        return HTMLResponse(html, status_code=200)
        
    except Exception as e:
        logger.error(f"Calculate payouts error: {e}")
        return HTMLResponse(
            content="""
            <div class="summary-card"><div class="summary-value">0</div><div class="summary-label">Партнёров</div></div>
            <div class="summary-card"><div class="summary-value">0₽</div><div class="summary-label">К выплате</div></div>
            <div class="summary-card"><div class="summary-value">0</div><div class="summary-label">Машин</div></div>
            """,
            status_code=200
        )

@router.get("/partner/statement/{month}")
async def partner_statement(
    partner_id: int,
    month: str,  # YYYY-MM
    db: AsyncSession = Depends(get_db)
):
    """
    Генерация PDF-стейтмента за месяц
    """
    try:
        # TODO: генерация PDF через reportlab
        
        return {
            "status": "pending",
            "message": "PDF generation in development"
        }
        
    except Exception as e:
        logger.error(f"Statement generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
