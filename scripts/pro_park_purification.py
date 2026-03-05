#!/usr/bin/env python3
"""
PRO-PARK PURIFICATION — THE GOLDEN STANDARD EXECUTION
Сброс сомнительных связей, глубокая синхронизация PRO, заполнение brand/model, валидация статусов.
Запуск: cd /root/dominion && PYTHONPATH=. python scripts/pro_park_purification.py
"""
import asyncio
import logging
import sys
from pathlib import Path

# Корень проекта в path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ID парка PRO из .env (для справки; в БД используем park_name)
PRO_PARK_ID_YANDEX = "056666aa12d34dd0a37a7a48a6b5a9f5"


async def reset_non_pro_bindings():
    """Сброс привязок для машин не из парка PRO: current_driver_id=NULL, is_active_dominion=False."""
    from app.database import AsyncSessionLocal
    from app.models.all_models import Vehicle, User
    from sqlalchemy import select, update, and_

    async with AsyncSessionLocal() as session:
        # Машины не PRO (учёт park_name)
        stmt = select(Vehicle.id, Vehicle.park_name, Vehicle.license_plate).where(
            Vehicle.park_name.isnot(None)
        )
        rows = (await session.execute(stmt)).all()
        non_pro = [r for r in rows if (r[1] or "PRO").upper() != "PRO"]
        non_pro_ids = [r[0] for r in non_pro]

        if not non_pro_ids:
            logger.info("Reset bindings: нет машин вне парка PRO, пропуск.")
            return 0

        # Снять водителей с этих машин
        await session.execute(
            update(Vehicle)
            .where(Vehicle.id.in_(non_pro_ids))
            .values(
                current_driver_id=None,
                yandex_driver_id=None,
                is_free=True,
                is_active_dominion=False,
            )
        )
        # Обнулить current_vehicle_id у пользователей, привязанных к этим машинам
        await session.execute(
            update(User).where(User.current_vehicle_id.in_(non_pro_ids)).values(current_vehicle_id=None)
        )
        await session.commit()
        logger.info("Reset bindings: сброшено %d машин не-PRO (current_driver_id=NULL, is_active_dominion=False)", len(non_pro_ids))
        return len(non_pro_ids)


async def deep_sync_pro():
    """Полный цикл sync_all_parks(); GO/PLUS/EXPRESS без ключей пропускаются."""
    from app.services.yandex_sync_service import yandex_sync

    logger.info("Deep Sync: запуск sync_all_parks() (только PRO с ключами)...")
    result = await yandex_sync.sync_all_parks()
    logger.info("Deep Sync: завершён. drivers=%s vehicles=%s deep_pull=%s live_300=%s",
                result.get("drivers"), result.get("vehicles"), result.get("deep_pull"), result.get("live_300"))
    return result


async def force_brand_model_pro():
    """Для каждой машины PRO принудительно fetch_vehicle_v2; при пустом ответе — лог."""
    from app.database import AsyncSessionLocal
    from app.models.all_models import Vehicle
    from sqlalchemy import select, and_
    from app.services.yandex_sync_service import yandex_sync

    async with AsyncSessionLocal() as session:
        stmt = select(Vehicle).where(
            and_(
                (Vehicle.park_name == "PRO") | (Vehicle.park_name.is_(None)),
                Vehicle.is_active == True,
            )
        )
        vehicles = (await session.execute(stmt)).scalars().all()

    updated = 0
    failed = 0
    for v in vehicles:
        if not v.yandex_car_id:
            continue
        try:
            data = await yandex_sync.fetch_vehicle_v2("PRO", v.yandex_car_id)
            if data:
                brand = data.get("brand")
                model = data.get("model")
                if brand and str(brand) != "None":
                    async with AsyncSessionLocal() as session:
                        v_ref = (await session.get(Vehicle, v.id))
                        if v_ref:
                            v_ref.brand = brand
                            v_ref.model = model or "—"
                            v_ref.color = data.get("color") or v_ref.color
                            v_ref.year = data.get("year") or v_ref.year
                            await session.commit()
                            updated += 1
                else:
                    logger.warning("PRO vehicle %s (%s): API вернул пустой brand/model: %s", v.license_plate, v.yandex_car_id, data)
                    failed += 1
            else:
                logger.warning("PRO vehicle %s (%s): fetch_vehicle_v2 пустой ответ", v.license_plate, v.yandex_car_id)
                failed += 1
        except Exception as e:
            logger.warning("PRO vehicle %s: %s", v.license_plate, e)
            failed += 1

    logger.info("Brand/Model fix: обновлено %d, без марки/модели или ошибка %d", updated, failed)
    return {"updated": updated, "failed": failed}


async def validate_pilot_status():
    """Проверка: Расулова Зарина, Доманский и др. — work_status working, не fired."""
    from app.database import AsyncSessionLocal
    from app.models.all_models import User
    from sqlalchemy import select, and_, or_

    async with AsyncSessionLocal() as session:
        stmt = select(User).where(
            and_(
                User.park_name == "PRO",
                or_(
                    User.yandex_driver_id.isnot(None),
                    User.yandex_contractor_id.isnot(None),
                ),
            )
        )
        users = (await session.execute(stmt)).scalars().all()

    working = []
    not_working = []
    for u in users:
        name = (u.full_name or "").lower()
        status = (getattr(u, "work_status", None) or "").lower()
        if "расулова" in name or "зарина" in name or "доманск" in name:
            if status == "working":
                working.append(u.full_name)
            else:
                not_working.append((u.full_name, status or "—"))
    logger.info("Расулова/Доманский check: working=%s not_working=%s", working, not_working)
    return {"working": working, "not_working": not_working}


async def final_report():
    """Итоговая таблица: активные в PRO, связанные водители, машины с именами (не None)."""
    from app.database import AsyncSessionLocal
    from app.models.all_models import Vehicle, User
    from sqlalchemy import select, and_, or_, func

    async with AsyncSessionLocal() as session:
        # Активные в PRO (водители с park_name=PRO, не архив)
        stmt_active = select(func.count(User.id)).where(
            and_(
                User.park_name == "PRO",
                User.is_archived == False,
                or_(User.yandex_driver_id.isnot(None), User.yandex_contractor_id.isnot(None)),
            )
        )
        active_count = (await session.execute(stmt_active)).scalar() or 0

        # Связано водителей (есть current_vehicle_id и машина PRO)
        stmt_linked = select(func.count(User.id)).where(
            and_(
                User.current_vehicle_id.isnot(None),
                User.park_name == "PRO",
            )
        )
        linked_count = (await session.execute(stmt_linked)).scalar() or 0

        # Машин PRO с заполненным brand (не None и не пусто)
        stmt_vehicles = select(func.count(Vehicle.id)).where(
            and_(
                (Vehicle.park_name == "PRO") | (Vehicle.park_name.is_(None)),
                Vehicle.is_active == True,
                Vehicle.brand.isnot(None),
                Vehicle.brand != "",
                Vehicle.brand != "None",
            )
        )
        vehicles_with_names = (await session.execute(stmt_vehicles)).scalar() or 0

        # Всего машин PRO (активных)
        stmt_total_pro = select(func.count(Vehicle.id)).where(
            and_(
                (Vehicle.park_name == "PRO") | (Vehicle.park_name.is_(None)),
                Vehicle.is_active == True,
            )
        )
        total_pro_vehicles = (await session.execute(stmt_total_pro)).scalar() or 0

    return {
        "active_in_pro": active_count,
        "linked_drivers": linked_count,
        "vehicles_with_names": vehicles_with_names,
        "total_pro_vehicles": total_pro_vehicles,
    }


async def main():
    print("\n" + "=" * 60)
    print("PRO-PARK PURIFICATION — THE GOLDEN STANDARD EXECUTION")
    print("=" * 60)

    # 1. Reset bindings
    n_reset = await reset_non_pro_bindings()

    # 2. Deep Sync
    sync_result = await deep_sync_pro()

    # 3. Brand/Model fix для PRO
    brand_result = await force_brand_model_pro()

    # 4. Валидация статусов пилотов
    pilot_status = await validate_pilot_status()

    # 5. Отчёт
    report = await final_report()

    print("\n" + "-" * 60)
    print("ОТЧЁТ О ЧИСТОТЕ (PRO)")
    print("-" * 60)
    print(f"Всего активных машин PRO:        {report['total_pro_vehicles']}")
    print(f"Всего активных водителей в PRO:  {report['active_in_pro']}")
    print(f"Связано водителей (есть авто):   {report['linked_drivers']}")
    print(f"Машин с именами (brand не None): {report['vehicles_with_names']}")
    print("-" * 60)
    print("Расулова Зарина / Доманский: working =", pilot_status["working"])
    if pilot_status["not_working"]:
        print("  not_working =", pilot_status["not_working"])
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
