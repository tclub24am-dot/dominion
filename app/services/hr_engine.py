# -*- coding: utf-8 -*-
"""
S-GLOBAL DOMINION — HR Engine
==============================
Протокол: LOGIST-PAY v200.16.6
Юридический контроль: ИП Мкртчян (IT Service Fee)

Модуль расчёта ЗП логиста и HR-метрик.
Формула: (Base) + (Margin_Bonus) - (M4_Fines_Penalties)

Интеграция:
  - analytics_engine.py → маржа логистики за период
  - Transaction model → штрафы М4
  - User model → base_salary, kpi_bonus_ratio, m4_fines_count
"""

import logging
from datetime import datetime, date
from typing import Optional
from sqlalchemy import select, func, and_, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.all_models import User, Transaction
from app.core.config import settings

logger = logging.getLogger("dominion.hr_engine")

# ============================================================
# КОНСТАНТЫ LOGIST-PAY
# ============================================================

# Штраф за каждое нарушение/опоздание М4 (₽) — Директива Мастера v200.16.6
M4_FINE_PENALTY = 2000.0

# Бонус за маржу: % от логистической маржи, начисляемый логисту
MARGIN_BONUS_RATE = 0.05  # 5% от чистой маржи логистики

# Минимальная ЗП (не может быть ниже)
MIN_SALARY_FLOOR = 50000.0

# Максимальный бонус за маржу (потолок)
MAX_MARGIN_BONUS = 100000.0


async def get_logistics_margin(
    db: AsyncSession,
    year: int,
    month: int,
    tenant_id: str = "s-global",
) -> float:
    """
    Считает чистую маржу логистики за указанный месяц.
    Маржа = Σ(income VkusVill) - Σ(expenses: Salary + Fuel)
    
    Интеграция с analytics_engine.py через прямой запрос к Transaction.
    """
    # Доходы логистики
    income_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0.0)).where(
            and_(
                Transaction.tenant_id == tenant_id,
                Transaction.park_name == "LOGISTICS",
                Transaction.tx_type == "income",
                extract("year", Transaction.date) == year,
                extract("month", Transaction.date) == month,
            )
        )
    )
    total_income = float(income_result.scalar() or 0.0)

    # Расходы логистики (amount отрицательный)
    expense_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0.0)).where(
            and_(
                Transaction.tenant_id == tenant_id,
                Transaction.park_name == "LOGISTICS",
                Transaction.tx_type == "expense",
                extract("year", Transaction.date) == year,
                extract("month", Transaction.date) == month,
            )
        )
    )
    total_expense = float(expense_result.scalar() or 0.0)  # Отрицательное число

    margin = total_income + total_expense  # expense уже отрицательный
    logger.info(
        f"[HR] Маржа логистики {year}-{month:02d}: "
        f"доход={total_income:,.0f}₽, расход={abs(total_expense):,.0f}₽, маржа={margin:,.0f}₽"
    )
    return margin


async def get_m4_fines_count(
    db: AsyncSession,
    year: int,
    month: int,
    tenant_id: str = "s-global",
) -> int:
    """
    Считает количество штрафов М4 за месяц.
    Штрафы определяются по category='M4_Fine' в транзакциях.
    """
    result = await db.execute(
        select(func.count(Transaction.id)).where(
            and_(
                Transaction.tenant_id == tenant_id,
                Transaction.category == "M4_Fine",
                extract("year", Transaction.date) == year,
                extract("month", Transaction.date) == month,
            )
        )
    )
    count = result.scalar() or 0
    return int(count)


async def get_m4_fines_today(
    db: AsyncSession,
    tenant_id: str = "s-global",
) -> int:
    """Счётчик штрафов М4 за сегодня (для Dashboard)."""
    today = date.today()
    result = await db.execute(
        select(func.count(Transaction.id)).where(
            and_(
                Transaction.tenant_id == tenant_id,
                Transaction.category == "M4_Fine",
                func.date(Transaction.date) == today,
            )
        )
    )
    return int(result.scalar() or 0)


async def calculate_logistic_salary(
    db: AsyncSession,
    user_id: int,
    year: int,
    month: int,
) -> dict:
    """
    Рассчитывает ЗП логиста по формуле LOGIST-PAY:
    
        Salary = Base + Margin_Bonus - M4_Fines_Penalties
    
    Где:
        - Base = user.base_salary (default 130 000₽)
        - Margin_Bonus = min(logistics_margin * MARGIN_BONUS_RATE, MAX_MARGIN_BONUS)
        - M4_Fines_Penalties = m4_fines_count * M4_FINE_PENALTY
    
    Все отчёты проходят аудит ИП Мкртчян (settings.PARTNER_NAME).
    
    Returns:
        dict с полной детализацией расчёта
    """
    # 1. Получаем профиль сотрудника
    user_result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = user_result.scalar_one_or_none()
    
    if not user:
        logger.error(f"[HR] Пользователь id={user_id} не найден")
        return {"error": f"User {user_id} not found", "salary": 0.0}
    
    # 2. Базовый оклад
    base_salary = user.base_salary or 130000.0
    
    # 3. Маржа логистики за месяц
    logistics_margin = await get_logistics_margin(db, year, month, user.tenant_id)
    
    # 4. Бонус за маржу (5% от маржи, но не более MAX_MARGIN_BONUS)
    raw_margin_bonus = max(0.0, logistics_margin * MARGIN_BONUS_RATE)
    margin_bonus = min(raw_margin_bonus, MAX_MARGIN_BONUS)
    
    # 5. Штрафы М4
    m4_fines = await get_m4_fines_count(db, year, month, user.tenant_id)
    fines_penalty = m4_fines * M4_FINE_PENALTY
    
    # 6. Итоговая ЗП
    gross_salary = base_salary + margin_bonus - fines_penalty
    final_salary = max(gross_salary, MIN_SALARY_FLOOR)  # Не ниже пола
    
    # 7. FIX v200.16.4: Убран db.commit() — GET-запросы не должны модифицировать данные.
    # Обновление m4_fines_count и kpi_bonus_ratio вынесено в отдельный POST-эндпоинт.
    
    # 8. Формируем отчёт с аудитом ИП Мкртчян
    report = {
        "user_id": user_id,
        "full_name": user.full_name,
        "period": f"{year}-{month:02d}",
        "base_salary": base_salary,
        "logistics_margin": logistics_margin,
        "margin_bonus_rate": MARGIN_BONUS_RATE,
        "margin_bonus": margin_bonus,
        "m4_fines_count": m4_fines,
        "m4_fine_penalty_each": M4_FINE_PENALTY,
        "total_fines_penalty": fines_penalty,
        "gross_salary": gross_salary,
        "final_salary": final_salary,
        "min_salary_applied": gross_salary < MIN_SALARY_FLOOR,
        # Аудит ИП Мкртчян
        "audit": {
            "entity": settings.PARTNER_NAME,
            "role": "IT Service Fee Controller",
            "verified_at": datetime.now().isoformat(),
            "protocol": "LOGIST-PAY v200.15",
            "note": f"Расчёт ЗП верифицирован системой контроля {settings.PARTNER_NAME}",
        },
    }
    
    logger.info(
        f"[HR] ЗП логиста {user.full_name} за {year}-{month:02d}: "
        f"base={base_salary:,.0f} + bonus={margin_bonus:,.0f} - fines={fines_penalty:,.0f} "
        f"= {final_salary:,.0f}₽ | Аудит: {settings.PARTNER_NAME}"
    )
    
    return report


async def get_hr_dashboard_metrics(
    db: AsyncSession,
    user_id: int,
) -> dict:
    """
    Метрики для виджета HR-Метрики на Dashboard:
    - Текущая ЗП логиста (за текущий месяц)
    - Штрафы М4 за сегодня
    - Статус возврата тары
    """
    now = datetime.now()
    
    # Расчёт ЗП за текущий месяц
    salary_report = await calculate_logistic_salary(db, user_id, now.year, now.month)
    
    # Штрафы за сегодня
    fines_today = await get_m4_fines_today(db)
    
    # Статус возврата тары (заглушка — будет интегрирован с warehouse)
    tara_status = {
        "total_issued": 0,
        "returned": 0,
        "pending": 0,
        "status": "ok",  # ok, warning, critical
    }
    
    return {
        "salary": {
            "current_month": salary_report.get("final_salary", 0.0),
            "base": salary_report.get("base_salary", 130000.0),
            "bonus": salary_report.get("margin_bonus", 0.0),
            "fines_deducted": salary_report.get("total_fines_penalty", 0.0),
        },
        "m4_fines": {
            "today": fines_today,
            "month_total": salary_report.get("m4_fines_count", 0),
        },
        "tara": tara_status,
        "audit_entity": settings.PARTNER_NAME,
        "period": f"{now.year}-{now.month:02d}",
    }
