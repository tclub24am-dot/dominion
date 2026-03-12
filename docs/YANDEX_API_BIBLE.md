# 📖 БИБЛИЯ Yandex Fleet API — S-GLOBAL DOMINION

> **Протокол:** VERSHINA v200.11 | **Обновлено:** 2026-02-15  
> **Базовый URL:** `https://fleet-api.taxi.yandex.net`  
> **Официальная дока:** https://fleet.yandex.ru/docs/api/ru/

---

## ⚡ БЫСТРЫЙ ПОИСК

| Задача | Раздел |
|--------|--------|
| Авторизация / заголовки | [§1](#1-авторизация) |
| Получить список машин | [§2.1](#21-список-автомобилей) |
| Получить одну машину | [§2.2](#22-получение-одного-автомобиля) |
| Парковая или подключённая? | [§2.3](#23-определение-типа-владения) |
| Список водителей | [§3.1](#31-список-водителей) |
| driver_profile_id vs contractor_profile_id | [§3.2](#32-два-типа-id-водителя) |
| Привязка водитель↔авто | [§3.3](#33-привязка-водитель--авто) |
| Условия работы (work rules) | [§4](#4-driverworkrules-условия-работы) |
| Список заказов | [§5.1](#51-список-заказов) |
| Трек заказа (GPS) | [§5.2](#52-трек-заказа) |
| Транзакции по парку | [§6.1](#61-транзакции-по-парку-v2) |
| Транзакции по водителю | [§6.2](#62-транзакции-по-водителю-v2) |
| Транзакции по заказам | [§6.3](#63-транзакции-по-заказам-v2) |
| Категории транзакций | [§6.4](#64-категории-транзакций-v2) |
| Создать транзакцию (выплата) | [§6.5](#65-создание-транзакции-v3) |
| Статус транзакции | [§6.6](#66-статус-транзакции-v3) |
| Все 84 категории | [§7](#7-полный-справочник-категорий-транзакций) |
| Финансовые формулы | [§8](#8-финансовая-архитектура) |
| Частые ошибки / ловушки | [§9](#9-известные-проблемы-и-ловушки) |
| Rate Limits | [§10](#10-rate-limits) |
| Мультипарковость | [§11](#11-мультипарковость-в-dominion) |

---

## 1. Авторизация

**Все запросы** требуют 3 заголовка:

```
X-Client-ID: <client_id>
X-Api-Key: <api_key>
Accept-Language: ru        ← ОБЯЗАТЕЛЬНО! Иначе категории на английском
```

### Конфигурация в `.env`

| Парк | Переменные |
|------|------------|
| **PRO** (основной) | `PRO_YANDEX_PARK_ID`, `PRO_YANDEX_CLIENT_ID`, `PRO_YANDEX_API_KEY` |
| GO | `GO_YANDEX_PARK_ID`, `GO_YANDEX_CLIENT_ID`, `GO_YANDEX_API_KEY` |
| PLUS | `PLUS_YANDEX_PARK_ID`, `PLUS_YANDEX_CLIENT_ID`, `PLUS_YANDEX_API_KEY` |
| EXPRESS | `EXPRESS_YANDEX_PARK_ID`, `EXPRESS_YANDEX_CLIENT_ID`, `EXPRESS_YANDEX_API_KEY` |

> Парки без полного набора переменных пропускаются при синхронизации.

---

## 2. Cars (Автомобили)

### 2.1 Список автомобилей

```
POST /v1/parks/cars/list
```

```json
{
  "query": { "park": { "id": "<park_id>" } },
  "fields": {
    "vehicle": ["id", "number", "vin", "status", "callsign", "brand", "model", "color", "year", "registration_cert", "rental"]
  },
  "limit": 500,
  "offset": 0
}
```

| Поле | Описание |
|------|----------|
| `id` | ID автомобиля (уникален **только в рамках парка!**) |
| `number` | Госномер |
| `vin` | VIN-код |
| `status` | `working` / `not_working` |
| `rental` | **Boolean** — `true` = парковый (SUBLEASE), `false` = подключённый (CONNECTED) |

> ⚠️ **Пагинация:** max 500 за раз → цикл с `offset += len(cars)`.  
> ⚠️ `car_id` уникален **только в рамках одного парка!**

### 2.2 Получение одного автомобиля

```
GET /v2/parks/vehicles/car?vehicle_id=<car_id>
```

Используется в Deep Pull V2 для проверки привязки.

### 2.3 Определение типа владения

API может вернуть **дубликаты** одной машины с противоречивым `rental`:

> **Правило Dominion:** если хотя бы одна запись имеет `rental: true`, автомобиль = **SUBLEASE** (парковый).

#### ❌ Несуществующие поля (вызывают 400):
- `car.ownership_type`
- `car.rent_type`

Тип владения определяется **только** через `/v1/parks/cars/list` → поле `rental`.

---

## 3. ContractorProfiles (Водители)

### 3.1 Список водителей

```
POST /v1/parks/driver-profiles/list
```

```json
{
  "query": { "park": { "id": "<park_id>" } },
  "fields": {
    "driver_profile": ["id", "first_name", "last_name", "middle_name", "park_id", "work_status", "phones"],
    "account": ["balance"],
    "car": ["id", "number", "vin", "status", "brand", "model"],
    "current_status": ["status"],
    "park": ["id"]
  },
  "limit": 100,
  "offset": 0
}
```

| Путь | Описание |
|------|----------|
| `driver_profile.id` | **driver_profile_id** — основной ID |
| `contractor_profile_id` | Альтернативный ID (для V3 API) |
| `driver_profile.work_status` | `working` / `not_working` / `fired` / `blocked` |
| `driver_profile.phones` | Массив: `["+79001234567"]` или `[{"phone": "+79001234567"}]` |
| `accounts[0].balance` | Баланс (строка или число) |
| `car.id` | ID привязанного авто (в контексте **данного** парка) |

> **Пагинация:** `limit` max 1000 (рекомендуется 100, иначе 504 timeout). Поле `total` — общее число.

### 3.2 Два типа ID водителя

| ID | Где используется | Хранение в Dominion |
|----|-----------------|---------------------|
| `driver_profile_id` | Транзакции V2, Заказы V1 | `User.yandex_driver_id` |
| `contractor_profile_id` | Транзакции V3 (создание) | `User.yandex_contractor_id` |

> ⚠️ Они могут **не совпадать**! Для JOIN с транзакциями используем `yandex_driver_id`.

### 3.3 Привязка водитель ↔ авто

```
PUT  /v1/parks/driver-profiles/car-bindings   — привязать
DELETE /v1/parks/driver-profiles/car-bindings  — отвязать
```

В Dominion привязка ищет машину по паре `(park_name, yandex_car_id)` — **никогда** только по `car_id`.

---

## 4. DriverWorkRules (Условия работы)

```
GET /v1/parks/driver-work-rules?park_id=<park_id>
```

```json
{
  "rules": [
    { "id": "06640a...", "is_enabled": true, "name": "Штатный" },
    { "id": "...", "is_enabled": true, "name": "Аренда" },
    { "id": "...", "is_enabled": true, "name": "Подключение" }
  ]
}
```

Используется для классификации водителей и расчёта комиссий.

---

## 5. Orders (Заказы)

### 5.1 Список заказов

```
POST /v1/parks/orders/list
```

```json
{
  "query": {
    "park": {
      "id": "<park_id>",
      "order": {
        "booked_at": {
          "from": "2026-02-01T00:00:00+03:00",
          "to": "2026-02-08T00:00:00+03:00"
        },
        "statuses": ["complete"]
      }
    }
  },
  "limit": 500,
  "cursor": ""
}
```

| Поле | Описание |
|------|----------|
| `id` | ID заказа |
| `short_id` | Порядковый номер |
| `status` | `complete`, `cancelled`, `driving`, `waiting`, `transporting` |
| `price` | Стоимость (строка) — **ЭТО "Сумма по поездкам"** |
| `payment_method` | `card`, `cash`, `corp`, `cashless` |
| `category` | `econom`, `comfort`, `business`, `vip` |
| `driver_profile.id` | ID водителя |
| `car.id` | ID авто |
| `driver_work_rule.id` | ID условия работы |
| `driver_work_rule.name` | Название условия |

> ⚠️ Обязательно одно из `booked_at` или `ended_at`.  
> ⚠️ Пагинация через **cursor** (не offset). Max 500.

### 5.2 Трек заказа

```
POST /v1/parks/orders/track?park_id=<park_id>&order_id=<order_id>
```

Возвращает GPS-трек (массив точек с координатами, скоростью, статусом).

---

## 6. Transactions (Транзакции)

### 6.1 Транзакции по парку (V2)

```
POST /v2/parks/transactions/list
```

```json
{
  "query": {
    "park": {
      "id": "<park_id>",
      "transaction": {
        "event_at": {
          "from": "2026-02-01T00:00:00+03:00",
          "to": "2026-02-08T00:00:00+03:00"
        }
      }
    }
  },
  "limit": 1000,
  "cursor": ""
}
```

| Поле | Описание |
|------|----------|
| `id` | Уникальный ID транзакции |
| `event_at` | Дата/время (ISO 8601 + timezone) |
| `category_id` | Машиночитаемый ID (`card`, `cash_collected`, etc.) |
| `category_name` | Локализованное название |
| `amount` | Сумма (строка, 4 знака). `+` = поступление, `-` = списание |
| `driver_profile_id` | ID водителя |
| `order_id` | ID заказа (может быть null) |
| `description` | Описание |
| `created_by.identity` | `platform` / `dispatcher` / `fleet-api` / `tech-support` |

> **Пагинация:** `limit` max 1000, `cursor` пустой = конец. ~3500-4800 транзакций/день в PRO.

### 6.2 Транзакции по водителю (V2)

```
POST /v2/parks/driver-profiles/transactions/list
```

Аналогично 6.1 + фильтр `driver_profile.id`.

### 6.3 Транзакции по заказам (V2)

```
POST /v2/parks/orders/transactions/list
```

Фильтр `order.ids` — массив до 100 ID заказов.

### 6.4 Категории транзакций (V2)

```
POST /v2/parks/transactions/categories/list
```

```json
{ "query": { "park": { "id": "<park_id>" } } }
```

Возвращает **все 84 категории**: `id`, `name`, `group_id`, `is_enabled`, `is_creatable`, `is_affecting_driver_balance`.

### 6.5 Создание транзакции (V3)

```
POST /v3/parks/driver-profiles/transactions
```

**Доп. заголовок:**
```
X-Idempotency-Token: <уникальный_токен_16-64_символа>
```

```json
{
  "park_id": "<park_id>",
  "contractor_profile_id": "<contractor_profile_id>",
  "amount": "-1500.0000",
  "description": "Моментальная выплата",
  "version": 1,
  "condition": { "balance_min": "0.0000" },
  "data": {
    "kind": "payout",
    "fee_amount": "0.0000",
    "rule": { "fee_percent": "0.0" }
  }
}
```

**11 типов (`data.kind`):**

| Kind | Описание |
|------|----------|
| `other` | Прочее |
| `rent` | Аренда |
| `deposit` | Депозит |
| `payout` | **Выплата** |
| `insurance` | Страховка |
| `fine` | Штраф |
| `damage` | Повреждения |
| `fuel` | Топливо |
| `referal` | Реферальная программа |
| `topup` | Пополнение |
| `bonus` | Бонус |

> ⚠️ Используется **`contractor_profile_id`**, НЕ `driver_profile_id`!  
> `amount` отрицательное = списание с баланса.  
> `version` — инкремент для обновления существующей транзакции.

### 6.6 Статус транзакции (V3)

```
GET /v3/parks/driver-profiles/transactions/status?park_id=<park_id>&contractor_profile_id=<id>&id=<tx_id>&version=1
```

Статусы: `in_progress`, `success`, `fail`.

---

## 7. Полный справочник категорий транзакций

### Группы

| group_id | Название | Влияет на баланс |
|----------|----------|:---------------:|
| `cash_collected` | Наличные | ❌ (водитель уже получил) |
| `platform_card` | Оплата картой | ✅ |
| `platform_corporate` | Корпоративная оплата | ✅ |
| `platform_promotion` | Промоакции | ✅ |
| `platform_bonus` | Бонусы | ✅ |
| `platform_tip` | Чаевые | ✅ |
| `platform_fees` | Комиссии платформы | ✅ |
| `partner_fees` | Комиссии партнёра | ✅ |
| `partner_other` | Прочие платежи партнёра | ✅ |
| `platform_other` | Прочие платежи платформы | ✅ |
| `partner_rides` | Платежи по поездкам партнёра | ✅ |

### cash_collected

| category_id | category_name |
|-------------|---------------|
| `cash_collected` | Наличные |
| `partner_ride_cash_collected` | Наличные, поездка партнёра |

### platform_card

| category_id | category_name |
|-------------|---------------|
| `card` | Оплата картой |
| `terminal_payment` | Оплата через терминал |
| `ewallet_payment` | Оплата электронным кошельком |
| `card_toll_road` | Оплата картой проезда по платной дороге |
| `platform_other_smena` | Оплата услуг: Смена |
| `compensation` | Компенсация оплаты поездки |

### platform_corporate

| category_id | category_name |
|-------------|---------------|
| `corporate` | Корпоративная оплата |
| `corporate_fee` | Скидка партнёра |

### platform_tip

| category_id | category_name |
|-------------|---------------|
| `tip` | Чаевые |

### platform_promotion

| category_id | category_name |
|-------------|---------------|
| `promotion_promocode` | Оплата промокодом |
| `promotion_discount` | Компенсация скидки по промокоду |
| `fix_price_compensation` | Компенсация за увеличенное время в пути |

### platform_bonus

| category_id | category_name |
|-------------|---------------|
| `bonus` | Бонус |
| `bonus_discount` | Бонус — скидка на комиссию |
| `commission_discount_bonus_points` | Цель: скидка на комиссию |
| `platform_bonus_fee` | Корректировка бонуса |

### platform_fees (Комиссии платформы)

| category_id | category_name |
|-------------|---------------|
| `platform_ride_fee` | Комиссия сервиса за заказ |
| `platform_ride_vat` | Комиссия сервиса, НДС |
| `platform_reposition_fee` | Режимы перемещения (Мой Район / По Делам) |
| `platform_freemode_fee` | Режим «Гибкий» |
| `platform_special_mode_fee` | Комиссия в режиме «Специальный» |
| `platform_additional_fee` | Дополнительная комиссия сервиса |
| `platform_courier_wo_box_fee` | Комиссия за отсутствие термокороба |
| `platform_service_fee` | Сервисный сбор (за счёт пользователя) |
| `platform_mandatory_fee` | Обязательный сбор (за счёт пассажира) |
| `platform_callcenter_fee` | Сбор за заказ по телефону |

### partner_fees (Комиссии партнёра/парка)

| category_id | category_name |
|-------------|---------------|
| `partner_subscription_fee` | Комиссия партнёра за смену |
| `partner_ride_fee` | Комиссия партнёра за заказ |
| `partner_bonus_fee` | Комиссия партнёра за бонус |

### platform_other

| category_id | category_name |
|-------------|---------------|
| `bank_payment` | Выплата в банк |
| `subscription` | Смена |
| `subscription_vat` | Смена, НДС |
| `platform_other_gas` | Заправки |
| `platform_other_gas_cashback` | Заправки (кешбэк) |
| `platform_other_gas_tip` | Заправки (чаевые) |
| `platform_other_gas_fleet_fee` | Заправки (комиссия) |
| `platform_other_carwash` | Мойки |
| `paid_parking` | Оплата парковки |
| `airport_charge_fix` | Аэропортовый сбор |
| `platform_other_rent_childseat` | Аренда кресла |
| `platform_other_rent_childseat_vat` | Аренда кресел, НДС |
| `platform_other_referral` | Сервисная реферальная программа |
| `platform_other_promotion` | Выплата по акции |
| `platform_other_scout` | Выплаты скаутам |
| `platform_fine` | Корректировка сервиса |
| `platform_selfemployed_tax` | Удержание в счёт уплаты налогов |
| `partner_fee_sales_tax` | Налог с продаж |
| `platform_security_deposit` | Адванс |
| `platform_loan_repayment_partial` | Адванс Про |
| `platform_store_purchase` | Покупки |
| `insurance_osago` | Оплата полиса ОСАГО |
| `osago_daily_compensation` | Компенсация ОСАГО |
| `platform_airport_charge` | Подача в аэропорту |

### partner_other (Платежи партнёра)

| category_id | category_name |
|-------------|---------------|
| `partner_service_recurrent_payment` | Условия работы, Списания |
| `partner_service_recurring_payment_cancellation` | Периодические списания, отмена долга |
| `partner_service_recurring_payment` | Платежи по расписанию |
| `partner_service_other` | Прочие платежи партнёра |
| `partner_service_financial_statement` | Финансовая ведомость через банк |
| `partner_service_manual` | Ручные списания |
| `partner_service_external_event_other` | Переводы. Иное |
| `partner_service_external_event_rent` | Переводы. Аренда |
| `partner_service_external_event_deposit` | Переводы. Депозит |
| `partner_service_external_event_payout` | Переводы. Вывод средств |
| `partner_service_external_event_insurance` | Переводы. Страховка |
| `partner_service_external_event_fine` | Переводы. Штраф |
| `partner_service_external_event_damage` | Переводы. Повреждения |
| `partner_service_external_event_fuel` | Переводы. Топливо |
| `partner_service_external_event_referal` | Переводы. Реферальная программа |
| `partner_service_external_event_topup` | Переводы. Пополнение |
| `partner_service_external_event_bonus` | Переводы. Бонус |
| `partner_service_external_event_balance_transfer` | Объединение балансов |
| `partner_service_transfer` | Перевод |
| `partner_service_transfer_commission` | Комиссия за перевод |
| `partner_service_balance_transfer` | Перевод баланса |
| `partner_service_traffic_fines` | Оплата штрафа |
| `partner_service_payment_systems` | Пополнение через платёжную систему |
| `partner_service_payment_systems_fee` | Комиссия пополнения |
| `cargo_cash_collection` | Списание в счёт заказа |
| `cargo_cash_collection_delivery_fee` | Списание доставки в счёт заказа |
| `cargo_cash_collection_overdraft` | Пополнение в счёт заказов |
| `parther_other_referral` | Партнёрская реферальная программа |

### partner_rides

| category_id | category_name |
|-------------|---------------|
| `partner_ride_card` | Оплата картой, поездка партнёра |

---

## 8. Финансовая архитектура

### 8.1 «Сумма по поездкам» (Dashboard)

**= NET сумма БЕЗНАЛИЧНЫХ транзакций через Яндекс. НАЛИЧНЫЕ НЕ ВКЛЮЧЕНЫ.**

```
Сумма по поездкам = NET(card + corporate + terminal_payment + ewallet_payment
                       + promotion_promocode + promotion_discount
                       + compensation + fix_price_compensation
                       + card_toll_road)
```

> Точность ~0.2% относительно Dashboard. `SUM(order.price)` даёт завышенный результат.

### 8.2 «Доход таксопарка»

```
Доход таксопарка = ABS(SUM(amount)) WHERE category_id = 'partner_ride_fee'
```

В транзакциях `partner_ride_fee` всегда **отрицательная** (списание с водителя → доход парка).

### 8.3 «Остаток к выплате»

```
Остаток к выплате = SUM(balance) WHERE balance > 0 AND work_status = 'working'
```

Источник: `/v1/parks/driver-profiles/list` → `accounts[0].balance`.

### 8.4 Маппинг категорий в Dominion

| category_id (Яндекс) | category (Dominion) |
|----------------------|---------------------|
| `card` | `Yandex_Оплата картой` |
| `cash_collected` | `Наличные` (fallback по name) |
| `corporate` | `Корпоративная оплата` (fallback по name) |
| `platform_ride_fee` | `Yandex_Комиссия сервиса за заказ` |
| `platform_selfemployed_tax` | `Yandex_Удержание в счёт уплаты налого` |
| `compensation` | `Yandex_Компенсация оплаты поездки` |
| `bonus` | `Yandex_Бонус` |
| `partner_service_manual` | `Yandex_Ручные списания` |
| `tip` | `Yandex_Чаевые` |
| *Остальные* | `category_name` as-is |

---

## 9. Известные проблемы и ловушки

### 9.1 Дубликаты машин с разным `rental`

**Проблема:** Одна машина возвращается дважды — `rental: true` и `rental: false`.  
**Решение:** Приоритет `rental: true` → SUBLEASE.

### 9.2 driver_profile_id ≠ contractor_profile_id

**Решение:** `User.yandex_driver_id` = `driver_profile_id` (приоритет для транзакций V2). `User.yandex_contractor_id` = `contractor_profile_id` (для V3).

### 9.3 Accept-Language → категории на английском

**Решение:** **ВСЕГДА** `Accept-Language: ru`. Английские категории в БД — мусор, удалять.

### 9.4 Фантомные транзакции `driver_balance`

Записи с `category = 'driver_balance' AND yandex_tx_id IS NULL` — артефакты. Удалять.

### 9.5 Sync Window (48 часов)

Стандартное окно: `window_minutes = 2880`. Для исторических данных — разовый deep sync с бо́льшим окном.

### 9.6 Triad и множественные парки

Dashboard Яндекс показывает один парк, Triad может суммировать все. Фильтровать по `park_name`.

### 9.7 car_id уникален ТОЛЬКО в рамках парка

Маппинг всегда `(park_name, car_id) → vehicle`. Никогда только `car_id`.

---

## 10. Rate Limits

| Параметр | Значение |
|----------|----------|
| Rate limit | 429 Too Many Requests |
| Задержка между батчами | `asyncio.sleep(0.2-0.3)` |
| Batch size: водители | 100 |
| Batch size: автомобили | 500 |
| Batch size: транзакции | 1000 |
| Параллельность | Семафор 3-5 |

**При 429:** ждать 1-2 сек → повторить → экспоненциальный backoff.

---

## 11. Мультипарковость в Dominion

### Принцип

- Каждый парк имеет свой набор ключей (`PARK_ID`, `CLIENT_ID`, `API_KEY`).
- `car_id` уникален **только в рамках парка** → маппинг `(park_name, car_id)`.
- Водитель привязывается к машине **только своего парка**.

### Порядок подключения парков

1. Настроить один парк (PRO) → проверить привязки
2. Добавить следующий (GO) → перезапуск → синхронизация
3. Проверить → следующий парк (PLUS, EXPRESS)

### В коде (`yandex_sync_service.py`)

- Маппинг: `vehicle_by_park_yandex[(park_key, str(car_id))]`
- Привязка: `bind_driver_to_car` передаёт `user.park_name`
- Фильтр: `work_status: ["working"]` в `_apply_driver_filters`

---

## 12. Ссылки на документацию Яндекс

| Раздел | URL |
|--------|-----|
| Главная | https://fleet.yandex.ru/docs/api/ru/ |
| Авторизация | https://fleet.yandex.ru/docs/api/ru/authorization |
| Cars | https://fleet.yandex.ru/docs/api/ru/openapi/Cars/ |
| ContractorProfiles | https://fleet.yandex.ru/docs/api/ru/openapi/ContractorProfiles/ |
| DriverWorkRules | https://fleet.yandex.ru/docs/api/ru/openapi/DriverWorkRules/v1parksdriver-work-rules-get |
| Orders | https://fleet.yandex.ru/docs/api/ru/openapi/Orders/v1parksorderslist-post |
| Transactions V2 | https://fleet.yandex.ru/docs/api/ru/openapi/Transactions/v2parkstransactionslist-post |
| Transactions V3 Create | https://fleet.yandex.ru/docs/api/ru/openapi/Transactions/v3parksdriver-profilestransactions-post |
| Transaction Categories | https://fleet.yandex.ru/docs/api/ru/openapi/Transactions/v2parkstransactionscategorieslist-post |

---

> **📖 Библия Yandex Fleet API — S-GLOBAL DOMINION — VERSHINA v200.11**
