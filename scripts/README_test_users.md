# Тестовые аккаунты руководителей S-GLOBAL DOMINION

## Запуск

```bash
cd /home/armsp/dominion
python scripts/create_test_users.py
```

> Скрипт идемпотентен: повторный запуск не создаёт дубликаты — выводит «уже существует, пропускаем».

---

## Аккаунты

| Имя | Логин | Пароль | Роль (DominionRole) | UserRole в БД |
|-----|-------|--------|---------------------|---------------|
| Афунц Алик | `afunts` | `Afunts2025!` | `DEPUTY` | `director` |
| Волков Михаил | `volkov` | `Volkov2025!` | `FINANCE_SECURITY` | `director` |
| Геворгян Левон | `gevorgyan` | `Gevorgyan2025!` | `FLEET_CHIEF` | `director` |
| Логист С-ГЛОБАЛ | `logist` | `Logist2025!` | `LOGIST` | `manager` |

---

## Permissions по ролям

### DEPUTY (Афунц Алик — Заместитель руководителя)
- `fleet:read`, `fleet:write` — полное управление флотом
- `finance:read`, `finance:write` — полный доступ к казне
- `security:read` — протоколы безопасности
- `gps:read` — GPS-телематика
- `hr:read`, `hr:write` — управление кадрами
- `partner:read` — партнёрские отчёты
- `tclub:ops` — операции T-CLUB24

### FINANCE_SECURITY (Волков Михаил — Финансовая безопасность)
- `finance:read`, `finance:write` — полный доступ к казне
- `security:read` — протоколы безопасности
- `hr:read` — просмотр кадровых данных
- `partner:read` — партнёрские отчёты

### FLEET_CHIEF (Геворгян Левон — Начальник флота)
- `fleet:read`, `fleet:write` — полное управление флотом
- `gps:read` — GPS-телематика
- `hr:read`, `hr:write` — управление водителями
- `finance:read` — просмотр финансов

### LOGIST (Логист С-ГЛОБАЛ — ВкусВилл EXPRESS)
- `logistics:read`, `logistics:write` — модуль LG: рейсы ВкусВилл, маршруты, тарифы
- `miks:read` — доступ к MIKS-чату и AI-советнику Mix (специализированный промпт)
- `hr:read` — просмотр ЗП водителей (Азат, Группа Бнян)
- Парк: `EXPRESS` | Алгоритм 50/50: маржа ООО С-ГЛОБАЛ / ИП Мкртчян

---

## Тумблеры доступа в БД

| Поле | afunts | volkov | gevorgyan | logist |
|------|--------|--------|-----------|--------|
| `can_see_treasury` | ✅ | ✅ | ✅ | ❌ |
| `can_see_fleet` | ✅ | ❌ | ✅ | ❌ |
| `can_see_analytics` | ✅ | ✅ | ✅ | ❌ |
| `can_see_logistics` | ✅ | ✅ | ✅ | ✅ |
| `can_see_hr` | ✅ | ✅ | ✅ | ✅ |
| `can_edit_users` | ❌ | ❌ | ❌ | ❌ |

---

## Важно

> ⚠️ **Пароли временные** — попросите руководителей сменить при первом входе.

> 🔐 **`can_edit_users = False`** для всех — редактирование пользователей доступно только `MASTER`.

> 📌 **Архитектурная заметка**: В таблице `users` поле `role` хранит `UserRole` enum (`director`).  
> `DominionRole` (из `app/core/permissions.py`) — это RBAC-слой, применяемый в middleware и эндпоинтах.  
> Маппинг: `DEPUTY` / `FLEET_CHIEF` / `FINANCE_SECURITY` → `UserRole.DIRECTOR` в БД.
