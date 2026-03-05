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
from sqlalchemy import select, func, desc, and_, or_
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
        
        # Базовый запрос
        stmt = (
            select(Transaction, User.id, User.full_name)
            .outerjoin(User, User.yandex_driver_id == Transaction.yandex_driver_id)
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
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stmt = (
        select(Transaction)
        .where(Transaction.amount > 0)
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
        
        # Базовый запрос
        stmt = select(Transaction).order_by(desc(Transaction.date))
        
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
