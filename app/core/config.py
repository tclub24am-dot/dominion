# -*- coding: utf-8 -*-
# app/core/config.py
# VERSHINA v200.15: FAIL-FAST — SECRET_KEY и ATS_WEBHOOK_SECRET обязательны

import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


def _clean_api_key(val: str | None) -> str | None:
    """Возвращает None если ключ невалидный: пустой, '()', 'pending', etc."""
    if not val:
        return None
    v = val.strip()
    if v in ("", "()", "pending", "none", "null", "undefined"):
        return None
    return v


class Settings(BaseSettings):
    # --- ОБЩИЕ ---
    PROJECT_NAME: str = "S-GLOBAL_Dominion"
    VERSION: str = "16.9.Nexus"
    PORT: int = 8001  # Порт Мастера
    HOST: str = "0.0.0.0"  # Доступ отовсюду
    PARTNER_NAME: str = "ИП Мкртчян"  # Юридическое лицо партнёра (IT Service Fee)
    
    # --- РЕЖИМ РАБОТЫ ---
    # DEBUG=True: включает X-Tenant-ID в ответах, расширенные логи и т.д.
    # В production ВСЕГДА должен быть False (или не задан)
    DEBUG: bool = False

    # --- БЕЗОПАСНОСТЬ ---
    # FAIL-FAST v200.15: SECRET_KEY ОБЯЗАТЕЛЕН. Нет .env → приложение падает при старте.
    # Никаких дефолтных паролей в production!
    SECRET_KEY: str  # Обязательное поле — pydantic бросит ValidationError если не задано
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    
    # --- БАЗА ДАННЫХ ---
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db/dominion")
    
    # --- ФИНАНСОВАЯ МАТРИЦА (Новая логика Мастера) ---
    TAXI_CONNECTED_RATE: float = 0.03  # 3% для 78 машин (подключки)
    TAXI_SUBLEASE_RATE: float = 0.04   # 4% для 42 машин (субаренда)
    TAXI_DAILY_FIX: float = 450.0      # Ежедневный фикс (300-500р)
    
    # Цены ВкусВилл (с НДС)
    VV_PRICE_DARKSTORE: float = 6599.0
    VV_PRICE_STORE: float = 5883.0
    VV_PRICE_SHMEL: float = 3882.0
    VV_PRICE_ZHUK: float = 2107.0
    
    # Расходы по логистике
    VV_DRIVER_PAY: float = 2000.0      # ЗП водителя за рейс
    VV_FUEL_DAILY: float = 5000.0      # Топливо в день на 5т
    
    # Оверхед (Постоянные расходы)
    FIXED_EXPENSES_MONTHLY: float = 178307.0  # Офис, инет, бух и т.д.
    SALARY_WITH_TAX_MONTHLY: float = 93746.0  # 8 сотрудников + налоги
    
    # --- АВТОСПИСАНИЯ ---
    DRIVER_NEGATIVE_LIMIT: float = -5000.0
    
    # --- MANUAL DRIVER OVERRIDES ---
    MANUAL_DRIVER_OVERRIDES: Optional[str] = os.getenv("MANUAL_DRIVER_OVERRIDES")
    
    # --- YANDEX FLEET API ---
    YANDEX_PARK_ID: Optional[str] = None
    YANDEX_CLIENT_ID: Optional[str] = None
    YANDEX_API_KEY: Optional[str] = None

    # --- YANDEX AUTOSYNC ---
    YANDEX_AUTOSYNC_ENABLED: bool = os.getenv("YANDEX_AUTOSYNC_ENABLED", "true").lower() == "true"
    YANDEX_AUTOSYNC_INTERVAL_SECONDS: int = int(os.getenv("YANDEX_AUTOSYNC_INTERVAL_SECONDS", "300"))  # Heavy cycle (5 min)
    YANDEX_FAST_PULSE_SECONDS: int = int(os.getenv("YANDEX_FAST_PULSE_SECONDS", "60"))  # Fast cycle (statuses, 60s)
    YANDEX_TX_SYNC_WINDOW_MINUTES: int = int(os.getenv("YANDEX_TX_SYNC_WINDOW_MINUTES", "2880"))
    YANDEX_ALLOW_SYNC_NOAUTH: bool = os.getenv("YANDEX_ALLOW_SYNC_NOAUTH", "false").lower() == "true"
    
    # --- MULTI-PARK CONFIGURATION (4 парка) ---
    # ВНИМАНИЕ: _clean_api_key() очищает "()", "pending", пустые строки → None
    # Парк считается активным ТОЛЬКО если ID + CLIENT_ID + API_KEY валидны
    PARKS: dict = {
        "PRO": {
            "ID": _clean_api_key(os.getenv("PRO_YANDEX_PARK_ID")),
            "CLIENT_ID": _clean_api_key(os.getenv("PRO_YANDEX_CLIENT_ID")),
            "API_KEY": _clean_api_key(os.getenv("PRO_YANDEX_API_KEY")),
        },
        "GO": {
            "ID": _clean_api_key(os.getenv("GO_YANDEX_PARK_ID")),
            "CLIENT_ID": _clean_api_key(os.getenv("GO_YANDEX_CLIENT_ID")),
            "API_KEY": _clean_api_key(os.getenv("GO_YANDEX_API_KEY")),
        },
        "PLUS": {
            "ID": _clean_api_key(os.getenv("PLUS_YANDEX_PARK_ID")),
            "CLIENT_ID": _clean_api_key(os.getenv("PLUS_YANDEX_CLIENT_ID")),
            "API_KEY": _clean_api_key(os.getenv("PLUS_YANDEX_API_KEY")),
        },
        "EXPRESS": {
            "ID": _clean_api_key(os.getenv("EXPRESS_YANDEX_PARK_ID")),
            "CLIENT_ID": _clean_api_key(os.getenv("EXPRESS_YANDEX_CLIENT_ID")),
            "API_KEY": _clean_api_key(os.getenv("EXPRESS_YANDEX_API_KEY")),
        },
    }
    
    # --- TELEGRAM БОТЫ ---
    TCLUB_BOT_TOKEN: Optional[str] = None
    SGLOBAL_BOT_TOKEN: Optional[str] = None
    ADMIN_ID: Optional[int] = None
    
    # --- ТЕЛЕФОНИЯ 1ATS (Open API) ---
    ATS_API_KEY: Optional[str] = None
    ATS_DOMAIN: str = "api.1ats.ru"
    # VERSHINA v200.16.4: ATS_WEBHOOK_SECRET — Optional для dev-режима.
    # В production ОБЯЗАТЕЛЬНО задать в .env: ATS_WEBHOOK_SECRET=<random_token>
    # Если не задан — telephony.py логирует WARNING и пропускает webhook без проверки.
    ATS_WEBHOOK_SECRET: Optional[str] = None
    
    # --- ЛОГИСТИКА И GPS ---
    ADVANTUM_API_URL: str = "https://api.advantum.ru/v1" # Добавляем это поле
    ADVANTUM_LOGIN: Optional[str] = None
    ADVANTUM_PASSWORD: Optional[str] = None
    ADVANTUM_TENANT: str = "s-global"  # Часто требуется для API Адвантума
    GLONASS_LOGIN: Optional[str] = None
    GLONASS_PASS: Optional[str] = None
    
    # --- КИС АРТ ---
    KIS_ART_MODE: str = "mock"
    KIS_ART_ENDPOINT: str = "https://api.kis-art.ru/v1/trips"
    KIS_ART_API_KEY: Optional[str] = None

    # --- SAAS MODULES ---
    MODULES_ENABLED: Optional[str] = os.getenv("MODULES_ENABLED")  # "kazna,fleet,..."
    MODULES_DISABLED: Optional[str] = os.getenv("MODULES_DISABLED")  # "security,ai_analyst"
    TRIAL_DAYS: int = int(os.getenv("TRIAL_DAYS", "30"))
    TRIAL_BASE_MODULES: str = os.getenv("TRIAL_BASE_MODULES", "core,messenger")
    
    # --- REDIS CACHE ---
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # --- ORACLE AI (GEMINI 3 FLASH via Ollama Bridge) ---
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3-flash-preview:cloud"
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434/v1"
    ORACLE_TIMEOUT: int = 60
    ORACLE_UPLOAD_DIR: str = "/root/dominion/storage/uploads"

    # --- MIKS / MATRIX / WEBRTC ---
    # VERSHINA v200.16.4: Pydantic native — SettingsConfigDict сам прочитает из .env
    MATRIX_HOMESERVER_URL: str = "http://synapse:8008"
    MATRIX_SERVER_NAME: str = "matrix.dominion.local"
    MATRIX_ACCESS_TOKEN: Optional[str] = None
    MATRIX_ADMIN_ACCESS_TOKEN: Optional[str] = None
    MATRIX_MIKS_ROOM_ID: Optional[str] = None
    MATRIX_OLLAMA_TAG_MODEL: str = "llama3.1:8b"
    MATRIX_ADMIN_SHARED_SECRET: Optional[str] = None
    ASTERISK_WS_URL: str = "wss://89.169.39.111:8089/ws"
    ASTERISK_SIP_REALM: str = "89.169.39.111"
    ASTERISK_SIP_WEBSOCKET_ENDPOINT: str = "sip:system@89.169.39.111"

    # Настройка Pydantic v2
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding='utf-8',
        extra="ignore"  # Игнорировать лишние поля
    )

settings = Settings()
