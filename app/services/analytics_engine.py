# -*- coding: utf-8 -*-
# app/services/analytics_engine.py
# Unified overlay metrics engine (v120.0)

from datetime import datetime, timedelta
from typing import Dict, Iterable, Optional

from sqlalchemy import and_, case, distinct, func, or_, select, false, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.all_models import (
    DriverProfile,
    DriverTensionHistory,
    FineInstallment,
    OwnershipType,
    ServiceOrder,
    Transaction,
    TripSheet,
    User,
    VehicleRepairHistory,
    Vehicle,
    WarehouseItem,
    ContractTerm,
)


class AnalyticsEngine:
    """
    Центральный сервис метрик для оверлеев и Kazna.
    - Маппинг 41 категорий Яндекса в 4 корзины
    - Статус "Живые 300" (водители с транзакциями за 48ч)
    - Оптимизированные агрегаты для Таксопарка и Казны
    """

    BUCKET_REVENUE = "revenue"
    BUCKET_YANDEX_EXPENSES = "yandex_expenses"
    BUCKET_OUR_EXPENSES = "our_expenses"
    BUCKET_PAYOUTS = "payouts"
    BUCKET_REFUND = "refund"

    CATEGORY_BUCKETS = {
        # ═══════════════════════════════════════════════════════
        # REVENUE — Доходы (оплата за поездки, бонусы, промо)
        # ═══════════════════════════════════════════════════════
        # --- Новый формат (raw) ---
        "Оплата картой": BUCKET_REVENUE,
        "Наличные": BUCKET_REVENUE,
        "Корпоративная оплата": BUCKET_REVENUE,
        "Оплата через терминал": BUCKET_REVENUE,
        "Оплата электронным кошельком": BUCKET_REVENUE,
        "Чаевые": BUCKET_REVENUE,
        "Бонус": BUCKET_REVENUE,
        "Бонус — скидка на комиссию": BUCKET_REVENUE,
        "Оплата промокодом": BUCKET_REVENUE,
        "Компенсация скидки по промокоду": BUCKET_REVENUE,
        "Компенсация за увеличенное время в пути": BUCKET_REVENUE,
        "Компенсация оплаты поездки": BUCKET_REVENUE,
        "Корректировка бонуса": BUCKET_REVENUE,
        "Подача в аэропорту": BUCKET_REVENUE,
        "Компенсация ОСАГО": BUCKET_REVENUE,
        "Оплата картой, поездка партнёра": BUCKET_REVENUE,
        "Наличные, поездка партнёра": BUCKET_REVENUE,
        "Выплата по акции": BUCKET_REVENUE,
        "Сервисная реферальная программа": BUCKET_REVENUE,
        "Партнёрская реферальная программа": BUCKET_REVENUE,
        "Цель: скидка на комиссию": BUCKET_REVENUE,
        # --- Старый формат (Yandex_ префикс) ---
        "Yandex_Оплата картой": BUCKET_REVENUE,
        "Yandex_Оплата наличными": BUCKET_REVENUE,
        "Yandex_Корпоративная оплата": BUCKET_REVENUE,
        "Yandex_Безналичная оплата": BUCKET_REVENUE,
        "Yandex_Оплата промокодом": BUCKET_REVENUE,
        "Yandex_Чаевые": BUCKET_REVENUE,
        "Yandex_Подача в аэропорту": BUCKET_REVENUE,
        "Yandex_Компенсация оплаты поездки": BUCKET_REVENUE,
        "Yandex_Бонус": BUCKET_REVENUE,
        "Yandex_Import": BUCKET_REVENUE,

        # ═══════════════════════════════════════════════════════
        # YANDEX_EXPENSES — Комиссии платформы и парка
        # ═══════════════════════════════════════════════════════
        # --- Новый формат (raw) ---
        "Комиссия сервиса за заказ": BUCKET_YANDEX_EXPENSES,
        "Комиссия сервиса, НДС": BUCKET_YANDEX_EXPENSES,
        "Комиссия партнёра за заказ": BUCKET_YANDEX_EXPENSES,
        "Комиссия партнёра за перевод": BUCKET_YANDEX_EXPENSES,
        "Комиссия партнёра за смену": BUCKET_YANDEX_EXPENSES,
        "Комиссия партнёра за бонус": BUCKET_YANDEX_EXPENSES,
        "Скидка партнёра": BUCKET_YANDEX_EXPENSES,
        "Корректировка сервиса": BUCKET_YANDEX_EXPENSES,
        "Сбор за заказ по телефону": BUCKET_YANDEX_EXPENSES,
        "Дополнительная комиссия сервиса": BUCKET_YANDEX_EXPENSES,
        "Комиссия сервиса в режиме «Специальный»": BUCKET_YANDEX_EXPENSES,
        "Комиссия сервиса за отсутствие термокороба": BUCKET_YANDEX_EXPENSES,
        "Сервисный сбор": BUCKET_YANDEX_EXPENSES,
        "Обязательный сбор": BUCKET_YANDEX_EXPENSES,
        "Удержание в счёт уплаты налогов": BUCKET_YANDEX_EXPENSES,
        "Налог с продаж": BUCKET_YANDEX_EXPENSES,
        "Адванс": BUCKET_YANDEX_EXPENSES,
        "Адванс Про": BUCKET_YANDEX_EXPENSES,
        "Заправки (комиссия)": BUCKET_YANDEX_EXPENSES,
        "Режим «Гибкий»": BUCKET_YANDEX_EXPENSES,
        "Стоимость режимов перемещения («Мой Район» / «По Делам»)": BUCKET_YANDEX_EXPENSES,
        "Аэропортовый сбор": BUCKET_YANDEX_EXPENSES,
        "Смена": BUCKET_YANDEX_EXPENSES,
        "Смена, НДС": BUCKET_YANDEX_EXPENSES,
        # --- Старый формат (Yandex_ префикс) ---
        "Yandex_Комиссия партнёра за перевод": BUCKET_YANDEX_EXPENSES,
        "Yandex_Комиссия партнёра за заказ": BUCKET_YANDEX_EXPENSES,
        "Yandex_Комиссия сервиса за заказ": BUCKET_YANDEX_EXPENSES,
        "Yandex_Комиссия сервиса, НДС": BUCKET_YANDEX_EXPENSES,
        "Yandex_Commission": BUCKET_YANDEX_EXPENSES,
        "Yandex_Заправки (комиссия)": BUCKET_YANDEX_EXPENSES,
        "Yandex_Адванс Про": BUCKET_YANDEX_EXPENSES,
        "Yandex_Сбор за заказ по телефону": BUCKET_YANDEX_EXPENSES,
        "Yandex_Комиссия сервиса за отсутствие": BUCKET_YANDEX_EXPENSES,
        "Yandex_Корректировка сервиса": BUCKET_YANDEX_EXPENSES,
        "Yandex_Удержание в счёт уплаты налого": BUCKET_YANDEX_EXPENSES,
        "Yandex_Режим «Гибкий»": BUCKET_YANDEX_EXPENSES,
        "Tax": BUCKET_YANDEX_EXPENSES,

        # ═══════════════════════════════════════════════════════
        # OUR_EXPENSES — Расходы парка
        # ═══════════════════════════════════════════════════════
        # --- Новый формат (raw) ---
        "Оплата полиса ОСАГО для такси": BUCKET_OUR_EXPENSES,
        "Ручные списания": BUCKET_OUR_EXPENSES,
        "Заправки": BUCKET_OUR_EXPENSES,
        "Заправки (кешбэк)": BUCKET_OUR_EXPENSES,
        "Заправки (чаевые)": BUCKET_OUR_EXPENSES,
        "Оплата картой проезда по платной дороге": BUCKET_OUR_EXPENSES,
        "Оплата парковки": BUCKET_OUR_EXPENSES,
        "Мойки": BUCKET_OUR_EXPENSES,
        "Покупки": BUCKET_OUR_EXPENSES,
        "Аренда кресла": BUCKET_OUR_EXPENSES,
        "Аренда кресел, НДС": BUCKET_OUR_EXPENSES,
        "Оплата штрафа": BUCKET_OUR_EXPENSES,
        "Прочие платежи партнёра": BUCKET_OUR_EXPENSES,
        "Условия работы, Списания": BUCKET_OUR_EXPENSES,
        "Финансовая ведомость через банк": BUCKET_OUR_EXPENSES,
        "Выплаты скаутам": BUCKET_OUR_EXPENSES,
        "Списание в счёт заказа": BUCKET_OUR_EXPENSES,
        "Списание доставки в счёт заказа": BUCKET_OUR_EXPENSES,
        "Пополнение в счёт заказов": BUCKET_OUR_EXPENSES,
        "Комиссия пополнения через платёжную систему": BUCKET_OUR_EXPENSES,
        # --- Старый формат ---
        "Yandex_Оплата полиса ОСАГО для такси": BUCKET_OUR_EXPENSES,
        "Yandex_Ручные списания": BUCKET_OUR_EXPENSES,
        "Yandex_Заправки": BUCKET_OUR_EXPENSES,
        "Yandex_Оплата картой проезда по платн": BUCKET_OUR_EXPENSES,
        "Расходы_Обслуживание": BUCKET_OUR_EXPENSES,
        "REPAIR_EXPENSE": BUCKET_OUR_EXPENSES,
        "Other": BUCKET_OUR_EXPENSES,
        "Work_Conditions_Deduction": BUCKET_OUR_EXPENSES,

        # ═══════════════════════════════════════════════════════
        # PAYOUTS — Выплаты и переводы
        # ═══════════════════════════════════════════════════════
        # --- Новый формат (raw) ---
        "Партнерские переводы. Аренда": BUCKET_PAYOUTS,
        "Партнерские переводы. Пополнение": BUCKET_PAYOUTS,
        "Партнерские переводы. Бонус": BUCKET_PAYOUTS,
        "Партнерские переводы. Вывод средств": BUCKET_PAYOUTS,
        "Партнерские переводы. Иное": BUCKET_PAYOUTS,
        "Партнерские переводы. Штраф": BUCKET_PAYOUTS,
        "Партнерские переводы. Депозит": BUCKET_PAYOUTS,
        "Партнерские переводы. Страховка": BUCKET_PAYOUTS,
        "Партнерские переводы. Повреждения": BUCKET_PAYOUTS,
        "Партнерские переводы. Топливо": BUCKET_PAYOUTS,
        "Партнерские переводы. Реферальная программа": BUCKET_PAYOUTS,
        "Перевод": BUCKET_PAYOUTS,
        "Перевод баланса": BUCKET_PAYOUTS,
        "Объединение балансов": BUCKET_PAYOUTS,
        "Платежи по расписанию": BUCKET_PAYOUTS,
        "Периодические списания, отмена долга": BUCKET_PAYOUTS,
        "Выплата в банк": BUCKET_PAYOUTS,
        "Пополнение через платёжную систему": BUCKET_PAYOUTS,
        # --- Старый формат ---
        "Yandex_Партнерские переводы. Аренда": BUCKET_PAYOUTS,
        "Yandex_Партнерские переводы. Пополнен": BUCKET_PAYOUTS,
        "Yandex_Партнерские переводы. Бонус": BUCKET_PAYOUTS,
        "Yandex_Партнерские переводы. Вывод ср": BUCKET_PAYOUTS,
        "Yandex_Партнерские переводы. Иное": BUCKET_PAYOUTS,
        "Yandex_Партнерские переводы. Штраф": BUCKET_PAYOUTS,
        "Yandex_Перевод": BUCKET_PAYOUTS,
        "Yandex_Платежи по расписанию": BUCKET_PAYOUTS,
        "Yandex_Моментальная выплата": BUCKET_PAYOUTS,
        "Fire_Pay": BUCKET_PAYOUTS,
        "Partner_Payout": BUCKET_PAYOUTS,

        # ═══════════════════════════════════════════════════════
        # REFUND
        # ═══════════════════════════════════════════════════════
        "Refund": BUCKET_REFUND,
    }

    PREFIX_BUCKETS = {
        # Старый формат (Yandex_ prefix) — для совместимости с историей
        "Yandex_Компенсация скидки по промокод": BUCKET_REVENUE,
        "Yandex_Удержание в счёт уплаты налого": BUCKET_YANDEX_EXPENSES,
        "Yandex_Стоимость режимов перемещения": BUCKET_YANDEX_EXPENSES,
        "Yandex_Партнерские переводы. Пополнен": BUCKET_PAYOUTS,
        "Yandex_Партнерские переводы. Вывод ср": BUCKET_PAYOUTS,
        "Yandex_Оплата картой проезда по платн": BUCKET_OUR_EXPENSES,
        # Новый формат — для длинных категорий
        "Партнерские переводы.": BUCKET_PAYOUTS,
        "Стоимость режимов перемещения": BUCKET_YANDEX_EXPENSES,
    }

    @staticmethod
    def _prefix_filter(prefixes: Iterable[str]):
        parts = [Transaction.category.like(f"{p}%") for p in prefixes]
        return or_(*parts) if parts else None

    @classmethod
    def _bucket_conditions(cls) -> Dict[str, object]:
        buckets = {
            cls.BUCKET_REVENUE: set(),
            cls.BUCKET_YANDEX_EXPENSES: set(),
            cls.BUCKET_OUR_EXPENSES: set(),
            cls.BUCKET_PAYOUTS: set(),
            cls.BUCKET_REFUND: set(),
        }
        for category, bucket in cls.CATEGORY_BUCKETS.items():
            buckets[bucket].add(category)

        conditions = {}
        for bucket, categories in buckets.items():
            parts = []
            if categories:
                parts.append(Transaction.category.in_(categories))
            prefix_filter = cls._prefix_filter(
                [p for p, b in cls.PREFIX_BUCKETS.items() if b == bucket]
            )
            if prefix_filter is not None:
                parts.append(prefix_filter)
            if bucket == cls.BUCKET_REVENUE:
                parts.append(and_(Transaction.category.is_(None), Transaction.category_type == "REVENUE"))
            if bucket == cls.BUCKET_REFUND:
                parts.append(Transaction.category == "Refund")
            if bucket in {cls.BUCKET_YANDEX_EXPENSES, cls.BUCKET_OUR_EXPENSES, cls.BUCKET_PAYOUTS}:
                parts.append(and_(Transaction.category.is_(None), Transaction.category_type == "EXPENSES"))
            conditions[bucket] = or_(*parts) if parts else None
        return conditions

    @classmethod
    def _bucket_sum_case(
        cls,
        bucket_condition,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        use_abs: bool = True,
    ):
        parts = [bucket_condition] if bucket_condition is not None else []
        if date_from is not None:
            parts.append(Transaction.date >= date_from)
        if date_to is not None:
            parts.append(Transaction.date <= date_to)
        if not parts:
            return 0
        value = func.abs(Transaction.amount) if use_abs else Transaction.amount
        return func.sum(case((and_(*parts), value), else_=0))

    @classmethod
    def get_category_bucket(cls, name: Optional[str]) -> str:
        if not name:
            return cls.BUCKET_OUR_EXPENSES
        if name in cls.CATEGORY_BUCKETS:
            return cls.CATEGORY_BUCKETS[name]
        for prefix, bucket in cls.PREFIX_BUCKETS.items():
            if name.startswith(prefix):
                return bucket
        return cls.BUCKET_OUR_EXPENSES

    @staticmethod
    def _avatar_seed(name: str) -> str:
        total = sum(ord(ch) for ch in name) if name else 0
        return str(total % 360)

    @staticmethod
    def _initials(name: Optional[str]) -> str:
        if not name:
            return "?"
        parts = [p for p in name.strip().split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[1][0]).upper()

    @classmethod
    async def get_kazna_summary(cls, db: AsyncSession, days: int = 7) -> Dict:
        now = datetime.now()
        to_date = now.date()
        from_date = to_date - timedelta(days=days)
        conditions = cls._bucket_conditions()

        totals_stmt = select(
            cls._bucket_sum_case(conditions[cls.BUCKET_REVENUE], from_date, to_date),
            cls._bucket_sum_case(conditions[cls.BUCKET_YANDEX_EXPENSES], from_date, to_date),
            cls._bucket_sum_case(conditions[cls.BUCKET_OUR_EXPENSES], from_date, to_date),
            cls._bucket_sum_case(conditions[cls.BUCKET_PAYOUTS], from_date, to_date),
            cls._bucket_sum_case(conditions[cls.BUCKET_REFUND], from_date, to_date, use_abs=True),
            func.count(Transaction.id).filter(
                and_(Transaction.date >= from_date, Transaction.date <= to_date)
            ),
        )

        revenue, yandex_expenses, our_expenses, payouts, refund_total, transactions_count = (
            await db.execute(totals_stmt)
        ).one()

        revenue = float(revenue or 0)
        yandex_expenses = float(yandex_expenses or 0)
        our_expenses = float(our_expenses or 0)
        payouts = float(payouts or 0)
        refund_total = float(refund_total or 0)
        revenue_adjusted = revenue - refund_total
        transactions_count = int(transactions_count or 0)
        total_expenses = yandex_expenses + our_expenses + payouts
        net_profit = revenue_adjusted - total_expenses

        cats_stmt = (
            select(Transaction.category, func.sum(Transaction.amount))
            .where(and_(Transaction.date >= from_date, Transaction.date <= to_date))
            .group_by(Transaction.category)
        )
        categories = (await db.execute(cats_stmt)).all()
        top_categories = sorted(
            [
                {"category": c or "Без категории", "amount": float(a or 0)}
                for c, a in categories
            ],
            key=lambda x: abs(x["amount"]),
            reverse=True,
        )[:5]

        live_300 = await cls.get_live_300(db)

        return {
            "status": "success",
            "period_days": days,
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "revenue": revenue_adjusted,
            "revenue_gross": revenue,
            "refund_total": refund_total,
            "yandex_expenses": yandex_expenses,
            "our_expenses": our_expenses,
            "payouts": payouts,
            "total_expenses": total_expenses,
            "net_profit": net_profit,
            "transactions_count": transactions_count,
            "top_categories": top_categories,
            "live_300": live_300,
            "timestamp": now.isoformat(),
        }

    @classmethod
    async def get_kazna_balance(cls, db: AsyncSession) -> Dict:
        conditions = cls._bucket_conditions()
        totals_stmt = select(
            cls._bucket_sum_case(conditions[cls.BUCKET_REVENUE]),
            cls._bucket_sum_case(conditions[cls.BUCKET_YANDEX_EXPENSES]),
            cls._bucket_sum_case(conditions[cls.BUCKET_OUR_EXPENSES]),
            cls._bucket_sum_case(conditions[cls.BUCKET_PAYOUTS]),
            cls._bucket_sum_case(conditions[cls.BUCKET_REFUND], use_abs=True),
        )
        revenue, yandex_expenses, our_expenses, payouts, refund_total = (
            await db.execute(totals_stmt)
        ).one()

        revenue = float(revenue or 0)
        yandex_expenses = float(yandex_expenses or 0)
        our_expenses = float(our_expenses or 0)
        payouts = float(payouts or 0)
        refund_total = float(refund_total or 0)
        revenue_adjusted = revenue - refund_total
        total_expenses = yandex_expenses + our_expenses + payouts
        balance = revenue_adjusted - total_expenses

        return {
            "balance": round(balance, 2),
            "revenue": revenue_adjusted,
            "revenue_gross": revenue,
            "refund_total": refund_total,
            "yandex_expenses": yandex_expenses,
            "our_expenses": our_expenses,
            "payouts": payouts,
            "total_expenses": total_expenses,
            "timestamp": datetime.now().isoformat(),
        }

    @classmethod
    async def get_live_300(cls, db: AsyncSession, now: Optional[datetime] = None) -> int:
        now = now or datetime.now()
        last_48_hours = now - timedelta(hours=48)
        core_stmt = select(func.count(User.id)).where(User.is_core_active == True)
        return int((await db.execute(core_stmt)).scalar() or 0)

    @classmethod
    async def is_live_driver(cls, db: AsyncSession, driver: User, now: Optional[datetime] = None) -> bool:
        if not driver or not driver.yandex_driver_id or not driver.is_active:
            return False
        now = now or datetime.now()
        last_48_hours = now - timedelta(hours=48)
        driver_ids = [driver.yandex_driver_id]
        if driver.yandex_contractor_id:
            driver_ids.append(driver.yandex_contractor_id)
        stmt = (
            select(func.count(Transaction.id))
            .select_from(Transaction)
            .where(
                and_(
                    Transaction.yandex_driver_id.in_(driver_ids),
                    Transaction.date >= last_48_hours,
                    Transaction.amount > 0,
                )
            )
        )
        return (await db.execute(stmt)).scalar() or 0 > 0

    @classmethod
    async def get_driver_brief(cls, db: AsyncSession, driver_id: int) -> Dict:
        now = datetime.now()
        last_48_hours = now - timedelta(hours=48)
        last_7_days = now - timedelta(days=7)
        last_3_days = now - timedelta(days=3)

        driver = await db.get(User, driver_id)
        if not driver:
            return {"status": "not_found"}

        profile_stmt = select(DriverProfile).where(DriverProfile.user_id == driver_id)
        profile = (await db.execute(profile_stmt)).scalar_one_or_none()
        online_seconds = int(profile.online_time_seconds or 0) if profile else 0
        # Нормализация timezone для сравнения
        profile_updated = profile.updated_at.replace(tzinfo=None) if profile and profile.updated_at and hasattr(profile.updated_at, 'tzinfo') and profile.updated_at.tzinfo else (profile.updated_at if profile else None)
        profile_recent = bool(profile_updated and profile_updated >= last_48_hours)

        revenue_stmt = select(func.sum(Transaction.amount)).where(
            and_(
                Transaction.yandex_driver_id == driver.yandex_driver_id,
                Transaction.amount > 0,
                Transaction.date >= last_48_hours,
            )
        )
        revenue = float((await db.execute(revenue_stmt)).scalar() or 0)
        hours = online_seconds / 3600 if online_seconds else 0.0
        kpi = round(revenue / hours, 2) if hours else 0.0

        daily_stmt = select(
            func.date(Transaction.date),
            func.sum(Transaction.amount),
        ).where(
            and_(
                Transaction.yandex_driver_id == driver.yandex_driver_id,
                Transaction.amount > 0,
                Transaction.date >= last_3_days,
            )
        ).group_by(func.date(Transaction.date))
        daily_rows = (await db.execute(daily_stmt)).all()
        daily_map = {day.isoformat(): float(amount or 0) for day, amount in daily_rows}

        def _risk_drop():
            days = [now.date() - timedelta(days=2), now.date() - timedelta(days=1), now.date()]
            series = [daily_map.get(d.isoformat()) for d in days]
            if any(v is None for v in series):
                return False, None
            if series[2] < series[1] < series[0] and series[0] > 0:
                drop_pct = round(((series[2] - series[0]) / series[0]) * 100, 1)
                reason = f"Падение выручки {abs(drop_pct)}% за 3 дня, подозрение на простой"
                return True, reason
            return False, None

        risk, risk_reason = _risk_drop()

        fines_stmt = select(func.count(Transaction.id)).where(
            and_(
                Transaction.yandex_driver_id == driver.yandex_driver_id,
                Transaction.date >= last_7_days,
                or_(
                    Transaction.category.ilike("%штраф%"),
                    Transaction.category.ilike("%fine%"),
                    Transaction.description.ilike("%штраф%"),
                ),
            )
        )
        has_fines = (await db.execute(fines_stmt)).scalar() or 0 > 0

        stars = max(0, min(5, int(round(driver.rating or 0))))
        live_driver = bool(
            driver.is_active
            and driver.yandex_driver_id
            and revenue > 0
            and online_seconds > 0
            and profile_recent
        )
        golden_star = bool(live_driver and kpi > 1.5 and not has_fines)

        return {
            "status": "ok",
            "driver_id": driver.id,
            "driver_name": driver.full_name,
            "driver_balance": float(driver.driver_balance or 0),
            "stars": stars,
            "golden_star": golden_star,
            "kpi": kpi,
            "online_hours": round(hours, 2),
            "revenue_48h": round(revenue, 2),
            "risk": risk,
            "risk_reason": risk_reason,
            "is_live": live_driver,
            "photo_url": driver.photo_url,
        }

    @classmethod
    async def get_fleet_park_stats(cls, db: AsyncSession, park_name: str) -> Dict:
        now = datetime.now()
        last_48_hours = now - timedelta(hours=48)
        park = park_name.upper()
        repair_categories = {"REPAIR_EXPENSE", "Расходы_Обслуживание"}

        # Фильтрация только активного флота (is_active_dominion = True)
        vehicles_stmt = select(
            Vehicle.id,
            Vehicle.license_plate,
            Vehicle.status,
            Vehicle.is_free,
            Vehicle.current_driver_id,
        ).where(
            and_(
                Vehicle.park_name == park,
                Vehicle.is_active_dominion == True
            )
        )
        vehicles = (await db.execute(vehicles_stmt)).all()

        repair_tx_stmt = select(Transaction.plate_info, Transaction.description).where(
            and_(
                Transaction.date >= last_48_hours,
                Transaction.category.in_(repair_categories),
            )
        )
        repair_txs = (await db.execute(repair_tx_stmt)).all()
        repair_plates = {p for p, _ in repair_txs if p}
        repair_descs = [d for _, d in repair_txs if d]

        def _in_repair(plate: str) -> bool:
            if plate in repair_plates:
                return True
            plate_upper = plate.upper()
            return any(plate_upper in (d or "").upper() for d in repair_descs)

        total = len(vehicles)
        working = 0
        reserve = 0
        repair = 0

        for _, plate, status, is_free, current_driver_id in vehicles:
            plate = plate or ""
            status_norm = (status or "").upper()
            auto_repair = _in_repair(plate) if plate else False
            
            # Приоритет статусов: repair > working > reserve
            if auto_repair or status_norm in {"SERVICE", "MAINTENANCE", "IN_SERVICE", "REPAIR"}:
                repair += 1
            elif status_norm == "WORKING":
                # Машина на линии — независимо от is_free или current_driver_id
                working += 1
            else:
                # Всё остальное — резерв
                reserve += 1

        live_drivers_stmt = select(func.count(distinct(Transaction.yandex_driver_id))).where(
            and_(
                Transaction.park_name == park,
                Transaction.yandex_driver_id.isnot(None),
                Transaction.date >= last_48_hours,
            )
        )
        live_drivers = (await db.execute(live_drivers_stmt)).scalar() or 0

        return {
            "park": park,
            "vehicles_total": total,
            "vehicles_working": working,
            "vehicles_reserve": reserve,
            "vehicles_repair": repair,
            "drivers_live": int(live_drivers or 0),
            "timestamp": now.isoformat(),
        }

    @classmethod
    async def get_vehicle_finance(cls, db: AsyncSession, vehicle_id: int, plate: str, days: int = 30) -> Dict:
        now = datetime.now()
        since = now - timedelta(days=days)
        plate_pattern = f"%{plate}%"

        income_stmt = select(func.sum(Transaction.amount)).where(
            and_(
                Transaction.amount > 0,
                Transaction.description.like(plate_pattern),
                Transaction.date >= since.date(),
            )
        )
        income = float((await db.execute(income_stmt)).scalar() or 0)

        repair_stmt = select(func.sum(VehicleRepairHistory.repair_cost)).where(
            and_(
                VehicleRepairHistory.vehicle_id == vehicle_id,
                VehicleRepairHistory.created_at >= since,
            )
        )
        repair_cost = float((await db.execute(repair_stmt)).scalar() or 0)
        profit = income - repair_cost

        return {
            "income": income,
            "repair_cost": repair_cost,
            "profit": profit,
            "period_days": days,
            "from_date": since.date().isoformat(),
            "to_date": now.date().isoformat(),
        }

    @classmethod
    async def get_fleet_overview(cls, db: AsyncSession) -> Dict:
        parks = ["PRO", "GO", "PLUS", "EXPRESS"]
        park_stats = {}
        totals = {
            "vehicles_total": 0,
            "vehicles_working": 0,
            "vehicles_reserve": 0,
            "vehicles_repair": 0,
        }
        for park in parks:
            stats = await cls.get_fleet_park_stats(db, park)
            park_stats[park] = stats
            totals["vehicles_total"] += stats["vehicles_total"]
            totals["vehicles_working"] += stats["vehicles_working"]
            totals["vehicles_reserve"] += stats["vehicles_reserve"]
            totals["vehicles_repair"] += stats["vehicles_repair"]

        last_7_days = datetime.now() - timedelta(days=7)
        active_driver_ids = select(distinct(Transaction.yandex_driver_id)).where(
            and_(Transaction.yandex_driver_id.isnot(None), Transaction.date >= last_7_days)
        )
        archived_stmt = select(func.count(User.id)).where(
            and_(
                User.is_active == False,
                or_(
                    User.yandex_driver_id.isnot(None),
                    User.yandex_contractor_id.isnot(None),
                ),
                ~User.yandex_driver_id.in_(active_driver_ids),
            )
        )
        archived_drivers = int((await db.execute(archived_stmt)).scalar() or 0)

        return {
            "parks": park_stats,
            "totals": totals,
            "archived_drivers": archived_drivers,
        }

    @classmethod
    async def get_fleet_command_data(cls, db: AsyncSession, include_all: bool = False) -> Dict:
        """
        Данные для Command Dashboard.
        
        include_all=False: Только "Живые 300" (is_active_dominion=True)
        include_all=True: Все машины (для вкладки АРХИВ)
        """
        now = datetime.now()
        last_48_hours = now - timedelta(hours=48)
        last_7_days = now - timedelta(days=7)
        last_3_days = now - timedelta(days=3)
        parks = ["PRO", "GO", "PLUS", "EXPRESS"]
        repair_categories = {"REPAIR_EXPENSE", "Расходы_Обслуживание"}

        # PROTOCOL "THE LIVE 300" v2: Строгая фильтрация
        # Боевой режим: ТОЛЬКО is_active_dominion=True (устанавливается recalculate_active_dominion)
        # Архив: все машины с is_active=True
        if include_all:
            where_clause = Vehicle.is_active == True
        else:
            where_clause = and_(
                Vehicle.is_active == True,
                Vehicle.is_active_dominion == True,
            )
        
        # JOIN с User через обратную связь: User.current_vehicle_id = Vehicle.id
        # (Vehicle.current_driver_id может быть NULL, но User.current_vehicle_id заполнен)
        vehicles_stmt = (
            select(Vehicle, User, DriverProfile)
            .outerjoin(User, or_(
                Vehicle.current_driver_id == User.id,
                User.current_vehicle_id == Vehicle.id,
            ))
            .outerjoin(DriverProfile, DriverProfile.user_id == User.id)
            .where(where_clause)
        )
        rows = (await db.execute(vehicles_stmt)).all()
        
        # Дедупликация: один Vehicle может JOIN с несколькими Users
        seen_vehicle_ids = set()
        deduped_rows = []
        for row in rows:
            v = row[0]
            if v and v.id not in seen_vehicle_ids:
                seen_vehicle_ids.add(v.id)
                deduped_rows.append(row)
        rows = deduped_rows
        
        # Счётчик всех машин для статистики
        total_vehicles_count = (await db.execute(
            select(func.count(Vehicle.id)).where(Vehicle.is_active == True)
        )).scalar() or 0
        vehicle_ids = [row[0].id for row in rows if row and row[0] is not None]
        driver_user_ids = [row[1].id for row in rows if row and row[1] is not None]
        terms_stmt = select(ContractTerm).where(
            or_(
                ContractTerm.vehicle_id.in_(vehicle_ids) if vehicle_ids else false(),
                ContractTerm.driver_id.in_(driver_user_ids) if driver_user_ids else false(),
                ContractTerm.is_default == True,
            )
        )
        terms = (await db.execute(terms_stmt)).scalars().all()
        terms_by_vehicle = {t.vehicle_id: t for t in terms if t.vehicle_id}
        terms_by_driver = {t.driver_id: t for t in terms if t.driver_id}
        default_terms = {t.park_name: t for t in terms if t.is_default}

        revenue_48_stmt = (
            select(
                User.id,
                func.sum(Transaction.amount),
            )
            .select_from(Transaction)
            .join(
                User,
                or_(
                    User.yandex_driver_id == Transaction.yandex_driver_id,
                    User.yandex_contractor_id == Transaction.yandex_driver_id,
                ),
            )
            .where(
                and_(
                    Transaction.yandex_driver_id.isnot(None),
                    Transaction.amount > 0,
                    Transaction.date >= last_48_hours,
                )
            )
            .group_by(User.id)
        )
        revenue_48_by_user = {
            user_id: float(amount or 0)
            for user_id, amount in (await db.execute(revenue_48_stmt)).all()
        }

        daily_stmt = select(
            Transaction.yandex_driver_id,
            func.date(Transaction.date),
            func.sum(Transaction.amount),
        ).where(
            and_(
                Transaction.yandex_driver_id.isnot(None),
                Transaction.amount > 0,
                Transaction.date >= last_3_days,
            )
        ).group_by(Transaction.yandex_driver_id, func.date(Transaction.date))
        daily_rows = (await db.execute(daily_stmt)).all()
        daily_by_driver: Dict[str, Dict[str, float]] = {}
        for driver_id, day, amount in daily_rows:
            if not driver_id:
                continue
            day_key = day.isoformat()
            daily_by_driver.setdefault(driver_id, {})[day_key] = float(amount or 0)

        active_driver_ids = select(distinct(Transaction.yandex_driver_id)).where(
            and_(Transaction.yandex_driver_id.isnot(None), Transaction.date >= last_7_days)
        )
        active_ids = {
            row[0]
            for row in (await db.execute(active_driver_ids)).all()
            if row[0]
        }

        fines_stmt = select(distinct(Transaction.yandex_driver_id)).where(
            and_(
                Transaction.yandex_driver_id.isnot(None),
                Transaction.date >= last_7_days,
                or_(
                    Transaction.category.ilike("%штраф%"),
                    Transaction.category.ilike("%fine%"),
                    Transaction.description.ilike("%штраф%"),
                ),
            )
        )
        fines_ids = {
            row[0]
            for row in (await db.execute(fines_stmt)).all()
            if row[0]
        }

        repair_tx_stmt = select(Transaction.plate_info, Transaction.description).where(
            and_(
                Transaction.date >= last_48_hours,
                Transaction.category.in_(repair_categories),
            )
        )
        repair_txs = (await db.execute(repair_tx_stmt)).all()
        repair_plates = {p for p, _ in repair_txs if p}
        repair_descs = [d for _, d in repair_txs if d]

        def _in_repair(plate: str) -> bool:
            if plate in repair_plates:
                return True
            plate_upper = plate.upper()
            return any(plate_upper in (d or "").upper() for d in repair_descs)

        def _risk_drop(driver_id: Optional[str]):
            if not driver_id:
                return False, None
            days = [now.date() - timedelta(days=2), now.date() - timedelta(days=1), now.date()]
            series = [
                daily_by_driver.get(driver_id, {}).get(d.isoformat())
                for d in days
            ]
            if any(v is None for v in series):
                return False, None
            if series[2] < series[1] < series[0] and series[0] > 0:
                drop_pct = round(((series[2] - series[0]) / series[0]) * 100, 1)
                reason = f"Падение выручки {abs(drop_pct)}% за 3 дня, подозрение на простой"
                return True, reason
            return False, None

        vehicles = []
        summary = {
            "totals": {"all": 0, "live": 0, "reserve": 0, "repair": 0, "archive": 0},
            "parks": {p: {"all": 0, "live": 0, "reserve": 0, "repair": 0, "archive": 0} for p in parks},
        }
        golden_top = []

        for vehicle, user, profile in rows:
            plate = (vehicle.license_plate or "").upper()
            park = (vehicle.park_name or "PRO").upper()
            park = park if park in summary["parks"] else "PRO"
            driver_id = user.yandex_driver_id if user else None
            online_seconds = int(profile.online_time_seconds or 0) if profile else 0
            
            # Нормализация datetime для сравнения (timezone-aware -> naive)
            def to_naive(dt):
                if dt and hasattr(dt, 'tzinfo') and dt.tzinfo:
                    return dt.replace(tzinfo=None)
                return dt
            
            profile_updated = to_naive(profile.updated_at) if profile else None
            user_last_active = to_naive(user.last_active_at) if user else None
            last_48_naive = to_naive(last_48_hours)
            
            profile_recent = bool(profile_updated and profile_updated >= last_48_naive)
            is_active = bool(user and user.is_active)
            revenue = float(revenue_48_by_user.get(user.id, 0.0)) if user else 0.0
            hours = online_seconds / 3600 if online_seconds else 0.0
            kpi = (revenue / hours) if hours else 0.0
            # REAL-TIME STATUS: Водитель "live" если:
            # 1. is_core_active = True (установлен синхронизацией)
            # 2. ИЛИ realtime_status = online/busy
            # 3. ИЛИ work_status = working
            # 4. ИЛИ есть транзакции за 48ч и активность
            is_core_active = bool(user and getattr(user, 'is_core_active', False))
            realtime_online = bool(
                user 
                and hasattr(user, 'realtime_status') 
                and str(getattr(user, 'realtime_status', '') or '').lower() in ('online', 'busy')
            )
            work_status_working = bool(
                user 
                and hasattr(user, 'work_status') 
                and str(getattr(user, 'work_status', '') or '').lower() == 'working'
            )
            has_recent_activity = bool(
                is_active
                and (user and user.id in revenue_48_by_user)
                and (
                    (online_seconds > 0 and profile_recent)
                    or (user_last_active and user_last_active >= last_48_naive)
                )
            )
            live_driver = is_core_active or realtime_online or work_status_working or has_recent_activity
            # Машина архивная только если у неё status ARCHIVE (не зависит от водителя)
            is_archive = (vehicle.status or "").upper() == "ARCHIVE"
            is_repair = _in_repair(plate) or (vehicle.status or "").upper() in {"SERVICE", "MAINTENANCE", "IN_SERVICE", "REPAIR"}
            risk, risk_reason = _risk_drop(driver_id)
            stars = 0
            if user and user.rating is not None:
                stars = max(0, min(5, int(round(user.rating))))
            has_fines = bool(driver_id in fines_ids)
            golden_star = bool(live_driver and kpi > 1.5 and not has_fines)
            priority_payout = bool(live_driver and stars >= 5)

            contract = (
                terms_by_vehicle.get(vehicle.id)
                or (terms_by_driver.get(user.id) if user else None)
                or default_terms.get(park)
            )
            if contract:
                contract_info = {
                    "driver_daily_rent": float(contract.driver_daily_rent or 0.0),
                    "commission_rate": float(contract.commission_rate or 0.0),
                    "is_repair": bool(contract.is_repair),
                    "is_day_off": bool(contract.is_day_off),
                    "is_idle": bool(contract.is_idle),
                }
            else:
                contract_info = {
                    "driver_daily_rent": float(getattr(user, "daily_rent", 0.0) or 0.0),
                    "commission_rate": float(getattr(vehicle, "commission_rate", 0.03) or 0.03),
                    "is_repair": False,
                    "is_day_off": False,
                    "is_idle": False,
                }

            # SUBLEASE SHIELD: Определяем тип собственности ДО статуса
            ownership_type_str = vehicle.ownership_type.value if hasattr(vehicle.ownership_type, "value") else str(vehicle.ownership_type)
            is_sublease = (
                getattr(vehicle, "is_park_car", False) 
                or "sublease" in ownership_type_str.lower()
            )
            
            # IMPERIAL STABILIZATION: Расширенная логика Live
            # Live если: sublease ИЛИ есть водитель ИЛИ live_driver
            is_live = (
                live_driver
                or vehicle.current_driver_id is not None
                or is_sublease  # Sublease машины всегда live
                or (user and getattr(user, 'is_core_active', False))
            )
            
            if is_archive:
                status = "archive"
            elif is_repair:
                status = "repair"
            elif is_live:
                status = "live"
            else:
                status = "reserve"

            summary["totals"]["all"] += 1
            summary["totals"][status] += 1
            summary["parks"][park]["all"] += 1
            summary["parks"][park][status] += 1
            
            vehicles.append(
                {
                    "id": vehicle.id,
                    "plate": plate,
                    "park": park,
                    "park_name": park,  # Для фронтенда — категория (PRO/GO/PLUS/EXPRESS)
                    "status": status,
                    "ownership_type": ownership_type_str,
                    "is_park_car": getattr(vehicle, "is_park_car", False),  # DEEP MAPPING v200.1
                    "is_sublease": is_sublease,  # SUBLEASE SHIELD
                    "is_active_dominion": getattr(vehicle, "is_active_dominion", False),  # PROTOCOL "THE LIVE 300"
                    "driver_name": user.full_name if user else None,
                    "driver_phone": user.username if user else None,
                    "driver_id": driver_id,
                    "user_id": user.id if user else None,
                    "driver_balance": float(user.driver_balance or 0) if user else 0.0,
                    "stars": stars,
                    "golden_star": golden_star,
                    "priority_payout": priority_payout,
                    "has_fines": has_fines,
                    "is_live": live_driver,
                    "realtime_status": (
                        "online" if is_core_active 
                        else str(getattr(user, 'realtime_status', 'offline') or 'offline')
                    ) if user else 'offline',
                    "is_archive": is_archive,
                    "is_repair": is_repair,
                    "is_free": bool(vehicle.is_free),
                    "online_hours": round(hours, 2),
                    "revenue_48h": round(revenue, 2),
                    "kpi": round(kpi, 2),
                    "risk": risk,
                    "risk_reason": risk_reason,
                    "photo_url": user.photo_url if user else None,
                    "avatar_text": cls._initials(user.full_name if user else None),
                    "avatar_hue": cls._avatar_seed(user.full_name if user else "Driver"),
                    "contract_terms": contract_info,
                }
            )
            if golden_star:
                golden_top.append(
                    {
                        "driver_name": user.full_name if user else "Без имени",
                        "driver_id": driver_id,
                        "user_id": user.id if user else None,
                        "kpi": round(kpi, 2),
                        "stars": stars,
                        "park": park,
                        "revenue_48h": round(revenue, 2),
                        "driver_balance": float(user.driver_balance or 0) if user else 0.0,
                        "avatar_text": cls._initials(user.full_name if user else None),
                        "avatar_hue": cls._avatar_seed(user.full_name if user else "Driver"),
                        "photo_url": user.photo_url if user else None,
                    }
                )

        live_300 = await cls.get_live_300(db)
        efficiency = round((live_300 / summary["totals"]["all"]) * 100, 2) if summary["totals"]["all"] else 0.0

        unassigned_stmt = select(User, DriverProfile).outerjoin(
            DriverProfile, DriverProfile.user_id == User.id
        ).where(
            and_(
                User.is_active == True,
                User.is_archived == False,
                User.current_vehicle_id.is_(None),
                User.yandex_driver_id.isnot(None),
            )
        )
        unassigned = (await db.execute(unassigned_stmt)).all()
        for user, profile in unassigned:
            park = (user.park_name or "PRO").upper()
            contract = terms_by_driver.get(user.id) or default_terms.get(park)
            if contract:
                contract_info = {
                    "driver_daily_rent": float(contract.driver_daily_rent or 0.0),
                    "commission_rate": float(contract.commission_rate or 0.0),
                    "is_repair": bool(contract.is_repair),
                    "is_day_off": bool(contract.is_day_off),
                    "is_idle": bool(contract.is_idle),
                }
            else:
                contract_info = {
                    "driver_daily_rent": float(getattr(user, "daily_rent", 0.0) or 0.0),
                    "commission_rate": 0.03,
                    "is_repair": False,
                    "is_day_off": False,
                    "is_idle": False,
                }
            vehicles.append(
                {
                    "id": -int(user.id),
                    "plate": "—",
                    "park": park,
                    "status": "reserve",
                    "ownership_type": "driver_only",
                    "driver_name": user.full_name,
                    "driver_phone": user.username,
                    "driver_id": user.yandex_driver_id,
                    "user_id": user.id,
                    "driver_balance": float(user.driver_balance or 0.0),
                    "stars": max(0, min(5, int(round(user.rating or 0)))),
                    "golden_star": False,
                    "priority_payout": False,
                    "has_fines": False,
                    "is_live": False,
                    "is_archive": False,
                    "is_repair": False,
                    "is_free": True,
                    "online_hours": round((profile.online_time_seconds or 0) / 3600, 2) if profile else 0.0,
                    "revenue_48h": 0.0,
                    "kpi": 0.0,
                    "risk": False,
                    "risk_reason": None,
                    "photo_url": user.photo_url,
                    "avatar_text": cls._initials(user.full_name),
                    "avatar_hue": cls._avatar_seed(user.full_name or "Driver"),
                    "contract_terms": contract_info,
                }
            )

        # Счётчики активных машин по паркам (для кнопок фильтров)
        # Считаем только реальные машины (id > 0), без "driver_only" записей
        active_counts_by_park = {
            park: sum(1 for v in vehicles if v.get("park") == park and v.get("id", 0) > 0)
            for park in parks
        }
        # Счёт машин Live (status=live или realtime_status=online/busy)
        # Только реальные машины (id > 0)
        live_count = sum(1 for v in vehicles if v.get("status") == "live" and v.get("id", 0) > 0)
        # Счёт водителей с привязкой
        drivers_bound_count = sum(1 for v in vehicles if v.get("driver_name"))
        # Счёт водителей "на линии" (realtime_status = online или busy)
        drivers_online_count = sum(
            1 for v in vehicles 
            if v.get("realtime_status") in ("online", "busy") or v.get("is_live")
        )
        # Резерв = Только реальные машины со статусом reserve
        reserve_count = sum(1 for v in vehicles if v.get("status") == "reserve" and v.get("id", 0) > 0)
        # Ремзона = реальные машины со статусом repair
        repair_count = sum(1 for v in vehicles if v.get("status") == "repair" and v.get("id", 0) > 0)
        
        return {
            "summary": summary,
            "live_300": live_300,
            "efficiency": efficiency,
            "timestamp": now.isoformat(),
            "vehicles": vehicles,
            "golden_top": sorted(golden_top, key=lambda x: x["kpi"], reverse=True)[:5],
            # PROTOCOL "THE LIVE 300": Счётчики для UI
            # Считаем только реальные машины (id > 0), без "driver_only" записей
            "active_dominion_count": sum(1 for v in vehicles if v.get("id", 0) > 0),  # Живые борты
            "total_vehicles_count": total_vehicles_count,  # Всего в системе
            "active_counts_by_park": active_counts_by_park,  # PRO: 18, GO: 14, etc.
            "drivers_bound_count": drivers_bound_count,  # Водителей с привязкой
            "drivers_online_count": drivers_online_count,  # На линии (online/busy)
            "live_count": live_count,  # Машины в статусе Live
            "reserve_count": reserve_count,  # Машины в резерве
            "repair_count": repair_count,  # Машины в ремзоне
        }

    @classmethod
    async def get_triad_data(cls, db: AsyncSession, park: str = "ALL", yandex_sync=None) -> Dict:
        """
        Триада Власти v2: ГИБРИДНЫЙ ДВИЖОК
        - Исполнители и Автомобили: REAL-TIME из Yandex API (с fallback на БД)
        - Финансы: из БД (транзакции), payout_remain из API
        - Парки без API-ключей: возвращают нули
        park: ALL | PRO | GO | PLUS | EXPRESS
        """
        import logging
        _log = logging.getLogger("TriadEngine")

        now = datetime.now()
        # ИСПРАВЛЕНИЕ: 7 дней = сегодня + 6 предыдущих дней (как в Яндекс "1-7 фев")
        start_date = (now - timedelta(days=6)).date()
        last_7_days = datetime.combine(start_date, datetime.min.time())  # Начало первого дня
        date_labels = [(start_date + timedelta(days=i)).isoformat() for i in range(7)]
        parks_list = ["PRO", "GO", "PLUS", "EXPRESS"]
        park_filter = park.upper() if park and park.upper() in parks_list else "ALL"

        # ——— Определяем активные парки через yandex_sync ———
        active_park_names = set()
        if yandex_sync and hasattr(yandex_sync, "active_parks"):
            active_park_names = set(yandex_sync.active_parks.keys())

        # Если запрошен конкретный парк без API-ключа → возвращаем нули
        if park_filter != "ALL" and active_park_names and park_filter not in active_park_names:
            _log.warning(f"[TRIAD] Парк {park_filter} не имеет API-ключей → возвращаем нули")
            return {
                "finance": {
                    "sum_trips": 0, "revenue_park": 0, "payout_remain": 0,
                    "weekly_dates": date_labels, "weekly_series": [0.0] * 7,
                },
                "performers": {
                    "on_line": 0, "free": 0, "in_order": 0, "busy": 0,
                    "avg_time_online": "0 ч 0 мин", "new_24h": 0, "churn": 0,
                },
                "assets": {
                    "total_active": 0, "working": 0, "no_driver": 0,
                    "in_service": 0, "preparation": 0,
                },
                "ops_summary": {
                    "repair_count": 0, "warehouse_status": "Н/Д",
                    "live_points": 0, "idle_count": 0,
                },
                "park": park_filter,
            }

        # Для park=ALL фильтруем только активные парки в БД-запросах
        active_park_filter = list(active_park_names) if active_park_names else parks_list

        # ============================================================
        # ФИНАНСЫ: ТОЧНАЯ ФОРМУЛА КАК В ЯНДЕКС FLEET
        # ============================================================

        # ── СУММА ПО ПОЕЗДКАМ (как в Яндекс Dashboard) ──
        # Яндекс Dashboard "Сумма по поездкам" = ВСЯ выручка по поездкам,
        # включая наличные. Это общая сумма, которую пассажиры заплатили.
        # Наличные ВКЛЮЧЕНЫ — они часть выручки поездки.
        _yandex_ride_cats = [
            # Оплата пассажиров (все способы)
            "Оплата картой",
            "Наличные",
            "Корпоративная оплата",
            "Оплата через терминал",
            "Оплата электронным кошельком",
            # Промо/компенсации (Яндекс покрывает разницу)
            "Оплата промокодом",
            "Компенсация скидки по промокоду",
            "Компенсация оплаты поездки",
            "Компенсация за увеличенное время в пути",
            # Оплата дорог (проходит через Яндекс)
            "Оплата картой проезда по платной дороге",
        ]

        # Грязный оборот = Яндекс + партнёрские поездки (расширенный охват)
        _gross_ride_cats = _yandex_ride_cats + [
            "Наличные, поездка партнёра",
            "Оплата картой, поездка партнёра",
        ]

        park_where = []
        if park_filter != "ALL":
            park_where.append(Transaction.park_name == park_filter)
        elif active_park_names:
            park_where.append(Transaction.park_name.in_(active_park_filter))

        # "Сумма по поездкам" (Яндекс) — NET, без наличных
        yandex_where = and_(
            Transaction.date >= last_7_days,
            Transaction.category.in_(_yandex_ride_cats),
            *park_where,
        )
        sum_trips_stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(yandex_where)
        sum_trips = float((await db.execute(sum_trips_stmt)).scalar() or 0)

        # "Грязный оборот" — NET, с наличными
        gross_where = and_(
            Transaction.date >= last_7_days,
            Transaction.category.in_(_gross_ride_cats),
            *park_where,
        )
        sum_gross_stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(gross_where)
        sum_gross = float((await db.execute(sum_gross_stmt)).scalar() or 0)

        # Ежедневная серия для графика (Яндекс-формула)
        daily_stmt = select(
            func.date(Transaction.date),
            func.sum(Transaction.amount),
        ).where(yandex_where).group_by(func.date(Transaction.date))
        daily_rows = (await db.execute(daily_stmt)).all()
        daily_map = {d.isoformat(): float(a or 0) for d, a in daily_rows}
        weekly_series = [daily_map.get(d, 0.0) for d in date_labels]

        # ── ДОХОД ТАКСОПАРКА ──
        # Яндекс Dashboard: ТОЛЬКО "Комиссия партнёра за заказ" (partner_ride_fee)
        # НЕ включает: за перевод, за смену, за бонус — они идут в другие метрики
        # Хранится как отрицательные числа → ABS
        _park_commission_cats = [
            "Комиссия партнёра за заказ",
        ]
        # NET sum (включая коррекции/возвраты), затем ABS — так считает Яндекс
        comm_where = and_(
            Transaction.date >= last_7_days,
            Transaction.category.in_(_park_commission_cats),
            *park_where,
        )
        comm_stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(comm_where)
        revenue_park = abs(float((await db.execute(comm_stmt)).scalar() or 0))

        # Ежедневная серия "Доход таксопарка" для второй линии графика
        daily_rev_stmt = select(
            func.date(Transaction.date),
            func.sum(Transaction.amount),
        ).where(comm_where).group_by(func.date(Transaction.date))
        daily_rev_rows = (await db.execute(daily_rev_stmt)).all()
        daily_rev_map = {d.isoformat(): abs(float(a or 0)) for d, a in daily_rev_rows}
        weekly_revenue_series = [daily_rev_map.get(d, 0.0) for d in date_labels]

        # ── ОСТАТОК К ВЫПЛАТЕ ──
        # Real-time из Yandex API: сумма положительных балансов водителей
        # Яндекс показывает "а балансов в плюсе" = эту метрику
        # "Остаток к выплате" Яндекса = (балансы в плюсе) - (платформенные сборы)
        # Мы показываем "балансы в плюсе" — это то, что реально на счетах водителей
        payout_remain = 0.0
        if yandex_sync:
            try:
                if park_filter != "ALL":
                    bal_data = await yandex_sync.get_realtime_balances(park_filter)
                    payout_remain = bal_data.get("payout_remain", 0.0)
                else:
                    for pn in active_park_names:
                        bal_data = await yandex_sync.get_realtime_balances(pn)
                        payout_remain += bal_data.get("payout_remain", 0.0)
            except Exception as e:
                _log.warning(f"[TRIAD] Ошибка получения балансов из API: {e}, fallback на БД")
                payout_stmt = select(func.coalesce(func.sum(User.driver_balance), 0)).where(
                    and_(User.driver_balance.isnot(None), User.driver_balance > 0)
                )
                if park_filter != "ALL":
                    payout_stmt = payout_stmt.where(User.park_name == park_filter)
                elif active_park_names:
                    payout_stmt = payout_stmt.where(User.park_name.in_(active_park_filter))
                payout_remain = float((await db.execute(payout_stmt)).scalar() or 0)
        else:
            payout_stmt = select(func.coalesce(func.sum(User.driver_balance), 0)).where(
                and_(User.driver_balance.isnot(None), User.driver_balance > 0)
            )
            if park_filter != "ALL":
                payout_stmt = payout_stmt.where(User.park_name == park_filter)
            elif active_park_names:
                payout_stmt = payout_stmt.where(User.park_name.in_(active_park_filter))
            payout_remain = float((await db.execute(payout_stmt)).scalar() or 0)

        # ============================================================
        # ИСПОЛНИТЕЛИ: REAL-TIME из Yandex API (с fallback на БД)
        # ============================================================
        on_line = 0
        free_count = 0
        in_order_count = 0
        busy_count = 0
        rt_source = "db"

        # active_vehicles из driver stats (кол-во уникальных car_id у онлайн-водителей)
        rt_active_vehicles = 0

        if yandex_sync:
            try:
                if park_filter != "ALL":
                    ds = await yandex_sync.get_realtime_driver_stats(park_filter)
                    on_line = ds.get("on_line", 0)
                    free_count = ds.get("free", 0)
                    in_order_count = ds.get("in_order", 0)
                    busy_count = ds.get("busy", 0)
                    rt_active_vehicles = ds.get("active_vehicles", 0)
                    rt_source = ds.get("source", "yandex_api")
                else:
                    for pn in active_park_names:
                        ds = await yandex_sync.get_realtime_driver_stats(pn)
                        on_line += ds.get("on_line", 0)
                        free_count += ds.get("free", 0)
                        in_order_count += ds.get("in_order", 0)
                        busy_count += ds.get("busy", 0)
                        rt_active_vehicles += ds.get("active_vehicles", 0)
                    rt_source = "yandex_api"
            except Exception as e:
                _log.warning(f"[TRIAD] RT drivers error: {e}, fallback на БД")
                rt_source = "db_fallback"
                yandex_sync = None  # Используем DB fallback ниже

        if rt_source.startswith("db") or rt_source == "no_keys":
            # DB FALLBACK для исполнителей
            driver_id_expr = func.coalesce(User.yandex_driver_id, User.yandex_contractor_id)
            perf_base = and_(
                User.work_status == "working",
                User.is_archived == False,
                driver_id_expr.isnot(None),
            )
            if park_filter != "ALL":
                perf_base = and_(perf_base, User.park_name == park_filter)
            elif active_park_names:
                perf_base = and_(perf_base, User.park_name.in_(active_park_filter))

            on_line = (await db.execute(select(func.count(User.id)).where(perf_base))).scalar() or 0
            free_count = (await db.execute(
                select(func.count(User.id)).where(and_(perf_base, User.realtime_status == "online"))
            )).scalar() or 0
            in_order_count = (await db.execute(
                select(func.count(User.id)).where(and_(perf_base, User.realtime_status == "busy"))
            )).scalar() or 0
            busy_count = max(0, on_line - free_count - in_order_count)

        # Среднее время на линии (из БД — API не даёт этого)
        perf_base_db = and_(
            User.work_status == "working",
            User.is_archived == False,
        )
        if park_filter != "ALL":
            perf_base_db = and_(perf_base_db, User.park_name == park_filter)
        elif active_park_names:
            perf_base_db = and_(perf_base_db, User.park_name.in_(active_park_filter))

        try:
            avg_time_stmt = select(
                func.coalesce(func.avg(DriverProfile.online_time_seconds), 0)
            ).select_from(User).join(DriverProfile, DriverProfile.user_id == User.id).where(perf_base_db)
            avg_seconds = float((await db.execute(avg_time_stmt)).scalar() or 0)
        except Exception:
            avg_seconds = 0.0
        avg_h = int(avg_seconds // 3600)
        avg_m = int((avg_seconds % 3600) // 60)
        avg_time_online = f"{avg_h} ч {avg_m} мин"

        last_24h = now - timedelta(hours=24)
        new_24h_stmt = select(func.count(User.id)).where(
            and_(User.is_archived == False, User.created_at >= last_24h)
        )
        if park_filter != "ALL":
            new_24h_stmt = new_24h_stmt.where(User.park_name == park_filter)
        elif active_park_names:
            new_24h_stmt = new_24h_stmt.where(User.park_name.in_(active_park_filter))
        new_24h = (await db.execute(new_24h_stmt)).scalar() or 0

        churn_stmt = select(func.count(User.id)).where(User.is_archived == True)
        if park_filter != "ALL":
            churn_stmt = churn_stmt.where(User.park_name == park_filter)
        elif active_park_names:
            churn_stmt = churn_stmt.where(User.park_name.in_(active_park_filter))
        churn = (await db.execute(churn_stmt)).scalar() or 0

        # ============================================================
        # АВТОМОБИЛИ: ГИБРИД DB + API
        # total_active = НАШ ФЛОТ из БД (is_active_dominion=True) — совпадает с кнопкой PRO
        # working = машины с онлайн-водителями (из API driver stats)
        # in_service = машины в ремонте из нашего флота (из БД)
        # no_driver = total - working - in_service (свободные борты)
        # Архивные записи ПОЛНОСТЬЮ исключены.
        # ============================================================
        veh_source = "hybrid"

        # 1. Наш флот из БД (is_active_dominion=True) — это число на кнопке парка
        fleet_base = and_(
            Vehicle.is_active_dominion == True,
        )
        if park_filter != "ALL":
            fleet_base = and_(fleet_base, Vehicle.park_name == park_filter)
        elif active_park_names:
            fleet_base = and_(fleet_base, Vehicle.park_name.in_(active_park_filter))

        total_active = (await db.execute(
            select(func.count(Vehicle.id)).where(fleet_base)
        )).scalar() or 0

        # 1b. Парковые vs Подключенные
        park_cars_c = (await db.execute(
            select(func.count(Vehicle.id)).where(and_(fleet_base, Vehicle.is_park_car == True))
        )).scalar() or 0
        private_cars_c = max(0, total_active - park_cars_c)

        # 2. В сервисе/ремонте (из нашего флота)
        service_statuses = Vehicle.status.in_(["service", "maintenance", "repair"])
        in_service_c = (await db.execute(
            select(func.count(Vehicle.id)).where(and_(fleet_base, service_statuses))
        )).scalar() or 0

        # 3. Работает = машины с онлайн-водителями (из API)
        if rt_source == "yandex_api" and rt_active_vehicles > 0:
            working_c = rt_active_vehicles
        else:
            # DB fallback: машины с привязанным водителем и status=working
            working_c = (await db.execute(
                select(func.count(Vehicle.id)).where(
                    and_(fleet_base, Vehicle.current_driver_id.isnot(None),
                         Vehicle.status == "working")
                )
            )).scalar() or 0

        # 4. Без водителя = наш флот - работающие - в сервисе
        no_driver_c = max(0, total_active - working_c - in_service_c)
        preparation_c = 0  # Убрана категория "Подготовка" — не нужна Мастеру

        # Оперативная сводка: АВТОСЕРВИС = машины в ремонте из нашего флота
        repair_count = in_service_c  # Точно из нашего флота, не из всего парка
        idle_count = int(no_driver_c)

        # ============================================================
        # ДОХОД ОТ АРЕНДЫ (субаренда) — 41 борт
        # driver_daily_rent * 7 дней = недельный доход от субарендных бортов
        # ============================================================
        sublease_base = and_(
            Vehicle.is_active_dominion == True,
            Vehicle.ownership_type.cast(String) == "SUBLEASE",
        )
        if park_filter != "ALL":
            sublease_base = and_(sublease_base, Vehicle.park_name == park_filter)
        elif active_park_names:
            sublease_base = and_(sublease_base, Vehicle.park_name.in_(active_park_filter))

        # Sublease fleet size
        sublease_count = (await db.execute(
            select(func.count(Vehicle.id)).where(sublease_base)
        )).scalar() or 0

        # Rental income: sum of driver_daily_rent from ContractTerm for sublease vehicles * 7
        rental_income_stmt = select(
            func.coalesce(func.sum(ContractTerm.driver_daily_rent), 0)
        ).select_from(ContractTerm).join(
            Vehicle, ContractTerm.vehicle_id == Vehicle.id
        ).where(sublease_base)
        daily_rental = float((await db.execute(rental_income_stmt)).scalar() or 0)
        rental_income_7d = round(daily_rental * 7, 2)

        # Sublease repair/idle/dayoff counts for smart cards
        sublease_repair_c = (await db.execute(
            select(func.count(Vehicle.id)).where(and_(sublease_base, service_statuses))
        )).scalar() or 0

        # Idle and day-off from ContractTerm
        sublease_idle_c = 0
        sublease_dayoff_c = 0
        try:
            sl_status_stmt = select(
                func.sum(case((ContractTerm.is_idle == True, 1), else_=0)),
                func.sum(case((ContractTerm.is_day_off == True, 1), else_=0)),
            ).select_from(ContractTerm).join(
                Vehicle, ContractTerm.vehicle_id == Vehicle.id
            ).where(sublease_base)
            sl_row = (await db.execute(sl_status_stmt)).one()
            sublease_idle_c = int(sl_row[0] or 0)
            sublease_dayoff_c = int(sl_row[1] or 0)
        except Exception:
            pass

        # Sublease repair list (for hover tooltip)
        sublease_repair_list = []
        try:
            sl_repair_stmt = select(
                Vehicle.license_plate, Vehicle.brand, Vehicle.model
            ).where(and_(sublease_base, service_statuses)).limit(10)
            sl_repair_rows = (await db.execute(sl_repair_stmt)).all()
            sublease_repair_list = [
                {"plate": r[0] or "—", "brand": r[1] or "", "model": r[2] or ""}
                for r in sl_repair_rows
            ]
        except Exception:
            pass

        # Sublease idle list
        sublease_idle_list = []
        try:
            sl_idle_stmt = select(
                Vehicle.license_plate, Vehicle.brand, Vehicle.model
            ).select_from(Vehicle).join(
                ContractTerm, ContractTerm.vehicle_id == Vehicle.id
            ).where(and_(
                sublease_base,
                or_(ContractTerm.is_idle == True, ContractTerm.is_day_off == True)
            )).limit(10)
            sl_idle_rows = (await db.execute(sl_idle_stmt)).all()
            sublease_idle_list = [
                {"plate": r[0] or "—", "brand": r[1] or "", "model": r[2] or ""}
                for r in sl_idle_rows
            ]
        except Exception:
            pass

        # ============================================================
        # ДОХОД ОТ ПОДКЛЮЧЕННЫХ — ДИНАМИЧЕСКИЙ % ИЗ ContractTerm
        # Никакого хардкода! Берём commission_rate из ContractTerm
        # ============================================================
        connected_base = and_(
            Vehicle.is_active_dominion == True,
            Vehicle.ownership_type.cast(String) == "CONNECTED",
        )
        if park_filter != "ALL":
            connected_base = and_(connected_base, Vehicle.park_name == park_filter)
        elif active_park_names:
            connected_base = and_(connected_base, Vehicle.park_name.in_(active_park_filter))

        # Average commission rate from ContractTerm (dynamic, not hardcoded)
        avg_comm_stmt = select(
            func.coalesce(func.avg(ContractTerm.commission_rate), 0.03)
        ).select_from(ContractTerm).join(
            Vehicle, ContractTerm.vehicle_id == Vehicle.id
        ).where(connected_base)
        connected_commission_rate = float((await db.execute(avg_comm_stmt)).scalar() or 0.03)

        # Connected income = sum_trips * connected_commission_rate (approximate)
        # More precise: per-vehicle trip revenue * per-vehicle commission_rate
        # For now: connected cars' share of total trips * their avg commission
        connected_count = (await db.execute(
            select(func.count(Vehicle.id)).where(connected_base)
        )).scalar() or 0

        if total_active > 0 and connected_count > 0:
            connected_share = connected_count / total_active
            connected_income = round(abs(sum_trips) * connected_share * connected_commission_rate, 2)
        else:
            connected_income = 0.0

        _log.info(
            f"[TRIAD] park={park_filter} | drivers_source={rt_source} online={on_line} | "
            f"vehicles_source={veh_source} total={total_active} | "
            f"sum_trips={sum_trips:.0f} revenue_park={revenue_park:.0f} payout={payout_remain:.0f} | "
            f"rental_7d={rental_income_7d:.0f} connected_income={connected_income:.0f} "
            f"connected_rate={connected_commission_rate:.3f}"
        )

        return {
            "finance": {
                "sum_trips": round(sum_trips, 2),
                "sum_gross": round(sum_gross, 2),
                "revenue_park": round(revenue_park, 2),
                "payout_remain": round(payout_remain, 2),
                "rental_income": rental_income_7d,
                "sublease_fleet_size": int(sublease_count),
                "connected_income": connected_income,
                "connected_commission_rate": connected_commission_rate,
                "weekly_dates": date_labels,
                "weekly_series": weekly_series,
                "weekly_revenue_series": [round(v, 2) for v in weekly_revenue_series],
            },
            "performers": {
                "on_line": int(on_line),
                "free": int(free_count),
                "in_order": int(in_order_count),
                "busy": int(busy_count),
                "avg_time_online": avg_time_online,
                "new_24h": int(new_24h),
                "churn": int(churn),
            },
            "assets": {
                "total_active": int(total_active),
                "park_cars": int(park_cars_c),
                "private_cars": int(private_cars_c),
                "working": int(working_c),
                "no_driver": int(no_driver_c),
                "in_service": int(in_service_c),
                "preparation": int(preparation_c),
            },
            "ops_summary": {
                "repair_count": int(repair_count),
                "warehouse_status": "В норме",
                "live_points": int(on_line),
                "idle_count": int(idle_count),
            },
            "sublease_summary": {
                "total": int(sublease_count),
                "repair_count": int(sublease_repair_c),
                "repair_list": sublease_repair_list,
                "idle_count": int(sublease_idle_c),
                "dayoff_count": int(sublease_dayoff_c),
                "idle_list": sublease_idle_list,
                "engines_on": 0,   # GPS placeholder — будет заполнено после интеграции
                "engines_off": 0,
                "low_battery": 0,
                "geofence_alerts": 0,
                "network_status": "OK",
            },
            "park": park_filter,
            "_sources": {"performers": rt_source, "vehicles": veh_source},
        }

    @classmethod
    async def get_overlay_metrics(
        cls, db: AsyncSession, now: Optional[datetime] = None,
        yandex_sync=None,
    ) -> Dict:
        now = now or datetime.now()
        last_7_days = now - timedelta(days=7)
        last_48_hours = now - timedelta(hours=48)
        today_start = datetime(now.year, now.month, now.day)

        conditions = cls._bucket_conditions()
        revenue_condition = conditions[cls.BUCKET_REVENUE]
        refund_condition = conditions[cls.BUCKET_REFUND]
        # Расходы БЕЗ выплат водителям (чистые операционные расходы)
        operational_expenses_condition = or_(
            conditions[cls.BUCKET_YANDEX_EXPENSES],
            conditions[cls.BUCKET_OUR_EXPENSES],
        )
        payout_condition = conditions[cls.BUCKET_PAYOUTS]

        # ═══════════════════════════════════════════════════════
        # FLEET OVERVIEW (is_active_dominion only)
        # ═══════════════════════════════════════════════════════
        fleet_overview = await cls.get_fleet_overview(db)
        fleet_command = await cls.get_fleet_command_data(db)

        # ═══════════════════════════════════════════════════════
        # LIVE 300: Водители с транзакциями за 48ч — ТОЛЬКО PRO
        # ═══════════════════════════════════════════════════════
        live_300_stmt = select(
            func.count(distinct(Transaction.yandex_driver_id))
        ).where(
            and_(
                Transaction.yandex_driver_id.isnot(None),
                Transaction.date >= last_48_hours,
                Transaction.park_name == "PRO",
            )
        )
        live_300 = (await db.execute(live_300_stmt)).scalar() or 0

        # ═══════════════════════════════════════════════════════
        # REALTIME: Водители онлайн/на заказе — ИЗ Yandex API
        # Тот же источник, что и Триада, для полного совпадения
        # ═══════════════════════════════════════════════════════
        drivers_on_line = 0
        drivers_free = 0
        drivers_in_order = 0
        drivers_busy = 0
        rt_source = "db"

        if yandex_sync:
            try:
                ds = await yandex_sync.get_realtime_driver_stats("PRO")
                drivers_on_line = ds.get("on_line", 0)
                drivers_free = ds.get("free", 0)
                drivers_in_order = ds.get("in_order", 0)
                drivers_busy = ds.get("busy", 0)
                rt_source = ds.get("source", "yandex_api")
            except Exception as e:
                logger.warning(f"[OVERLAY] RT drivers API error: {e}, fallback на БД")
                rt_source = "db_fallback"

        if rt_source.startswith("db"):
            # DB fallback — те же поля, что и в Триаде
            drivers_online_stmt = select(
                func.count(User.id).filter(User.realtime_status.in_(["online", "busy"])),
                func.count(User.id).filter(User.realtime_status == "online"),
                func.count(User.id).filter(User.realtime_status == "busy"),
            ).where(
                and_(
                    User.is_active == True,
                    User.yandex_driver_id.isnot(None),
                )
            )
            drivers_on_line, drivers_free, drivers_busy = (
                await db.execute(drivers_online_stmt)
            ).one()
            drivers_in_order = 0

        # ═══════════════════════════════════════════════════════
        # WAREHOUSE & SERVICE
        # ═══════════════════════════════════════════════════════
        low_stock_stmt = select(func.count(WarehouseItem.id)).where(
            WarehouseItem.quantity <= WarehouseItem.min_threshold
        )
        trips_stmt = select(func.count(TripSheet.id))

        low_stock = (await db.execute(low_stock_stmt)).scalar() or 0
        trips_total = (await db.execute(trips_stmt)).scalar() or 0
        # Ремонт — из fleet_overview (статус машин), а не из ServiceOrder
        vehicles_repair = int(fleet_overview["totals"].get("vehicles_repair", 0))

        # ═══════════════════════════════════════════════════════
        # КАЗНА: Финансы — ТОЛЬКО PRO парк
        # ═══════════════════════════════════════════════════════
        park_filter = Transaction.park_name == "PRO"

        kazna_stmt = select(
            # 0: Revenue (ABS) за 7 дней
            func.sum(
                case(
                    (and_(revenue_condition, Transaction.date >= last_7_days, park_filter),
                     func.abs(Transaction.amount)),
                    else_=0,
                )
            ),
            # 1: Refund (ABS) за 7 дней
            func.sum(
                case(
                    (and_(refund_condition, Transaction.date >= last_7_days, park_filter),
                     func.abs(Transaction.amount)),
                    else_=0,
                )
            ),
            # 2: Операционные расходы (ABS, без выплат) за 7 дней
            func.sum(
                case(
                    (and_(operational_expenses_condition, Transaction.date >= last_7_days, park_filter),
                     func.abs(Transaction.amount)),
                    else_=0,
                )
            ),
            # 3: Выплаты водителям (ABS) за 7 дней
            func.sum(
                case(
                    (and_(payout_condition, Transaction.date >= last_7_days, park_filter),
                     func.abs(Transaction.amount)),
                    else_=0,
                )
            ),
            # 4: Revenue за сегодня
            func.sum(
                case(
                    (and_(revenue_condition, Transaction.date >= today_start, park_filter),
                     func.abs(Transaction.amount)),
                    else_=0,
                )
            ),
            # 5: Refund за сегодня
            func.sum(
                case(
                    (and_(refund_condition, Transaction.date >= today_start, park_filter),
                     func.abs(Transaction.amount)),
                    else_=0,
                )
            ),
            # 6: Кол-во транзакций за 7 дней
            func.count(Transaction.id).filter(
                and_(Transaction.date >= last_7_days, park_filter)
            ),
        )

        (revenue_7d, refund_7d, expenses_7d, payouts_7d,
         revenue_today, refund_today, transactions_7d) = (
            await db.execute(kazna_stmt)
        ).one()

        revenue_7d = float(revenue_7d or 0)
        refund_7d = float(refund_7d or 0)
        expenses_7d = float(expenses_7d or 0)
        payouts_7d = float(payouts_7d or 0)
        revenue_today = float(revenue_today or 0)
        refund_today = float(refund_today or 0)
        transactions_7d = int(transactions_7d or 0)

        revenue_7d_adjusted = revenue_7d - refund_7d
        revenue_today_adjusted = revenue_today - refund_today
        # P&L = Доход - Операционные расходы (БЕЗ выплат водителям)
        kazna_profit_7d = revenue_7d_adjusted - expenses_7d

        # ═══════════════════════════════════════════════════════
        # ДОХОД ПАРКА: Комиссия партнёра за заказ (реальный доход)
        # ═══════════════════════════════════════════════════════
        park_commission_stmt = select(
            func.coalesce(func.sum(Transaction.amount), 0)
        ).where(
            and_(
                Transaction.category == "Комиссия партнёра за заказ",
                Transaction.date >= last_7_days,
                park_filter,
            )
        )
        park_commission_7d = abs(float(
            (await db.execute(park_commission_stmt)).scalar() or 0
        ))

        # ═══════════════════════════════════════════════════════
        # ГРЯЗНЫЙ ОБОРОТ: Сумма всех платежей за поездки (с наличными)
        # ═══════════════════════════════════════════════════════
        _gross_ride_cats = [
            "Оплата картой", "Наличные", "Корпоративная оплата",
            "Оплата через терминал", "Оплата электронным кошельком",
            "Оплата промокодом", "Компенсация скидки по промокоду",
            "Компенсация оплаты поездки", "Компенсация за увеличенное время в пути",
            "Оплата картой проезда по платной дороге",
            "Оплата картой, поездка партнёра", "Наличные, поездка партнёра",
        ]
        gross_stmt = select(
            func.coalesce(func.sum(Transaction.amount), 0)
        ).where(
            and_(
                Transaction.category.in_(_gross_ride_cats),
                Transaction.date >= last_7_days,
                park_filter,
            )
        )
        gross_revenue_7d = float((await db.execute(gross_stmt)).scalar() or 0)

        has_kazna_data = transactions_7d > 0 or revenue_7d > 0 or expenses_7d > 0
        has_fleet_data = (fleet_overview["totals"]["vehicles_total"] > 0) or live_300 > 0

        return {
            "vehicles_total": int(fleet_overview["totals"]["vehicles_total"]),
            "vehicles_working": int(fleet_overview["totals"]["vehicles_working"]),
            "vehicles_repair": vehicles_repair,
            "drivers_active": int(live_300 or 0),
            "drivers_online": int(drivers_on_line or 0),
            "drivers_free": int(drivers_free or 0),
            "drivers_in_order": int(drivers_in_order or 0),
            "drivers_busy": int(drivers_busy or 0),
            "live_300": int(live_300 or 0),
            "fleet_parks": fleet_overview["parks"],
            "fleet_totals": fleet_overview["totals"],
            "fleet_archived_drivers": fleet_overview["archived_drivers"],
            "golden_top": fleet_command["golden_top"],
            "revenue_7d": revenue_7d_adjusted,
            "revenue_gross_7d": revenue_7d,
            "gross_revenue_7d": gross_revenue_7d,
            "park_commission_7d": park_commission_7d,
            "refund_7d": refund_7d,
            "expenses_7d": expenses_7d,
            "payouts_7d": payouts_7d,
            "kazna_profit_7d": kazna_profit_7d,
            "revenue_today": revenue_today_adjusted,
            "revenue_gross_today": revenue_today,
            "refund_today": refund_today,
            "transactions_7d": transactions_7d,
            "low_stock": int(low_stock or 0),
            "service_in_progress": vehicles_repair,
            "trips_total": int(trips_total or 0),
            "has_kazna_data": has_kazna_data,
            "has_fleet_data": has_fleet_data,
            "timestamp": now.isoformat(),
        }

    @classmethod
    async def _get_contract_terms(cls, db: AsyncSession, vehicle: Vehicle, driver: Optional[User]) -> Dict:
        if not vehicle:
            return {}
        park = (vehicle.park_name or "PRO").upper()
        term_stmt = select(ContractTerm).where(
            ContractTerm.vehicle_id == vehicle.id
        ).order_by(ContractTerm.updated_at.desc())
        term = (await db.execute(term_stmt)).scalar_one_or_none()
        if not term and driver:
            driver_stmt = select(ContractTerm).where(
                ContractTerm.driver_id == driver.id
            ).order_by(ContractTerm.updated_at.desc())
            term = (await db.execute(driver_stmt)).scalar_one_or_none()
        if not term:
            default_stmt = select(ContractTerm).where(
                and_(ContractTerm.is_default == True, ContractTerm.park_name == park)
            )
            term = (await db.execute(default_stmt)).scalar_one_or_none()
        if not term:
            return {
                "partner_daily_rent": 0.0,
                "driver_daily_rent": float(getattr(driver, "daily_rent", 0.0) or 0.0),
                "commission_rate": float(getattr(vehicle, "commission_rate", 0.03) or 0.03),
                "day_off_rate": 0.0,
                "is_repair": False,
                "is_day_off": False,
                "is_idle": False,
            }
        return {
            "partner_daily_rent": float(term.partner_daily_rent or 0.0),
            "driver_daily_rent": float(term.driver_daily_rent or 0.0),
            "commission_rate": float(term.commission_rate or 0.0),
            "day_off_rate": float(term.day_off_rate or 0.0),
            "is_repair": bool(term.is_repair),
            "is_day_off": bool(term.is_day_off),
            "is_idle": bool(term.is_idle),
        }

    @classmethod
    async def calculate_smart_deduction(
        cls, db: AsyncSession, vehicle_id: int, on_date: Optional[datetime] = None
    ) -> Dict:
        """
        Умное списание: учитывает статусы и активность.
        - IN_REPAIR: водитель не платит, партнер получает по договору.
        - DAY_OFF: водитель платит 0 или льготную ставку.
        - DEFAULT: полное списание субаренды при наличии активности.
        """
        vehicle = await db.get(Vehicle, vehicle_id)
        if not vehicle:
            return {"status": "error", "message": "vehicle_not_found"}
        driver = await db.get(User, vehicle.current_driver_id) if vehicle.current_driver_id else None
        terms = await cls._get_contract_terms(db, vehicle, driver)
        now = on_date or datetime.now()
        date_start = datetime(now.year, now.month, now.day)
        date_end = date_start + timedelta(days=1)
        plate = (vehicle.license_plate or "").upper()
        activity_filter = [
            Transaction.date >= date_start,
            Transaction.date < date_end,
        ]
        if driver and driver.yandex_driver_id:
            activity_filter.append(Transaction.yandex_driver_id == driver.yandex_driver_id)
        elif plate:
            activity_filter.append(Transaction.description.ilike(f"%{plate}%"))
        activity_stmt = select(func.count(Transaction.id)).where(and_(*activity_filter))
        activity_count = (await db.execute(activity_stmt)).scalar() or 0
        has_activity = activity_count > 0

        partner_charge = terms["partner_daily_rent"]
        driver_charge = 0.0
        reason = "no_activity"

        if terms["is_repair"]:
            driver_charge = 0.0
            reason = "repair"
        elif terms["is_day_off"]:
            driver_charge = terms["day_off_rate"]
            reason = "day_off"
        elif terms["is_idle"]:
            driver_charge = 0.0
            reason = "idle"
        else:
            if has_activity:
                driver_charge = terms["driver_daily_rent"]
                reason = "active"

        return {
            "status": "ok",
            "vehicle_id": vehicle_id,
            "driver_id": driver.id if driver else None,
            "park_name": vehicle.park_name,
            "driver_charge": float(driver_charge),
            "partner_charge": float(partner_charge),
            "commission_rate": float(terms["commission_rate"]),
            "has_activity": has_activity,
            "reason": reason,
            "timestamp": now.isoformat(),
        }


class TensionRadar:
    """
    РАДАР НАПРЯЖЕННОСТИ: Анализ финансового давления на водителей.
    """

    @staticmethod
    async def get_avg_income_7days(db: AsyncSession, driver_id: int) -> float:
        """Считает реальный средний грязный доход водителя за неделю"""
        seven_days_ago = datetime.now() - timedelta(days=7)
        stmt = select(func.avg(Transaction.raw_amount)).where(
            Transaction.tx_type == "income",
            Transaction.date >= seven_days_ago
        )
        result = await db.execute(stmt)
        return float(result.scalar() or 0.0)

    @staticmethod
    async def calculate_daily_tension(db: AsyncSession):
        """
        ГЛАВНЫЙ ЦИКЛ: Расчет индекса для всех воинов с долгами.
        """
        try:
            stmt = select(FineInstallment).where(
                FineInstallment.status == 'active',
                FineInstallment.is_frozen == False
            )
            result = await db.execute(stmt)
            installments = result.scalars().all()

            results_summary = []

            for item in installments:
                avg_income = await TensionRadar.get_avg_income_7days(db, item.driver_id)
                daily_pay = float(item.daily_deduction_default)
                if avg_income > 0:
                    tension = (daily_pay / avg_income) * 100
                else:
                    tension = 100.0

                risk_level = "LOW"
                if tension > 60:
                    risk_level = "CRITICAL"
                elif tension > 40:
                    risk_level = "HIGH"
                elif tension > 25:
                    risk_level = "MEDIUM"

                history = DriverTensionHistory(
                    driver_id=item.driver_id,
                    tension_index=round(tension, 2),
                )
                db.add(history)

                results_summary.append({
                    "driver_id": item.driver_id,
                    "index": round(tension, 2),
                    "risk": risk_level
                })

            await db.commit()
            return results_summary
        except Exception:
            await db.rollback()
            return []


tension_radar = TensionRadar()
