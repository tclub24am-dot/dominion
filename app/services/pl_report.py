# -*- coding: utf-8 -*-
# app/services/pl_report.py
# P&L Report Service (Profit & Loss)

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.all_models import Transaction

logger = logging.getLogger("PLReport")


class PLReportService:
    """
    Сервис генерации P&L отчётов (Прибыли и Убытки)
    """
    
    async def generate_pl_report(
        self, 
        db: AsyncSession, 
        days: int = 30, 
        park_name: Optional[str] = None
    ) -> Dict:
        """
        Генерация P&L отчёта за указанный период
        
        Args:
            db: Сессия базы данных
            days: Количество дней для отчёта
            park_name: Фильтр по парку (опционально)
        
        Returns:
            Dict с данными отчёта
        """
        try:
            since = datetime.now() - timedelta(days=days)
            
            # Базовый запрос
            stmt = select(Transaction).where(Transaction.date >= since)
            
            if park_name:
                stmt = stmt.where(Transaction.park_name == park_name)
            
            result = await db.execute(stmt)
            transactions = result.scalars().all()
            
            # Агрегация по категориям
            revenue = 0.0
            expenses = 0.0
            payouts = 0.0
            
            for tx in transactions:
                amount = float(tx.amount or 0)
                category = (tx.category or "").lower()
                
                if "оплата" in category or "бонус" in category or "чаевые" in category:
                    revenue += amount
                elif "комиссия" in category or "сбор" in category:
                    expenses += abs(amount)
                elif "выплата" in category or "перевод" in category:
                    payouts += abs(amount)
            
            net_profit = revenue - expenses - payouts
            
            return {
                "period_days": days,
                "park_name": park_name or "Все парки",
                "revenue": round(revenue, 2),
                "expenses": round(expenses, 2),
                "payouts": round(payouts, 2),
                "net_profit": round(net_profit, 2),
                "transactions_count": len(transactions),
                "generated_at": datetime.now().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"P&L report generation error: {e}")
            return {
                "period_days": days,
                "park_name": park_name or "Все парки",
                "revenue": 0,
                "expenses": 0,
                "payouts": 0,
                "net_profit": 0,
                "transactions_count": 0,
                "error": str(e),
                "generated_at": datetime.now().isoformat(),
            }


# Singleton instance
pl_report = PLReportService()
