# -*- coding: utf-8 -*-
# app/routes/kazna.py
# КАЗНА ИМПЕРИИ — Финансовый центр

import logging
from typing import List, Optional
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_, or_, case, text
from decimal import Decimal, ROUND_HALF_UP
from pydantic import BaseModel
try:
    import httpx
except Exception:
    httpx = None

from app.database import get_db
from app.models.all_models import Transaction, Vehicle, User
from app.services.auth import get_current_user
from app.core.config import settings
from app.services.analytics_engine import AnalyticsEngine

logger = logging.getLogger("Dominion.Kazna")

# v22.1: Prefix добавляется в main.py!
router = APIRouter(tags=["Казна: Финансовое Ядро"])

# Инициализация шаблонов
templates = Jinja2Templates(directory="app/templates")

# =================================================================
# YANDEX FALLBACK (Contractor Profiles)
# =================================================================

async def fetch_driver_name_from_yandex(park_name: str, contractor_profile_id: str) -> Optional[str]:
    """
    Экстренный запрос к Яндекс Fleet API:
    GET /v2/parks/contractors/driver-profile?contractor_profile_id=...
    """
    if not contractor_profile_id or not park_name:
        return None
    park = settings.PARKS.get(park_name.upper())
    if not park:
        return None

    park_id = park.get("ID")
    client_id = park.get("CLIENT_ID")
    api_key = park.get("API_KEY")
    if not park_id or not client_id or not api_key:
        return None

    url = "https://fleet-api.taxi.yandex.net/v2/parks/contractors/driver-profile"
    headers = {
        "X-Park-ID": park_id,
        "X-Client-ID": client_id,
        "X-Api-Key": api_key,
        "Accept": "application/json",
        "Accept-Language": "ru_RU",
        "Content-Type": "application/json"
    }
    params = {"contractor_profile_id": contractor_profile_id}

    if httpx is None:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code != 200:
                logger.warning(f"Yandex driver-profile lookup failed: {resp.status_code} {resp.text[:120]}")
                return None
            payload = resp.json()
    except Exception as e:
        logger.warning(f"Yandex driver-profile lookup error: {e}")
        return None

    person = payload.get("person") or {}
    full_name = person.get("full_name") or {}
    last_name = full_name.get("last_name") or ""
    first_name = full_name.get("first_name") or ""
    middle_name = full_name.get("middle_name") or ""
    parts = [p for p in [last_name, first_name, middle_name] if p]
    return " ".join(parts) if parts else None

# =================================================================
# SCHEMAS
# =================================================================

class TransactionOut(BaseModel):
    id: int
    date: datetime
    category: str
    contractor: str
    description: str
    amount: float

    class Config:
        from_attributes = True

# =================================================================
# ТРАНЗАКЦИИ
# =================================================================

@router.get("/transactions", response_class=HTMLResponse)
async def get_transactions(
    request: Request,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    category: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Список транзакций с фильтрами (v22.6 IRON ORDER)
    
    Параметры:
    - limit: количество записей (по умолчанию 10)
    - offset: смещение для пагинации
    - category: фильтр по категории
    - from_date: начало периода (YYYY-MM-DD)
    - to_date: конец периода (YYYY-MM-DD)
    
    Возвращает: HTML виджет с премиальным дизайном (ZEBRA style)
    """
    try:
        # ПРИНУДИТЕЛЬНОЕ ОБНОВЛЕНИЕ СЕССИИ
        db.expire_all()
        
        # v200.14: Изоляция тенанта — только транзакции текущего тенанта
        tenant_id = getattr(request.state, "tenant_id", "s-global")
        
        # Базовый запрос
        stmt = (
            select(Transaction, User.id, User.full_name)
            .outerjoin(User, User.yandex_driver_id == Transaction.yandex_driver_id)
            .where(Transaction.tenant_id == tenant_id)
            .order_by(desc(Transaction.date))
        )
        
        # Фильтры
        if category:
            stmt = stmt.where(Transaction.category == category)
            
        if from_date:
            try:
                from_dt = datetime.fromisoformat(from_date)
                stmt = stmt.where(Transaction.date >= from_dt.date())
            except:
                pass
                
        if to_date:
            try:
                to_dt = datetime.fromisoformat(to_date)
                stmt = stmt.where(Transaction.date <= to_dt.date())
            except:
                pass
        
        # Пагинация
        stmt = stmt.offset(offset).limit(limit)
        
        result = await db.execute(stmt)
        transactions = result.all()
        
        logger.info(f"✓ Transactions query: {len(transactions)} records")
        
        # Подготовка данных для шаблона (v30.1 FULL TIMESTAMP)
        name_cache: dict = {}
        transactions_list = []
        for tx, driver_id, driver_name in transactions:
            # Детальное время
            if hasattr(tx.date, 'isoformat'):
                date_str = tx.date.isoformat()
            elif hasattr(tx.date, 'strftime'):
                date_str = tx.date.strftime('%Y-%m-%d %H:%M:%S')
            else:
                date_str = str(tx.date)
            
            contractor = tx.contractor
            if contractor and str(contractor).strip().upper() in {"N/A", "NONE", "NULL", "NAN"}:
                contractor = None
            contractor = contractor or driver_name
            if not contractor and tx.yandex_driver_id:
                cache_key = f"{tx.park_name}:{tx.yandex_driver_id}"
                if cache_key not in name_cache:
                    name_cache[cache_key] = await fetch_driver_name_from_yandex(
                        tx.park_name or "PRO",
                        tx.yandex_driver_id
                    )
                contractor = name_cache.get(cache_key)
            contractor = contractor or "Неизвестный водитель"
            transactions_list.append({
                "id": tx.id,
                "date": date_str,
                "category": tx.category or "Без категории",
                "contractor": contractor,
                "driver_id": driver_id,
                "description": tx.description or "",
                "amount": float(tx.amount) if tx.amount else 0.0
            })

        data = {
            "transactions": transactions_list,
            "count": len(transactions_list),
            "timestamp": datetime.now().isoformat()
        }
        
        rows = []
        for tx in transactions_list:
            rows.append(
                f"<tr><td>{tx['date']}</td><td>{tx['category']}</td>"
                f"<td>{tx['contractor']}</td><td>{tx['amount']}</td></tr>"
            )
        html = "".join(rows) or "<tr><td colspan='4'>Пусто</td></tr>"
        response = HTMLResponse(content=html, status_code=200)
        if current_user and current_user.role == "Master":
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response
        
    except Exception as e:
        logger.error(f"Transactions query error: {e}", exc_info=True)
        return HTMLResponse(
            content=f'<div style="padding: 20px; color: #ff5252;">⚠️ Ошибка загрузки транзакций: {str(e)}</div>',
            status_code=200
        )

@router.get("/transactions/recent")
async def get_recent_transactions(
    request: Request,
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # v200.14: Изоляция тенанта — только транзакции текущего тенанта
    tenant_id = getattr(request.state, "tenant_id", "s-global")
    stmt = (
        select(Transaction)
        .where(
            and_(
                Transaction.amount > 0,
                Transaction.tenant_id == tenant_id
            )
        )
        .order_by(desc(Transaction.date))
        .limit(limit)
    )
    result = await db.execute(stmt)
    items = []
    for tx in result.scalars().all():
        items.append({
            "id": tx.id,
            "time": tx.date.strftime("%H:%M") if tx.date else "",
            "category": tx.category or "",
            "amount": int(tx.amount or 0)
        })
    return JSONResponse(content={"items": items})

@router.get("/summary")
async def get_summary(
    days: int = Query(7, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Финансовая сводка за период
    
    Возвращает:
    - Общая выручка
    - Общие расходы
    - Чистая прибыль
    - Топ категорий
    """
    try:
        db.expire_all()
        summary = await AnalyticsEngine.get_kazna_summary(db, days=days)
        logger.info(
            "✓ Summary: %s transactions, profit: %s₽",
            summary.get("transactions_count", 0),
            f"{summary.get('net_profit', 0):,.2f}",
        )
        return summary
    except Exception as e:
        logger.error(f"Summary error: {e}")
        return {
            "status": "error",
            "message": str(e),
            "net_profit": 0,
            "transactions_count": 0,
        }

@router.get("/balance")
async def get_balance(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Текущий баланс (выручка минус расходы всех времён)
    """
    try:
        db.expire_all()
        balance = await AnalyticsEngine.get_kazna_balance(db)
        balance["formatted"] = f"{balance.get('balance', 0):,.0f}₽"
        return balance
    except Exception as e:
        logger.error(f"Balance error: {e}")
        return {"balance": 0, "formatted": "0₽"}

@router.get("/transactions/filtered", response_class=HTMLResponse)
async def get_transactions_filtered(
    request: Request,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Фильтрованный список транзакций (v30.1 PROFESSIONAL)
    """
    try:
        db.expire_all()
        
        # Базовый запрос
        stmt = (
            select(Transaction, User.id, User.full_name)
            .outerjoin(User, User.yandex_driver_id == Transaction.yandex_driver_id)
            .order_by(desc(Transaction.date))
        )
        
        # Фильтр по периоду
        if from_date:
            try:
                from_dt = datetime.fromisoformat(from_date)
                stmt = stmt.where(Transaction.date >= from_dt.date())
            except:
                pass
                
        if to_date:
            try:
                to_dt = datetime.fromisoformat(to_date)
                stmt = stmt.where(Transaction.date <= to_dt.date())
            except:
                pass
        
        # Фильтр по категории
        if category:
            stmt = stmt.where(Transaction.category == category)
        
        # Поиск по контрагенту или описанию
        if search:
            search_pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Transaction.contractor.ilike(search_pattern),
                    Transaction.description.ilike(search_pattern)
                )
            )
        
        # Пагинация
        stmt = stmt.limit(limit)
        
        result = await db.execute(stmt)
        transactions = result.all()
        
        logger.info(f"✓ Filtered transactions: {len(transactions)} records")
        
        # Подготовка данных
        name_cache: dict = {}
        transactions_list = []
        for tx, driver_id, driver_name in transactions:
            contractor = tx.contractor or driver_name
            if not contractor and tx.yandex_driver_id:
                cache_key = f"{tx.park_name}:{tx.yandex_driver_id}"
                if cache_key not in name_cache:
                    name_cache[cache_key] = await fetch_driver_name_from_yandex(
                        tx.park_name or "PRO",
                        tx.yandex_driver_id
                    )
                contractor = name_cache.get(cache_key)
            contractor = contractor or "N/A"
            transactions_list.append({
                "id": tx.id,
                "date": tx.date.isoformat() if hasattr(tx.date, 'isoformat') else str(tx.date),
                "category": tx.category or "Без категории",
                "contractor": contractor,
                "driver_id": driver_id,
                "description": tx.description or "",
                "amount": float(tx.amount) if tx.amount else 0.0
            })
        
        data = {
            "transactions": transactions_list,
            "count": len(transactions_list),
            "timestamp": datetime.now().isoformat()
        }
        
        rows = []
        for tx in transactions_list:
            rows.append(
                f"<tr><td>{tx['date']}</td><td>{tx['category']}</td>"
                f"<td>{tx['contractor']}</td><td>{tx['amount']}</td></tr>"
            )
        html = "".join(rows) or "<tr><td colspan='4'>Пусто</td></tr>"
        response = HTMLResponse(content=html, status_code=200)
        if current_user and current_user.role == "Master":
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response
        
    except Exception as e:
        logger.error(f"Filtered transactions error: {e}", exc_info=True)
        return HTMLResponse(
            content=f'<div style="padding: 20px; color: #ff5252;">⚠️ Ошибка: {str(e)}</div>',
            status_code=200
        )

@router.get("/transactions/export")
async def export_transactions(
    request: Request,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Экспорт транзакций в CSV (v30.1)
    """
    try:
        from fastapi.responses import StreamingResponse
        import io
        import csv
        
        db.expire_all()
        
        # v200.14: Изоляция тенанта — только транзакции текущего тенанта
        tenant_id = getattr(request.state, "tenant_id", "s-global")
        
        # Базовый запрос
        stmt = select(Transaction).where(
            Transaction.tenant_id == tenant_id
        ).order_by(desc(Transaction.date))
        
        # Применяем те же фильтры
        if from_date:
            try:
                from_dt = datetime.fromisoformat(from_date)
                stmt = stmt.where(Transaction.date >= from_dt.date())
            except:
                pass
                
        if to_date:
            try:
                to_dt = datetime.fromisoformat(to_date)
                stmt = stmt.where(Transaction.date <= to_dt.date())
            except:
                pass
        
        if category:
            stmt = stmt.where(Transaction.category == category)
        
        if search:
            search_pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Transaction.contractor.ilike(search_pattern),
                    Transaction.description.ilike(search_pattern)
                )
            )
        
        result = await db.execute(stmt)
        transactions = result.scalars().all()
        
        # Создаем CSV
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        
        # Заголовок
        writer.writerow(['ID', 'Дата', 'Время', 'Категория', 'Контрагент', 'Описание', 'Сумма', 'Тип'])
        
        # Данные
        for tx in transactions:
            date_str = tx.date.strftime('%d.%m.%Y') if hasattr(tx.date, 'strftime') else str(tx.date)
            time_str = tx.date.strftime('%H:%M:%S') if hasattr(tx.date, 'strftime') else '00:00:00'
            
            writer.writerow([
                tx.id,
                date_str,
                time_str,
                tx.category or '',
                tx.contractor or '',
                tx.description or '',
                f"{tx.amount:.2f}",
                "Приход" if tx.amount > 0 else "Расход"
            ])
        
        output.seek(0)
        
        filename = f"transactions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        logger.info(f"✓ Exported {len(transactions)} transactions to CSV")
        
        return StreamingResponse(
            iter([output.getvalue().encode('utf-8-sig')]),  # BOM для Excel
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except Exception as e:
        logger.error(f"Export error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/categories")
async def get_categories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Список всех категорий транзакций
    """
    try:
        stmt = select(Transaction.category).distinct()
        result = await db.execute(stmt)
        categories = {row[0] for row in result.all() if row[0]}
        categories.update(AnalyticsEngine.CATEGORY_BUCKETS.keys())
        items = [
            {"name": name, "bucket": AnalyticsEngine.get_category_bucket(name)}
            for name in sorted(categories)
        ]
        return {"categories": items, "count": len(items)}

    except Exception as e:
        logger.error(f"Categories error: {e}")
        return {"categories": [], "count": 0}


# =================================================================
# FINANCE ENGINE v200.12: IT SERVICE FEE 50/50
# =================================================================

# Категории для сегментации
LOGISTICS_CATEGORIES = {"VkusVill", "Логистика", "ВкусВилл", "vkusvill"}
FLEET_CATEGORIES = {"SubRent", "Таксопарк", "fleet", "Аренда", "Субаренда"}


async def calculate_it_service_fee(
    db: AsyncSession,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    tenant_id: str = "s-global"
) -> dict:
    """
    Расчёт распределения прибыли по схеме 50/50.

    VERSHINA v200.14 PERFORMANCE: Агрегация выполняется на стороне PostgreSQL
    через func.sum + CASE WHEN. Python не загружает транзакции в память.

    ПРАВИЛА:
    - ЛОГИСТИКА (VkusVill): 50% чистой маржи = IT Service Fee (ИП Мкртчян)
    - ТАКСОПАРК (fleet): 100% прибыли = ООО 'С-ГЛОБАЛ'
    - ДРУГИЕ НАПРАВЛЕНИЯ: 100% прибыли = ООО 'С-ГЛОБАЛ'

    Returns:
        dict с breakdown по секторам
    """
    try:
        # ================================================================
        # SQL-АГРЕГАЦИЯ: категоризация через CASE WHEN на стороне PostgreSQL
        # Логика: LOGISTICS = VkusVill/vkus*, FLEET = SubRent/rent*/fleet*
        # ================================================================

        # Условие: транзакция относится к логистике
        is_logistics_cond = or_(
            Transaction.category.in_(list(LOGISTICS_CATEGORIES)),
            func.lower(Transaction.category).like("%vkus%"),
        )

        # Условие: транзакция относится к таксопарку
        is_fleet_cond = or_(
            Transaction.category.in_(list(FLEET_CATEGORIES)),
            func.lower(Transaction.category).like("%subrent%"),
            func.lower(Transaction.category).like("%rent%"),
        )

        # Базовые фильтры (период + tenant)
        base_filters = [Transaction.tenant_id == tenant_id]
        if from_date:
            base_filters.append(Transaction.date >= from_date)
        if to_date:
            base_filters.append(Transaction.date <= to_date)

        # Один SQL-запрос: агрегируем revenue/expenses по трём секторам + count
        stmt = select(
            # LOGISTICS
            func.coalesce(
                func.sum(case((and_(is_logistics_cond, Transaction.amount > 0), Transaction.amount), else_=0.0)),
                0.0
            ).label("logistics_revenue"),
            func.coalesce(
                func.sum(case((and_(is_logistics_cond, Transaction.amount < 0), func.abs(Transaction.amount)), else_=0.0)),
                0.0
            ).label("logistics_expenses"),
            # FLEET
            func.coalesce(
                func.sum(case((and_(is_fleet_cond, ~is_logistics_cond, Transaction.amount > 0), Transaction.amount), else_=0.0)),
                0.0
            ).label("fleet_revenue"),
            func.coalesce(
                func.sum(case((and_(is_fleet_cond, ~is_logistics_cond, Transaction.amount < 0), func.abs(Transaction.amount)), else_=0.0)),
                0.0
            ).label("fleet_expenses"),
            # OTHER (не логистика и не флот)
            func.coalesce(
                func.sum(case((and_(~is_logistics_cond, ~is_fleet_cond, Transaction.amount > 0), Transaction.amount), else_=0.0)),
                0.0
            ).label("other_revenue"),
            func.coalesce(
                func.sum(case((and_(~is_logistics_cond, ~is_fleet_cond, Transaction.amount < 0), func.abs(Transaction.amount)), else_=0.0)),
                0.0
            ).label("other_expenses"),
            # Общее число транзакций в периоде
            func.count(Transaction.id).label("tx_count"),
        ).where(and_(*base_filters))

        result = await db.execute(stmt)
        row = result.one()

        # FIX v200.16.4: Decimal для финансовых расчётов — исключает потерю точности
        _Q2 = Decimal("0.01")
        logistics_revenue = Decimal(str(row.logistics_revenue))
        logistics_expenses = Decimal(str(row.logistics_expenses))
        fleet_revenue = Decimal(str(row.fleet_revenue))
        fleet_expenses = Decimal(str(row.fleet_expenses))
        other_revenue = Decimal(str(row.other_revenue))
        other_expenses = Decimal(str(row.other_expenses))
        tx_count = int(row.tx_count)

        # Расчёт маржи (Decimal — точная арифметика)
        logistics_margin = logistics_revenue - logistics_expenses
        fleet_margin = fleet_revenue - fleet_expenses
        other_margin = other_revenue - other_expenses

        # ================================================================
        # ПРАВИЛА РАСПРЕДЕЛЕНИЯ (v200.14: защита от отрицательных выплат)
        # FIX v200.16.4: Decimal + ROUND_HALF_UP (банковское округление)
        # ================================================================
        # ЛОГИСТИКА: 50% чистой маржи -> IT Service Fee (ИП Мкртчян)
        # ВАЖНО: max(0, ...) — при убытке ИП Мкртчян НЕ получает ничего
        # и НЕ несёт убытки. Убыток остаётся на балансе ООО С-ГЛОБАЛ.
        _HALF = Decimal("0.5")
        if logistics_margin > 0:
            it_service_fee = (logistics_margin * _HALF).quantize(_Q2, rounding=ROUND_HALF_UP)
            logistics_to_ooo = (logistics_margin * _HALF).quantize(_Q2, rounding=ROUND_HALF_UP)
            logistics_loss = Decimal("0.00")
        else:
            # Убыточный период: ИП Мкртчян = 0, убыток = ООО С-ГЛОБАЛ
            it_service_fee = Decimal("0.00")
            logistics_to_ooo = Decimal("0.00")
            logistics_loss = abs(logistics_margin).quantize(_Q2, rounding=ROUND_HALF_UP)

        # ТАКСОПАРК: 100% -> ООО С-ГЛОБАЛ (IT-партнёр не участвует)
        fleet_to_ooo = max(Decimal("0.00"), fleet_margin.quantize(_Q2, rounding=ROUND_HALF_UP))
        fleet_loss = abs(fleet_margin).quantize(_Q2, rounding=ROUND_HALF_UP) if fleet_margin < 0 else Decimal("0.00")

        # ПРОЧИЕ: 100% -> ООО С-ГЛОБАЛ
        other_to_ooo = max(Decimal("0.00"), other_margin.quantize(_Q2, rounding=ROUND_HALF_UP))
        other_loss = abs(other_margin).quantize(_Q2, rounding=ROUND_HALF_UP) if other_margin < 0 else Decimal("0.00")

        total_ooo_profit = logistics_to_ooo + fleet_to_ooo + other_to_ooo
        total_loss = logistics_loss + fleet_loss + other_loss

        logger.info(
            f"[Finance 50/50] tenant={tenant_id!r} "
            f"logistics_margin={logistics_margin:.2f} it_fee={it_service_fee:.2f} "
            f"fleet_margin={fleet_margin:.2f} total_ooo={total_ooo_profit:.2f} "
            f"total_loss={total_loss:.2f} tx_count={tx_count} [SQL-aggregated]"
        )

        # FIX v200.16.4: Decimal → float для JSON-сериализации (точность сохранена в расчётах)
        _f = float  # shorthand
        total_margin = (logistics_margin + fleet_margin + other_margin).quantize(_Q2, rounding=ROUND_HALF_UP)

        return {
            "period": {
                "from": from_date.isoformat() if from_date else None,
                "to": to_date.isoformat() if to_date else None
            },
            "logistics": {
                "revenue": _f(logistics_revenue),
                "expenses": _f(logistics_expenses),
                "margin": _f(logistics_margin),
                "it_service_fee": _f(it_service_fee),   # 50% -> ИП Мкртчян (0 при убытке)
                "to_ooo": _f(logistics_to_ooo),          # 50% -> ООО С-ГЛОБАЛ (0 при убытке)
                "loss": _f(logistics_loss),              # Убыток периода (прозрачность)
                "is_profitable": logistics_margin > 0
            },
            "fleet": {
                "revenue": _f(fleet_revenue),
                "expenses": _f(fleet_expenses),
                "margin": _f(fleet_margin),
                "to_ooo": _f(fleet_to_ooo),              # 100% -> ООО С-ГЛОБАЛ
                "loss": _f(fleet_loss),
                "is_profitable": fleet_margin > 0
            },
            "other": {
                "revenue": _f(other_revenue),
                "expenses": _f(other_expenses),
                "margin": _f(other_margin),
                "to_ooo": _f(other_to_ooo),              # 100% -> ООО С-ГЛОБАЛ
                "loss": _f(other_loss),
                "is_profitable": other_margin > 0
            },
            "summary": {
                "total_it_service_fee": _f(it_service_fee),   # ИП Мкртчян
                "total_ooo_profit": _f(total_ooo_profit),     # ООО С-ГЛОБАЛ
                "total_margin": _f(total_margin),
                "total_loss": _f(total_loss),                 # Суммарный убыток (если есть)
                "transactions_count": tx_count
            },
            "recipients": {
                "IP_KHACHATRYAN": {
                    "type": "IT Service Fee (50% Logistics)",
                    "amount": _f(it_service_fee),
                    "note": "Только при прибыльной логистике. При убытке = 0."
                },
                "OOO_S_GLOBAL": {
                    "type": "General Profit",
                    "amount": _f(total_ooo_profit),
                    "note": "100% Fleet + 100% Other + 50% Logistics (при прибыли)"
                }
            },
            "tenant_id": tenant_id
        }

    except Exception as e:
        logger.error(f"[Finance 50/50] Calculation error tenant={tenant_id!r}: {e}", exc_info=True)
        return {
            "error": str(e),
            "logistics": {},
            "fleet": {},
            "other": {},
            "summary": {}
        }


@router.get("/profit-distribution")
async def get_profit_distribution(
    request: Request,
    from_date: Optional[str] = Query(None, description="Начало периода YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, description="Конец периода YYYY-MM-DD"),
    # v200.14 IDOR FIX: tenant_id УДАЛЁН из Query-параметров.
    # Извлекается ТОЛЬКО из request.state (TenantMiddleware).
    # Владелец одного парка не может получить данные другого парка.
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Эндпоинт распределения прибыли 50/50 (v200.12)

    v200.14: tenant_id извлекается из JWT/middleware — IDOR исправлен.
    
    Возвращает детализированный отчёт:
    - Logistics Profit Sharing (доля ИП Мкртчян)
    - General Empire Profit (100% ООО С-ГЛОБАЛ)
    
    ПРАВИЛА:
    - ЛОГИСТИКА ВкусВилл: 50% маржи = IT Service Fee
    - ТАКСОПАРК и остальные: 100% = ООО С-ГЛОБАЛ
    """
    try:
        # v200.14: tenant_id из middleware (Hard Isolation)
        tenant_id = getattr(request.state, "tenant_id", "s-global")

        # Парсинг дат
        from_dt = None
        to_dt = None
        
        if from_date:
            from_dt = datetime.fromisoformat(from_date)
        if to_date:
            to_dt = datetime.fromisoformat(to_date)
        
        # Расчёт
        distribution = await calculate_it_service_fee(
            db=db,
            from_date=from_dt,
            to_date=to_dt,
            tenant_id=tenant_id
        )
        
        logger.info(f"Profit distribution calculated: IT Fee = {distribution.get('summary', {}).get('total_it_service_fee', 0):,.2f}₽")
        
        return JSONResponse(content=distribution)
        
    except Exception as e:
        logger.error(f"Profit distribution error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profit-distribution/export")
async def export_profit_distribution(
    request: Request,
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    # v200.14 IDOR FIX: tenant_id УДАЛЁН из Query-параметров.
    # Извлекается ТОЛЬКО из request.state (TenantMiddleware).
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Экспорт отчёта распределения прибыли в CSV для финансового аудита.
    v200.14: tenant_id извлекается из JWT/middleware — IDOR исправлен.
    """
    try:
        from fastapi.responses import StreamingResponse
        import io
        import csv

        # v200.14: tenant_id из middleware (Hard Isolation)
        tenant_id = getattr(request.state, "tenant_id", "s-global")

        # Расчёт
        from_dt = datetime.fromisoformat(from_date) if from_date else None
        to_dt = datetime.fromisoformat(to_date) if to_date else None
        
        distribution = await calculate_it_service_fee(
            db=db,
            from_date=from_dt,
            to_date=to_dt,
            tenant_id=tenant_id
        )
        
        # Создаём CSV
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        
        # Заголовок отчёта
        writer.writerow(['ОТЧЁТ РАСПРЕДЕЛЕНИЯ ПРИБЫЛИ v200.12'])
        writer.writerow(['Период', f"{from_date or 'начало'} - {to_date or 'конец'}"])
        writer.writerow(['Tenant ID', tenant_id])
        writer.writerow([])
        
        # ЛОГИСТИКА
        writer.writerow(['ЛОГИСТИКА (ВкусВилл)'])
        writer.writerow(['Выручка', distribution['logistics'].get('revenue', 0)])
        writer.writerow(['Расходы', distribution['logistics'].get('expenses', 0)])
        writer.writerow(['Маржа', distribution['logistics'].get('margin', 0)])
        writer.writerow(['IT Service Fee (ИП Мкртчян 50%)', distribution['logistics'].get('it_service_fee', 0)])
        writer.writerow(['ООО С-ГЛОБАЛ (50%)', distribution['logistics'].get('to_ooo', 0)])
        writer.writerow([])
        
        # ТАКСОПАРК
        writer.writerow(['ТАКСОПАРК (T-CLUB24)'])
        writer.writerow(['Выручка', distribution['fleet'].get('revenue', 0)])
        writer.writerow(['Расходы', distribution['fleet'].get('expenses', 0)])
        writer.writerow(['Маржа', distribution['fleet'].get('margin', 0)])
        writer.writerow(['ООО С-ГЛОБАЛ (100%)', distribution['fleet'].get('to_ooo', 0)])
        writer.writerow([])
        
        # ПРОЧИЕ
        writer.writerow(['ПРОЧИЕ НАПРАВЛЕНИЯ'])
        writer.writerow(['Выручка', distribution['other'].get('revenue', 0)])
        writer.writerow(['Расходы', distribution['other'].get('expenses', 0)])
        writer.writerow(['Маржа', distribution['other'].get('margin', 0)])
        writer.writerow(['ООО С-ГЛОБАЛ (100%)', distribution['other'].get('to_ooo', 0)])
        writer.writerow([])
        
        # ИТОГО
        writer.writerow(['ИТОГО'])
        writer.writerow(['ИП Мкртчян (IT Service Fee)', distribution['summary'].get('total_it_service_fee', 0)])
        writer.writerow(['ООО С-ГЛОБАЛ', distribution['summary'].get('total_ooo_profit', 0)])
        writer.writerow(['Общая маржа', distribution['summary'].get('total_margin', 0)])
        
        output.seek(0)
        
        filename = f"profit_distribution_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        return StreamingResponse(
            iter([output.getvalue().encode('utf-8-sig')]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        logger.error(f"Export profit distribution error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
