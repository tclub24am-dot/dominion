# -*- coding: utf-8 -*-
# scripts/create_test_users.py
# ═══════════════════════════════════════════════════════════════════════════════
# S-GLOBAL DOMINION — Создание тестовых аккаунтов руководителей
# Протокол VERSHINA v200.11
# ═══════════════════════════════════════════════════════════════════════════════
#
# Запуск:
#   cd /home/armsp/dominion
#   python scripts/create_test_users.py
#
# ═══════════════════════════════════════════════════════════════════════════════

import asyncio
import sys
import os

# Добавляем корень проекта в sys.path для корректного импорта app.*
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.database import SessionLocal
from app.models.all_models import User, UserRole
from app.services.auth import hash_password

# ───────────────────────────────────────────────────────────────────────────────
# РЕЕСТР РУКОВОДИТЕЛЕЙ S-GLOBAL DOMINION
# Роли в БД (UserRole): DIRECTOR — для заместителей и начальников флота
# DominionRole (RBAC): хранится в permissions.py, применяется в middleware
# ───────────────────────────────────────────────────────────────────────────────

TEST_USERS = [
    {
        # Афунц Алик Арменович — Заместитель руководителя
        # DominionRole: DEPUTY → permissions: fleet:rw, finance:rw, hr:rw, gps:r, partner:r, tclub:ops
        "username": "afunts",
        "full_name": "Афунц Алик",
        "password": "Afunts2025!",
        "role": UserRole.DIRECTOR,          # UserRole для поля User.role в БД
        "dominion_role": "deputy",          # DominionRole для RBAC (информационно)
        "dominion_role_label": "DEPUTY",
        "park_name": "PRO",
        "tenant_id": "s-global",
        "can_see_treasury": True,           # Доступ к финансам (казна)
        "can_see_fleet": True,              # Доступ к флоту
        "can_see_analytics": True,          # Доступ к аналитике
        "can_see_logistics": True,          # Доступ к логистике
        "can_see_hr": True,                 # Доступ к HR
        "can_edit_users": False,            # Редактирование пользователей — только MASTER
    },
    {
        # Волков Михаил Юрьевич — Финансовая безопасность
        # DominionRole: FINANCE_SECURITY → permissions: finance:rw, security:r, hr:r, partner:r
        "username": "volkov",
        "full_name": "Волков Михаил",
        "password": "Volkov2025!",
        "role": UserRole.DIRECTOR,          # UserRole для поля User.role в БД
        "dominion_role": "finance_security",
        "dominion_role_label": "FINANCE_SECURITY",
        "park_name": "PRO",
        "tenant_id": "s-global",
        "can_see_treasury": True,           # Финансовая безопасность — полный доступ к казне
        "can_see_fleet": False,             # Флот — не в зоне ответственности
        "can_see_analytics": True,          # Аналитика — нужна для аудита
        "can_see_logistics": True,          # Логистика — доступ для контроля
        "can_see_hr": True,                 # HR — доступ для финансового аудита
        "can_edit_users": False,
    },
    {
        # Геворгян Левон Гагикович — Начальник флота
        # DominionRole: FLEET_CHIEF → permissions: fleet:rw, gps:r, hr:rw, finance:r
        "username": "gevorgyan",
        "full_name": "Геворгян Левон",
        "password": "Gevorgyan2025!",
        "role": UserRole.DIRECTOR,          # UserRole для поля User.role в БД
        "dominion_role": "fleet_chief",
        "dominion_role_label": "FLEET_CHIEF",
        "park_name": "PRO",
        "tenant_id": "s-global",
        "can_see_treasury": True,           # Доступ к финансам (для FLEET_CHIEF)
        "can_see_fleet": True,              # Основная зона ответственности
        "can_see_analytics": True,          # Аналитика флота
        "can_see_logistics": True,          # Логистика — в зоне флота
        "can_see_hr": True,                 # HR водителей — в зоне флота
        "can_edit_users": False,
    },
    {
        # Логист С-ГЛОБАЛ — ВкусВилл EXPRESS
        # DominionRole: LOGIST → permissions: logistics:rw, miks:r, hr:r
        # Алгоритм 50/50: маржа рейсов делится между ООО С-ГЛОБАЛ и ИП Мкртчян
        # Водители: Азат (Mercedes Atego), Группа Бнян (Шахзод/Зариф/Шавкат)
        "username": "logist",
        "full_name": "Логист С-ГЛОБАЛ",
        "password": "Logist2025!",
        "role": UserRole.MANAGER,           # UserRole для поля User.role в БД
        "dominion_role": "logist",
        "dominion_role_label": "LOGIST",
        "park_name": "EXPRESS",
        "tenant_id": "s-global",
        "can_see_treasury": False,          # Казна — не в зоне ответственности
        "can_see_fleet": False,             # Флот — не в зоне ответственности
        "can_see_analytics": False,         # Аналитика — не нужна
        "can_see_logistics": True,          # Основная зона: модуль LG (ВкусВилл)
        "can_see_hr": True,                 # HR — просмотр ЗП водителей
        "can_edit_users": False,
    },
]


# ───────────────────────────────────────────────────────────────────────────────
# ОСНОВНАЯ ФУНКЦИЯ СОЗДАНИЯ ПОЛЬЗОВАТЕЛЕЙ
# ───────────────────────────────────────────────────────────────────────────────

async def create_test_users():
    """
    Создаёт тестовые аккаунты руководителей S-GLOBAL DOMINION.
    Идемпотентна: повторный запуск не дублирует записи.
    """
    print("\n" + "═" * 65)
    print("  ⚜  S-GLOBAL DOMINION — Инициализация аккаунтов руководителей")
    print("═" * 65)

    created_count = 0
    skipped_count = 0
    results = []

    async with SessionLocal() as session:
        for user_data in TEST_USERS:
            username = user_data["username"]

            # ── Проверка существования ──────────────────────────────────────
            result = await session.execute(
                select(User.id).where(User.username == username)
            )
            existing = result.scalar_one_or_none()

            if existing:
                print(f"  ⏭  Пропускаем: {user_data['full_name']} ({username}) — уже существует (id={existing})")
                skipped_count += 1
                results.append({
                    "status": "skipped",
                    "full_name": user_data["full_name"],
                    "username": username,
                    "password": user_data["password"],
                    "dominion_role": user_data["dominion_role_label"],
                })
                continue

            # ── Создание нового пользователя ────────────────────────────────
            try:
                new_user = User(
                    username=username,
                    hashed_password=hash_password(user_data["password"]),
                    full_name=user_data["full_name"],
                    role=user_data["role"],
                    tenant_id=user_data["tenant_id"],
                    park_name=user_data["park_name"],
                    is_active=True,
                    is_archived=False,
                    # Тумблеры доступа
                    can_see_treasury=user_data["can_see_treasury"],
                    can_see_fleet=user_data["can_see_fleet"],
                    can_see_analytics=user_data["can_see_analytics"],
                    can_see_logistics=user_data["can_see_logistics"],
                    can_see_hr=user_data["can_see_hr"],
                    can_edit_users=user_data["can_edit_users"],
                )
                session.add(new_user)
                await session.flush()  # Получаем id без коммита

                print(
                    f"  ✅ Создан: {user_data['full_name']} ({username})"
                    f" — роль: {user_data['dominion_role_label']}"
                    f" [id={new_user.id}]"
                )
                created_count += 1
                results.append({
                    "status": "created",
                    "full_name": user_data["full_name"],
                    "username": username,
                    "password": user_data["password"],
                    "dominion_role": user_data["dominion_role_label"],
                })

            except Exception as e:
                await session.rollback()
                print(f"  ❌ ОШИБКА при создании {username}: {e}")
                results.append({
                    "status": "error",
                    "full_name": user_data["full_name"],
                    "username": username,
                    "password": user_data["password"],
                    "dominion_role": user_data["dominion_role_label"],
                })
                continue

        # ── Финальный коммит всех созданных пользователей ───────────────────
        try:
            await session.commit()
        except Exception as e:
            await session.rollback()
            print(f"\n  ❌ КРИТИЧЕСКАЯ ОШИБКА при коммите: {e}")
            return

    # ── Итоговая таблица ─────────────────────────────────────────────────────
    print("\n" + "═" * 65)
    print("  📋 ИТОГОВАЯ ТАБЛИЦА АККАУНТОВ РУКОВОДИТЕЛЕЙ")
    print("═" * 65)
    print(f"  {'Имя':<22} {'Логин':<14} {'Пароль':<18} {'Роль':<20} {'Статус'}")
    print("  " + "─" * 63)

    for r in results:
        status_icon = "✅" if r["status"] == "created" else ("⏭" if r["status"] == "skipped" else "❌")
        print(
            f"  {r['full_name']:<22} {r['username']:<14} {r['password']:<18}"
            f" {r['dominion_role']:<20} {status_icon}"
        )

    print("═" * 65)
    print(f"\n  Итого: создано — {created_count}, пропущено — {skipped_count}")
    print("\n  ⚠️  ВАЖНО: Пароли временные!")
    print("  Попросите руководителей сменить пароль при первом входе.\n")


# ───────────────────────────────────────────────────────────────────────────────
# ТОЧКА ВХОДА
# ───────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    asyncio.run(create_test_users())
