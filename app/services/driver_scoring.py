# -*- coding: utf-8 -*-
"""
S-GLOBAL DOMINION — Driver Scoring Service
============================================
Протокол: VERSHINA v200.16.6
AI-скоринг надёжности водителей.

Модуль предоставляет:
- calculate_reliability_score() — расчёт коэффициента надёжности
- check_blacklist_status() — проверка статуса в чёрном списке
"""

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timedelta

from app.models.all_models import User, Transaction

logger = logging.getLogger("dominion.driver_scoring")


class DriverScoring:
    """AI-скоринг надёжности водителей."""

    async def calculate_reliability_score(
        self,
        driver_id: int,
        db: AsyncSession,
    ) -> dict:
        """
        Расчёт коэффициента надёжности водителя.
        
        Факторы:
        - Количество штрафов за 90 дней
        - Активность аккаунта
        - Рейтинг
        
        Returns:
            dict: score (0-100), stars (1-5), status (excellent/good/warning/critical)
        """
        try:
            user = await db.get(User, driver_id)
            if not user:
                return {"score": 0, "stars": 1, "status": "critical", "factors": []}

            # Базовый скор
            score = 80.0

            # Штрафы за 90 дней
            cutoff = datetime.now() - timedelta(days=90)
            fines_result = await db.execute(
                select(func.count(Transaction.id)).where(
                    and_(
                        Transaction.contractor == user.full_name,
                        Transaction.category.like("%Штраф%"),
                        Transaction.date >= cutoff.date(),
                    )
                )
            )
            fines_count = fines_result.scalar() or 0
            score -= fines_count * 5  # -5 за каждый штраф

            # Рейтинг
            if user.rating and user.rating >= 4.8:
                score += 10
            elif user.rating and user.rating >= 4.5:
                score += 5

            # Активность
            if not user.is_active:
                score -= 30

            # Нормализация
            score = max(0, min(100, score))

            # Звёзды
            if score >= 90:
                stars, status = 5, "excellent"
            elif score >= 75:
                stars, status = 4, "good"
            elif score >= 50:
                stars, status = 3, "warning"
            else:
                stars, status = 1, "critical"

            return {
                "score": round(score, 1),
                "stars": stars,
                "status": status,
                "factors": [
                    f"Штрафов за 90 дней: {fines_count}",
                    f"Рейтинг: {user.rating or 'N/A'}",
                    f"Активен: {'Да' if user.is_active else 'Нет'}",
                ],
            }

        except Exception as e:
            logger.error(f"[SCORING] Error for driver {driver_id}: {e}")
            return {"score": 0, "stars": 1, "status": "critical", "factors": [str(e)]}

    async def check_blacklist_status(
        self,
        driver_id: int,
        db: AsyncSession,
    ) -> dict:
        """
        Проверка статуса водителя в чёрном списке.
        
        Returns:
            dict: blacklisted (bool), reason (str), since (datetime)
        """
        try:
            user = await db.get(User, driver_id)
            if not user:
                return {"blacklisted": False, "reason": None, "since": None}

            # Деактивированный аккаунт = чёрный список
            if not user.is_active:
                return {
                    "blacklisted": True,
                    "reason": "Аккаунт деактивирован",
                    "since": None,
                }

            return {"blacklisted": False, "reason": None, "since": None}

        except Exception as e:
            logger.error(f"[BLACKLIST] Error for driver {driver_id}: {e}")
            return {"blacklisted": False, "reason": None, "since": None}


# Синглтон для использования в роутерах
driver_scoring = DriverScoring()
