# -*- coding: utf-8 -*-
"""
S-GLOBAL DOMINION — M4 Mock Data Loader
========================================
Протокол: VERSHINA v200.15
Дата: 10.03.2026

Заполняет БД тестовыми рейсами за 10 марта 2026:
  - Азат (5-тонник ВкусВилл) — 2 рейса (Даркстор + Магазин)
  - 3 Газели (партнёрские) — по 1 рейсу каждая

Запуск:
  docker exec -e PYTHONPATH=/app dominion_app python /app/scripts/load_m4_march_10.py

Юридическое лицо: ИП Мкртчян (IT Service Fee — 50% логистической маржи)
"""

import asyncio
import sys
import os
from datetime import datetime, date

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import AsyncSessionLocal
from app.models.all_models import Transaction


# ============================================================
# ДАННЫЕ РЕЙСОВ ЗА 10.03.2026
# ============================================================

REPORT_DATE = datetime(2026, 3, 10)

# Цены ВкусВилл (с НДС) — из config.py
VV_PRICE_DARKSTORE = 6599.0
VV_PRICE_STORE = 5883.0
VV_PRICE_SHMEL = 3882.0

# Расходы
DRIVER_PAY_5T = 2000.0       # ЗП водителя 5-тонника за рейс
DRIVER_PAY_GAZELLE = 1500.0  # ЗП водителя газели за рейс
FUEL_5T = 2500.0             # Топливо 5-тонник за рейс
FUEL_GAZELLE = 1800.0        # Топливо газель за рейс

TRANSACTIONS = [
    # ================================================================
    # АЗАТ — 5-тонник (собственный), 2 рейса
    # ================================================================
    {
        "category": "VkusVill",
        "contractor": "Азат (5т)",
        "description": "Рейс #1 — Даркстор (ВкусВилл)",
        "plate_info": "А001АА777",
        "amount": VV_PRICE_DARKSTORE,
        "tx_type": "income",
        "responsibility": "park",
    },
    {
        "category": "VkusVill",
        "contractor": "Азат (5т)",
        "description": "Рейс #2 — Магазин (ВкусВилл)",
        "plate_info": "А001АА777",
        "amount": VV_PRICE_STORE,
        "tx_type": "income",
        "responsibility": "park",
    },
    # Расходы Азата
    {
        "category": "Salary",
        "contractor": "Азат (5т)",
        "description": "ЗП водителя — 2 рейса",
        "plate_info": "А001АА777",
        "amount": -(DRIVER_PAY_5T * 2),
        "tx_type": "expense",
        "responsibility": "park",
    },
    {
        "category": "Fuel",
        "contractor": "Азат (5т)",
        "description": "Топливо — 2 рейса",
        "plate_info": "А001АА777",
        "amount": -(FUEL_5T * 2),
        "tx_type": "expense",
        "responsibility": "park",
    },

    # ================================================================
    # ГАЗЕЛЬ #1 — Партнёрская (Шмель)
    # ================================================================
    {
        "category": "VkusVill",
        "contractor": "Газель-1 (партнёр)",
        "description": "Рейс — Шмель (ВкусВилл)",
        "plate_info": "В002ВВ750",
        "amount": VV_PRICE_SHMEL,
        "tx_type": "income",
        "responsibility": "park",
    },
    {
        "category": "Salary",
        "contractor": "Газель-1 (партнёр)",
        "description": "ЗП водителя газели",
        "plate_info": "В002ВВ750",
        "amount": -DRIVER_PAY_GAZELLE,
        "tx_type": "expense",
        "responsibility": "park",
    },
    {
        "category": "Fuel",
        "contractor": "Газель-1 (партнёр)",
        "description": "Топливо газели",
        "plate_info": "В002ВВ750",
        "amount": -FUEL_GAZELLE,
        "tx_type": "expense",
        "responsibility": "park",
    },

    # ================================================================
    # ГАЗЕЛЬ #2 — Партнёрская (Шмель)
    # ================================================================
    {
        "category": "VkusVill",
        "contractor": "Газель-2 (партнёр)",
        "description": "Рейс — Шмель (ВкусВилл)",
        "plate_info": "С003СС750",
        "amount": VV_PRICE_SHMEL,
        "tx_type": "income",
        "responsibility": "park",
    },
    {
        "category": "Salary",
        "contractor": "Газель-2 (партнёр)",
        "description": "ЗП водителя газели",
        "plate_info": "С003СС750",
        "amount": -DRIVER_PAY_GAZELLE,
        "tx_type": "expense",
        "responsibility": "park",
    },
    {
        "category": "Fuel",
        "contractor": "Газель-2 (партнёр)",
        "description": "Топливо газели",
        "plate_info": "С003СС750",
        "amount": -FUEL_GAZELLE,
        "tx_type": "expense",
        "responsibility": "park",
    },

    # ================================================================
    # ГАЗЕЛЬ #3 — Партнёрская (Даркстор)
    # ================================================================
    {
        "category": "VkusVill",
        "contractor": "Газель-3 (партнёр)",
        "description": "Рейс — Даркстор (ВкусВилл)",
        "plate_info": "Е004ЕЕ750",
        "amount": VV_PRICE_DARKSTORE,
        "tx_type": "income",
        "responsibility": "park",
    },
    {
        "category": "Salary",
        "contractor": "Газель-3 (партнёр)",
        "description": "ЗП водителя газели",
        "plate_info": "Е004ЕЕ750",
        "amount": -DRIVER_PAY_GAZELLE,
        "tx_type": "expense",
        "responsibility": "park",
    },
    {
        "category": "Fuel",
        "contractor": "Газель-3 (партнёр)",
        "description": "Топливо газели",
        "plate_info": "Е004ЕЕ750",
        "amount": -FUEL_GAZELLE,
        "tx_type": "expense",
        "responsibility": "park",
    },
]


async def load_mock_data():
    """Загружает тестовые транзакции за 10.03.2026 в БД."""
    
    print("=" * 60)
    print("  S-GLOBAL DOMINION — M4 Mock Data Loader")
    print("  Дата отчёта: 10.03.2026")
    print("  Юр. лицо: ИП Мкртчян (IT Service Fee)")
    print("=" * 60)
    
    async with AsyncSessionLocal() as session:
        # Проверяем, нет ли уже данных за эту дату (идемпотентность)
        from sqlalchemy import select, func
        
        existing = await session.execute(
            select(func.count(Transaction.id)).where(
                Transaction.category.in_(["VkusVill", "Salary", "Fuel"]),
                Transaction.date >= datetime(2026, 3, 10, 0, 0, 0),
                Transaction.date < datetime(2026, 3, 11, 0, 0, 0),
                Transaction.description.like("%ВкусВилл%") | Transaction.description.like("%рейс%"),
            )
        )
        count = existing.scalar()
        
        if count and count > 0:
            print(f"\n⚠️  Найдено {count} транзакций за 10.03.2026. Пропускаем загрузку (идемпотентность).")
            print("   Для перезагрузки — удалите старые записи вручную.")
            return
        
        # Загружаем транзакции
        total_income = 0.0
        total_expense = 0.0
        
        for i, tx_data in enumerate(TRANSACTIONS, 1):
            tx = Transaction(
                tenant_id="s-global",
                park_name="LOGISTICS",
                category=tx_data["category"],
                category_type="REVENUE" if tx_data["tx_type"] == "income" else "EXPENSES",
                contractor=tx_data["contractor"],
                description=tx_data["description"],
                plate_info=tx_data["plate_info"],
                amount=tx_data["amount"],
                tx_type=tx_data["tx_type"],
                date=REPORT_DATE,
                responsibility=tx_data["responsibility"],
            )
            session.add(tx)
            
            if tx_data["amount"] > 0:
                total_income += tx_data["amount"]
            else:
                total_expense += abs(tx_data["amount"])
            
            print(f"  [{i:02d}] {tx_data['contractor']:25s} | {tx_data['description']:35s} | {tx_data['amount']:>+10,.0f} ₽")
        
        await session.commit()
        
        # Итоги
        margin = total_income - total_expense
        it_service_fee = max(0, margin * 0.5)  # 50% маржи → ИП Мкртчян
        ooo_share = max(0, margin * 0.5)       # 50% маржи → ООО С-ГЛОБАЛ
        
        print("\n" + "=" * 60)
        print("  📊 ИТОГИ ЗА 10.03.2026:")
        print(f"  💰 Доход (ВкусВилл):        {total_income:>12,.0f} ₽")
        print(f"  💸 Расходы (ЗП + Топливо):  {total_expense:>12,.0f} ₽")
        print(f"  📈 Маржа:                   {margin:>12,.0f} ₽")
        print("-" * 60)
        print(f"  🏛️  ИП Мкртчян (50%):       {it_service_fee:>12,.0f} ₽")
        print(f"  🏢 ООО С-ГЛОБАЛ (50%):      {ooo_share:>12,.0f} ₽")
        print("=" * 60)
        print(f"\n✅ Загружено {len(TRANSACTIONS)} транзакций в БД.")
        print("   Мастер может открыть Dashboard и увидеть финансовую победу!")


if __name__ == "__main__":
    asyncio.run(load_mock_data())
