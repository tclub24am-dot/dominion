# -*- coding: utf-8 -*-
# app/services/yandex_sync_service.py
# YANDEX FLEET SYNC — Синхронизация с Яндекс.Такси API

import logging
import httpx
import json
import asyncio
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from sqlalchemy import select, update, and_, or_, delete, func, distinct
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database import AsyncSessionLocal
from app.models.all_models import Vehicle, User, Transaction, ContractTerm, UserRole, OwnershipType, FinancialLog

logger = logging.getLogger("YandexSync")

class YandexSyncService:
    """
    SYNC SERVICE для Яндекс.Такси API
    Синхронизация: автомобили, балансы, транзакции
    
    Документация: https://fleet.yandex.ru/docs/api/ru/
    """
    
    def __init__(self):
        self.base_url = "https://fleet-api.taxi.yandex.net"
        
        # API Sync Log
        self.log_file = Path("/root/dominion/storage/api_sync.log")
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # MULTI-PARK: Проверяем наличие хотя бы одного активного парка
        self.active_parks = {}
        for park_name, cfg in settings.PARKS.items():
            if all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")]):
                self.active_parks[park_name] = cfg
        
        if not self.active_parks:
            logger.warning("Yandex API: Нет активных парков. Sync disabled.")
            self.enabled = False
        else:
            logger.info(f"✓ Yandex Sync Service: {len(self.active_parks)} парков активно")
            logger.info(f"  Активные парки: {list(self.active_parks.keys())}")
            logger.info(f"  API Log: {self.log_file}")
            self.enabled = True
        
        # Fallback для совместимости со старыми методами
        first_park = next(iter(self.active_parks.values()), {}) if self.active_parks else {}
        self.park_id = first_park.get("ID")
        self.client_id = first_park.get("CLIENT_ID")
        self.api_key = first_park.get("API_KEY")
        
        # СЕМАФОР: Ограничение параллельных запросов к API Яндекса (избежание 504)
        self._api_semaphore = asyncio.Semaphore(5)
    
    def _log_api_call(self, method: str, url: str, status: int, response: Dict = None):
        """Логирование всех API вызовов для отладки"""
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                log_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "method": method,
                    "url": url,
                    "status": status,
                    "response_size": len(str(response)) if response else 0
                }
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"API log write error: {e}")
    
    def _get_headers(self) -> Dict:
        """Заголовки для Yandex Fleet API
        
        Документация: https://fleet.yandex.ru/docs/api/ru/interaction
        
        ВАЖНО (исправлено согласно документации):
        - X-Client-ID: ID клиентского приложения (обязателен)
        - X-API-Key: Секретный ключ API (обязателен, с ПРОПИСНОЙ буквой!)
        - Accept-Language: Язык ответа (по умолчанию en)
        """
        normalized_client_id = self._normalize_client_id(self.client_id or "")
        headers = {
            "X-Client-ID": normalized_client_id,
            "X-API-Key": self.api_key,  # ✅ ИСПРАВЛЕНО: была X-Api-Key, правильно X-API-Key!
            "X-Park-ID": self.park_id,
            "Accept-Language": "ru",
            "Content-Type": "application/json"
        }
        logger.debug(f"API Headers: Client-ID={normalized_client_id[:20] if normalized_client_id else 'NONE'}..., API-Key={'*'*20}")
        return headers

    def _normalize_client_id(self, client_id: str) -> str:
        """
        Автоматическое добавление префикса taxi/park/ для X-Client-ID.
        Протокол Яндекса ТРЕБУЕТ формат: taxi/park/{UUID}
        """
        if not client_id:
            return ""
        client_id = client_id.strip()
        # Если уже содержит префикс - возвращаем как есть
        if client_id.startswith("taxi/park/"):
            return client_id
        # Если это просто UUID - добавляем префикс
        return f"taxi/park/{client_id}"
    
    def _get_headers_for_park(self, park_config: Dict) -> Dict:
        client_id = self._normalize_client_id(park_config.get("CLIENT_ID") or "")
        return {
            "X-Client-ID": client_id,
            "X-API-Key": park_config.get("API_KEY"),
            "X-Park-ID": park_config.get("ID"),
            "Accept-Language": "ru",
            "Content-Type": "application/json",
        }

    async def _request_raw(self, method: str, url: str, headers: Dict, params: Dict = None, payload: Dict = None) -> Dict:
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                if method.upper() == "GET":
                    resp = await client.get(url, headers=headers, params=params)
                elif method.upper() == "PUT":
                    resp = await client.put(url, headers=headers, params=params, json=payload)
                else:
                    resp = await client.post(url, headers=headers, params=params, json=payload)
            if resp.status_code == 200:
                return resp.json()
            logger.warning("Request failed: %s %s -> %s", method, url, resp.status_code)
        except Exception as e:
            logger.error("Request error: %s", e)
        return {}

    def _normalize_tx_category(self, category_id: Optional[str], category_name: Optional[str]) -> str:
        """
        Нормализация категории транзакции.
        Стратегия: используем русское category_name от Yandex API (Accept-Language: ru).
        Для category_id которые не всегда возвращают стабильный category_name — маппим явно.
        Результат: единообразные русские названия без Yandex_ префикса.
        """
        raw_id = (category_id or "").strip()
        raw_name = (category_name or "").strip()

        # Полный маппинг category_id → стабильное русское название
        # Покрывает все 84 категории Yandex Fleet API
        category_map = {
            # === cash_collected ===
            "cash_collected": "Наличные",
            "partner_ride_cash_collected": "Наличные, поездка партнёра",
            # === platform_card ===
            "card": "Оплата картой",
            "terminal_payment": "Оплата через терминал",
            "ewallet_payment": "Оплата электронным кошельком",
            "card_toll_road": "Оплата картой проезда по платной дороге",
            "platform_other_smena": "Оплата услуг: Смена",
            "compensation": "Компенсация оплаты поездки",
            # === platform_corporate ===
            "corporate": "Корпоративная оплата",
            "corporate_fee": "Скидка партнёра",
            # === platform_tip ===
            "tip": "Чаевые",
            # === platform_promotion ===
            "promotion_promocode": "Оплата промокодом",
            "promotion_discount": "Компенсация скидки по промокоду",
            "fix_price_compensation": "Компенсация за увеличенное время в пути",
            # === platform_bonus ===
            "bonus": "Бонус",
            "bonus_discount": "Бонус — скидка на комиссию",
            "commission_discount_bonus_points": "Цель: скидка на комиссию",
            "platform_bonus_fee": "Корректировка бонуса",
            # === platform_fees ===
            "platform_ride_fee": "Комиссия сервиса за заказ",
            "platform_ride_vat": "Комиссия сервиса, НДС",
            "platform_reposition_fee": "Стоимость режимов перемещения («Мой Район» / «По Делам»)",
            "platform_freemode_fee": "Режим «Гибкий»",
            "platform_special_mode_fee": "Комиссия сервиса в режиме «Специальный»",
            "platform_additional_fee": "Дополнительная комиссия сервиса",
            "platform_courier_wo_box_fee": "Комиссия сервиса за отсутствие термокороба",
            "platform_service_fee": "Сервисный сбор",
            "platform_mandatory_fee": "Обязательный сбор",
            "platform_callcenter_fee": "Сбор за заказ по телефону",
            # === partner_fees ===
            "partner_subscription_fee": "Комиссия партнёра за смену",
            "partner_ride_fee": "Комиссия партнёра за заказ",
            "partner_bonus_fee": "Комиссия партнёра за бонус",
            # === platform_other ===
            "bank_payment": "Выплата в банк",
            "subscription": "Смена",
            "subscription_vat": "Смена, НДС",
            "platform_other_gas": "Заправки",
            "platform_other_gas_cashback": "Заправки (кешбэк)",
            "platform_other_gas_tip": "Заправки (чаевые)",
            "platform_other_gas_fleet_fee": "Заправки (комиссия)",
            "platform_other_carwash": "Мойки",
            "paid_parking": "Оплата парковки",
            "airport_charge_fix": "Аэропортовый сбор",
            "platform_other_rent_childseat": "Аренда кресла",
            "platform_other_rent_childseat_vat": "Аренда кресел, НДС",
            "platform_other_referral": "Сервисная реферальная программа",
            "platform_other_promotion": "Выплата по акции",
            "platform_other_scout": "Выплаты скаутам",
            "platform_fine": "Корректировка сервиса",
            "platform_selfemployed_tax": "Удержание в счёт уплаты налогов",
            "partner_fee_sales_tax": "Налог с продаж",
            "platform_security_deposit": "Адванс",
            "platform_loan_repayment_partial": "Адванс Про",
            "platform_store_purchase": "Покупки",
            "insurance_osago": "Оплата полиса ОСАГО для такси",
            "osago_daily_compensation": "Компенсация ОСАГО",
            "platform_airport_charge": "Подача в аэропорту",
            # === partner_other ===
            "partner_service_recurrent_payment": "Условия работы, Списания",
            "partner_service_recurring_payment_cancellation": "Периодические списания, отмена долга",
            "partner_service_recurring_payment": "Платежи по расписанию",
            "partner_service_other": "Прочие платежи партнёра",
            "partner_service_financial_statement": "Финансовая ведомость через банк",
            "partner_service_manual": "Ручные списания",
            "partner_service_external_event_other": "Партнерские переводы. Иное",
            "partner_service_external_event_rent": "Партнерские переводы. Аренда",
            "partner_service_external_event_deposit": "Партнерские переводы. Депозит",
            "partner_service_external_event_payout": "Партнерские переводы. Вывод средств",
            "partner_service_external_event_insurance": "Партнерские переводы. Страховка",
            "partner_service_external_event_fine": "Партнерские переводы. Штраф",
            "partner_service_external_event_damage": "Партнерские переводы. Повреждения",
            "partner_service_external_event_fuel": "Партнерские переводы. Топливо",
            "partner_service_external_event_referal": "Партнерские переводы. Реферальная программа",
            "partner_service_external_event_topup": "Партнерские переводы. Пополнение",
            "partner_service_external_event_bonus": "Партнерские переводы. Бонус",
            "partner_service_external_event_balance_transfer": "Объединение балансов",
            "partner_service_transfer": "Перевод",
            "partner_service_transfer_commission": "Комиссия партнёра за перевод",
            "partner_service_balance_transfer": "Перевод баланса",
            "partner_service_traffic_fines": "Оплата штрафа",
            "partner_service_payment_systems": "Пополнение через платёжную систему",
            "partner_service_payment_systems_fee": "Комиссия пополнения через платёжную систему",
            "cargo_cash_collection": "Списание в счёт заказа",
            "cargo_cash_collection_delivery_fee": "Списание доставки в счёт заказа",
            "cargo_cash_collection_overdraft": "Пополнение в счёт заказов",
            "parther_other_referral": "Партнёрская реферальная программа",
            # === partner_rides ===
            "partner_ride_card": "Оплата картой, поездка партнёра",
        }

        if raw_id in category_map:
            return category_map[raw_id]
        # Fallback: используем category_name как есть (русское от Yandex API)
        if raw_name:
            return raw_name
        if raw_id:
            return raw_id
        return "Other"

    def _find_first_vehicle_id(self, payload) -> Optional[str]:
        candidates = []
        key_hits = {"car_id", "vehicle_id", "carId", "vehicleId"}

        def walk(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k in key_hits and isinstance(v, (str, int)):
                        candidates.append(str(v))
                    if isinstance(v, (dict, list)):
                        walk(v)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(payload)
        return candidates[0] if candidates else None

    def _extract_car_meta(self, payload: Dict) -> Dict:
        def pick(obj):
            if not isinstance(obj, dict):
                return {}
            return {
                "id": obj.get("id"),
                "number": obj.get("number") or obj.get("plate") or obj.get("license_plate"),
                "vin": obj.get("vin"),
                "status": obj.get("status"),
            }

        for key in ("car", "vehicle"):
            meta = pick(payload.get(key) or {})
            if meta.get("id") or meta.get("number") or meta.get("vin"):
                return meta
        contractor = payload.get("contractor") or {}
        meta = pick(contractor.get("car") or contractor.get("vehicle") or {})
        if meta.get("id") or meta.get("number") or meta.get("vin"):
            return meta
        profile = payload.get("profile") or {}
        meta = pick(profile.get("car") or profile.get("vehicle") or {})
        if meta.get("id") or meta.get("number") or meta.get("vin"):
            return meta
        return {}

    def _log_sync_issue(self, message: str) -> None:
        try:
            log_path = Path("/root/dominion/app/logs/sync.log")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat()} {message}\n")
        except Exception:
            logger.warning("Failed to write sync.log")

    def _manual_driver_overrides(self) -> List[Dict]:
        raw = settings.MANUAL_DRIVER_OVERRIDES
        if not raw:
            return []
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return [data]
            if isinstance(data, list):
                return data
        except Exception:
            logger.warning("Failed to parse MANUAL_DRIVER_OVERRIDES")
        return []

    async def _request_list(self, method: str, url: str, headers: Dict, payload: Dict) -> Dict:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    if method.upper() == "GET":
                        resp = await client.get(url, headers=headers, params=payload)
                    else:
                        resp = await client.post(url, headers=headers, json=payload)
                
                # Обработка 429 Rate Limit
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 2))
                    logger.warning(f"429 Rate Limit, waiting {retry_after}s before retry (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_after)
                    continue
                
                if resp.status_code == 200:
                    return resp.json()
                if method.upper() == "GET" and resp.status_code in {404, 405}:
                    async with httpx.AsyncClient(timeout=20.0) as client:
                        resp = await client.post(url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        return resp.json()
                logger.warning("List request failed: %s %s -> %s", method, url, resp.status_code)
            except Exception as e:
                logger.error("List request error: %s", e)
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
        return {}

    async def _fetch_car_details_forced(self, car_id: str) -> Dict:
        """
        Принудительное получение данных по машине через car-endpoint.
        Эндпоинт: /v1/parks/vehicles/car?id={vehicle_id}
        Используем, когда VIN/СТС пустые или прочерки.
        """
        if not self.enabled or not car_id:
            return {}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = f"{self.base_url}/v1/parks/vehicles/car"
                response = await client.get(
                    url,
                    headers=self._get_headers(),
                    params={"id": car_id, "park_id": self.park_id}
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.warning(f"Forced car details error {response.status_code} for {car_id}")
                    return {}
        except Exception as e:
            logger.error(f"Forced car details fetch error: {e}")
            return {}
    
    async def get_vehicle_details(self, car_id: str) -> Dict:
        """
        ДЕТАЛЬНЫЕ ДАННЫЕ ПО МАШИНЕ (VIN, СТС, Позывной)
        API: GET /v1/parks/vehicles/{car_id}
        """
        if not self.enabled:
            return {}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = f"{self.base_url}/v1/parks/vehicles/{car_id}"
                
                response = await client.get(
                    url,
                    headers=self._get_headers(),
                    params={"park_id": self.park_id}
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.warning(f"Vehicle details API error: {response.status_code}")
                    return {}
                    
        except Exception as e:
            logger.error(f"Vehicle details fetch error: {e}")
            return {}
    
    async def fetch_vehicle_v2(self, park_name: str, car_id: str) -> Dict:
        """
        ХИРУРГИЧЕСКИЙ МАППИНГ V2: Получение машины по ID
        API: GET /v2/parks/vehicles/car?vehicle_id={car_id}
        
        Возвращает: {id, number, vin, brand, model, status, ...}
        Использует семафор для избежания 504 Timeout.
        """
        if not car_id:
            return {}
        
        cfg = self.active_parks.get(park_name.upper()) or settings.PARKS.get(park_name.upper())
        if not cfg or not all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")]):
            return {}
        
        # Используем семафор если он инициализирован
        sem = getattr(self, '_v2_semaphore', None)
        
        async def _fetch():
            try:
                url = f"{self.base_url}/v2/parks/vehicles/car"
                params = {"vehicle_id": car_id}
                headers = self._get_headers_for_park(cfg)
                
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(url, headers=headers, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        vehicle = data.get("vehicle") or data
                        # V2 API может вернуть vehicle_specifications / vehicle_licenses — нормализуем на верхний уровень
                        specs = vehicle.get("vehicle_specifications") or {}
                        licenses = vehicle.get("vehicle_licenses") or {}
                        if specs or licenses:
                            vehicle = dict(vehicle)
                            vehicle["brand"] = vehicle.get("brand") or specs.get("brand")
                            vehicle["model"] = vehicle.get("model") or specs.get("model")
                            vehicle["color"] = vehicle.get("color") or specs.get("color")
                            vehicle["year"] = vehicle.get("year") or specs.get("year")
                            vehicle["vin"] = vehicle.get("vin") or specs.get("vin")
                            vehicle["number"] = vehicle.get("number") or licenses.get("licence_plate_number")
                        logger.debug(f"V2 Vehicle {car_id}: plate={vehicle.get('number')}, vin={vehicle.get('vin')}")
                        return vehicle
                    elif resp.status_code == 404:
                        return {}  # Машина не найдена - это нормально
                    else:
                        logger.warning(f"V2 Vehicle fetch {car_id}: {resp.status_code}")
                        return {}
            except Exception as e:
                logger.warning(f"V2 Vehicle fetch error {car_id}: {e}")
                return {}
        
        if sem:
            async with sem:
                return await _fetch()
        return await _fetch()

    async def get_vehicle_by_id(self, car_id: str, park_name: str) -> Dict:
        """Алиас для fetch_vehicle_v2: парк обязателен (car_id уникален в рамках парка)."""
        return await self.fetch_vehicle_v2((park_name or "PRO").upper(), str(car_id))

    async def sync_vehicles(self) -> Dict:
        """
        Синхронизация списка автомобилей с ДЕТАЛЬНЫМИ ДАННЫМИ
        API: POST /v1/parks/cars/list (ИСПРАВЛЕННЫЙ ЭНДПОИНТ!)
        
        Согласно документации:
        https://fleet.yandex.ru/docs/api/ru/all-resources
        POST https://fleet-api.taxi.yandex.net/v1/parks/cars/list — Получение списка автомобилей
        """
        if not self.enabled:
            return {"status": "disabled", "synced": 0}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Чистим ручные записи перед синком (все без yandex_car_id)
                async with AsyncSessionLocal() as cleanup_session:
                    await cleanup_session.execute(delete(Vehicle).where(Vehicle.yandex_car_id == None))
                    await cleanup_session.commit()
                
                # ✅ ИСПРАВЛЕНО: Используем ПРАВИЛЬНЫЙ эндпоинт из документации
                url = f"{self.base_url}/v1/parks/cars/list"
                
                payload = {
                    "query": {
                        "park": {
                            "id": self.park_id
                        }
                    },
                    "limit": 1000
                }
                
                # DEBUG: логируем заголовки (без приватных данных)
                headers = self._get_headers()
                logger.info(f"🔄 Sync request: POST {url}")
                logger.debug(f"Sync headers: X-Client-ID={headers.get('X-Client-ID', 'N/A')[:20]}..., X-API-Key={'*'*10}")
                
                response = await client.post(
                    url,
                    headers=headers,
                    json=payload
                )

                # Логируем вызов в файл для отладки real-time синка
                try:
                    response_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                    self._log_api_call("POST", url, response.status_code, response_data)
                except Exception:
                    pass
                
                if response.status_code != 200:
                    error_text = response.text if response.text else "No response body"
                    logger.error(f"Yandex API error: {response.status_code} - {error_text[:200]}")
                    return {"status": "error", "code": response.status_code, "error": error_text[:100]}
                
                data = response.json()
                # ✅ ИСПРАВЛЕНО: v1 API возвращает "cars", а не "vehicles"!
                cars = data.get("cars", [])  # Правильный ключ для /v1/parks/cars/list
                
                if not cars:
                    logger.warning(f"No cars returned from API. Response keys: {list(data.keys())}")
                    logger.info(f"Full response: {data}")
                
                logger.info(f"📥 Received {len(cars)} cars from Yandex API")
                
                # Синхронизируем с БД
                synced_count = 0
                
                async with AsyncSessionLocal() as session:
                    for idx, car in enumerate(cars):
                        car_id = car.get("id")
                        license_plate = car.get("number", "").replace(" ", "")
                        
                        # Основные данные из списка
                        brand = car.get("brand") or car.get("car_brand")
                        model = car.get("model") or car.get("car_model")
                        status = car.get("status", "unknown")
                        
                        # КРИТИЧНО: Если базовых данных нет - запрашиваем ДЕТАЛИ!
                        vin = car.get("vin") or car.get("vehicle_vin") or car.get("chassis_number")
                        color = car.get("color") or car.get("car_color")
                        year = car.get("year") or car.get("car_year") or car.get("manufacture_year")
                        callsign = car.get("callsign") or car.get("call_sign")
                        sts_number = car.get("registration_cert") or car.get("sts") or car.get("cert_number")
                        
                        # VIN INTEGRITY CHECK: VIN должен быть ровно 17 символов
                        # Если пришёл короткий код — считаем что VIN неполный и перезапрашиваем
                        vin_is_valid = vin and len(str(vin).strip()) == 17
                        
                        # МАСТЕР ТРЕБУЕТ ДАННЫХ! Если пусто или VIN короткий - запрос к vehicle_details
                        if not vin_is_valid or not sts_number or not callsign:
                            logger.info(f"  🔍 Fetching details for {license_plate}...")
                            details = await self.get_vehicle_details(car_id)
                            
                            if details:
                                detail_vin = details.get("vin") or details.get("chassis_number")
                                # Предпочитаем полный 17-значный VIN из details
                                if detail_vin and len(str(detail_vin).strip()) == 17:
                                    vin = detail_vin
                                elif not vin:
                                    vin = detail_vin
                                sts_number = sts_number or details.get("registration_certificate") or details.get("sts_number")
                                callsign = callsign or details.get("callsign") or details.get("call_sign")
                                color = color or details.get("color")
                                year = year or details.get("year")
                                
                                logger.info(f"    ✓ Details fetched: VIN={vin if vin else 'EMPTY'} (len={len(vin) if vin else 0})")

                        # Если всё ещё пусто или VIN неполный — принудительный car endpoint
                        vin_still_short = not vin or vin in ['-', '—'] or len(str(vin).strip()) != 17
                        if vin_still_short or (not sts_number or sts_number in ['-', '—']):
                            forced = await self._fetch_car_details_forced(car_id)
                            if forced:
                                vehicle_info = forced.get("vehicle", forced)
                                forced_vin = vehicle_info.get("vin") or vehicle_info.get("chassis_number")
                                # Предпочитаем полный 17-значный VIN
                                if forced_vin and len(str(forced_vin).strip()) == 17:
                                    vin = forced_vin
                                elif not vin or vin in ['-', '—']:
                                    vin = forced_vin
                                sts_number = sts_number or vehicle_info.get("registration_certificate") or vehicle_info.get("sts_number")
                                callsign = callsign or vehicle_info.get("callsign") or vehicle_info.get("call_sign")
                                color = color or vehicle_info.get("color")
                                year = year or vehicle_info.get("year")
                                logger.info(f"    ✓ Forced details fetched for {license_plate}")
                        
                        # Проверяем существование
                        stmt = select(Vehicle).where(Vehicle.license_plate == license_plate)
                        result = await session.execute(stmt)
                        vehicle = result.scalar_one_or_none()
                        
                        if vehicle:
                            # Обновляем существующую (v30.1 OVERRIDE LOGIC)
                            vehicle.brand = brand
                            vehicle.model = model
                            vehicle.vin = vin or "Внешнее авто"
                            vehicle.color = color
                            vehicle.year = year
                            vehicle.callsign = callsign or "Внешнее авто"
                            vehicle.sts_number = sts_number or "Внешнее авто"
                            vehicle.yandex_car_id = car_id
                            
                            # v31.0: Сохраняем данные из Яндекс.Диспетчерской
                            vehicle.yandex_status = status  # working/not_working из API
                            vehicle.yandex_rental = car.get("rental")  # True=парковый, False=подключённый
                            vehicle.yandex_park_id = self.park_id  # ID парка (PRO, GO, PLUS, EXPRESS)
                            vehicle.yandex_last_sync_at = datetime.now()  # Время синхронизации
                            
                            # КРИТИЧНО: Проверяем приоритет статуса
                            # Если статус был изменен Мастером вручную в последние 24 часа - НЕ ПЕРЕЗАПИСЫВАЕМ!
                            time_since_update = (datetime.now() - vehicle.last_update).total_seconds() / 3600 if vehicle.last_update else 999
                            
                            if vehicle.status in ['service', 'offline', 'debt_lock'] and time_since_update < 24:
                                # Ручной статус имеет приоритет!
                                logger.info(f"  🔒 Manual status preserved: {license_plate} [{vehicle.status}]")
                            else:
                                # v35.1: Статус напрямую из Яндекс API (§2 Библии)
                                # working → working, not_working → not_working (НЕ "no_driver"!)
                                vehicle.status = status if status else "working"
                            
                            vehicle.last_update = datetime.now()
                            
                            logger.info(f"  ✓ Updated: {license_plate} | VIN:{vin if vin else 'EMPTY'} (len={len(vin) if vin else 0})")
                        else:
                            # Создаём новую (v31.0 YANDEX SYNC)
                            vehicle = Vehicle(
                                brand=brand,
                                model=model,
                                license_plate=license_plate,
                                vin=vin or "Внешнее авто",
                                color=color,
                                year=year,
                                callsign=callsign or "Внешнее авто",
                                sts_number=sts_number or "Внешнее авто",
                                yandex_car_id=car_id,
                                status=status if status else "working",
                                ownership_type="connected",
                                last_update=datetime.now(),
                                # v31.0: Поля синхронизации с Яндекс.Диспетчерской
                                yandex_status=status,
                                yandex_rental=car.get("rental"),
                                yandex_park_id=self.park_id,
                                yandex_last_sync_at=datetime.now()
                            )
                            session.add(vehicle)
                            
                            logger.info(f"  ✓ Created: {license_plate}")
                        
                        synced_count += 1
                    
                    await session.commit()
                
                logger.info(f"✓ Synced {synced_count} vehicles to database")
                
                return {
                    "status": "success",
                    "synced": synced_count,
                    "total": len(cars)
                }
                
        except Exception as e:
            logger.error(f"Vehicle sync error: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}
    
    async def get_balance_info(self) -> Dict:
        """
        Получение баланса парка (для виджета Казна)
        API: POST /v2/parks/balances/list
        Документация: https://fleet.yandex.ru/docs/api/ru/
        """
        if not self.enabled:
            return {"balance": 0, "blocked": 0}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = f"{self.base_url}/v2/parks/balances/list"
                
                payload = {
                    "query": {
                        "park": {
                            "ids": [self.park_id]  # v2 требует массив IDs
                        }
                    }
                }
                
                response = await client.post(
                    url,
                    headers=self._get_headers(),
                    json=payload
                )
                
                self._log_api_call("POST", url, response.status_code, response.json() if response.status_code == 200 else {})
                
                if response.status_code == 200:
                    data = response.json()
                    parks = data.get("parks", [])
                    
                    if parks:
                        park_data = parks[0]
                        balance = park_data.get("balance", 0)
                        
                        logger.info(f"💰 Balance: {balance}₽")
                        
                        return {
                            "balance": float(balance),
                            "blocked": 0,
                            "available": float(balance)
                        }
                else:
                    logger.warning(f"Balance API error: {response.status_code} - {response.text[:200]}")
                    return {"balance": 0, "blocked": 0, "available": 0}
                    
        except Exception as e:
            logger.error(f"Balance fetch error: {e}")
            return {"balance": 0, "blocked": 0, "available": 0}
    
    async def sync_transactions(self, from_date: datetime, to_date: datetime = None) -> Dict:
        """
        Синхронизация транзакций (THE TRUTH LAYER)
        API: POST /v2/parks/transactions/list
        Документация: https://fleet.yandex.ru/docs/api/ru/
        
        Категории:
        - payment: доход
        - refund: корректировки
        - fines: штрафы ГИБДД
        - gas_station: заправки
        - service_fee: комиссия Яндекса
        """
        if not self.enabled:
            return {"status": "disabled", "synced": 0}
        
        if to_date is None:
            to_date = datetime.now()
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"{self.base_url}/v2/parks/transactions/list"
                
                # v2 API требует другую структуру
                payload = {
                    "query": {
                        "park": {
                            "id": self.park_id,
                            "transaction": {
                                "event_at": {
                                    "from": from_date.strftime("%Y-%m-%dT00:00:00+03:00"),
                                    "to": to_date.strftime("%Y-%m-%dT23:59:59+03:00")
                                }
                            }
                        }
                    },
                    "limit": 1000
                }
                
                response = await client.post(
                    url,
                    headers=self._get_headers(),
                    json=payload
                )
                
                # Логируем API вызов
                data = response.json() if response.status_code == 200 else {}
                self._log_api_call("POST", url, response.status_code, data)
                
                if response.status_code != 200:
                    logger.error(f"Transactions API error: {response.status_code}")
                    logger.error(f"Response: {response.text[:500]}")
                    return {"status": "error", "code": response.status_code}
                
                transactions = data.get("transactions", [])
                
                logger.info(f"📥 Yandex API: Received {len(transactions)} transactions")
                
                # РЕАЛЬНАЯ ЗАПИСЬ В БД (v22.1)
                synced_count = 0
                skipped_count = 0
                
                async with AsyncSessionLocal() as session:
                    for tx in transactions:
                        try:
                            # Извлекаем данные
                            tx_id = tx.get("id", "")
                            category_id = tx.get("category_id") or tx.get("category")
                            category_name = tx.get("category_name") or tx.get("category_title")
                            amount = float(tx.get("amount", 0))
                            description = tx.get("description", "")
                            
                            # Парсим дату (v30.1 CRITICAL DATE FIX)
                            event_at_str = tx.get("event_at", "")
                            if event_at_str:
                                try:
                                    # Формат: 2026-01-27T10:30:00+00:00 или 2026-01-27T10:30:00Z
                                    # КРИТИЧНО: проверяем разумность даты
                                    event_at = datetime.fromisoformat(event_at_str.replace("Z", "+00:00"))
                                    
                                    # Защита от будущих дат (максимум +1 день от сегодня)
                                    today = datetime.now()
                                    if event_at.date() > (today + timedelta(days=1)).date():
                                        logger.warning(f"⚠ Future date detected: {event_at_str}, skipping transaction")
                                        continue
                                    
                                    # Защита от древних дат (минимум 2025 год)
                                    if event_at.year < 2025:
                                        logger.warning(f"⚠ Ancient date detected: {event_at_str}, skipping")
                                        continue
                                    
                                    # Конвертируем в московское время, затем делаем naive для БД
                                    from zoneinfo import ZoneInfo
                                    moscow_tz = ZoneInfo("Europe/Moscow")
                                    event_at_moscow = event_at.astimezone(moscow_tz)
                                    # Убираем timezone (naive datetime для PostgreSQL)
                                    event_at = event_at_moscow.replace(tzinfo=None)
                                except Exception as date_err:
                                    logger.error(f"Date parsing error for '{event_at_str}': {date_err}")
                                    continue
                            else:
                                event_at = datetime.now()
                            
                            category = self._normalize_tx_category(category_id, category_name)
                            
                            # Специальная маркировка для ручных списаний
                            if category_id and ("correction" in category_id or "manual" in category_id):
                                if "work_conditions" in category_id:
                                    category = "Work_Conditions_Deduction"
                                    logger.info(f"🟣 Work conditions deduction: {amount}₽")
                                else:
                                    category = "Manual_Adjustment"
                                    logger.info(f"⚡ Manual adjustment detected: {amount}₽")
                            elif category_id and ("periodic" in category_id or "debt_cancellation" in category_id):
                                category = "Periodic_Deduction"
                                logger.info(f"🟠 Periodic payment detected: {amount}₽")
                            elif category_id and ("scheduled" in category_id):
                                category = "Scheduled_Payout"
                                logger.info(f"📆 Scheduled payout detected: {amount}₽")
                            
                            # Проверяем существование (v30.1 по ID транзакции Яндекса)
                            # ВАЖНО: проверяем по description, где храним tx_id
                            stmt = select(Transaction).where(
                                Transaction.description.like(f"%{tx_id}%")
                            )
                            result = await session.execute(stmt)
                            existing = result.scalar_one_or_none()
                            
                            if not existing:
                                # Создаём новую транзакцию (v30.1 с полным временем!)
                                transaction = Transaction(
                                    category=category,
                                    contractor="Yandex.Taxi",
                                    description=f"[{tx_id}] {category_id}: {description}" if description else f"[{tx_id}] {category_id}",
                                    amount=amount,
                                    date=event_at,  # ПОЛНОЕ ВРЕМЯ, не только дата!
                                    tx_type="api_import"
                                )
                                
                                session.add(transaction)
                                synced_count += 1
                            else:
                                skipped_count += 1
                                
                        except Exception as e:
                            logger.warning(f"Failed to process transaction: {e}")
                            continue
                    
                    await session.commit()
                
                logger.info(f"✓ DB SYNC: {synced_count} new, {skipped_count} skipped")
                
                return {
                    "status": "success",
                    "synced": synced_count,
                    "skipped": skipped_count,
                    "total": len(transactions)
                }
                
        except Exception as e:
            logger.error(f"Transaction sync error: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}
    
    async def get_driver_stats(self, driver_id: str) -> Dict:
        """
        Статистика водителя (время на линии)
        API: GET /v1/parks/driver-profiles/{driver_id}
        """
        if not self.enabled:
            return {"online_time": 0, "trips": 0}
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = f"{self.base_url}/v1/parks/driver-profiles/{driver_id}"
                
                response = await client.get(
                    url,
                    headers=self._get_headers(),
                    params={"park_id": self.park_id}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "online_time": data.get("work_status", {}).get("online_seconds", 0),
                        "trips": data.get("work_status", {}).get("trips_count", 0),
                        "balance": data.get("balance", 0)
                    }
                    
        except Exception as e:
            logger.error(f"Driver stats error: {e}")
        
        return {"online_time": 0, "trips": 0, "balance": 0}

    def _park_name_by_id(self, park_id: Optional[str]) -> Optional[str]:
        if not park_id:
            return None
        for name, cfg in settings.PARKS.items():
            if cfg.get("ID") == park_id:
                return name
        return None

    def _default_commission(self, park_name: str) -> float:
        park = (park_name or "PRO").upper()
        if park == "PRO":
            return 0.04
        if park == "GO":
            return 0.035
        return 0.03

    def _list_payload(self, park_id: Optional[str]) -> Dict:
        return {
            "query": {"park": {"id": park_id}},
            "limit": 1000
        }

    def _apply_driver_filters(self, payload: Dict) -> Dict:
        """
        НЕ ограничиваем work_status! Нам нужны ВСЕ водители парка,
        чтобы корректно связать User ↔ Transaction по yandex_driver_id.
        Ранее фильтр ["working"] отсекал 95% водителей, ломая все JOIN-ы.
        """
        return payload

    def _within_days(self, value: Optional[str], days: int = 30) -> bool:
        if not value:
            return False
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return False
        return dt >= datetime.now() - timedelta(days=days)

    def _is_recent_activity(self, profile: Dict, days: int = 30) -> bool:
        if not profile:
            return True
        keys = [
            "last_order_at",
            "last_order_date",
            "last_ride_at",
            "last_transaction_at",
            "last_activity_at",
        ]
        for key in keys:
            value = profile.get(key) or (profile.get("profile") or {}).get(key)
            if value and self._within_days(value, days):
                return True
        return True

    def _is_park_self_employed(self, profile: Dict) -> bool:
        if not profile:
            return False
        truthy_keys = {
            "taxi_park",
            "park_self_employed",
            "park_driver",
            "park_car",
            "park_owned",
            "is_park_car",
        }
        text_keys = {"driver_type", "category", "type", "contractor_type", "profile_type"}
        stack = [profile]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                for key, value in item.items():
                    key_lower = str(key).lower()
                    if key_lower in truthy_keys and value:
                        return True
                    if key_lower in text_keys and isinstance(value, str):
                        value_lower = value.lower()
                        if "park" in value_lower or "самозан" in value_lower:
                            return True
                    if isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(item, list):
                for value in item:
                    if isinstance(value, (dict, list)):
                        stack.append(value)
        return False

    async def _fetch_driver_profiles_for_park(self, park_name: str, cfg: Dict) -> Dict:
        url = f"{self.base_url}/v1/parks/driver-profiles/list"
        payload = self._apply_driver_filters(self._list_payload(cfg.get("ID")))
        data = await self._request_list("POST", url, self._get_headers_for_park(cfg), payload)
        profiles = (
            data.get("driver_profiles")
            or data.get("drivers")
            or data.get("profiles")
            or data.get("items")
            or []
        )
        filtered = [p for p in profiles if self._is_recent_activity(p)]
        return {"park": park_name, "profiles": filtered}

    async def _fetch_driver_profiles_for_park_full(self, park_name: str, cfg: Dict) -> Dict:
        """
        Потоковая синхронизация водителей с батчами по 100 записей.
        Использует семафор для предотвращения 504 Timeout.
        """
        url = f"{self.base_url}/v1/parks/driver-profiles/list"
        BATCH_LIMIT = 100  # Батчи по 100 для избежания 504
        offset = 0
        all_profiles: List[Dict] = []
        
        while True:
            payload = {
                "query": {"park": {"id": cfg.get("ID")}},
                "fields": {
                    "driver_profile": [
                        "id", "first_name", "last_name", "middle_name",
                        "park_id", "work_status", "phones",
                    ],
                    "account": ["balance"],
                    "car": ["id", "number", "vin", "status", "brand", "model"],
                    "current_status": ["status"],
                    "park": ["id"],
                },
                "limit": BATCH_LIMIT,
                "offset": offset,
            }
            payload = self._apply_driver_filters(payload)
            
            # Используем семафор для ограничения параллельных запросов
            async with self._api_semaphore:
                data = await self._request_list("POST", url, self._get_headers_for_park(cfg), payload)
            
            profiles = (
                data.get("driver_profiles")
                or data.get("drivers")
                or data.get("profiles")
                or data.get("items")
                or []
            )
            if not profiles:
                break
            all_profiles.extend([p for p in profiles if self._is_recent_activity(p)])
            logger.debug(f"Парк {park_name}: загружено {len(all_profiles)} профилей (batch offset={offset})")
            if len(profiles) < BATCH_LIMIT:
                break
            offset += BATCH_LIMIT
            # Пауза между батчами для избежания 429 Rate Limit
            await asyncio.sleep(0.3)
        logger.info(f"Парк {park_name}: всего {len(all_profiles)} активных профилей")
        return {"park": park_name, "profiles": all_profiles}

    async def sync_vehicle_ownership(self) -> Dict:
        """
        Синхронизация типа владения (Парк/Подключение) через /v1/parks/cars/list.
        Поле rental=true → Парковый (SUBLEASE), rental=false → Подключенный (CONNECTED).
        """
        results = {"updated_park": 0, "updated_connected": 0}
        for park_name, cfg in settings.PARKS.items():
            if not all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")]):
                continue
            park_plates_rental = {}  # plate -> True/False
            offset = 0
            while True:
                payload = {
                    "query": {"park": {"id": cfg.get("ID")}},
                    "limit": 100,
                    "offset": offset,
                }
                async with self._api_semaphore:
                    data = await self._request_list(
                        "POST",
                        f"{self.base_url}/v1/parks/cars/list",
                        self._get_headers_for_park(cfg),
                        payload,
                    )
                cars = data.get("cars", [])
                if not cars:
                    break
                for c in cars:
                    plate = (c.get("number") or "").replace(" ", "").upper()
                    if plate:
                        # ВАЖНО: если хотя бы одна запись с rental=True, оставляем True
                        # (дубликаты в API: одна машина может быть и rental=True и rental=False)
                        if c.get("rental") is True:
                            park_plates_rental[plate] = True
                        elif plate not in park_plates_rental:
                            park_plates_rental[plate] = False
                        # v35.1: Также обновляем yandex_status при синхронизации ownership
                        car_status = c.get("status")
                        if car_status and plate not in getattr(self, '_plate_status_cache', {}):
                            if not hasattr(self, '_plate_status_cache'):
                                self._plate_status_cache = {}
                            self._plate_status_cache[plate] = car_status
                if len(cars) < 100:
                    break
                offset += 100
                await asyncio.sleep(0.3)

            if not park_plates_rental:
                continue

            async with AsyncSessionLocal() as session:
                from sqlalchemy import text as sa_text
                park_plates = [p for p, r in park_plates_rental.items() if r]
                conn_plates = [p for p, r in park_plates_rental.items() if not r]
                # Сначала сбрасываем ВСЕ в connected, потом устанавливаем park
                # Это гарантирует корректный результат независимо от дубликатов
                if conn_plates:
                    r2 = await session.execute(sa_text("""
                        UPDATE vehicles SET is_park_car = false, ownership_type = 'CONNECTED'
                        WHERE REPLACE(UPPER(license_plate), ' ', '') = ANY(:plates)
                        AND park_name = :park
                    """), {"plates": conn_plates, "park": park_name})
                    results["updated_connected"] += r2.rowcount
                # Park ПОСЛЕ connected — имеет финальный приоритет
                if park_plates:
                    r1 = await session.execute(sa_text("""
                        UPDATE vehicles SET is_park_car = true, ownership_type = 'SUBLEASE'
                        WHERE REPLACE(UPPER(license_plate), ' ', '') = ANY(:plates)
                        AND park_name = :park
                    """), {"plates": park_plates, "park": park_name})
                    results["updated_park"] += r1.rowcount
                
                # v35.1: Обновляем yandex_status для ВСЕХ машин из API
                status_cache = getattr(self, '_plate_status_cache', {})
                if status_cache:
                    working_plates = [p for p, s in status_cache.items() if s == "working"]
                    not_working_plates = [p for p, s in status_cache.items() if s != "working"]
                    if working_plates:
                        await session.execute(sa_text("""
                            UPDATE vehicles SET yandex_status = 'working', status = 'working'
                            WHERE REPLACE(UPPER(license_plate), ' ', '') = ANY(:plates)
                            AND park_name = :park
                            AND status NOT IN ('service', 'offline', 'debt_lock')
                        """), {"plates": working_plates, "park": park_name})
                    if not_working_plates:
                        await session.execute(sa_text("""
                            UPDATE vehicles SET yandex_status = 'not_working'
                            WHERE REPLACE(UPPER(license_plate), ' ', '') = ANY(:plates)
                            AND park_name = :park
                        """), {"plates": not_working_plates, "park": park_name})
                    self._plate_status_cache = {}
                
                await session.commit()

            logger.info(
                f"Парк {park_name}: владение обновлено — "
                f"park={results['updated_park']}, connected={results['updated_connected']}"
            )
        return results

    async def fetch_driver_profiles(self, park_name: str) -> List[Dict]:
        park = (park_name or "PRO").upper()
        cfg = settings.PARKS.get(park, {})
        if not all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")]):
            return []
        response = await self._fetch_driver_profiles_for_park(park, cfg)
        return response.get("profiles") or []

    async def fetch_driver_profile(self, park_name: str, contractor_profile_id: str) -> Dict:
        """
        Deep Pull V2: Получение детального профиля водителя с привязкой к авто.
        API: GET /v2/parks/contractors/driver-profile
        """
        park = (park_name or "PRO").upper()
        cfg = settings.PARKS.get(park, {})
        if not all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")]):
            return {}
        url = f"{self.base_url}/v2/parks/contractors/driver-profile"
        params = {"contractor_profile_id": contractor_profile_id}
        
        async with self._api_semaphore:
            return await self._request_raw("GET", url, self._get_headers_for_park(cfg), params=params)

    async def fetch_driver_profile_v1(self, park_name: str, driver_profile_id: str) -> Dict:
        park = (park_name or "PRO").upper()
        cfg = settings.PARKS.get(park, {})
        if not all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")]):
            return {}
        url = f"{self.base_url}/v1/parks/driver-profiles/profile"
        params = {"driver_profile_id": driver_profile_id}
        return await self._request_raw("GET", url, self._get_headers_for_park(cfg), params=params)

    async def bind_driver_to_car(self, park_name: str, driver_profile_id: str, car_id: str) -> Dict:
        park = (park_name or "PRO").upper()
        cfg = settings.PARKS.get(park, {})
        if not all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")]):
            return {"status": "error", "message": "missing_credentials"}
        url = f"{self.base_url}/v1/parks/driver-profiles/car-bindings"
        params = {"driver_profile_id": str(driver_profile_id), "car_id": str(car_id)}
        return await self._request_raw("PUT", url, self._get_headers_for_park(cfg), params=params, payload=params)

    async def fetch_supply_hours(self, park_name: str, contractor_profile_id: str, period_from: str, period_to: str) -> Dict:
        park = (park_name or "PRO").upper()
        cfg = settings.PARKS.get(park, {})
        if not all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")]):
            return {}
        url = f"{self.base_url}/v2/parks/contractors/supply-hours"
        params = {
            "contractor_profile_id": contractor_profile_id,
            "period_from": period_from,
            "period_to": period_to,
        }
        return await self._request_raw("GET", url, self._get_headers_for_park(cfg), params=params)

    async def fetch_driver_work_rules(self, park_name: str) -> Dict:
        park = (park_name or "PRO").upper()
        cfg = settings.PARKS.get(park, {})
        if not all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")]):
            return {}
        url = f"{self.base_url}/v1/parks/driver-work-rules"
        params = {"park_id": cfg.get("ID")}
        return await self._request_raw("GET", url, self._get_headers_for_park(cfg), params=params)

    async def fetch_orders(self, park_name: str, from_dt: str, to_dt: str, statuses: Optional[List[str]] = None) -> List[Dict]:
        """
        Получение списка заказов парка через /v1/parks/orders/list.
        §5.1 YANDEX_API_BIBLE: Пагинация через cursor, max 500.
        """
        park = (park_name or "PRO").upper()
        cfg = settings.PARKS.get(park, {})
        if not all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")]):
            return []
        
        url = f"{self.base_url}/v1/parks/orders/list"
        all_orders: List[Dict] = []
        cursor = ""
        
        while True:
            payload = {
                "query": {
                    "park": {
                        "id": cfg.get("ID"),
                        "order": {
                            "booked_at": {"from": from_dt, "to": to_dt},
                            "statuses": statuses or ["complete"],
                        },
                    }
                },
                "limit": 500,
                "cursor": cursor,
            }
            async with self._api_semaphore:
                data = await self._request_raw("POST", url, self._get_headers_for_park(cfg), payload=payload)
            
            orders = data.get("orders") or []
            all_orders.extend(orders)
            
            cursor = data.get("cursor", "")
            if not cursor or not orders:
                break
            await asyncio.sleep(0.2)
        
        return all_orders

    async def fetch_transactions_live(self, park_name: str, window_minutes: int = 60) -> Dict:
        park = (park_name or "PRO").upper()
        cfg = settings.PARKS.get(park, {})
        if not all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")]):
            return {"park": park, "transactions": []}
        now = datetime.now()
        from_dt = now - timedelta(minutes=window_minutes)
        return await self._fetch_transactions_for_park(park, cfg, from_dt, now)

    async def update_vehicle_rent_details(self, park_name: str, vehicle_id: str, rent_term_id: Optional[str], platform_channels_enabled: bool = True) -> Dict:
        park = (park_name or "PRO").upper()
        cfg = settings.PARKS.get(park, {})
        if not all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")]):
            return {}
        url = f"{self.base_url}/v1/parks/vehicles/rent-details"
        params = {"vehicle_id": vehicle_id}
        payload = {
            "platform_channels_enabled": bool(platform_channels_enabled),
            "rent_term_id": rent_term_id,
        }
        return await self._request_raw("PUT", url, self._get_headers_for_park(cfg), params=params, payload=payload)

    async def upsert_rent_term(
        self,
        park_name: str,
        rent_term_id: str,
        name: str,
        daily_amount: str,
        working_days: int = 1,
        non_working_days: int = 0,
        minimum_period_days: int = 1,
        deposit_amount_total: Optional[str] = None,
        deposit_amount_daily: Optional[str] = None,
        is_buyout_possible: bool = True,
    ) -> Dict:
        park = (park_name or "PRO").upper()
        cfg = settings.PARKS.get(park, {})
        if not all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")]):
            return {}
        url = f"{self.base_url}/v1/parks/vehicles/rent-terms"
        headers = self._get_headers_for_park(cfg)
        headers["X-Idempotency-Token"] = uuid.uuid4().hex
        payload = {
            "rent_term_id": rent_term_id,
            "name": name,
            "schemas": [
                {
                    "working_days": int(working_days),
                    "non_working_days": int(non_working_days),
                    "daily_amount": str(daily_amount),
                }
            ],
            "minimum_period_days": int(minimum_period_days),
            "deposit_amount_total": deposit_amount_total,
            "deposit_amount_daily": deposit_amount_daily,
            "is_buyout_possible": bool(is_buyout_possible),
        }
        return await self._request_raw("PUT", url, headers, payload=payload)

    # ================================================================
    # RENT-TERMS: Получение условий аренды из Яндекс API
    # GET /v2/parks/vehicles/rent-terms/list
    # ================================================================
    async def fetch_rent_terms(self, park_name: str = "PRO") -> list:
        """Получить список rent-terms из Яндекс Fleet API для парка."""
        park = (park_name or "PRO").upper()
        cfg = settings.PARKS.get(park, {})
        if not all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")]):
            return []
        url = f"{self.base_url}/v1/parks/vehicles/rent-terms"
        headers = self._get_headers_for_park(cfg)
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.get(url, headers=headers, params={"park_id": cfg["ID"]})
            if resp.status_code == 200:
                data = resp.json()
                terms = data.get("rent_terms", data.get("items", []))
                if isinstance(terms, list):
                    logger.info(f"[RENT-TERMS] Fetched {len(terms)} terms from park {park}")
                    return terms
                return []
            else:
                logger.warning(f"[RENT-TERMS] {park}: status={resp.status_code}, body={resp.text[:300]}")
                return []
        except Exception as e:
            logger.error(f"[RENT-TERMS] {park}: {e}")
            return []

    async def fetch_rent_terms_all_parks(self) -> dict:
        """Получить rent-terms для всех активных парков."""
        result = {}
        for park_name in self.active_parks:
            terms = await self.fetch_rent_terms(park_name)
            result[park_name] = terms
        return result

    async def _fetch_vehicle_profiles_for_park(self, park_name: str, cfg: Dict) -> Dict:
        """Получение ВСЕХ автомобилей парка с пагинацией (батчи по 500)."""
        url = f"{self.base_url}/v1/parks/cars/list"
        BATCH = 500
        offset = 0
        all_vehicles = []
        while True:
            payload = {
                "query": {"park": {"id": cfg.get("ID")}},
                "fields": {
                    "vehicle": [
                        "id", "number", "vin", "status",
                        "callsign", "brand", "model", "color", "year",
                        "registration_cert", "rental",
                    ],
                },
                "limit": BATCH,
                "offset": offset,
            }
            async with self._api_semaphore:
                data = await self._request_list("POST", url, self._get_headers_for_park(cfg), payload)
            vehicles = data.get("cars") or data.get("vehicles") or data.get("items") or []
            if not vehicles:
                break
            all_vehicles.extend(vehicles)
            if len(vehicles) < BATCH:
                break
            offset += BATCH
            await asyncio.sleep(0.3)
        logger.info(f"Парк {park_name}: загружено {len(all_vehicles)} автомобилей")
        return {"park": park_name, "vehicles": all_vehicles}

    async def _fetch_transactions_for_park(self, park_name: str, cfg: Dict, from_dt: datetime, to_dt: datetime) -> Dict:
        """
        Получение транзакций через API V2 с cursor-пагинацией.
        API: POST /v2/parks/transactions/list
        
        V2 Format требует:
        - query.park.id
        - query.transaction.event_at.from / to
        - cursor для пагинации
        - limit до 1000
        """
        url = f"{self.base_url}/v2/parks/transactions/list"
        all_transactions = []
        cursor = None
        page = 0
        max_pages = 100  # Защита от бесконечного цикла (100 * 1000 = 100K макс)
        
        while page < max_pages:
            # V2 API payload формат — transaction ВНУТРИ park
            payload = {
                "query": {
                    "park": {
                        "id": cfg.get("ID"),
                        "transaction": {
                            "event_at": {
                                "from": from_dt.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                                "to": to_dt.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                            }
                        }
                    }
                },
                "limit": 1000
            }
            
            if cursor:
                payload["cursor"] = cursor
            
            async with self._api_semaphore:
                data = await self._request_list("POST", url, self._get_headers_for_park(cfg), payload)
            
            transactions = data.get("transactions") or data.get("items") or []
            all_transactions.extend(transactions)
            
            # Проверяем cursor для следующей страницы
            next_cursor = data.get("cursor") or data.get("next_cursor")
            if not next_cursor or not transactions:
                break
            
            cursor = next_cursor
            page += 1
            logger.debug(f"[{park_name}] Transactions page {page}, fetched {len(transactions)}, total {len(all_transactions)}")
        
        logger.info(f"[{park_name}] Total transactions fetched: {len(all_transactions)}")
        return {"park": park_name, "transactions": all_transactions}

    async def sync_driver_profiles_multi_park(self) -> Dict:
        """
        Синхронизация водителей из нескольких парков.
        Используем поле таксопарка в профиле для авто-распределения.
        
        БАТЧИ: Обработка пачками по 50 с семафором для избежания 504 Timeout.
        """
        results = {"status": "success", "parks": {}, "created": 0, "updated": 0, "skipped": 0}
        
        # Семафор для ограничения параллельных V2 запросов (избежание 504)
        self._v2_semaphore = asyncio.Semaphore(10)
        BATCH_SIZE_PROCESS = 50  # Обработка профилей пачками
        
        tasks = []
        for park_name, cfg in settings.PARKS.items():
            if not all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")]):
                results["parks"][park_name] = {"status": "skipped", "reason": "missing_credentials"}
                continue
            tasks.append(self._fetch_driver_profiles_for_park_full(park_name, cfg))
        
        # Параллельный fetch всех парков с семафором
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        overrides = self._manual_driver_overrides()

        async with AsyncSessionLocal() as session:
            # car_id в Яндекс API уникален в рамках парка — маппинг (park, yandex_car_id) -> vehicle.id
            vehicle_map_stmt = select(
                Vehicle.id, Vehicle.yandex_car_id, Vehicle.license_plate, Vehicle.vin, Vehicle.park_name
            )
            vehicle_rows = (await session.execute(vehicle_map_stmt)).all()
            park_upper = lambda p: (p or "PRO").upper()
            vehicle_by_park_yandex = {
                (park_upper(row[4]), row[1]): row[0] for row in vehicle_rows if row[1]
            }
            vehicle_by_plate = {str(row[2]).replace(" ", "").upper(): row[0] for row in vehicle_rows if row[2]}
            vehicle_by_vin = {str(row[3]).upper(): row[0] for row in vehicle_rows if row[3]}

            for response in responses:
                if isinstance(response, Exception):
                    continue
                park_name = response.get("park")
                profiles = response.get("profiles") or []
                seen_ids = set()
                for override in overrides:
                    override_park_id = override.get("park_id")
                    override_park = self._park_name_by_id(override_park_id) or (override.get("park_name") or park_name)
                    if override_park != park_name:
                        continue
                    profiles.append({
                        "contractor_profile_id": override.get("contractor_profile_id"),
                        "driver_profile_id": override.get("driver_profile_id"),
                        "id": override.get("id"),
                        "park_id": override_park_id,
                        "person": {"full_name": {"first_name": override.get("first_name"), "last_name": override.get("last_name")}},
                        "full_name": override.get("full_name"),
                    })
                created = 0
                updated = 0
                skipped = 0
                batch_counter = 0
                BATCH_SIZE = 100
                logger.info(f"Парк {park_name}: начало синхронизации {len(profiles)} профилей...")

                for profile in profiles:
                  try:
                    driver_profile = profile.get("driver_profile") or profile
                    contractor_id = (
                        profile.get("contractor_profile_id")
                        or driver_profile.get("contractor_profile_id")
                    )
                    driver_profile_id = (
                        driver_profile.get("id")
                        or profile.get("driver_profile_id")
                        or profile.get("driver_id")
                        or profile.get("id")
                    )
                    # КРИТИЧЕСКИ: driver_profile_id = основной ID, совпадает с Transaction.yandex_driver_id
                    # contractor_id — вторичный, хранится отдельно в yandex_contractor_id
                    driver_id = driver_profile_id or contractor_id
                    if not driver_id:
                        skipped += 1
                        continue
                    seen_ids.add(str(driver_id))
                    person = profile.get("person") or {}
                    full_name_obj = person.get("full_name") or {}

                    # Извлекаем телефон из profiles API
                    phones = profile.get("phones") or driver_profile.get("phones") or []
                    phone_number = None
                    if isinstance(phones, list) and phones:
                        phone_number = phones[0] if isinstance(phones[0], str) else phones[0].get("phone", None)
                    elif isinstance(phones, str):
                        phone_number = phones

                    # Извлекаем баланс водителя из accounts
                    accounts = profile.get("accounts") or profile.get("account") or []
                    driver_balance = 0.0
                    if isinstance(accounts, list) and accounts:
                        try:
                            balance = float(accounts[0].get("balance", 0) or 0)
                            driver_balance = balance  # Сохраняем как есть, включая отрицательные значения
                        except (ValueError, TypeError):
                            driver_balance = 0.0
                    elif isinstance(accounts, dict):
                        try:
                            balance = float(accounts.get("balance", 0) or 0)
                            driver_balance = balance  # Сохраняем как есть, включая отрицательные значения
                        except (ValueError, TypeError):
                            driver_balance = 0.0

                    name = (
                        profile.get("full_name")
                        or " ".join(
                            [
                                p for p in [
                                    full_name_obj.get("last_name") or driver_profile.get("last_name"),
                                    full_name_obj.get("first_name") or driver_profile.get("first_name"),
                                    full_name_obj.get("middle_name") or driver_profile.get("middle_name"),
                                ] if p
                            ]
                        ).strip()
                    )
                    park_id_from_profile = (
                        driver_profile.get("park_id")
                        or profile.get("park_id")
                        or (profile.get("park") or {}).get("id")
                        or (profile.get("taxi_park") or {}).get("id")
                    )
                    mapped_park = self._park_name_by_id(park_id_from_profile) or park_name

                    driver_id_str = str(driver_id)
                    contractor_id_str = str(contractor_id) if contractor_id else None
                    driver_profile_id_str = str(driver_profile_id) if driver_profile_id else None

                    # Поиск: по driver_profile_id (основной) или contractor_id (вторичный)
                    search_clauses = [User.yandex_driver_id == driver_id_str]
                    if driver_profile_id_str and driver_profile_id_str != driver_id_str:
                        search_clauses.append(User.yandex_driver_id == driver_profile_id_str)
                    if contractor_id_str:
                        search_clauses.append(User.yandex_driver_id == contractor_id_str)
                        search_clauses.append(User.yandex_contractor_id == contractor_id_str)
                    stmt = select(User).where(or_(*search_clauses)).limit(1)
                    user = (await session.execute(stmt)).scalars().first()

                    # Формируем username: телефон > driver_id
                    username_val = phone_number or f"driver_{driver_id_str}"

                    if not user:
                        # Проверяем уникальность username
                        uname_check = await session.execute(
                            select(User.id).where(User.username == username_val).limit(1)
                        )
                        if uname_check.scalar():
                            username_val = f"driver_{driver_id_str}"

                        user = User(
                            username=username_val,
                            hashed_password="",
                            full_name=name or f"Driver {driver_id}",
                            role=UserRole.MANAGER,
                            is_active=True,
                            is_archived=False,
                            can_see_fleet=True,
                            yandex_driver_id=driver_id_str,
                            yandex_contractor_id=contractor_id_str,
                            driver_balance=driver_balance,
                            park_name=mapped_park,
                        )
                        session.add(user)
                        created += 1
                    else:
                        # ИМПЕРСКАЯ ИСКЛЮЧИТЕЛЬНОСТЬ: master/admin НЕПРИКОСНОВЕННЫ
                        if user.username in ("master", "admin") or user.role == UserRole.MASTER:
                            skipped += 1
                            continue

                        if name and user.full_name != name:
                            user.full_name = name
                        if user.park_name != mapped_park:
                            user.park_name = mapped_park
                        if contractor_id_str and user.yandex_contractor_id != contractor_id_str:
                            user.yandex_contractor_id = contractor_id_str
                        # Обновляем телефон если получили из API
                        if phone_number and user.username != phone_number:
                            uname_check2 = await session.execute(
                                select(User.id).where(User.username == phone_number, User.id != user.id).limit(1)
                            )
                            if not uname_check2.scalar():
                                user.username = phone_number
                        # Обновляем баланс из API
                        user.driver_balance = driver_balance
                        # Исправляем yandex_driver_id чтобы совпадал с Transaction.yandex_driver_id
                        if driver_profile_id_str and user.yandex_driver_id != driver_profile_id_str:
                            existing_check = await session.execute(
                                select(User.id).where(
                                    User.yandex_driver_id == driver_profile_id_str,
                                    User.id != user.id
                                ).limit(1)
                            )
                            if not existing_check.scalar():
                                user.yandex_driver_id = driver_profile_id_str
                        user.is_archived = False
                        updated += 1
                    
                    # v35.1: Извлекаем данные ВУ, рейтинг, даты из профиля
                    # driver_license может быть в person или в driver_profile
                    driver_license = (
                        person.get("driver_license") or
                        driver_profile.get("driver_license") or
                        profile.get("driver_license") or {}
                    )
                    if driver_license:
                        license_number = driver_license.get("number") or driver_license.get("license_number")
                        if license_number:
                            user.license_number = str(license_number).strip()
                        license_issue = driver_license.get("issue_date") or driver_license.get("issued_at")
                        if license_issue:
                            try:
                                user.license_issue_date = datetime.fromisoformat(str(license_issue).replace("Z", "+00:00")).date() if "T" in str(license_issue) else datetime.strptime(str(license_issue)[:10], "%Y-%m-%d").date()
                            except Exception:
                                pass
                        license_expiry = driver_license.get("expiry_date") or driver_license.get("expire_date") or driver_license.get("expiration_date")
                        if license_expiry:
                            try:
                                user.license_expiry_date = datetime.fromisoformat(str(license_expiry).replace("Z", "+00:00")).date() if "T" in str(license_expiry) else datetime.strptime(str(license_expiry)[:10], "%Y-%m-%d").date()
                            except Exception:
                                pass
                        license_country = driver_license.get("country") or driver_license.get("country_code")
                        if license_country:
                            user.license_country = str(license_country).lower()
                        exp_from = driver_license.get("experience") or driver_license.get("driving_experience_from") or driver_license.get("experience_from")
                        if exp_from:
                            try:
                                user.driving_experience_from = datetime.fromisoformat(str(exp_from).replace("Z", "+00:00")).date() if "T" in str(exp_from) else datetime.strptime(str(exp_from)[:10], "%Y-%m-%d").date()
                            except Exception:
                                pass
                    
                    # Рейтинг из Яндекса
                    rating_val = (
                        profile.get("rating") or
                        driver_profile.get("rating") or
                        (profile.get("driver_metrics") or {}).get("rating")
                    )
                    if rating_val:
                        try:
                            user.yandex_rating = float(rating_val)
                        except (ValueError, TypeError):
                            pass
                    
                    # Дата принятия в парк
                    hire_date_val = (
                        profile.get("hire_date") or
                        driver_profile.get("hire_date") or
                        profile.get("created_date") or
                        driver_profile.get("created_date")
                    )
                    if hire_date_val:
                        try:
                            user.hire_date = datetime.fromisoformat(str(hire_date_val).replace("Z", "+00:00")).date() if "T" in str(hire_date_val) else datetime.strptime(str(hire_date_val)[:10], "%Y-%m-%d").date()
                        except Exception:
                            pass
                    
                    # Лимит баланса
                    balance_limit_val = None
                    if isinstance(accounts, list) and accounts:
                        balance_limit_val = accounts[0].get("limit") or accounts[0].get("balance_limit")
                    elif isinstance(accounts, dict):
                        balance_limit_val = accounts.get("limit") or accounts.get("balance_limit")
                    if balance_limit_val is not None:
                        try:
                            user.balance_limit = float(balance_limit_val)
                        except (ValueError, TypeError):
                            pass
                    
                    # Дата рождения
                    birth_date_val = person.get("birth_date") or driver_profile.get("birth_date")
                    if birth_date_val:
                        try:
                            user.birth_date = datetime.fromisoformat(str(birth_date_val).replace("Z", "+00:00")).date() if "T" in str(birth_date_val) else datetime.strptime(str(birth_date_val)[:10], "%Y-%m-%d").date()
                        except Exception:
                            pass
                    
                    # Сохраняем yandex_work_status и yandex_last_sync_at
                    user.yandex_last_sync_at = datetime.now()
                    
                    # REAL-TIME STATUS: work_status и current_status для "Живые 300" и Матрицы
                    work_status = (
                        driver_profile.get("work_status")
                        or profile.get("work_status")
                        or (profile.get("profile") or {}).get("work_status")
                    )
                    current_status = (
                        (profile.get("current_status") or {}).get("status")
                        or profile.get("status")
                    )
                    # Если work_status == "working" -> is_core_active = True (Живые 300)
                    if str(work_status).lower() == "working":
                        user.is_active = True
                        user.is_core_active = True
                        user.last_active_at = datetime.now()
                    else:
                        user.is_core_active = False
                    
                    # REAL-TIME STATUS: Сохраняем статусы для UI
                    user.work_status = str(work_status).lower() if work_status else "not_working"
                    if current_status:
                        status_lower = str(current_status).lower()
                        if status_lower in ("busy", "on_order", "driving"):
                            user.realtime_status = "busy"
                            user.is_core_active = True  # Зелёный в матрице
                        elif status_lower in ("online", "free", "waiting"):
                            user.realtime_status = "online"
                            user.is_core_active = True  # На линии
                        else:
                            user.realtime_status = "offline"
                    else:
                        user.realtime_status = "online" if str(work_status).lower() == "working" else "offline"

                    # car_id в контексте парка (docs: YANDEX_PARKS_И_ПРИВЯЗКИ) — V2: driver_profile.car.id
                    driver_profile_obj = profile.get("driver_profile") or profile
                    car = profile.get("car") or driver_profile_obj.get("car") or {}
                    car_id = car.get("id") or profile.get("car_id") or driver_profile_obj.get("car_id") or (profile.get("profile") or {}).get("car_id")
                    plate = car.get("number")
                    vin = car.get("vin")
                    car_status = car.get("status")
                    brand = car.get("brand")
                    model = car.get("model")
                    
                    # ХИРУРГИЧЕСКИЙ МАППИНГ V2: Если car_id есть, но plate/vin нет — тянем через V2
                    if car_id and (not plate or not vin):
                        v2_data = await self.fetch_vehicle_v2(mapped_park, str(car_id))
                        if v2_data:
                            plate = plate or v2_data.get("number") or v2_data.get("license_plate")
                            vin = vin or v2_data.get("vin")
                            car_status = car_status or v2_data.get("status")
                            brand = brand or v2_data.get("brand")
                            model = model or v2_data.get("model")
                    
                    vehicle_id = None
                    park_key = park_upper(mapped_park)
                    if car_id:
                        vehicle_id = vehicle_by_park_yandex.get((park_key, str(car_id)))
                    if not vehicle_id and plate:
                        vehicle_id = vehicle_by_plate.get(str(plate).replace(" ", "").upper())
                    if not vehicle_id and vin:
                        vehicle_id = vehicle_by_vin.get(str(vin).upper())
                    if not vehicle_id and car_id:
                        try:
                            normalized_plate = str(plate).replace(" ", "").upper() if plate else None
                            if not normalized_plate:
                                normalized_plate = f"UNKNOWN-{str(car_id)[:8].upper()}"
                            # DEEP MAPPING v200.1: Детекция собственности при создании
                            raw_own = str(car.get("ownership_type") or car.get("ownership") or "").lower()
                            is_park_flag = (
                                "park" in raw_own or raw_own == "rent"
                                or car.get("rent_type") == "park" or car.get("is_park_car")
                            )
                            vehicle = Vehicle(
                                license_plate=normalized_plate,
                                brand=brand,
                                model=model,
                                vin=str(vin).upper() if vin else None,
                                ownership_type=OwnershipType.SUBLEASE if is_park_flag else OwnershipType.CONNECTED,
                                is_park_car=is_park_flag,  # Владелец: Таксопарк
                                status="service" if car_status and str(car_status).lower() in {"blocked", "not_working", "repairing", "debt_lock", "inactive"} else "working",
                                is_active=True,
                                is_free=False,
                                park_name=(mapped_park or "PRO").upper(),
                                yandex_car_id=str(car_id),
                                last_update=datetime.now(),
                                created_at=datetime.now(),
                            )
                            session.add(vehicle)
                            await session.flush()
                            vehicle_id = vehicle.id
                            vehicle_by_park_yandex[(park_key, str(car_id))] = vehicle_id
                            vehicle_by_plate[normalized_plate] = vehicle_id
                            if vin:
                                vehicle_by_vin[str(vin).upper()] = vehicle_id
                            logger.debug(f"Created vehicle {normalized_plate} for car_id {car_id} park={park_key}")
                        except Exception as ve:
                            self._log_sync_issue(
                                f"Driver {driver_id_str} has car_id {car_id} but vehicle creation failed: {ve}"
                            )

                    if vehicle_id:
                        if user.current_vehicle_id and user.current_vehicle_id != vehicle_id:
                            prev_vehicle = await session.get(Vehicle, user.current_vehicle_id)
                            if prev_vehicle:
                                prev_vehicle.current_driver_id = None
                                prev_vehicle.yandex_driver_id = None
                                prev_vehicle.is_free = True
                                prev_vehicle.last_update = datetime.now()
                        user.current_vehicle_id = vehicle_id
                        vehicle = await session.get(Vehicle, vehicle_id)
                        if vehicle:
                            vehicle.current_driver_id = user.id
                            vehicle.yandex_driver_id = driver_id_str
                            vehicle.is_free = False
                            vehicle.park_name = (mapped_park or "PRO").upper()
                            vehicle.last_update = datetime.now()
                            
                            # DEEP MAPPING v200.1: Субаренда + is_park_car
                            # ТОЛЬКО обновляем если API ЯВНО предоставляет данные о владении
                            raw_ownership = str(
                                car.get("ownership_type")
                                or car.get("ownership")
                                or profile.get("ownership_type")
                                or ""
                            ).lower().strip()
                            if raw_ownership:  # Обновляем ТОЛЬКО если API вернул данные
                                is_park_car_flag = (
                                    self._is_park_self_employed(profile)
                                    or "park" in raw_ownership
                                    or raw_ownership == "rent"
                                    or car.get("rent_type") == "park"
                                    or car.get("is_park_car")
                                )
                                is_sublease = is_park_car_flag or "rent" in raw_ownership or "sublease" in raw_ownership
                                vehicle.ownership_type = OwnershipType.SUBLEASE if is_sublease else OwnershipType.CONNECTED
                                vehicle.is_park_car = bool(is_park_car_flag)

                    # EXORCISM v200.11: Обновляем yandex_current_car JSONB при каждой синхронизации
                    if car_id or plate:
                        user.yandex_current_car = {
                            "car_id": str(car_id) if car_id else None,
                            "car_number": str(plate).replace(" ", "").upper() if plate else None,
                            "brand": str(brand) if brand else None,
                            "model": str(model) if model else None,
                            "vin": str(vin).upper() if vin else None,
                        }
                    elif not vehicle_id:
                        # Нет машины — очищаем поле
                        user.yandex_current_car = {}

                    term_stmt = select(ContractTerm).where(ContractTerm.driver_id == user.id).limit(1)
                    existing_term = (await session.execute(term_stmt)).scalars().first()
                    if not existing_term:
                        term = ContractTerm(
                            driver_id=user.id,
                            park_name=mapped_park,
                            is_default=False,
                            partner_daily_rent=0.0,
                            driver_daily_rent=float(user.daily_rent or 0.0),
                            commission_rate=self._default_commission(mapped_park),
                            day_off_rate=0.0,
                            is_repair=False,
                            is_day_off=False,
                            is_idle=False,
                        )
                        session.add(term)
                    
                    # Batch commit every BATCH_SIZE records для избежания потери данных при ошибках
                    batch_counter += 1
                    if batch_counter % BATCH_SIZE == 0:
                        await session.commit()
                        logger.info(f"Парк {park_name}: обработано {batch_counter} водителей...")
                  except Exception as e:
                    logger.warning(f"Парк {park_name}: ошибка при обработке водителя: {e}")
                    # Откатываем транзакцию чтобы продолжить обработку остальных
                    try:
                        await session.rollback()
                    except Exception:
                        pass
                    skipped += 1
                    continue

                logger.info(f"Парк {park_name} синхронизирован успешно: создано {created}, обновлено {updated}, пропущено {skipped}")
                results["parks"][park_name] = {"status": "success", "total": len(profiles)}
                results["created"] += created
                results["updated"] += updated
                results["skipped"] += skipped

                # Архивируем ТОЛЬКО тех, кого НЕТ в API И кто не имел транзакций за 30 дней
                if seen_ids:
                    archive_stmt = select(User).where(
                        and_(
                            User.park_name == park_name,
                            User.yandex_driver_id.isnot(None),
                            ~User.yandex_driver_id.in_(list(seen_ids)),
                            User.is_archived == False,
                        )
                    )
                    archive_users = (await session.execute(archive_stmt)).scalars().all()
                    from sqlalchemy import func as sa_func
                    archived_count = 0
                    for u in archive_users:
                        if u.username in ("master", "admin") or u.role == UserRole.MASTER:
                            continue
                        # Проверяем: были ли транзакции за последние 30 дней?
                        tx_check = await session.execute(
                            select(sa_func.count()).select_from(Transaction).where(
                                and_(
                                    Transaction.yandex_driver_id == u.yandex_driver_id,
                                    Transaction.date >= datetime.now() - timedelta(days=30),
                                )
                            )
                        )
                        if tx_check.scalar() > 0:
                            # Водитель активен по транзакциям — НЕ архивируем
                            continue
                        u.is_archived = True
                        u.is_active = False
                        archived_count += 1
                    if archived_count > 0:
                        logger.info(f"Парк {park_name}: заархивировано {archived_count} неактивных водителей")

            await session.commit()

        return results

    async def sync_vehicles_multi_park(self) -> Dict:
        results = {"status": "success", "parks": {}, "synced": 0, "total": 0}
        responses = []
        
        # Последовательный запрос к каждому парку с задержкой 1 сек
        for park_name, cfg in settings.PARKS.items():
            if not all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")]):
                results["parks"][park_name] = {"status": "skipped", "reason": "missing_credentials"}
                continue
            
            # Задержка 1 сек между запросами к разным паркам
            if responses:
                await asyncio.sleep(1)
            
            try:
                response = await self._fetch_vehicle_profiles_for_park(park_name, cfg)
                responses.append(response)
            except Exception as e:
                logger.error(f"Error fetching vehicles for park {park_name}: {e}")
                responses.append({"park": park_name, "vehicles": [], "error": str(e)})

        async with AsyncSessionLocal() as session:
            for response in responses:
                if isinstance(response, Exception):
                    continue
                park_name = response.get("park")
                vehicles = response.get("vehicles") or []
                results["total"] += len(vehicles)

                for vehicle_data in vehicles:
                    car_id = vehicle_data.get("id")
                    license_plate = (vehicle_data.get("number") or vehicle_data.get("license_plate") or "").replace(" ", "")
                    if not license_plate:
                        continue
                    brand = vehicle_data.get("brand") or vehicle_data.get("car_brand")
                    model = vehicle_data.get("model") or vehicle_data.get("car_model")
                    status = vehicle_data.get("status", "unknown")
                    raw_status = str(status or "").lower()
                    vin = vehicle_data.get("vin") or vehicle_data.get("vehicle_vin") or vehicle_data.get("chassis_number")
                    color = vehicle_data.get("color") or vehicle_data.get("car_color")
                    year = vehicle_data.get("year") or vehicle_data.get("car_year") or vehicle_data.get("manufacture_year")
                    callsign = vehicle_data.get("callsign") or vehicle_data.get("call_sign")
                    sts_number = vehicle_data.get("registration_cert") or vehicle_data.get("sts") or vehicle_data.get("cert_number")
                    park_profile = vehicle_data.get("park_profile") or {}
                    raw_ownership = str(
                        vehicle_data.get("ownership_type")
                        or vehicle_data.get("car_ownership_type")
                        or vehicle_data.get("ownership")
                        or park_profile.get("ownership_type")
                        or ""
                    ).lower()
                    is_park_property = bool(
                        vehicle_data.get("is_park_property")
                        or vehicle_data.get("is_park_car")
                        or vehicle_data.get("park_car")
                        or vehicle_data.get("park_owned")
                        or park_profile.get("is_park_property")
                        or park_profile.get("park_car")
                        or park_profile.get("park_owned")
                    )
                    # DEEP MAPPING v200.1: Детекция собственности таксопарка
                    # Согласно Yandex API: rental=true означает парковая машина
                    # park_profile.is_park_property=true также означает парковую машину
                    is_park_car_flag = bool(
                        is_park_property
                        or vehicle_data.get("rental") == True  # V1 API поле
                        or raw_ownership == "park"
                        or "park" in raw_ownership
                        or raw_ownership == "rent"
                        or vehicle_data.get("rent_type") == "park"
                        or vehicle_data.get("leasing_company")  # Лизинг = парковое авто
                        or (park_profile.get("is_park_property") == True)  # V2 API поле
                    )
                    ownership_type = OwnershipType.SUBLEASE if (
                        is_park_car_flag or "rent" in raw_ownership or "sublease" in raw_ownership
                    ) else OwnershipType.CONNECTED
                    driver_ids = []
                    for key in ("current_driver_id", "driver_profile_id", "contractor_profile_id", "driver_id"):
                        if vehicle_data.get(key):
                            driver_ids.append(str(vehicle_data.get(key)))
                    for key in ("driver_ids", "drivers"):
                        vals = vehicle_data.get(key)
                        if isinstance(vals, list):
                            for item in vals:
                                if isinstance(item, dict) and item.get("id"):
                                    driver_ids.append(str(item.get("id")))
                                elif isinstance(item, (str, int)):
                                    driver_ids.append(str(item))
                    driver = vehicle_data.get("driver") or {}
                    if driver.get("id"):
                        driver_ids.append(str(driver.get("id")))
                    driver_profile = vehicle_data.get("driver_profile") or {}
                    if driver_profile.get("id"):
                        driver_ids.append(str(driver_profile.get("id")))

                    stmt = select(Vehicle).where(Vehicle.license_plate == license_plate)
                    vehicle = (await session.execute(stmt)).scalar_one_or_none()
                    if not vehicle:
                        vehicle = Vehicle(
                            license_plate=license_plate,
                            ownership_type=ownership_type,
                            is_park_car=is_park_car_flag,  # Владелец: Таксопарк
                            park_name=(park_name or "PRO").upper(),  # Категория
                            status=status if status else "working",  # v35.1: статус напрямую из API
                            yandex_status=status,  # v35.1: КРИТИЧНО — сохраняем yandex_status!
                            created_at=datetime.now(),
                            last_update=datetime.now(),
                        )
                        session.add(vehicle)

                    # Владение: обновляем ТОЛЬКО если API ЯВНО вернул данные
                    # ВАЖНО: Если is_park_car=True → НЕ снижаем до False (дубликаты в API)
                    # sync_vehicle_ownership() из /v1/parks/cars/list имеет финальный приоритет
                    has_ownership_data = bool(
                        raw_ownership.strip()
                        or is_park_property
                        or vehicle_data.get("rental") is not None
                    )
                    if has_ownership_data:
                        # Только ПОВЫШАЕМ до park, не снижаем (дубли в API с разными rental)
                        if is_park_car_flag:
                            vehicle.ownership_type = OwnershipType.SUBLEASE
                            vehicle.is_park_car = True
                        elif not vehicle.is_park_car:
                            # Обновляем connected только если ещё не park
                            vehicle.ownership_type = ownership_type
                            vehicle.is_park_car = False
                    # VIN INTEGRITY: если VIN короткий — дотянуть через V2 API
                    vin_is_full = vin and len(str(vin).strip()) == 17
                    if not vin_is_full and car_id:
                        v2_data = await self.fetch_vehicle_v2(park_name, str(car_id))
                        if v2_data:
                            v2_vin = v2_data.get("vin")
                            if v2_vin and len(str(v2_vin).strip()) == 17:
                                vin = v2_vin
                            elif not vin:
                                vin = v2_vin
                    
                    vehicle.brand = brand
                    vehicle.model = model
                    vehicle.vin = vin or vehicle.vin or "Внешнее авто"
                    vehicle.color = color
                    vehicle.year = year
                    vehicle.callsign = callsign or vehicle.callsign or "Внешнее авто"
                    vehicle.sts_number = sts_number or vehicle.sts_number or "Внешнее авто"
                    vehicle.yandex_car_id = car_id
                    vehicle.park_name = (park_name or "PRO").upper()
                    if raw_status in {"removed", "archived", "deleted"}:
                        vehicle.is_active = False
                        vehicle.status = "archive"
                        vehicle.is_free = True
                        vehicle.current_driver_id = None
                        vehicle.yandex_driver_id = None
                    else:
                        vehicle.is_active = True
                        if vehicle.status not in ["service", "offline", "debt_lock"]:
                            vehicle.status = status if status else "working"  # v35.1: статус из API
                    # v35.1: КРИТИЧНО — ВСЕГДА записываем yandex_status из Яндекс API
                    vehicle.yandex_status = status
                    vehicle.yandex_rental = vehicle_data.get("rental")
                    vehicle.last_update = datetime.now()

                    driver = None
                    matched_driver_id = None
                    for driver_id in driver_ids:
                        stmt_driver = select(User).where(
                            or_(
                                User.yandex_driver_id == str(driver_id),
                                User.yandex_contractor_id == str(driver_id),
                            )
                        ).limit(1)
                        driver = (await session.execute(stmt_driver)).scalars().first()
                        if driver:
                            matched_driver_id = str(driver_id)
                            break
                    if not driver and driver_ids:
                        matched_driver_id = str(driver_ids[0])
                        driver = User(
                            username=f"driver_{matched_driver_id}",
                            hashed_password="",
                            full_name=f"Driver {matched_driver_id}",
                            is_active=True,
                            can_see_fleet=True,
                            yandex_driver_id=matched_driver_id,
                            park_name=vehicle.park_name,
                        )
                        session.add(driver)
                        await session.flush()
                    if driver:

                        if driver.current_vehicle_id and driver.current_vehicle_id != vehicle.id:
                            prev_vehicle = await session.get(Vehicle, driver.current_vehicle_id)
                            if prev_vehicle:
                                prev_vehicle.current_driver_id = None
                                prev_vehicle.yandex_driver_id = None
                                prev_vehicle.is_free = True
                                prev_vehicle.last_update = datetime.now()

                        driver.current_vehicle_id = vehicle.id
                        vehicle.current_driver_id = driver.id
                        vehicle.yandex_driver_id = str(driver.yandex_driver_id)
                        vehicle.is_free = False

                        term_stmt = select(ContractTerm).where(ContractTerm.vehicle_id == vehicle.id)
                        term = (await session.execute(term_stmt)).scalar_one_or_none()
                        if not term:
                            term = ContractTerm(
                                vehicle_id=vehicle.id,
                                driver_id=driver.id,
                                park_name=vehicle.park_name,
                                is_default=False,
                                partner_daily_rent=0.0,
                                driver_daily_rent=float(driver.daily_rent or 0.0),
                                commission_rate=self._default_commission(vehicle.park_name),
                                day_off_rate=0.0,
                                is_repair=False,
                                is_day_off=False,
                                is_idle=False,
                            )
                            session.add(term)
                    else:
                        if vehicle.current_driver_id:
                            prev_driver = await session.get(User, vehicle.current_driver_id)
                            if prev_driver and prev_driver.current_vehicle_id == vehicle.id:
                                prev_driver.current_vehicle_id = None
                        vehicle.current_driver_id = None
                        vehicle.yandex_driver_id = None
                        vehicle.is_free = True

                    results["synced"] += 1

                results["parks"][park_name] = {"status": "success", "total": len(vehicles)}

            await session.commit()
        return results

    async def sync_transactions_multi_park(self, window_minutes: int = 2880) -> Dict:
        now = datetime.now()
        from_dt = now - timedelta(minutes=window_minutes)
        results = {"status": "success", "parks": {}, "synced": 0, "skipped": 0}
        responses = []
        
        # Последовательный запрос к каждому парку с задержкой 1 сек
        for park_name, cfg in settings.PARKS.items():
            if not all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")]):
                results["parks"][park_name] = {"status": "skipped", "reason": "missing_credentials"}
                continue
            
            # Задержка 1 сек между запросами к разным паркам
            if responses:
                await asyncio.sleep(1)
            
            try:
                response = await self._fetch_transactions_for_park(park_name, cfg, from_dt, now)
                responses.append(response)
            except Exception as e:
                logger.error(f"Error fetching transactions for park {park_name}: {e}")
                responses.append({"park": park_name, "transactions": [], "error": str(e)})

        async with AsyncSessionLocal() as session:
            incoming_by_driver: Dict[str, datetime] = {}
            for response in responses:
                if isinstance(response, Exception):
                    continue
                park_name = response.get("park")
                transactions = response.get("transactions") or []
                for tx in transactions:
                    # V2 API маппинг полей
                    tx_id = tx.get("id") or tx.get("transaction_id") or ""
                    category_id = (
                        tx.get("category_id") 
                        or tx.get("category") 
                        or tx.get("type")
                    )
                    category_name = (
                        tx.get("category_name") 
                        or tx.get("category_title") 
                        or tx.get("type_name")
                    )
                    # V2 может использовать 'value' вместо 'amount'
                    amount = float(tx.get("amount") or tx.get("value") or 0)
                    description = tx.get("description") or tx.get("comment") or ""
                    # V2 использует 'created_at' или 'event_at'
                    event_at_str = (
                        tx.get("event_at") 
                        or tx.get("created_at") 
                        or tx.get("date")
                        or ""
                    )
                    # V2 driver ID маппинг
                    driver_profile_id = (
                        tx.get("driver_profile_id")
                        or tx.get("contractor_profile_id")
                        or (tx.get("driver") or {}).get("id")
                        or (tx.get("driver") or {}).get("profile_id")
                        or (tx.get("contractor") or {}).get("id")
                    )
                    if event_at_str:
                        try:
                            # Убираем timezone info для совместимости с БД
                            dt = datetime.fromisoformat(event_at_str.replace("Z", "+00:00"))
                            event_at = dt.replace(tzinfo=None) if dt.tzinfo else dt
                        except Exception:
                            try:
                                # Альтернативный парсинг
                                event_at = datetime.strptime(event_at_str[:19], "%Y-%m-%dT%H:%M:%S")
                            except Exception:
                                event_at = datetime.now()
                    else:
                        event_at = datetime.now()

                    if driver_profile_id and amount > 0:
                        driver_key = str(driver_profile_id)
                        prev = incoming_by_driver.get(driver_key)
                        if not prev or event_at > prev:
                            incoming_by_driver[driver_key] = event_at

                    # Уникальный ID из Яндекс API для предотвращения дублей
                    clean_tx_id = str(tx_id).strip() if tx_id else None
                    if not clean_tx_id:
                        clean_tx_id = None

                    normalized_cat = self._normalize_tx_category(category_id, category_name)
                    desc_text = f"[{tx_id}] {category_id}: {description}" if description else f"[{tx_id}] {category_id}"
                    driver_id_str = str(driver_profile_id) if driver_profile_id else None

                    if clean_tx_id:
                        # UPSERT с ON CONFLICT DO NOTHING по partial unique index
                        from sqlalchemy import text as sa_text
                        insert_stmt = pg_insert(Transaction).values(
                            park_name=park_name,
                            yandex_tx_id=clean_tx_id,
                            yandex_driver_id=driver_id_str,
                            category=normalized_cat,
                            contractor="Yandex.Taxi",
                            description=desc_text,
                            amount=amount,
                            date=event_at,
                            tx_type="api_import",
                        ).on_conflict_do_nothing(
                            index_elements=['park_name', 'yandex_tx_id'],
                            index_where=sa_text("yandex_tx_id IS NOT NULL"),
                        )
                        result_proxy = await session.execute(insert_stmt)
                        if result_proxy.rowcount == 0:
                            results["skipped"] += 1
                            continue
                    else:
                        # Без yandex_tx_id — fallback на точный поиск
                        stmt = select(Transaction).where(
                            and_(
                                Transaction.park_name == park_name,
                                Transaction.yandex_driver_id == driver_id_str,
                                Transaction.amount == amount,
                                Transaction.date == event_at,
                                Transaction.category == normalized_cat,
                            )
                        ).limit(1)
                        existing = (await session.execute(stmt)).scalars().first()
                        if existing:
                            results["skipped"] += 1
                            continue
                        transaction = Transaction(
                            park_name=park_name,
                            yandex_driver_id=driver_id_str,
                            category=normalized_cat,
                            contractor="Yandex.Taxi",
                            description=desc_text,
                            amount=amount,
                            date=event_at,
                            tx_type="api_import",
                        )
                        session.add(transaction)
                    
                    # DIGITAL RAIN: Запись в FinancialLog для реального времени
                    driver_id_for_log = None
                    vehicle_id_for_log = None
                    if driver_profile_id:
                        # Пытаемся найти связанного водителя и машину
                        driver_stmt = select(User).where(
                            or_(
                                User.yandex_driver_id == str(driver_profile_id),
                                User.yandex_contractor_id == str(driver_profile_id),
                            )
                        ).limit(1)
                        driver_user = (await session.execute(driver_stmt)).scalars().first()
                        if driver_user:
                            driver_id_for_log = driver_user.id
                            vehicle_id_for_log = driver_user.current_vehicle_id
                    
                    # Определяем тип записи по категории
                    entry_type = "yandex_income" if amount > 0 else "yandex_expense"
                    if category_id and "refund" in str(category_id).lower():
                        entry_type = "yandex_refund"
                    elif category_id and "fine" in str(category_id).lower():
                        entry_type = "yandex_fine"
                    elif category_id and "commission" in str(category_id).lower():
                        entry_type = "yandex_commission"
                    
                    financial_log = FinancialLog(
                        vehicle_id=vehicle_id_for_log,
                        driver_id=driver_id_for_log,
                        park_name=park_name,
                        entry_type=entry_type,
                        amount=amount,
                        note=f"{category_name or category_id}: {description}" if description else str(category_name or category_id),
                        meta={"tx_id": tx_id, "yandex_driver_id": str(driver_profile_id) if driver_profile_id else None},
                        created_at=event_at,
                    )
                    session.add(financial_log)
                    results["synced"] += 1

                results["parks"][park_name] = {"status": "success", "total": len(transactions)}

            if incoming_by_driver:
                driver_keys = list(incoming_by_driver.keys())
                drivers_stmt = select(User).where(
                    or_(
                        User.yandex_driver_id.in_(driver_keys),
                        User.yandex_contractor_id.in_(driver_keys),
                    )
                )
                drivers = (await session.execute(drivers_stmt)).scalars().all()
                for driver in drivers:
                    last_seen = (
                        incoming_by_driver.get(str(driver.yandex_driver_id))
                        or (incoming_by_driver.get(str(driver.yandex_contractor_id)) if driver.yandex_contractor_id else None)
                    )
                    if last_seen:
                        driver.is_active = True
                        # Приводим к naive datetime для сравнения
                        last_seen_naive = last_seen.replace(tzinfo=None) if hasattr(last_seen, 'tzinfo') and last_seen.tzinfo else last_seen
                        driver_last = getattr(driver, "last_active_at", None)
                        driver_last_naive = driver_last.replace(tzinfo=None) if driver_last and hasattr(driver_last, 'tzinfo') and driver_last.tzinfo else driver_last
                        if not driver_last_naive or driver_last_naive < last_seen_naive:
                            driver.last_active_at = last_seen_naive
                        driver.is_core_active = True
                        
                        # PROTOCOL "THE LIVE 300": Обновляем last_transaction_at для машины
                        if driver.current_vehicle_id:
                            vehicle = await session.get(Vehicle, driver.current_vehicle_id)
                            if vehicle:
                                if not vehicle.last_transaction_at or vehicle.last_transaction_at < last_seen_naive:
                                    vehicle.last_transaction_at = last_seen_naive

                reset_stmt = select(User).where(
                    and_(
                        User.is_core_active == True,
                        ~or_(
                            User.yandex_driver_id.in_(driver_keys),
                            User.yandex_contractor_id.in_(driver_keys),
                        )
                    )
                )
                reset_users = (await session.execute(reset_stmt)).scalars().all()
                for user in reset_users:
                    # ИМПЕРСКАЯ ИСКЛЮЧИТЕЛЬНОСТЬ: Аккаунт master НЕПРИКОСНОВЕНЕН
                    if user.username == "master" or user.role == UserRole.MASTER:
                        continue
                    user.is_core_active = False

            await session.commit()
        return results

    async def deep_pull_driver_bindings(
        self,
        window_hours: Optional[int] = 48,
        concurrency: int = 15,
        include_unlinked: bool = True,
    ) -> Dict:
        """
        Усиленный режим: индивидуальные запросы профиля водителя
        для активных (48ч) и всех безмашинных, привязка car_id -> vehicle.
        """
        results = {"status": "success", "processed": 0, "linked": 0, "skipped": 0}

        async with AsyncSessionLocal() as session:
            active_ids: List[str] = []
            if window_hours is not None:
                since = datetime.now() - timedelta(hours=window_hours)
                active_stmt = select(distinct(Transaction.yandex_driver_id)).where(
                    and_(Transaction.yandex_driver_id.isnot(None), Transaction.date >= since)
                )
                active_ids = [row[0] for row in (await session.execute(active_stmt)).all() if row[0]]

            unlinked_ids: List[str] = []
            if include_unlinked:
                unlinked_stmt = select(User).where(
                    and_(
                        or_(User.yandex_driver_id.isnot(None), User.yandex_contractor_id.isnot(None)),
                        User.current_vehicle_id.is_(None),
                        User.is_archived == False,
                    )
                )
                unlinked_users = (await session.execute(unlinked_stmt)).scalars().all()
                for user in unlinked_users:
                    if user.yandex_driver_id:
                        unlinked_ids.append(user.yandex_driver_id)
                    if user.yandex_contractor_id:
                        unlinked_ids.append(user.yandex_contractor_id)

            target_ids = list({str(i) for i in (active_ids + unlinked_ids) if i})
            if not target_ids:
                return results

            # car_id в Яндекс API уникален в рамках парка — маппинг (park, yandex_car_id) -> vehicle.id
            vehicle_map_stmt = select(
                Vehicle.id, Vehicle.yandex_car_id, Vehicle.license_plate, Vehicle.vin, Vehicle.park_name
            )
            vehicle_rows = (await session.execute(vehicle_map_stmt)).all()
            _park_up = lambda p: (p or "PRO").upper()
            vehicle_by_park_yandex = {
                (_park_up(row[4]), row[1]): row[0] for row in vehicle_rows if row[1]
            }
            vehicle_by_plate = {str(row[2]).replace(" ", "").upper(): row[0] for row in vehicle_rows if row[2]}
            vehicle_by_vin = {str(row[3]).upper(): row[0] for row in vehicle_rows if row[3]}

            reverse_map = {}
            vehicle_tasks = []
            for park_name, cfg in settings.PARKS.items():
                if not all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")]):
                    continue
                vehicle_tasks.append(self._fetch_vehicle_profiles_for_park(park_name, cfg))
            vehicle_responses = await asyncio.gather(*vehicle_tasks, return_exceptions=True)
            for response in vehicle_responses:
                if isinstance(response, Exception):
                    continue
                park_name = response.get("park")
                vehicles = response.get("vehicles") or []
                for vehicle_data in vehicles:
                    car_id = (
                        vehicle_data.get("id")
                        or vehicle_data.get("car_id")
                        or (vehicle_data.get("vehicle") or {}).get("id")
                    )
                    plate = (
                        vehicle_data.get("number")
                        or vehicle_data.get("license_plate")
                        or (vehicle_data.get("vehicle") or {}).get("number")
                    )
                    vin = (
                        vehicle_data.get("vin")
                        or (vehicle_data.get("vehicle") or {}).get("vin")
                    )
                    car_status = (
                        vehicle_data.get("status")
                        or (vehicle_data.get("vehicle") or {}).get("status")
                    )
                    driver_ids = []
                    for key in ("current_driver_id", "driver_profile_id", "contractor_profile_id", "driver_id"):
                        if vehicle_data.get(key):
                            driver_ids.append(str(vehicle_data.get(key)))
                    for key in ("driver_ids", "drivers"):
                        vals = vehicle_data.get(key)
                        if isinstance(vals, list):
                            for item in vals:
                                if isinstance(item, dict) and item.get("id"):
                                    driver_ids.append(str(item.get("id")))
                                elif isinstance(item, (str, int)):
                                    driver_ids.append(str(item))
                    driver = vehicle_data.get("driver") or {}
                    if driver.get("id"):
                        driver_ids.append(str(driver.get("id")))
                    driver_profile = vehicle_data.get("driver_profile") or {}
                    if driver_profile.get("id"):
                        driver_ids.append(str(driver_profile.get("id")))

                    for driver_id in driver_ids:
                        reverse_map.setdefault((park_name or "PRO").upper(), {})[driver_id] = {
                            "car_id": str(car_id) if car_id else None,
                            "plate": str(plate) if plate else None,
                            "vin": str(vin) if vin else None,
                            "status": str(car_status) if car_status else None,
                        }

            sem = asyncio.Semaphore(max(1, min(concurrency, 20)))

            async def fetch_profile(driver_id: str):
                async with sem:
                    user_stmt = select(User).where(
                        or_(
                            User.yandex_driver_id == str(driver_id),
                            User.yandex_contractor_id == str(driver_id),
                        )
                    ).limit(1)
                    user = (await session.execute(user_stmt)).scalars().first()
                    if not user:
                        return None, None
                    park = (user.park_name or "PRO").upper()
                    contractor_id = user.yandex_contractor_id or user.yandex_driver_id
                    profile = await self.fetch_driver_profile(park, str(contractor_id))
                    profile_v1 = {}
                    if not profile or not isinstance(profile, dict):
                        profile_v1 = await self.fetch_driver_profile_v1(park, str(user.yandex_driver_id))
                    return user, profile, profile_v1

            tasks = [fetch_profile(driver_id) for driver_id in target_ids]
            profiles = await asyncio.gather(*tasks, return_exceptions=True)

            for item in profiles:
                if isinstance(item, Exception):
                    results["skipped"] += 1
                    continue
                user, profile, profile_v1 = item
                if not user or (not profile and not profile_v1):
                    results["skipped"] += 1
                    continue
                results["processed"] += 1

                car_id = (
                    (profile or {}).get("car_id")
                    or ((profile or {}).get("profile") or {}).get("car_id")
                    or ((profile or {}).get("contractor") or {}).get("car_id")
                    or ((profile or {}).get("vehicle") or {}).get("id")
                    or ((profile or {}).get("car") or {}).get("id")
                    or (self._find_first_vehicle_id(profile) if profile else None)
                )
                profile_obj = profile or {}
                car_meta = self._extract_car_meta(profile) if profile else {}
                plate = car_meta.get("number") or profile_obj.get("car_number")
                vin = car_meta.get("vin") or profile_obj.get("vin")
                car_status = car_meta.get("status") or profile_obj.get("car_status")
                if not car_id and not profile_v1:
                    profile_v1 = await self.fetch_driver_profile_v1((user.park_name or "PRO").upper(), str(user.yandex_driver_id))
                if not car_id and profile_v1:
                    car_id = (
                        profile_v1.get("car_id")
                        or (profile_v1.get("profile") or {}).get("car_id")
                        or (profile_v1.get("vehicle") or {}).get("id")
                        or (profile_v1.get("car") or {}).get("id")
                        or self._find_first_vehicle_id(profile_v1)
                    )
                    car_meta_v1 = self._extract_car_meta(profile_v1)
                    plate = plate or car_meta_v1.get("number") or profile_v1.get("car_number")
                    vin = vin or car_meta_v1.get("vin") or profile_v1.get("vin")
                    car_status = car_status or car_meta_v1.get("status") or profile_v1.get("car_status")

                work_status = (
                    ((profile or {}).get("profile") or {}).get("work_status")
                    or ((profile or {}).get("driver_profile") or {}).get("work_status")
                    or (profile or {}).get("work_status")
                    or ((profile_v1 or {}).get("profile") or {}).get("work_status")
                    or ((profile_v1 or {}).get("driver_profile") or {}).get("work_status")
                    or (profile_v1 or {}).get("work_status")
                )

                vehicle_id = None
                driver_park = _park_up(user.park_name)
                if car_id:
                    vehicle_id = vehicle_by_park_yandex.get((driver_park, str(car_id)))
                if not car_id:
                    park_key = driver_park
                    reverse = reverse_map.get(park_key, {}).get(str(user.yandex_driver_id))
                    if reverse:
                        car_id = reverse.get("car_id")
                        plate = plate or reverse.get("plate")
                        vin = vin or reverse.get("vin")
                        car_status = car_status or reverse.get("status")
                        if car_id:
                            vehicle_id = vehicle_by_park_yandex.get((driver_park, str(car_id)))
                if not vehicle_id and car_id:
                    park = (user.park_name or "PRO").upper()
                    cfg = settings.PARKS.get(park, {})
                    if all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")]):
                        details = await self._request_raw(
                            "GET",
                            f"{self.base_url}/v2/parks/vehicles/car",
                            self._get_headers_for_park(cfg),
                            params={"vehicle_id": str(car_id)},
                        )
                        vehicle_licenses = details.get("vehicle_licenses") or {}
                        vehicle_specs = details.get("vehicle_specifications") or {}
                        park_profile = details.get("park_profile") or {}
                        plate = plate or vehicle_licenses.get("licence_plate_number")
                        vin = vin or vehicle_specs.get("vin")
                        car_status = car_status or park_profile.get("status")
                if not vehicle_id and plate:
                    vehicle_id = vehicle_by_plate.get(str(plate).replace(" ", "").upper())
                if not vehicle_id and vin:
                    vehicle_id = vehicle_by_vin.get(str(vin).upper())

                if not vehicle_id and car_id:
                    try:
                        normalized_plate = str(plate).replace(" ", "").upper() if plate else None
                        if not normalized_plate:
                            normalized_plate = f"UNKNOWN-{str(car_id)[:8].upper()}"
                        
                        # PASSPORT DATA INJECTION: Получаем brand/model через V2 API (парк водителя!)
                        brand = None
                        model = None
                        color = None
                        year = None
                        try:
                            v2_data = await self.get_vehicle_by_id(str(car_id), driver_park)
                            if v2_data:
                                brand = v2_data.get("brand")
                                model = v2_data.get("model")
                                color = v2_data.get("color")
                                year = v2_data.get("year")
                                plate = plate or v2_data.get("number") or v2_data.get("license_plate")
                                vin = vin or v2_data.get("vin")
                                if plate:
                                    normalized_plate = str(plate).replace(" ", "").upper()
                        except Exception as e:
                            logger.debug(f"V2 API call failed for car {car_id}: {e}")
                        
                        vehicle = Vehicle(
                            license_plate=normalized_plate,
                            brand=brand,
                            model=model,
                            color=color,
                            year=year,
                            vin=str(vin).upper() if vin else None,
                            ownership_type="connected",
                            status="service" if car_status and str(car_status).lower() in {"blocked", "not_working", "repairing", "debt_lock", "inactive"} else "working",
                            is_active=True,
                            is_free=False,
                            park_name=(user.park_name or "PRO").upper(),
                            yandex_car_id=str(car_id),
                            last_update=datetime.now(),
                            created_at=datetime.now(),
                        )
                        session.add(vehicle)
                        await session.flush()
                        vehicle_id = vehicle.id
                        vehicle_by_park_yandex[(driver_park, str(car_id))] = vehicle_id
                        vehicle_by_plate[normalized_plate] = vehicle_id
                        if vin:
                            vehicle_by_vin[str(vin).upper()] = vehicle_id
                    except Exception:
                        self._log_sync_issue(
                            f"Driver {user.yandex_driver_id} has car_id {car_id} but vehicle creation failed"
                        )

                if not vehicle_id:
                    if str(work_status).lower() == "working":
                        try:
                            debug_path = Path("/root/dominion/DEBUG_PROFILE.json")
                            with open(debug_path, "a", encoding="utf-8") as f:
                                f.write(json.dumps(profile or profile_v1, ensure_ascii=False) + "\n")
                        except Exception:
                            logger.warning("Failed to write DEBUG_PROFILE.json")
                    results["skipped"] += 1
                    continue

                if user.current_vehicle_id and user.current_vehicle_id != vehicle_id:
                    prev_vehicle = await session.get(Vehicle, user.current_vehicle_id)
                    if prev_vehicle and prev_vehicle.current_driver_id == user.id:
                        prev_vehicle.current_driver_id = None
                        prev_vehicle.yandex_driver_id = None
                        prev_vehicle.is_free = True
                        prev_vehicle.last_update = datetime.now()

                vehicle = await session.get(Vehicle, vehicle_id)
                if vehicle:
                    user.current_vehicle_id = vehicle.id
                    vehicle.current_driver_id = user.id
                    vehicle.yandex_driver_id = str(user.yandex_driver_id)
                    vehicle.is_free = False
                    vehicle.last_update = datetime.now()
                    if car_status and str(car_status).lower() in {"blocked", "not_working", "repairing", "debt_lock", "inactive"}:
                        vehicle.status = "service"
                    
                    # EXORCISM v200.11: Обновляем yandex_current_car JSONB
                    user.yandex_current_car = {
                        "car_id": str(car_id) if car_id else None,
                        "car_number": str(plate).replace(" ", "").upper() if plate else None,
                        "brand": vehicle.brand,
                        "model": vehicle.model,
                        "vin": vehicle.vin,
                    }
                    results["linked"] += 1
                else:
                    results["skipped"] += 1

            await session.commit()

        return results

    async def recalculate_active_dominion(self) -> Dict:
        """
        PROTOCOL "THE LIVE 300" v2 — Строгий пересчёт флага is_active_dominion.
        
        Машина входит в "Имперское Ядро" ТОЛЬКО если:
        1. is_park_car=True (субаренда) И is_active=True И park_name в активных парках
        2. ИЛИ привязанный водитель is_core_active (работает прямо сейчас)
        3. ИЛИ привязанный водитель имел доходные транзакции за 48ч
        4. ИЛИ yandex_driver_id машины имел транзакции за 48ч
        
        СТРОГО: current_driver_id САМА ПО СЕБЕ НЕ ДОСТАТОЧНА.
        Водитель должен быть АКТИВЕН (is_core_active или транзакции 48ч).
        """
        from app.models.all_models import Vehicle, User, Transaction
        
        now = datetime.now()
        threshold_48h = now - timedelta(hours=48)
        
        activated = 0
        deactivated = 0
        
        # Определяем активные парки (только те, у которых есть API-ключи)
        active_park_names = set(self.active_parks.keys()) if self.active_parks else set()
        
        async with AsyncSessionLocal() as session:
            # Получаем только машины из активных парков (PRO в первую очередь)
            if active_park_names:
                stmt = select(Vehicle).where(Vehicle.park_name.in_(active_park_names))
            else:
                stmt = select(Vehicle)
            vehicles = (await session.execute(stmt)).scalars().all()
            
            # Деактивируем ВСЕ машины из неактивных парков
            if active_park_names:
                from sqlalchemy import update as sa_update
                deact_stmt = (
                    sa_update(Vehicle)
                    .where(~Vehicle.park_name.in_(active_park_names))
                    .where(Vehicle.is_active_dominion == True)
                    .values(is_active_dominion=False)
                )
                deact_result = await session.execute(deact_stmt)
                deactivated += deact_result.rowcount
            
            # Получаем ID водителей из "Живых" (is_core_active=True)
            live_drivers_stmt = select(User.id).where(User.is_core_active == True)
            live_driver_ids = set((await session.execute(live_drivers_stmt)).scalars().all())
            
            # Получаем yandex_driver_id водителей с транзакциями за 48ч
            tx_stmt = select(Transaction.yandex_driver_id).where(
                and_(
                    Transaction.amount > 0,
                    Transaction.date >= threshold_48h,
                )
            ).distinct()
            tx_results = await session.execute(tx_stmt)
            active_yandex_ids_from_tx = {str(row[0]) for row in tx_results.fetchall() if row[0]}
            
            # Собираем yandex_driver_id по user_id для быстрого lookup
            user_yandex_ids_stmt = select(User.id, User.yandex_driver_id, User.yandex_contractor_id).where(
                User.yandex_driver_id.isnot(None)
            )
            user_rows = (await session.execute(user_yandex_ids_stmt)).all()
            user_to_yandex_ids = {}
            for uid, ydid, ycid in user_rows:
                ids = set()
                if ydid:
                    ids.add(str(ydid))
                if ycid:
                    ids.add(str(ycid))
                user_to_yandex_ids[uid] = ids
            
            # Обратная связь: User.current_vehicle_id → Vehicle.id
            # (водитель привязан к машине через User.current_vehicle_id)
            vehicle_to_user_ids_stmt = select(User.current_vehicle_id, User.id).where(
                User.current_vehicle_id.isnot(None)
            )
            vu_rows = (await session.execute(vehicle_to_user_ids_stmt)).all()
            vehicle_to_user_ids = {}
            for vid, uid in vu_rows:
                vehicle_to_user_ids.setdefault(vid, set()).add(uid)
            
            for vehicle in vehicles:
                was_active = vehicle.is_active_dominion
                should_be_active = False
                
                # Условие 1: SUBLEASE SHIELD — Парковые (субаренда) машины
                is_sublease = (
                    vehicle.is_park_car 
                    or (vehicle.ownership_type and str(
                        vehicle.ownership_type.value if hasattr(vehicle.ownership_type, 'value') 
                        else vehicle.ownership_type
                    ).lower() == "sublease")
                )
                if is_sublease and vehicle.is_active:
                    should_be_active = True
                
                # Собираем все привязанные user_id: из Vehicle.current_driver_id И User.current_vehicle_id
                bound_user_ids = set()
                if vehicle.current_driver_id:
                    bound_user_ids.add(vehicle.current_driver_id)
                if vehicle.id in vehicle_to_user_ids:
                    bound_user_ids.update(vehicle_to_user_ids[vehicle.id])
                
                # Условие 2: Привязанный водитель is_core_active
                if bound_user_ids & live_driver_ids:
                    should_be_active = True
                
                # Условие 3: Привязанный водитель имел транзакции за 48ч
                for uid in bound_user_ids:
                    if uid in user_to_yandex_ids:
                        driver_yandex_ids = user_to_yandex_ids[uid]
                        if driver_yandex_ids & active_yandex_ids_from_tx:
                            should_be_active = True
                            break
                
                # Условие 4: yandex_driver_id самой машины имел транзакции за 48ч
                if vehicle.yandex_driver_id and str(vehicle.yandex_driver_id) in active_yandex_ids_from_tx:
                    should_be_active = True
                
                # Обновляем флаг
                if should_be_active != was_active:
                    vehicle.is_active_dominion = should_be_active
                    if should_be_active:
                        activated += 1
                    else:
                        deactivated += 1
            
            await session.commit()
        
        logger.info(f"[LIVE 300] Recalculated: +{activated} activated, -{deactivated} deactivated, live_drivers={len(live_driver_ids)}")
        return {
            "status": "success",
            "activated": activated,
            "deactivated": deactivated,
            "live_drivers": len(live_driver_ids),
        }

    async def force_bind_sublease_vehicles(self) -> Dict:
        """
        Принудительная связка водителей для машин.
        Алгоритм PLATE MATCHER: сличение по госномерам.
        """
        results = {"status": "success", "bound": 0, "already_bound": 0, "no_driver": 0, "plate_matched": 0}
        
        def normalize_plate(plate: str) -> str:
            """Нормализация госномера: убираем пробелы, приводим к верхнему регистру."""
            if not plate:
                return ""
            return str(plate).replace(" ", "").replace("-", "").upper()
        
        async with AsyncSessionLocal() as session:
            # ШАГ 1: Все машины без водителя (включая sublease без is_active_dominion)
            # SUBLEASE SHIELD: Включаем все sublease машины независимо от is_active_dominion
            stmt = select(Vehicle).where(
                and_(
                    Vehicle.is_active == True,
                    Vehicle.current_driver_id == None,
                    or_(
                        Vehicle.is_active_dominion == True,
                        Vehicle.is_park_car == True
                    )
                )
            )
            vehicles = (await session.execute(stmt)).scalars().all()
            
            # Добавляем sublease машины (проверяем строковое значение)
            sublease_stmt = select(Vehicle).where(
                and_(
                    Vehicle.is_active == True,
                    Vehicle.current_driver_id == None
                )
            )
            all_vehicles = (await session.execute(sublease_stmt)).scalars().all()
            sublease_vehicles = [
                v for v in all_vehicles 
                if v not in vehicles and str(v.ownership_type).lower() in ('sublease', 'ownershiptype.sublease')
            ]
            vehicles = list(vehicles) + sublease_vehicles
            
            # ШАГ 2: Все водители с данными о машине
            all_drivers_stmt = select(User).where(
                and_(
                    User.is_archived == False,
                    User.current_vehicle_id == None,
                    or_(
                        User.yandex_driver_id.isnot(None),
                        User.yandex_contractor_id.isnot(None)
                    )
                )
            )
            all_drivers = (await session.execute(all_drivers_stmt)).scalars().all()
            
            # Строим индекс водителей по park_name для быстрого поиска
            drivers_by_park = {}
            for driver in all_drivers:
                park = (driver.park_name or "PRO").upper()
                if park not in drivers_by_park:
                    drivers_by_park[park] = []
                drivers_by_park[park].append(driver)
            
            for vehicle in vehicles:
                driver = None
                vehicle_plate = normalize_plate(vehicle.license_plate)
                vehicle_park = (vehicle.park_name or "PRO").upper()
                
                # МЕТОД 1: По yandex_driver_id машины
                if vehicle.yandex_driver_id:
                    driver_stmt = select(User).where(
                        or_(
                            User.yandex_driver_id == vehicle.yandex_driver_id,
                            User.yandex_contractor_id == vehicle.yandex_driver_id
                        )
                    ).limit(1)
                    driver = (await session.execute(driver_stmt)).scalars().first()
                
                # МЕТОД 2: По current_vehicle_id водителя
                if not driver:
                    driver_stmt2 = select(User).where(
                        User.current_vehicle_id == vehicle.id
                    ).limit(1)
                    driver = (await session.execute(driver_stmt2)).scalars().first()
                
                # МЕТОД 3: PLATE MATCHER — сравнение госномеров
                if not driver and vehicle_plate:
                    park_drivers = drivers_by_park.get(vehicle_park, [])
                    for candidate in park_drivers:
                        # Проверяем есть ли у водителя сохраненный госномер
                        if hasattr(candidate, 'car_plate') and candidate.car_plate:
                            candidate_plate = normalize_plate(candidate.car_plate)
                            if candidate_plate == vehicle_plate:
                                driver = candidate
                                results["plate_matched"] += 1
                                break
                
                # МЕТОД 4: Активный водитель из того же парка
                if not driver and vehicle_park:
                    driver_stmt3 = select(User).where(
                        and_(
                            User.park_name == vehicle_park,
                            User.is_core_active == True,
                            User.current_vehicle_id == None,
                            User.is_archived == False
                        )
                    ).limit(1)
                    driver = (await session.execute(driver_stmt3)).scalars().first()
                
                # МЕТОД 5: DEEP SEARCH — Поиск по госномеру во ВСЕХ парках
                if not driver and vehicle_plate:
                    for park_name, park_drivers in drivers_by_park.items():
                        if park_name == vehicle_park:
                            continue  # Уже проверяли
                        for candidate in park_drivers:
                            if hasattr(candidate, 'car_plate') and candidate.car_plate:
                                candidate_plate = normalize_plate(candidate.car_plate)
                                if candidate_plate == vehicle_plate:
                                    driver = candidate
                                    results["plate_matched"] += 1
                                    break
                        if driver:
                            break
                
                # МЕТОД 6: Активный водитель из ЛЮБОГО парка (последняя надежда)
                if not driver:
                    driver_stmt4 = select(User).where(
                        and_(
                            User.is_core_active == True,
                            User.current_vehicle_id == None,
                            User.is_archived == False
                        )
                    ).limit(1)
                    driver = (await session.execute(driver_stmt4)).scalars().first()
                
                if driver:
                    vehicle.current_driver_id = driver.id
                    vehicle.yandex_driver_id = driver.yandex_driver_id
                    vehicle.is_free = False
                    driver.current_vehicle_id = vehicle.id
                    results["bound"] += 1
                    # Убираем водителя из пула доступных
                    if vehicle_park in drivers_by_park and driver in drivers_by_park[vehicle_park]:
                        drivers_by_park[vehicle_park].remove(driver)
                else:
                    results["no_driver"] += 1
            
            await session.commit()
        
        logger.info(f"[PLATE MATCHER] Bound: {results['bound']}, Plate matched: {results['plate_matched']}, No driver: {results['no_driver']}")
        return results

    async def fill_vehicle_passports(self) -> Dict:
        """
        PASSPORT DATA INJECTION: Заполнение brand/model для машин с None.
        Запрашивает данные через V2 API с fallback на дефолтные значения.
        """
        results = {"status": "success", "updated": 0, "failed": 0, "fallback": 0}
        
        # Fallback карта по госномерам (первые буквы часто указывают на марку)
        DEFAULT_BRANDS = {
            "К": "Kia",
            "Х": "Hyundai", 
            "Т": "Toyota",
            "Н": "Nissan",
            "С": "Skoda",
            "В": "Volkswagen",
            "Р": "Renault",
            "М": "Mazda",
            "У": "Unknown",
            "А": "Unknown",
            "О": "Unknown",
            "Е": "Unknown",
        }
        
        async with AsyncSessionLocal() as session:
            # Машины с пустым brand/model (включая строку "None")
            stmt = select(Vehicle).where(
                and_(
                    Vehicle.is_active == True,
                    or_(
                        Vehicle.brand == None,
                        Vehicle.brand == "",
                        Vehicle.brand == "None"
                    )
                )
            )
            vehicles = (await session.execute(stmt)).scalars().all()
            
            for vehicle in vehicles:
                try:
                    updated = False
                    
                    # Метод 1: V2 API (только если API активен)
                    if vehicle.yandex_car_id and self.parks:
                        park_name = (vehicle.park_name or "PRO").upper()
                        v2_data = await self.get_vehicle_by_id(vehicle.yandex_car_id, park_name)
                        
                        if v2_data:
                            brand = v2_data.get("brand")
                            model = v2_data.get("model")
                            
                            if brand and brand != "None":
                                vehicle.brand = brand
                                vehicle.model = model or "—"
                                vehicle.color = v2_data.get("color") or vehicle.color
                                vehicle.year = v2_data.get("year") or vehicle.year
                                results["updated"] += 1
                                updated = True
                    
                    # Метод 2: Fallback по госномеру (ВСЕГДА если API не помог)
                    if not updated and vehicle.license_plate:
                        plate = vehicle.license_plate.upper()
                        first_letter = plate[0] if plate else ""
                        
                        fallback_brand = DEFAULT_BRANDS.get(first_letter, "Автомобиль")
                        vehicle.brand = fallback_brand
                        vehicle.model = "—"
                        results["fallback"] += 1
                        updated = True
                    
                    if not updated:
                        results["failed"] += 1
                        
                except Exception as e:
                    logger.debug(f"Failed to fill passport for {vehicle.license_plate}: {e}")
                    results["failed"] += 1
            
            await session.commit()
        
        logger.info(f"[PASSPORT] Updated: {results['updated']}, Fallback: {results['fallback']}, Failed: {results['failed']}")
        return results

    async def sync_all_parks(self) -> Dict:
        drivers = await self.sync_driver_profiles_multi_park()
        vehicles = await self.sync_vehicles_multi_park()
        transactions = await self.sync_transactions_multi_park()
        deep_pull = await self.deep_pull_driver_bindings(window_hours=None, concurrency=15, include_unlinked=True)
        
        # Принудительная связка субаренды
        sublease_bind = await self.force_bind_sublease_vehicles()
        
        # PASSPORT DATA INJECTION: Заполнение brand/model
        passport_fill = await self.fill_vehicle_passports()
        
        # PROTOCOL "THE LIVE 300": Пересчёт флага активности в конце
        live_300 = await self.recalculate_active_dominion()
        
        return {
            "status": "success",
            "passport_fill": passport_fill,
            "drivers": drivers,
            "vehicles": vehicles,
            "transactions": transactions,
            "deep_pull": deep_pull,
            "sublease_bind": sublease_bind,
            "live_300": live_300,
            "timestamp": datetime.now().isoformat(),
        }

    async def check_parks_health(self) -> Dict:
        results = {}
        for park_name, cfg in settings.PARKS.items():
            if not all([cfg.get("ID"), cfg.get("CLIENT_ID"), cfg.get("API_KEY")]):
                results[park_name] = 403
                continue
            url = f"{self.base_url}/v1/parks/driver-profiles/list"
            payload = self._list_payload(cfg.get("ID"))
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    resp = await client.post(url, headers=self._get_headers_for_park(cfg), json=payload)
                results[park_name] = resp.status_code
            except Exception:
                results[park_name] = 401
        return results

    # ═══════════════════════════════════════════════════════════════════════════
    # REAL-TIME API METHODS — Лёгкие read-only вызовы для Triad виджетов
    # ═══════════════════════════════════════════════════════════════════════════

    async def cleanup_inactive_parks(self) -> Dict:
        """
        Очистка данных для парков БЕЗ валидных API-ключей.
        Все Vehicle и User с park_name не в active_parks → деактивируются.
        Вызывается один раз при старте приложения.
        """
        all_park_names = set(settings.PARKS.keys())  # PRO, GO, PLUS, EXPRESS
        active_park_names = set(self.active_parks.keys())
        inactive_park_names = all_park_names - active_park_names

        if not inactive_park_names:
            logger.info("[CLEANUP] Все парки активны, очистка не требуется.")
            return {"cleaned_parks": [], "vehicles": 0, "users": 0}

        logger.warning(f"[CLEANUP] Деактивация данных для парков без API-ключей: {inactive_park_names}")
        vehicles_cleaned = 0
        users_cleaned = 0

        async with AsyncSessionLocal() as session:
            for park_name in inactive_park_names:
                # Деактивируем автомобили
                v_stmt = (
                    update(Vehicle)
                    .where(Vehicle.park_name == park_name)
                    .values(
                        is_active_dominion=False,
                        is_active=False,
                        status="offline",
                        current_driver_id=None,
                        yandex_driver_id=None,
                    )
                )
                v_result = await session.execute(v_stmt)
                vehicles_cleaned += v_result.rowcount

                # Деактивируем водителей (кроме master)
                u_stmt = (
                    update(User)
                    .where(
                        and_(
                            User.park_name == park_name,
                            User.role != UserRole.MASTER,
                            User.username != "master",
                        )
                    )
                    .values(
                        is_archived=True,
                        is_active=False,
                        is_core_active=False,
                        work_status="not_working",
                        realtime_status="offline",
                    )
                )
                u_result = await session.execute(u_stmt)
                users_cleaned += u_result.rowcount

            await session.commit()

        logger.warning(
            f"[CLEANUP] Готово: парки {inactive_park_names} — "
            f"vehicles={vehicles_cleaned}, users={users_cleaned} деактивировано"
        )
        return {
            "cleaned_parks": list(inactive_park_names),
            "vehicles": vehicles_cleaned,
            "users": users_cleaned,
        }

    async def get_realtime_driver_stats(self, park: str = "PRO") -> Dict:
        """
        REAL-TIME: Получить текущие статусы водителей И автомобилей из Яндекс API.
        on_line = ТОЛЬКО те, у кого current_status НЕ offline.
        active_vehicles = уникальные car_id привязанные к онлайн-водителям.
        Пагинация: если total > limit, делаем доп. запросы.
        НЕ пишет в БД — только read-only для Triad виджета.
        """
        park_upper = park.upper()
        cfg = self.active_parks.get(park_upper)
        if not cfg:
            return {
                "on_line": 0, "free": 0, "in_order": 0, "busy": 0,
                "active_vehicles": 0, "source": "no_keys",
            }

        try:
            url = f"{self.base_url}/v1/parks/driver-profiles/list"
            headers = self._get_headers_for_park(cfg)

            all_profiles = []
            offset = 0
            page_limit = 1000
            total = None

            while True:
                payload = {
                    "query": {
                        "park": {"id": cfg["ID"]},
                        "driver_profile": {"work_status": ["working"]},
                    },
                    "fields": {
                        "driver_profile": ["id"],
                        "current_status": ["status"],
                        "car": ["id"],
                    },
                    "limit": page_limit,
                    "offset": offset,
                }
                async with self._api_semaphore:
                    data = await self._request_list("POST", url, headers, payload)

                profiles = data.get("driver_profiles") or []
                all_profiles.extend(profiles)

                if total is None:
                    total = data.get("total", len(profiles))

                offset += len(profiles)
                if offset >= total or len(profiles) < page_limit:
                    break

            # Подсчёт: on_line = НЕ offline, active_vehicles = уникальные car_id
            free = 0
            in_order = 0
            busy = 0
            active_car_ids = set()

            for p in all_profiles:
                cs = (p.get("current_status") or {}).get("status", "offline").lower()
                if cs == "offline":
                    continue  # НЕ считаем offline как "на линии"

                # Считаем привязанную машину
                car_id = (p.get("car") or {}).get("id")
                if car_id:
                    active_car_ids.add(car_id)

                if cs in ("free", "online", "waiting"):
                    free += 1
                elif cs in ("in_order_free", "in_order_busy", "in_order",
                            "on_order", "driving", "transporting"):
                    in_order += 1
                elif cs in ("busy",):
                    busy += 1
                else:
                    # Неизвестный статус но не offline → считаем free
                    free += 1

            on_line = free + in_order + busy

            logger.info(
                f"[RT-DRIVERS] park={park_upper}: total_working={total} "
                f"online={on_line} free={free} in_order={in_order} busy={busy} "
                f"active_vehicles={len(active_car_ids)}"
            )
            return {
                "on_line": on_line,
                "free": free,
                "in_order": in_order,
                "busy": busy,
                "active_vehicles": len(active_car_ids),
                "source": "yandex_api",
            }
        except Exception as e:
            logger.error(f"[RT-DRIVERS] Ошибка API park={park_upper}: {e}")
            return {
                "on_line": 0, "free": 0, "in_order": 0, "busy": 0,
                "active_vehicles": 0, "source": "error",
            }

    async def get_realtime_vehicle_stats(self, park: str = "PRO") -> Dict:
        """
        REAL-TIME: Получить текущие статусы автомобилей из Яндекс API.
        Формат ответа: cars = [{id, status, number, ...}, ...] — плоский объект.
        Пагинация: если total > limit, делаем доп. запросы.
        НЕ пишет в БД — только read-only для Triad виджета.
        """
        park_upper = park.upper()
        cfg = self.active_parks.get(park_upper)
        if not cfg:
            return {
                "total_active": 0, "working": 0, "no_driver": 0,
                "in_service": 0, "preparation": 0, "source": "no_keys",
            }

        try:
            url = f"{self.base_url}/v1/parks/cars/list"
            headers = self._get_headers_for_park(cfg)

            all_cars = []
            offset = 0
            page_limit = 1000
            api_total = None

            while True:
                payload = {
                    "query": {"park": {"id": cfg["ID"]}},
                    "limit": page_limit,
                    "offset": offset,
                }
                async with self._api_semaphore:
                    data = await self._request_list("POST", url, headers, payload)

                cars = data.get("cars") or []
                all_cars.extend(cars)

                if api_total is None:
                    api_total = data.get("total", len(cars))

                offset += len(cars)
                if offset >= api_total or len(cars) < page_limit:
                    break

            # Подсчёт статусов (формат: car.status напрямую)
            total_active = 0  # Только working
            in_service = 0    # not_working, blocked и т.д.

            for car in all_cars:
                status = str(car.get("status") or "unknown").lower()
                if status == "working":
                    total_active += 1
                elif status in ("not_working", "blocked", "service",
                                "maintenance", "repair"):
                    in_service += 1
                # removed/archived/deleted — не считаем

            # Для определения working/no_driver используем данные из get_realtime_driver_stats
            # (вызывающий код в get_triad_data может использовать on_line из driver stats)
            # Пока: все active — это "работающие" машины
            working = total_active  # Будет уточнено в get_triad_data
            no_driver = 0
            preparation = 0

            logger.info(
                f"[RT-VEHICLES] park={park_upper}: api_total={api_total} "
                f"active(working)={total_active} service={in_service}"
            )
            return {
                "total_active": total_active,
                "working": working,
                "no_driver": no_driver,
                "in_service": in_service,
                "preparation": preparation,
                "source": "yandex_api",
            }
        except Exception as e:
            logger.error(f"[RT-VEHICLES] Ошибка API park={park_upper}: {e}")
            return {
                "total_active": 0, "working": 0, "no_driver": 0,
                "in_service": 0, "preparation": 0, "source": "error",
            }

    async def get_realtime_balances(self, park: str = "PRO") -> Dict:
        """
        REAL-TIME: Получить сумму балансов водителей (остаток к выплате).
        Формат: accounts = [{"balance": "123.45", "id": "..."}]
        Пагинация: если total > limit, делаем доп. запросы.
        НЕ пишет в БД — только read-only для Triad виджета.
        """
        park_upper = park.upper()
        cfg = self.active_parks.get(park_upper)
        if not cfg:
            return {"payout_remain": 0.0, "source": "no_keys"}

        try:
            url = f"{self.base_url}/v1/parks/driver-profiles/list"
            headers = self._get_headers_for_park(cfg)

            payout = 0.0
            offset = 0
            page_limit = 1000
            total = None

            while True:
                payload = {
                    "query": {
                        "park": {"id": cfg["ID"]},
                        "driver_profile": {"work_status": ["working"]},
                    },
                    "fields": {
                        "driver_profile": ["id"],
                        "account": ["balance"],
                    },
                    "limit": page_limit,
                    "offset": offset,
                }
                async with self._api_semaphore:
                    data = await self._request_list("POST", url, headers, payload)

                profiles = data.get("driver_profiles") or []

                for p in profiles:
                    # Формат: "accounts": [{"balance": "123.45", "id": "..."}]
                    accounts = p.get("accounts") or p.get("account") or []
                    balance = 0.0
                    if isinstance(accounts, list) and accounts:
                        try:
                            balance = float(accounts[0].get("balance", 0) or 0)
                            # Сохраняем отрицательные значения для долгов
                            balance = -abs(balance) if balance < 0 else balance
                        except (ValueError, TypeError):
                            balance = 0.0
                    elif isinstance(accounts, dict):
                        try:
                            balance = float(accounts.get("balance", 0) or 0)
                            # Сохраняем отрицательные значения для долгов
                            balance = -abs(balance) if balance < 0 else balance
                        except (ValueError, TypeError):
                            balance = 0.0
                    if balance > 0:
                        payout += balance

                if total is None:
                    total = data.get("total", len(profiles))

                offset += len(profiles)
                if offset >= total or len(profiles) < page_limit:
                    break

            logger.info(f"[RT-BALANCES] park={park_upper}: payout_remain={payout:.2f} (total_drivers={total})")
            return {"payout_remain": round(payout, 2), "source": "yandex_api"}
        except Exception as e:
            logger.error(f"[RT-BALANCES] Ошибка API park={park_upper}: {e}")
            return {"payout_remain": 0.0, "source": "error"}


yandex_sync = YandexSyncService()
