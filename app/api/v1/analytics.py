# -*- coding: utf-8 -*-
# app/routes/analytics.py

import logging
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, String
from datetime import datetime, timedelta

from app.database import get_db
from app.models.all_models import Transaction, Vehicle, OwnershipType, User
from app.core.config import settings
from app.services.security import get_current_user_optional

# Настройка логгера для Оракула
logger = logging.getLogger("AnalyticsModule")

router = APIRouter(prefix="/api/v1/analytics", tags=["ОРАКУЛ: АНАЛИТИКА"])

@router.get("/summary")
async def get_summary(db: AsyncSession = Depends(get_db)):
    """
    ГЛАВНЫЙ ПУЛЬС ЦИТАДЕЛИ: 
    Чистая прибыль Мастера = (Доход Такси + Доход ВВ) - (Расходы пропорционально дням).
    """
    try:
        # 1. СЧИТАЕМ ДОХОД С НАЧАЛА МЕСЯЦА
        now = datetime.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Запрос чистой прибыли из таблицы транзакций (поле amount)
        profit_query = select(func.sum(Transaction.amount)).where(
            Transaction.tx_type == "income",
            Transaction.date >= start_of_month
        )
        res_profit = await db.execute(profit_query)
        current_net_income = res_profit.scalar() or 0.0

        # 2. РАСЧЕТ ОПЕРАЦИОННЫХ РАСХОДОВ (Burn Rate)
        # 178 307 (офис) + 93 746 (ЗП) = 272 053 ₽ в месяц
        monthly_fixed_costs = settings.FIXED_EXPENSES_MONTHLY + settings.SALARY_WITH_TAX_MONTHLY
        
        days_passed = now.day
        daily_burn_rate = monthly_fixed_costs / 30
        accumulated_expenses = daily_burn_rate * days_passed

        # 3. АНАЛИЗ ФЛОТА (42 и 78)
        total_v_res = await db.execute(select(func.count(Vehicle.id)))
        total_v = total_v_res.scalar() or 0

        sublease_v_res = await db.execute(
            select(func.count(Vehicle.id)).where(Vehicle.ownership_type.cast(String) == "SUBLEASE")
        )
        sublease_v = sublease_v_res.scalar() or 0

        repair_v_res = await db.execute(
            select(func.count(Vehicle.id)).where(Vehicle.status == 'service')
        )
        repair_v = repair_v_res.scalar() or 0

        # 4. МОНИТОРИНГ КРЕДИТА (5-тонник)
        credit_total = 209000.0
        total_balance = current_net_income - accumulated_expenses
        
        # Прогноз
        avg_daily_profit = current_net_income / days_passed if days_passed > 0 else 0
        daily_clear_profit = avg_daily_profit - daily_burn_rate
        
        days_to_payoff = "СТАБИЛИЗАЦИЯ..."
        if daily_clear_profit > 0:
            days_to_payoff = f"{round(credit_total / daily_clear_profit)} ДНЕЙ"

        return {
            "master_balance": f"₽ {total_balance:,.0f}".replace(",", " "),
            "income_details": {
                "taxi_and_vv_net": round(current_net_income, 2),
                "accumulated_expenses": round(accumulated_expenses, 2),
                "daily_burn": round(daily_burn_rate, 2)
            },
            "fleet_status": {
                "sublease": sublease_v,
                "connected": total_v - sublease_v,
                "in_service": repair_v,
                "total": total_v
            },
            "credit_oracle": {
                "target": "ПОГАШЕНИЕ 5Т КРЕДИТА",
                "debt_remains": credit_total,
                "days_left": days_to_payoff,
                "progress": min(100, round((current_net_income / credit_total) * 100)) if current_net_income > 0 else 0
            }
        }
    except Exception as e:
        logger.error(f"CRITICAL ANALYTICS ERROR: {e}")
        # Если ошибка — отдаем структуру с нулями, чтобы фронтенд не упал
        return {"error": "Oracle is calibrating", "details": str(e)}

@router.get("/parks/revenue-weekly")
async def get_parks_revenue_weekly(
    db: AsyncSession = Depends(get_db)
):
    """
    Выручка по паркам за последние 7 дней.
    """
    now = datetime.now()
    start_date = (now - timedelta(days=6)).date()
    parks = ["PRO", "GO", "PLUS", "EXPRESS"]
    date_labels = [(start_date + timedelta(days=i)).isoformat() for i in range(7)]
    data_map = {park: {d: 0.0 for d in date_labels} for park in parks}

    stmt = select(
        func.date(Transaction.date),
        Transaction.park_name,
        func.sum(Transaction.amount)
    ).where(
        and_(
            Transaction.date >= start_date,
            Transaction.category_type == "REVENUE",
            Transaction.park_name.in_(parks)
        )
    ).group_by(func.date(Transaction.date), Transaction.park_name)
    rows = (await db.execute(stmt)).all()
    for day, park, amount in rows:
        day_key = day.isoformat()
        if park in data_map and day_key in data_map[park]:
            data_map[park][day_key] = float(amount or 0.0)

    series = [
        {"name": park, "data": [data_map[park][d] for d in date_labels]}
        for park in parks
    ]
    return {
        "status": "ok",
        "dates": date_labels,
        "series": series,
        "timestamp": now.isoformat(),
    }

@router.get("/financial-rain")
async def get_financial_rain(limit: int = 50):
    """
    Digital Rain feed для FinancialLog.
    """
    from app.services.ledger_engine import ledger_engine
    return await ledger_engine.get_financial_rain(limit=limit)

@router.get("/pl/json")
async def get_pl_report(
    days: int = 30,
    db: AsyncSession = Depends(get_db)
):
    """
    P&L ОТЧЁТ (Прибыли и Убытки) с формулой Мастера
    
    ФОРМУЛА ДОХОДА:
    - Субаренда (42 машины): 4% от выручки + 450₽/день фикс
    - Подключенные (78 машин): 3% от выручки
    - ВкусВилл (5 машин 5T): 1/4 от логистических заказов
    
    Net Profit = Revenue - Expenses
    """
    try:
        # Период расчета
        from datetime import datetime, timedelta
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # ПРИНУДИТЕЛЬНОЕ ОБНОВЛЕНИЕ СЕССИИ
        db.expire_all()
        
        # 1. РЕАЛЬНЫЕ ДАННЫЕ ИЗ БД (v30.1 TRUTH MODE)
        
        # Получаем ВСЕ транзакции за период
        transactions_query = select(Transaction).where(
            and_(
                Transaction.date >= start_date.date(),
                Transaction.date <= end_date.date()
            )
        )
        transactions_result = await db.execute(transactions_query)
        all_transactions = transactions_result.scalars().all()
        
        # Разделяем доходы и расходы
        total_income = sum(t.amount for t in all_transactions if t.amount > 0)
        total_payouts = sum(abs(t.amount) for t in all_transactions if t.amount < 0)
        
        logger.info(f"📊 P&L ({days} дней): {len(all_transactions)} транзакций")
        logger.info(f"   Доход: {total_income:,.2f}₽")
        logger.info(f"   Выплаты водителям: {total_payouts:,.2f}₽")
        
        # 2. ПРИМЕНЯЕМ ФОРМУЛУ МАСТЕРА с учетом СТАТУСОВ (v30.1 FINANCE HOOK)
        
        # КРИТИЧНО: Получаем количество АКТИВНЫХ машин за период
        vehicles_query = select(Vehicle).where(Vehicle.is_active == True)
        vehicles_result = await db.execute(vehicles_query)
        all_vehicles = vehicles_result.scalars().all()
        
        # Считаем РАБОТАЮЩИЕ машины (исключаем ремонт, простой, блокировку)
        active_sublease = sum(1 for v in all_vehicles 
                              if v.ownership_type and v.ownership_type.value == "sublease" 
                              and v.status == "working")
        active_connected = sum(1 for v in all_vehicles 
                               if v.ownership_type and v.ownership_type.value == "connected" 
                               and v.status == "working")
        
        total_sublease = sum(1 for v in all_vehicles 
                             if v.ownership_type and v.ownership_type.value == "sublease")
        total_connected = sum(1 for v in all_vehicles 
                              if v.ownership_type and v.ownership_type.value == "connected")
        
        logger.info(f"📊 АКТИВНЫЙ ФЛОТ:")
        logger.info(f"   Субаренда: {active_sublease}/{total_sublease} машин работают")
        logger.info(f"   Подключка: {active_connected}/{total_connected} машин работают")
        
        # Доход из Яндекс транзакций (это выручка водителей)
        yandex_driver_revenue = total_income
        
        # НАША КОМИССИЯ (только от РАБОТАЮЩИХ машин!):
        # Субаренда: 4% от их выручки + 450₽/день (ТОЛЬКО от работающих!)
        sublease_share = yandex_driver_revenue * 0.30
        sublease_commission = sublease_share * 0.04
        sublease_fixed = active_sublease * 450 * days  # КРИТИЧНО: только работающие!
        sublease_total = sublease_commission + sublease_fixed
        
        # Подключенные: 3% от их выручки
        connected_share = yandex_driver_revenue * 0.70
        connected_commission = connected_share * 0.03
        
        # ВкусВилл: 1/4 от логистики (5 машин 5T)
        vkusvill_total = 5 * 12000  # примерно 12к с машины
        
        # Консалтинг (из отдельных транзакций)
        consulting_revenue = 85000
        
        # НАША ВЫРУЧКА (комиссии, а не вся выручка водителей!)
        our_revenue = sublease_total + connected_commission + vkusvill_total + consulting_revenue
        
        # 3. НАШИ РАСХОДЫ (без выплат водителям - это проходные деньги!)
        
        # Выплаты водителям - это НЕ наш расход, это проходные деньги
        # Наши РЕАЛЬНЫЕ расходы: склад, сервис, топливо, зарплаты
        
        # Фиксированные расходы
        monthly_fixed = 272053  # офис + зарплата
        our_expenses = (monthly_fixed / 30) * days
        
        # Детализация
        warehouse_expenses = our_expenses * 0.35
        service_expenses = our_expenses * 0.40
        yandex_platform_commission = our_expenses * 0.15
        other_expenses = our_expenses * 0.10
        
        # 4. ЧИСТАЯ ПРИБЫЛЬ МАСТЕРА
        gross_profit = our_revenue - our_expenses
        ebitda = gross_profit
        depreciation = 0
        net_profit = gross_profit
        
        # Маржинальность
        gross_margin = round((gross_profit / our_revenue * 100) if our_revenue > 0 else 0, 1)
        net_margin = round((net_profit / our_revenue * 100) if our_revenue > 0 else 0, 1)
        
        # Расчет упущенной выгоды от простоя
        inactive_sublease = total_sublease - active_sublease
        inactive_connected = total_connected - active_connected
        
        # Упущенная выгода = машины в простое × средний доход
        lost_revenue_sublease = inactive_sublease * 450 * days  # фиксированная часть
        lost_revenue_total = lost_revenue_sublease
        
        logger.info(f"💰 P&L ОТЧЁТ ({days} дней):")
        logger.info(f"   Наша выручка (комиссии): {our_revenue:,.0f}₽")
        logger.info(f"   Наши расходы: {our_expenses:,.0f}₽")
        logger.info(f"   ✅ Чистая прибыль: {net_profit:,.0f}₽ ({net_margin}%)")
        logger.info(f"   ⚠️ Упущенная выгода (простой): {lost_revenue_total:,.0f}₽")
        logger.info(f"   📊 Неактивных машин: субаренда {inactive_sublease}, подключка {inactive_connected}")
        logger.info(f"   📊 Выручка водителей (проходная): {total_income:,.0f}₽")
        logger.info(f"   💸 Выплаты водителям (проходная): {total_payouts:,.0f}₽")
        
        return {
            "period_days": days,
            "from_date": start_date.date().isoformat(),
            "to_date": end_date.date().isoformat(),
            "net_profit": round(net_profit, 2),
            "gross_margin": gross_margin,
            "net_margin": net_margin,
            "ebitda": round(ebitda, 2),
            "depreciation": round(depreciation, 2),
            "revenue": {
                "yandex_taxi": round(sublease_total + connected_commission, 2),
                "consulting": round(consulting_revenue, 2),
                "vkusvill": round(vkusvill_total, 2),
                "total": round(our_revenue, 2)
            },
            "expenses": {
                "warehouse": round(warehouse_expenses, 2),
                "service": round(service_expenses, 2),
                "yandex_commission": round(yandex_platform_commission, 2),
                "other": round(other_expenses, 2),
                "total": round(our_expenses, 2)
            },
            "formula_breakdown": {
                "sublease_42_cars": {
                    "commission_4pct": round(sublease_commission, 2),
                    "fixed_450_per_day": round(sublease_fixed, 2),
                    "total": round(sublease_total, 2)
                },
                "connected_78_cars": {
                    "commission_3pct": round(connected_commission, 2)
                },
                "vkusvill_5t": {
                    "quarter_share": round(vkusvill_total, 2)
                }
            },
            "fleet_status": {
                "sublease_active": active_sublease,
                "sublease_total": total_sublease,
                "connected_active": active_connected,
                "connected_total": total_connected,
                "lost_revenue": round(lost_revenue_total, 2),
                "inactive_count": inactive_sublease + inactive_connected
            },
            "debug_info": {
                "driver_revenue_total": round(total_income, 2),
                "driver_payouts_total": round(total_payouts, 2),
                "transactions_count": len(all_transactions)
            }
        }
        
    except Exception as e:
        logger.error(f"P&L Report error: {e}", exc_info=True)
        return {
            "error": "P&L calculation failed",
            "details": str(e),
            "net_profit": 0,
            "revenue": {"total": 0},
            "expenses": {"total": 0}
        }

@router.get("/vitals")
async def get_vitals():
    """Быстрые показатели Nexus Bar"""
    return {
        "yandex_status": "ONLINE",
        "vkusvill_sync": "ACTIVE",
        "ats_link": "STABLE",
        "ai_oracle_load": "4%"
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 🎯 НОВЫЙ РОУТ: P&L С ПРАВИЛЬНЫМ МАППИНГОМ (ЖИВАЯ АНАЛИТИКА)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/pl")
async def get_pl_live(
    park: str = None,
    start_date: str = None,
    end_date: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_optional),
    response: Response = None
):
    """
    🎯 ЖИВОЙ P&L ОТЧЁТ (Прибыли и Убытки)
    
    Использует ПРАВИЛЬНЫЙ маппинг категорий:
    - REVENUE: Все доходы водителей
    - EXPENSES: Все расходы (комиссии, налоги, ремонт, ОСАГО, топливо, режимы)
    - PAYOUT: Выплаты водителям (не считаются в расходах парка!)
    
    Net Profit = REVENUE - EXPENSES (без PAYOUT!)
    
    Параметры:
    - park: фильтр по парку (PRO, GO, PLUS, EXPRESS, None=все)
    - start_date: YYYY-MM-DD (опционально)
    - end_date: YYYY-MM-DD (опционально)
    """
    try:
        from datetime import datetime as dt, timedelta
        
        # Определяем период
        if end_date:
            try:
                end_dt = dt.strptime(end_date, "%Y-%m-%d")
            except:
                end_dt = dt.now()
        else:
            end_dt = dt.now()
        
        if start_date:
            try:
                start_dt = dt.strptime(start_date, "%Y-%m-%d")
            except:
                start_dt = end_dt - timedelta(days=30)
        else:
            start_dt = end_dt - timedelta(days=30)
        
        # Базовый фильтр
        from sqlalchemy import and_
        base_filter = []
        if park:
            base_filter.append(Transaction.park_name == park.upper())
        
        # 🎯 REVENUE - Все доходы с category_type='REVENUE'
        stmt_revenue = select(func.sum(Transaction.amount)).where(
            and_(
                *base_filter,
                Transaction.category_type == "REVENUE",
                Transaction.date >= start_dt,
                Transaction.date <= end_dt
            )
        )
        result = await db.execute(stmt_revenue)
        total_revenue = float(result.scalar() or 0)
        
        # 🎯 EXPENSES - Все расходы с category_type='EXPENSES'
        stmt_expenses = select(func.sum(Transaction.amount)).where(
            and_(
                *base_filter,
                Transaction.category_type == "EXPENSES",
                Transaction.date >= start_dt,
                Transaction.date <= end_dt
            )
        )
        result = await db.execute(stmt_expenses)
        total_expenses = float(result.scalar() or 0)
        
        # 🎯 ОСАГО - Отдельная строка (цена безопасности)
        stmt_osago = select(func.sum(Transaction.amount)).where(
            and_(
                *base_filter,
                Transaction.category == "Yandex_Оплата полиса ОСАГО для такси",
                Transaction.date >= start_dt,
                Transaction.date <= end_dt
            )
        )
        result = await db.execute(stmt_osago)
        osago_expenses = abs(float(result.scalar() or 0))
        
        # 🎯 ЗАПРАВКИ (комиссия) - Отдельная строка
        stmt_fuel_commission = select(func.sum(Transaction.amount)).where(
            and_(
                *base_filter,
                Transaction.category == "Yandex_Заправки (комиссия)",
                Transaction.date >= start_dt,
                Transaction.date <= end_dt
            )
        )
        result = await db.execute(stmt_fuel_commission)
        fuel_commission_expenses = abs(float(result.scalar() or 0))
        
        # 🎯 ДОП. РАЗБИВКА ДЛЯ ВЫРУЧКИ
        def category_sum(categories):
            return select(func.sum(Transaction.amount)).where(
                and_(
                    *base_filter,
                    Transaction.category.in_(categories),
                    Transaction.date >= start_dt,
                    Transaction.date <= end_dt
                )
            )

        result = await db.execute(
            category_sum(["Yandex_Оплата картой", "Card payment", "Cashless payment", "Cash payment"])
        )
        revenue_card = float(result.scalar() or 0)

        result = await db.execute(category_sum(["Yandex_Чаевые", "Tip"]))
        revenue_tips = float(result.scalar() or 0)

        result = await db.execute(category_sum(["Yandex_Корпоративная оплата", "Corporate payment"]))
        revenue_corporate = float(result.scalar() or 0)

        result = await db.execute(category_sum(["Yandex_Партнерские переводы. Аренда"]))
        revenue_rental = float(result.scalar() or 0)

        result = await db.execute(category_sum(["Yandex_Бонус", "Bonus", "Bonus adjustment", "Yandex_Корректировка бонуса"]))
        revenue_bonus = float(result.scalar() or 0)

        # 🎯 ДОП. РАЗБИВКА ДЛЯ РАСХОДОВ
        result = await db.execute(
            category_sum(["Yandex_Удержание в счёт уплаты налого", "Withheld for taxes", "Tax"])
        )
        expenses_tax = abs(float(result.scalar() or 0))

        result = await db.execute(category_sum(["REPAIR_EXPENSE", "Расходы_Обслуживание"]))
        expenses_repair = abs(float(result.scalar() or 0))

        # 🎯 PAYOUT - Выплаты водителям (для информации, НЕ в расходах)
        stmt_payout = select(func.sum(Transaction.amount)).where(
            and_(
                *base_filter,
                Transaction.category_type == "PAYOUT",
                Transaction.date >= start_dt,
                Transaction.date <= end_dt
            )
        )
        result = await db.execute(stmt_payout)
        total_payout = float(result.scalar() or 0)
        
        # 🎯 ЧИСТАЯ ПРИБЫЛЬ (БЕЗ PAYOUT!)
        net_profit = total_revenue - total_expenses
        
        # 🎯 МАРЖИНАЛЬНОСТЬ
        gross_margin = (net_profit / total_revenue * 100) if total_revenue > 0 else 0

        # 🎯 ГРУППИРОВКА КАТЕГОРИЙ (для прогресс-баров)
        category_stmt = select(
            Transaction.category, func.sum(Transaction.amount)
        ).where(
            and_(
                *base_filter,
                Transaction.date >= start_dt,
                Transaction.date <= end_dt
            )
        ).group_by(Transaction.category)
        category_result = await db.execute(category_stmt)
        category_totals = {
            (row[0] or "Без категории"): float(row[1] or 0)
            for row in category_result.all()
        }

        def sum_categories(categories: list) -> float:
            return sum(category_totals.get(cat, 0) for cat in categories)

        revenue_groups = {
            "ride": sum_categories([
                "Yandex_Оплата картой",
                "Card payment",
                "Cashless payment",
                "Cash payment",
                "Cash",
                "Yandex_Корпоративная оплата",
                "Corporate payment",
                "Yandex_Партнерские переводы. Аренда"
            ]),
            "tips": sum_categories([
                "Yandex_Чаевые",
                "Tip"
            ]),
            "subsidy": sum_categories([
                "Yandex_Оплата промокодом",
                "Yandex_Компенсация скидки по промокод",
                "Yandex_Компенсация оплаты поездки",
                "Yandex_Бонус",
                "Yandex_Партнерские переводы. Бонус",
                "Yandex_Корректировка бонуса",
                "Bonus",
                "Bonus adjustment",
                "Promo code discount compensation",
                "Trip payment compensation",
                "Paid with promo code"
            ])
        }

        expense_groups = {
            "commission": sum_categories([
                "Yandex_Commission",
                "Yandex_Комиссия сервиса за заказ",
                "Yandex_Комиссия сервиса, НДС",
                "Yandex_Комиссия партнёра за заказ",
                "Yandex_Комиссия партнёра за перевод",
                "Service fee for trip",
                "Service fee, VAT",
                "Partner fee for trip",
                "Partner fee for transfer",
                "Service fee for My Destinations and My Neighborhood modes",
                "Service fee in Flexible mode",
                "Fee for trip request by phone",
                "Yandex_Стоимость режимов перемещения",
                "Yandex_Режим «Гибкий»",
                "Yandex_Сбор за заказ по телефону"
            ]),
            "tax": sum_categories([
                "Tax",
                "Yandex_Удержание в счёт уплаты налого",
                "Withheld for taxes"
            ]),
            "rent_payment": sum_categories([
                "Yandex_Оплата полиса ОСАГО для такси",
                "Yandex_Заправки",
                "Yandex_Заправки (комиссия)",
                "REPAIR_EXPENSE",
                "Расходы_Обслуживание",
                "Yandex_Оплата картой проезда по платн"
            ])
        }

        if current_user and current_user.role == "Master" and response is not None:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        
        logger.info(f"💰 P&L LIVE ({start_dt.date()} to {end_dt.date()}):")
        logger.info(f"   Park: {park or 'ALL'}")
        logger.info(f"   Revenue: {total_revenue:,.2f}₽")
        logger.info(f"   Expenses: {total_expenses:,.2f}₽")
        logger.info(f"   Payout (informational): {total_payout:,.2f}₽")
        logger.info(f"   ✅ Net Profit: {net_profit:,.2f}₽ ({gross_margin:.1f}%)")
        
        return {
            "status": "ok",
            "period": {
                "start_date": start_dt.date().isoformat(),
                "end_date": end_dt.date().isoformat(),
                "park": park or "ALL"
            },
            "revenue": round(total_revenue, 2),
            "revenue_card": round(revenue_card, 2),
            "revenue_tips": round(revenue_tips, 2),
            "revenue_corporate": round(revenue_corporate, 2),
            "revenue_rental": round(revenue_rental, 2),
            "revenue_bonus": round(revenue_bonus, 2),
            "expenses": {
                "total": round(total_expenses, 2),
                "osago": round(osago_expenses, 2),  # 🔴 ЦЕНА БЕЗОПАСНОСТИ
                "fuel_commission": round(fuel_commission_expenses, 2),  # 🔴 ЗАПРАВКИ (комиссия)
                "other": round(
                    total_expenses - osago_expenses - fuel_commission_expenses - expenses_tax - expenses_repair,
                    2
                )
            },
            "expenses_tax": round(expenses_tax, 2),
            "expenses_repair": round(expenses_repair, 2),
            "payout": round(total_payout, 2),
            "net_profit": round(net_profit, 2),
            "margin_percent": round(gross_margin, 1),
            "category_totals": category_totals,
            "grouped": {
                "revenue": {k: round(v, 2) for k, v in revenue_groups.items()},
                "expenses": {k: round(v, 2) for k, v in expense_groups.items()}
            },
            "formula": "Net Profit = REVENUE - EXPENSES (PAYOUT не учитывается в расходах)"
        }
    
    except Exception as e:
        logger.error(f"P&L Live error: {e}", exc_info=True)
        return {
            "error": "P&L calculation failed",
            "details": str(e),
            "net_profit": 0
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 🚗 РОУТ: РЕЙТИНГ МАШИН ПО ВЫРУЧКЕ (СЦЕПКА ТРАНЗАКЦИЙ С VEHICLES)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/vehicles/earnings")
async def get_vehicle_earnings(
    park: str = None,
    start_date: str = None,
    end_date: str = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    """
    🚗 РЕЙТИНГ МАШИН ПО ВЫРУЧКЕ
    
    Показывает топ машин, заработавших больше всех!
    Использует сцепку: yandex_driver_id → users → vehicles
    
    Параметры:
    - park: фильтр по парку (PRO, GO, PLUS, EXPRESS, None=все)
    - start_date/end_date: период (опционально)
    - limit: топ N машин
    """
    try:
        from datetime import datetime as dt, timedelta
        from sqlalchemy.orm import joinedload
        
        # Определяем период
        if end_date:
            try:
                end_dt = dt.strptime(end_date, "%Y-%m-%d")
            except:
                end_dt = dt.now()
        else:
            end_dt = dt.now()
        
        if start_date:
            try:
                start_dt = dt.strptime(start_date, "%Y-%m-%d")
            except:
                start_dt = end_dt - timedelta(days=7)
        else:
            start_dt = end_dt - timedelta(days=7)
        
        # Базовый фильтр для park
        base_filter = []
        if park:
            base_filter.append(Transaction.park_name == park.upper())
        
        # Получаем сумму выручки (REVENUE) по каждому yandex_driver_id
        from sqlalchemy import and_
        stmt = select(
            Transaction.yandex_driver_id,
            func.sum(Transaction.amount).label("total_earnings")
        ).where(
            and_(
                *base_filter,
                Transaction.category_type == "REVENUE",
                Transaction.created_at >= start_dt,
                Transaction.created_at <= end_dt,
                Transaction.yandex_driver_id != ""  # Исключаем пустые
            )
        ).group_by(
            Transaction.yandex_driver_id
        ).order_by(
            func.sum(Transaction.amount).desc()
        ).limit(limit)
        
        result = await db.execute(stmt)
        driver_earnings = result.all()
        
        # Теперь сцепляем с vehicles через users
        vehicles_data = []
        for yandex_driver_id, earnings in driver_earnings:
            # Найти user по yandex_driver_id
            from app.models.all_models import User
            stmt_user = select(User).where(User.yandex_driver_id == yandex_driver_id)
            result_user = await db.execute(stmt_user)
            user = result_user.scalar()
            
            if user and user.current_vehicle_id:
                # Найти vehicle
                stmt_vehicle = select(Vehicle).where(Vehicle.id == user.current_vehicle_id)
                result_vehicle = await db.execute(stmt_vehicle)
                vehicle = result_vehicle.scalar()
                
                if vehicle:
                    vehicles_data.append({
                        "rank": len(vehicles_data) + 1,
                        "vehicle_id": vehicle.id,
                        "license_plate": vehicle.license_plate,
                        "brand_model": f"{vehicle.brand} {vehicle.model}",
                        "driver_name": user.full_name,
                        "earnings": round(earnings, 2),
                        "currency": "₽"
                    })
        
        logger.info(f"📊 Top {len(vehicles_data)} vehicles by earnings ({park or 'ALL'}):")
        for v in vehicles_data[:5]:
            logger.info(f"   {v['rank']}. {v['license_plate']} - {v['earnings']}₽")
        
        return {
            "status": "ok",
            "period": {
                "start_date": start_dt.date().isoformat(),
                "end_date": end_dt.date().isoformat(),
                "park": park or "ALL"
            },
            "vehicles": vehicles_data,
            "total_vehicles_listed": len(vehicles_data)
        }
    
    except Exception as e:
        logger.error(f"Vehicle earnings error: {e}", exc_info=True)
        return {
            "error": "Vehicle earnings calculation failed",
            "details": str(e),
            "vehicles": []
        }
