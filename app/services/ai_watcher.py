# -*- coding: utf-8 -*-
# app/services/ai_watcher.py

import asyncio
from datetime import datetime
from sqlalchemy import select, func, and_

from app.database import AsyncSessionLocal
from app.models.all_models import Transaction, Vehicle, WarehouseItem, ServiceOrder, ChatMessage, OracleArchive
from app.core.modules import get_enabled_modules
from app.services.oracle_service import oracle_service
from app.api.v1.messenger import messenger_manager


async def _build_report():
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day)

    async with AsyncSessionLocal() as session:
        revenue_today = (
            await session.execute(
                select(func.sum(Transaction.amount)).where(
                    and_(
                        Transaction.category_type == "REVENUE",
                        Transaction.date >= today_start
                    )
                )
            )
        ).scalar() or 0
        expenses_today = (
            await session.execute(
                select(func.sum(Transaction.amount)).where(
                    and_(
                        Transaction.category_type == "EXPENSES",
                        Transaction.date >= today_start
                    )
                )
            )
        ).scalar() or 0
        net_today = float(revenue_today) - abs(float(expenses_today))

        accidents = (
            await session.execute(
                select(func.count(Vehicle.id)).where(
                    Vehicle.status.in_(["accident", "dtp", "ДТП"])
                )
            )
        ).scalar() or 0

        service_in_progress = (
            await session.execute(
                select(func.count(ServiceOrder.id)).where(ServiceOrder.status == "in_progress")
            )
        ).scalar() or 0

        low_stock = (
            await session.execute(
                select(func.count(WarehouseItem.id)).where(
                    WarehouseItem.quantity <= WarehouseItem.min_threshold
                )
            )
        ).scalar() or 0

    anomalies = []
    if net_today < 0:
        anomalies.append(f"Казна: отрицательный баланс за сегодня ({net_today:,.0f}₽)")
    if accidents >= 10:
        anomalies.append(f"Флот: ДТП >= 10 (сейчас {accidents})")
    if service_in_progress >= 10:
        anomalies.append(f"Автосервис: в работе {service_in_progress} заказов")
    if low_stock > 0:
        anomalies.append(f"Склад: дефицит позиций {low_stock}")

    return anomalies, {
        "net_today": net_today,
        "accidents": accidents,
        "service_in_progress": service_in_progress,
        "low_stock": low_stock
    }


async def ai_watcher_loop():
    while True:
        try:
            enabled_modules = set(get_enabled_modules())
            if "messenger" not in enabled_modules:
                await asyncio.sleep(900)
                continue

            anomalies, metrics = await _build_report()
            if anomalies:
                base_text = "🛰️ Имперский мониторинг (каждые 15 минут)\n" + "\n".join(
                    f"- {item}" for item in anomalies
                )

                final_text = base_text
                if oracle_service.is_live:
                    prompt = (
                        "Сделай короткий отчет для Мастера по аномалиям:\n"
                        f"{base_text}\n"
                        f"Метрики: {metrics}"
                    )
                    try:
                        ai_response = await oracle_service.send_message(message=prompt, group="MASTER")
                        final_text = ai_response.get("message") if isinstance(ai_response, dict) else str(ai_response)
                    except Exception:
                        final_text = base_text

                async with AsyncSessionLocal() as session:
                    archive = OracleArchive(
                        title="AI Watcher",
                        channel="MASTER",
                        content=final_text,
                        severity="warning" if anomalies else "info",
                        meta=metrics
                    )
                    session.add(archive)
                    msg = ChatMessage(
                        role="assistant",
                        content=final_text,
                        group_name="MASTER",
                        user_id=None
                    )
                    session.add(msg)
                    await session.commit()
                    await session.refresh(msg)

                await messenger_manager.broadcast("MASTER", {
                    "type": "message",
                    "message": {
                        "id": msg.id,
                        "role": msg.role,
                        "content": msg.content,
                        "channel": "MASTER",
                        "created_at": msg.created_at.isoformat() if msg.created_at else None
                    }
                })
        except Exception:
            pass

        await asyncio.sleep(900)
