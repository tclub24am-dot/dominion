# ОТЧЁТ ОБ АУДИТЕ S-GLOBAL DOMINION (VERSHINA v200.16)

**Статус:** ⚠️ ТРЕБУЮТСЯ КРИТИЧЕСКИЕ ИСПРАВЛЕНИЯ (ТЕНАНТЫ)
**Дата:** 2026-03-13
**Аудитор:** Roo (Oracle Agent)

---

## 1. АУДИТ ТЕНАНТОВ (ИЗОЛЯЦИЯ ДАННЫХ)
**Оценка:** 🔴 КРИТИЧЕСКИ (ВЫЯВЛЕНЫ УТЕЧКИ)

Выявлены массовые нарушения протокола Hard Isolation. Многие эндпоинты выполняют запросы к БД без фильтрации по `tenant_id`, что позволяет пользователю одного тенанта видеть или изменять данные другого.

### Зоны риска:
- **`app/api/v1/fleet.py`**:
  - `get_active_vehicles` (line 491): `select(Vehicle)` без фильтра.
  - `get_vehicles_table` (line 831): `select(Vehicle)` без фильтра.
  - `get_vehicles_list_json` (line 983): `select(Vehicle, User)` без фильтра.
  - `update_vehicle_status`, `get_contract_terms`, `update_contract_terms`: запросы по ID без проверки тенанта.
  - `lookup_vehicle`, `lookup_driver`: глобальный поиск по VIN/Plate/Phone.
- **`app/api/v1/kazna.py`**:
  - `get_transactions` (line 136): `select(Transaction, User)` без фильтра.
  - `get_recent_transactions` (line 236): `select(Transaction)` без фильтра.
  - `get_transactions_filtered` (line 321): `select(Transaction)` без фильтра.
  - `export_transactions` (line 435): `select(Transaction)` без фильтра.

**Рекомендация:** Внедрить обязательный `where(Model.tenant_id == tenant_id)` во все запросы, используя `request.state.tenant_id`.

---

## 2. ТЕХНИЧЕСКАЯ ДИАГНОСТИКА (ПРОИЗВОДИТЕЛЬНОСТЬ)
**Оценка:** ✅ ИСПРАВЛЕНО

- **SQLAlchemy Pool:** Пул был занижен (5 соединений). Оптимизирован до `pool_size=50`, `max_overflow=20` для работы под высокой нагрузкой на 128GB RAM.
- **Блокирующие вызовы:** В `oracle_service.py` и `miks.py` используется `httpx.AsyncClient`, что исключает блокировку event loop.
- **Миграции:** Исправлен краш в `app/create_db.py` (дублирование индекса `ix_call_logs_timestamp`).

---

## 3. ИНФРАСТРУКТУРА (128GB RAM TUNING)
**Оценка:** ✅ ОПТИМИЗИРОВАНО

- **PostgreSQL:** Настроены `shared_buffers=32GB` и `effective_cache_size=96GB` в `docker-compose.yml`.
- **Asterisk:** Увеличен лимит памяти до 2GB.
- **Redis:** Включена политика `allkeys-lru` для эффективного кэширования.

---

## 4. MIKS & SECURITY (HMAC / MATRIX)
**Оценка:** ✅ СТАБИЛЬНО

- **HMAC:** Пароли Matrix генерируются детерминистически через HMAC-SHA256 от `user_id` и `SECRET_KEY`, что исключает их хранение в открытом виде.
- **Telephony:** Webhook'и защищены проверкой `X-Webhook-Signature` (HMAC-SHA256).
- **Secrets:** Все чувствительные данные вынесены в `.env` и управляются через Pydantic `BaseSettings`.

---

## 5. ДИЗАЙН-КОД (IVORY LUXE)
**Оценка:** ✅ СООТВЕТСТВУЕТ

- **Эстетика:** Тема `theme-ivory` в `globals.css` использует радиальные градиенты, золотые акценты (`#8B6914`) и текстуру зернистости (Grain).
- **Компоненты:** `LoginPage.jsx`, `Dashboard.jsx` и `BottomDrawer.jsx` корректно поддерживают переключение тем и сохраняют "дорогой" вид.

---

## ИТОГОВЫЙ ПЛАН ДЕЙСТВИЙ (NEXT STEPS)
1. **СРОЧНО:** Пропатчить `fleet.py` и `kazna.py` для обеспечения изоляции тенантов.
2. **ТЕСТ:** Проверить производительность БД под нагрузкой 50+ RPS.
3. **DEPLOY:** Применить оптимизированный `docker-compose.yml` на боевом сервере.

**Вердикт:** Система готова к масштабированию после устранения утечек тенантов.
