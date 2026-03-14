# -*- coding: utf-8 -*-
# main.py
# ============================================================
# S-GLOBAL DOMINION — ПРОТОКОЛ «ЕДИНОВЛАСТИЕ ФРОНТЕНДА»
# FastAPI отдаёт ТОЛЬКО: API, Static, SPA fallback, WebSocket
# ============================================================

from datetime import datetime, timedelta
import asyncio
import uvicorn
import logging
import os
from fastapi import FastAPI, Request, Depends, Response, Cookie, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.openapi.utils import get_openapi
from contextlib import asynccontextmanager
from typing import Dict, Optional

# Импорт базы и настроек
from app.database import engine, Base, AsyncSessionLocal
from app.core.config import settings
from sqlalchemy import text, select, and_, or_, func

# Импорт роутеров
from app.api.v1 import auth, kazna, fleet, logistics, warehouse, analytics
from app.api.v1.telephony import webhook_router as telephony_webhook_router, api_router as telephony_api_router
from app.api.v1.miks import router as miks_router
from app.api.v1.parks_info import router as parks_info_router
from app.api.v1.kazna import get_transactions as kazna_transactions_handler
from app.api.v1.partner import router as partners
from app.api.v1.cashflow import router as cashflow_router
from app.api.v1.realtime import router as realtime, ws_router as realtime_ws
from app.api.v1.neural_core import router as neural_core_router
from app.api.v1.messenger import router as messenger_router, ws_router as messenger_ws
from app.api.v1.hr_center import router as hr_center_router

# Импорт security
from app.services.security import get_current_user_from_cookie, get_current_user_optional
from app.services.auth import hash_password
from app.services.ledger_engine import ledger_engine
from app.core.permissions import require_module, has_module_access
from app.core.tenant_middleware import TenantMiddleware, get_current_tenant
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.all_models import User
from app.database import get_db
from fastapi import Request

# 1. НАСТРОЙКА ЛОГИРОВАНИЯ (ОПТИМИЗИРОВАНО ДЛЯ СТАБИЛЬНОСТИ)
logging.basicConfig(
    level=logging.WARNING,  # 🔒 WARNING вместо INFO (уменьшает нагрузку на CPU)
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("DominionCore")

# 🔒 ОТКЛЮЧАЕМ VERBOSE ЛОГИРОВАНИЕ SQLALCHEMY (убивает CPU!)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.dialects").setLevel(logging.WARNING)

# 2. ИНИЦИАЛИЗАЦИЯ ШАБЛОНОВ NEXUS (Jinja2) — нужен для HTMX-виджетов в API-роутерах
TEMPLATE_DIR = "app/templates"
if not os.path.exists(TEMPLATE_DIR):
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    os.makedirs(os.path.join(TEMPLATE_DIR, "modules"), exist_ok=True)

templates = Jinja2Templates(directory=TEMPLATE_DIR)

# 3. ЖИЗНЕННЫЙ ЦИКЛ (Lifespan)
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    МИНИМАЛЬНЫЙ LIFESPAN БЕЗ БЛОКИРОВАНИЯ
    (Scheduler и assets отключены для стабильности)
    """
    logger.info("🟢 ДОМИНИОН: ГОТОВ К БОЯМ")
    watcher_task = None
    ledger_task = None
    fast_task = None
    heavy_task = None
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS is_free BOOLEAN DEFAULT TRUE")
            )
            await session.execute(
                text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS thread_id TEXT")
            )
            await session.execute(
                text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS parent_id INTEGER")
            )
            await session.execute(
                text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS attachments JSONB DEFAULT '[]'::jsonb")
            )
            await session.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS photo_url VARCHAR")
            )
            await session.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS yandex_contractor_id VARCHAR")
            )
            await session.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMPTZ")
            )
            await session.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_archived BOOLEAN DEFAULT FALSE")
            )
            await session.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_core_active BOOLEAN DEFAULT FALSE")
            )
            await session.execute(
                text(
                    "DO $$ BEGIN "
                    "IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN "
                    "CREATE TYPE user_role AS ENUM ('master','director','admin','convoy_head','manager'); "
                    "END IF; "
                    "END $$;"
                )
            )
            await session.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS role user_role")
            )
            await session.execute(
                text(
                    "UPDATE users SET role = CASE "
                    "WHEN role IS NULL THEN 'manager'::user_role "
                    "WHEN lower(role::text) IN ('master','director','admin','convoy_head','manager') THEN lower(role::text)::user_role "
                    "WHEN lower(role::text) = 'finance' THEN 'director'::user_role "
                    "WHEN lower(role::text) = 'mechanic' THEN 'admin'::user_role "
                    "WHEN lower(role::text) = 'driver' THEN 'manager'::user_role "
                    "ELSE 'manager'::user_role END"
                )
            )
            await session.execute(
                text(
                    "ALTER TABLE users ALTER COLUMN role TYPE user_role USING (role::user_role)"
                )
            )
            await session.execute(
                text("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'manager'")
            )
            await session.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS oracle_archive ("
                    "id SERIAL PRIMARY KEY, "
                    "title TEXT DEFAULT 'AI Watcher', "
                    "channel TEXT DEFAULT 'MASTER', "
                    "content TEXT NOT NULL, "
                    "severity TEXT DEFAULT 'info', "
                    "meta JSONB DEFAULT '{}'::jsonb, "
                    "created_at TIMESTAMPTZ DEFAULT NOW()"
                    ")"
                )
            )
            await session.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS contract_terms ("
                    "id SERIAL PRIMARY KEY, "
                    "vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE CASCADE, "
                    "driver_id INTEGER REFERENCES users(id) ON DELETE SET NULL, "
                    "park_name VARCHAR DEFAULT 'PRO', "
                    "is_default BOOLEAN DEFAULT FALSE, "
                    "partner_daily_rent DOUBLE PRECISION DEFAULT 0.0, "
                    "driver_daily_rent DOUBLE PRECISION DEFAULT 0.0, "
                    "commission_rate DOUBLE PRECISION DEFAULT 0.03, "
                    "day_off_rate DOUBLE PRECISION DEFAULT 0.0, "
                    "is_repair BOOLEAN DEFAULT FALSE, "
                    "is_day_off BOOLEAN DEFAULT FALSE, "
                    "is_idle BOOLEAN DEFAULT FALSE, "
                    "meta JSONB DEFAULT '{}'::jsonb, "
                    "created_at TIMESTAMPTZ DEFAULT NOW(), "
                    "updated_at TIMESTAMPTZ DEFAULT NOW()"
                    ")"
                )
            )
            await session.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS contract_term_history ("
                    "id SERIAL PRIMARY KEY, "
                    "contract_term_id INTEGER REFERENCES contract_terms(id) ON DELETE CASCADE, "
                    "vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE CASCADE, "
                    "changed_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, "
                    "changed_by VARCHAR, "
                    "changes JSONB DEFAULT '{}'::jsonb, "
                    "note TEXT, "
                    "changed_at TIMESTAMPTZ DEFAULT NOW()"
                    ")"
                )
            )
            await session.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS financial_log ("
                    "id SERIAL PRIMARY KEY, "
                    "vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE SET NULL, "
                    "driver_id INTEGER REFERENCES users(id) ON DELETE SET NULL, "
                    "park_name VARCHAR DEFAULT 'PRO', "
                    "entry_type VARCHAR DEFAULT 'auto_deduction', "
                    "amount DOUBLE PRECISION DEFAULT 0.0, "
                    "note TEXT, "
                    "meta JSONB DEFAULT '{}'::jsonb, "
                    "created_at TIMESTAMPTZ DEFAULT NOW()"
                    ")"
                )
            )
            await session.commit()
            master_username = os.getenv("MASTER_BOOTSTRAP_USERNAME", "master")
            master_password = os.getenv("MASTER_BOOTSTRAP_PASSWORD", "MasterSpartak777!")
            master_full_name = os.getenv("MASTER_BOOTSTRAP_NAME", "Master Spartak")
            result = await session.execute(
                text("SELECT id FROM users WHERE username = :u LIMIT 1"),
                {"u": master_username}
            )
            if not result.first():
                await session.execute(
                    text(
                        "INSERT INTO users (username, hashed_password, full_name, role, is_active, "
                        "can_see_treasury, can_see_fleet, can_see_analytics, can_see_logistics, "
                        "can_see_hr, can_edit_users, rating, park_name, language, theme) "
                        "VALUES (:u, :p, :n, 'master', TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, 5.0, 'PRO', 'ru', 'dominion')"
                    ),
                    {"u": master_username, "p": hash_password(master_password), "n": master_full_name}
                )
                await session.commit()
        async def daily_ledger_loop():
            while True:
                now = datetime.now()
                next_midnight = (now + timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                sleep_seconds = (next_midnight - now).total_seconds()
                await asyncio.sleep(max(5, sleep_seconds))
                try:
                    result = await ledger_engine.run_daily_deductions()
                    logger.warning(
                        "Ledger auto-deduction: processed=%s deducted=%s alerts=%s",
                        result.get("processed"),
                        result.get("deducted"),
                        result.get("alerts"),
                    )
                except Exception:
                    logger.warning("Ledger auto-deduction failed", exc_info=True)
        ledger_task = asyncio.create_task(daily_ledger_loop())
        # ================================================================
        # ДВУХКОНТУРНЫЙ ПУЛЬС СИСТЕМЫ
        # Контур 1 (FAST, 60s): Статусы водителей, онлайн-данные, балансы
        #   — Лёгкие запросы, мгновенное отражение реальности
        # Контур 2 (HEAVY, 300s): Профили, транспорт, транзакции, reestry
        #   — Тяжёлая синхронизация, полное обновление из Яндекса
        # ================================================================
        from app.services.yandex_sync_service import yandex_sync

        # CLEANUP: Деактивируем данные парков без API-ключей (GO/PLUS/EXPRESS если "()")
        try:
            cleanup = await yandex_sync.cleanup_inactive_parks()
            logger.warning("Park cleanup on startup: %s", cleanup)
        except Exception:
            logger.warning("Park cleanup failed", exc_info=True)

        async def fast_pulse_loop():
            """Контур 1 — БЫСТРЫЙ ПУЛЬС (60s): статусы, онлайн, балансы."""
            await asyncio.sleep(8)
            while True:
                if not settings.YANDEX_AUTOSYNC_ENABLED or not yandex_sync.enabled:
                    await asyncio.sleep(settings.YANDEX_FAST_PULSE_SECONDS)
                    continue
                try:
                    for park_name in yandex_sync.active_parks:
                        try:
                            stats = await yandex_sync.get_realtime_driver_stats(park_name)
                            balances = await yandex_sync.get_realtime_balances(park_name)
                            logger.warning(
                                "⚡ Fast pulse [%s]: online=%s free=%s in_order=%s vehicles=%s balance=%.0f",
                                park_name,
                                stats.get("on_line", 0),
                                stats.get("free", 0),
                                stats.get("in_order", 0),
                                stats.get("active_vehicles", 0),
                                balances.get("total_balance", 0),
                            )
                        except Exception:
                            logger.warning("Fast pulse [%s] failed", park_name, exc_info=True)
                    # Инвалидируем кэш Триады чтобы следующий запрос получил свежие данные
                    _triad_cache.clear()
                except Exception:
                    logger.warning("Fast pulse loop error", exc_info=True)
                await asyncio.sleep(settings.YANDEX_FAST_PULSE_SECONDS)

        async def heavy_sync_loop():
            """Контур 2 — ТЯЖЁЛАЯ СИНХРОНИЗАЦИЯ (300s): профили, транспорт, транзакции."""
            await asyncio.sleep(15)
            while True:
                if not settings.YANDEX_AUTOSYNC_ENABLED or not yandex_sync.enabled:
                    await asyncio.sleep(settings.YANDEX_AUTOSYNC_INTERVAL_SECONDS)
                    continue
                try:
                    drivers = await yandex_sync.sync_driver_profiles_multi_park()
                    vehicles = await yandex_sync.sync_vehicles_multi_park()
                    transactions = await yandex_sync.sync_transactions_multi_park(
                        window_minutes=settings.YANDEX_TX_SYNC_WINDOW_MINUTES
                    )
                    # Синхронизация типа владения (Парк/Подключение)
                    ownership = await yandex_sync.sync_vehicle_ownership()
                    logger.warning(
                        "🔄 Heavy sync: drivers=%s vehicles=%s tx=%s ownership_park=%s",
                        drivers.get("created"),
                        vehicles.get("synced"),
                        transactions.get("synced"),
                        ownership.get("updated_park", 0),
                    )
                    # Инвалидируем кэш Триады
                    _triad_cache.clear()
                except Exception:
                    logger.warning("Heavy sync failed", exc_info=True)
                await asyncio.sleep(settings.YANDEX_AUTOSYNC_INTERVAL_SECONDS)

        fast_task = asyncio.create_task(fast_pulse_loop())
        heavy_task = asyncio.create_task(heavy_sync_loop())
    except Exception as e:
        logger.warning(f"⚠️ Не удалось обновить схему vehicles.is_free: {e}")
    
    # IRON SHIELD v200.16: Oracle handshake запускается в lifespan (event loop гарантирован)
    try:
        from app.services.oracle_service import oracle_service
        if oracle_service.api_key and oracle_service.api_key != "pending_configure_in_google_ai_studio":
            asyncio.create_task(oracle_service._check_handshake())
            logger.info("🔮 Oracle handshake task scheduled")
    except Exception as e:
        logger.warning(f"⚠️ Oracle handshake scheduling failed: {e}")
    
    yield
    if watcher_task:
        watcher_task.cancel()
    if ledger_task:
        ledger_task.cancel()
    if fast_task:
        fast_task.cancel()
    if heavy_task:
        heavy_task.cancel()
    logger.info("🛑 ДОМИНИОН: КОНСЕРВАЦИЯ")

# ============================================================
# OAUTH2 BEARER — глобальная схема авторизации для Swagger UI
# Мастер Спартак вставляет токен один раз — замочки на всех эндпоинтах
# ============================================================
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)

app = FastAPI(
    title="S-GLOBAL DOMINION",
    description=(
        "## 🏆 VERSHINA v200.11 — Абсолютное техническое превосходство\n\n"
        "**Авторизация:** Нажмите кнопку **Authorize** (🔒) вверху страницы, "
        "введите токен в поле `Bearer <ваш_токен>` или получите токен через "
        "`POST /api/v1/auth/token`."
    ),
    version="18.0.SPA",
    lifespan=lifespan,
    swagger_ui_parameters={
        "persistAuthorization": True,       # токен сохраняется между перезагрузками
        "displayRequestDuration": True,     # время выполнения запроса
        "filter": True,                     # поиск по эндпоинтам
        "tryItOutEnabled": True,            # Try it out включён по умолчанию
    },
)


def custom_openapi():
    """
    КАСТОМНЫЙ OpenAPI SCHEMA — добавляет глобальный BearerAuth security scheme.
    Все эндпоинты получают иконку замочка 🔒 в Swagger UI.
    """
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # Добавляем securitySchemes в components
    openapi_schema.setdefault("components", {})
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "JWT токен авторизации. Получите токен через `POST /api/v1/auth/token`, "
                "затем вставьте его сюда в формате: `<ваш_токен>` (без слова Bearer)."
            ),
        }
    }

    # Глобальный security на верхнем уровне — применяется ко всем операциям
    # (Swagger UI покажет замочек на каждом эндпоинте)
    openapi_schema["security"] = [{"BearerAuth": []}]

    # Также явно прописываем security в каждую операцию для надёжности,
    # кроме webhook-эндпоинтов телефонии — они защищаются секретом, не JWT.
    for path, path_data in openapi_schema.get("paths", {}).items():
        is_telephony_webhook = path.startswith("/api/v1/telephony/webhook/")
        for operation in path_data.values():
            if isinstance(operation, dict):
                if is_telephony_webhook:
                    operation["security"] = []
                    operation["description"] = (
                        (operation.get("description", "") + "\n\n").strip()
                        + "Доступ открыт для внешних систем телефонии. Защита: `Authorization: Bearer <ATS_WEBHOOK_SECRET>`, `X-Webhook-Token` или `X-Webhook-Signature`."
                    ).strip()
                else:
                    operation.setdefault("security", [{"BearerAuth": []}])

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# 4. ПРОТОКОЛ CORS (Связи между мирами)
# ВАЖНО: allow_origins=["*"] + allow_credentials=True — невалидная комбинация по спецификации CORS.
# Браузеры блокируют такие запросы. Указываем конкретные домены Цитадели.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://s-global.space",
        "http://localhost:5173",   # Vite dev server
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 5. TENANT ISOLATION MIDDLEWARE (v200.12) — SaaS Мультитенантность
app.add_middleware(TenantMiddleware)

# 5. МОНТАЖ СТАТИЧЕСКИХ МИРОВ
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/storage", StaticFiles(directory="storage"), name="storage")  # PDF путевые листы

# 6. ПОДКЛЮЧЕНИЕ МОДУЛЕЙ УПРАВЛЕНИЯ (API v1)
app.include_router(auth, prefix="/api/v1/auth", tags=["Врата"])
app.include_router(realtime, tags=["Real-Time Engine: Вездещее Око 2026"], dependencies=[Depends(require_module("fleet"))])
app.include_router(realtime_ws, tags=["WebSocket Endpoints"])  # WebSocket без зависимостей
app.include_router(fleet, prefix="/api/v1/fleet", tags=["Флот"], dependencies=[Depends(require_module("fleet"))])
app.include_router(kazna, prefix="/api/v1/kazna", tags=["Казна"], dependencies=[Depends(require_module("kazna"))])
app.include_router(logistics, prefix="/api/v1/logistics", tags=["Логистика"], dependencies=[Depends(require_module("logistics"))])
app.include_router(warehouse, prefix="/api/v1/warehouse", tags=["Склад"], dependencies=[Depends(require_module("warehouse"))])
app.include_router(analytics, prefix="/api/v1/analytics", tags=["Аналитика"], dependencies=[Depends(require_module("kazna"))])
app.include_router(partners, prefix="/api/v1/partners", tags=["Партнёры"], dependencies=[Depends(require_module("partners"))])
app.include_router(cashflow_router, prefix="/api/v1/cashflow", tags=["CashFlow: Календарь будущих обязательств v30.0"], dependencies=[Depends(require_module("kazna"))])
app.include_router(neural_core_router, tags=["Neural Core"])
app.include_router(messenger_router, tags=["Imperial Messenger"], dependencies=[Depends(require_module("messenger"))])
# VERSHINA v200.16.3: Webhook-роутер БЕЗ JWT/модульных зависимостей — для внешних ATS (1ATS, Asterisk)
app.include_router(telephony_webhook_router, prefix="/api/v1/telephony", tags=["Телефония: Webhooks"])
# Внутренний API телефонии — с полной авторизацией и модульной защитой
app.include_router(telephony_api_router, prefix="/api/v1/telephony", tags=["Телефония"], dependencies=[Depends(require_module("telephony"))])
app.include_router(miks_router, prefix="/api/v1/miks", tags=["MIKS"], dependencies=[Depends(require_module("messenger"))])
app.include_router(parks_info_router, prefix="/api/v1/fleet", tags=["Parks Info"])
app.include_router(hr_center_router, prefix="/api/v1/hr", tags=["HR Center: LOGIST-PAY v200.16.6"])
app.include_router(messenger_ws, tags=["WebSocket Messenger"])  # WebSocket без зависимостей

# Legacy NOAUTH sets (для обратной совместимости с YANDEX_ALLOW_SYNC_NOAUTH)
_FLEET_API_NOAUTH = {
    "/api/v1/fleet/triad-data",
    "/api/v1/fleet/legion-data",
    "/api/v1/fleet/drivers-list-data",
    "/api/v1/fleet/vehicles-list-data",
    "/api/v1/fleet/command-data",
}

# Триада Власти — вне require_module("fleet"), чтобы работать без cookie при YANDEX_ALLOW_SYNC_NOAUTH
# Кеш real-time данных (30 секунд TTL) чтобы не долбить Яндекс API при каждом F5
_triad_cache: Dict[str, tuple] = {}  # park -> (timestamp, data)
_TRIAD_CACHE_TTL = 30  # секунд

@app.get("/api/v1/fleet/triad-data", tags=["Флот"])
async def get_triad_data(
    park: str = "PRO",
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Триада Власти v2: Гибридный движок (API + DB) с кешем 30 сек."""
    from app.services.analytics_engine import AnalyticsEngine
    from app.services.yandex_sync_service import yandex_sync
    import time

    if current_user is None and not getattr(settings, "YANDEX_ALLOW_SYNC_NOAUTH", False):
        return JSONResponse(status_code=401, content={"error": "unauthorized"})

    park_key = (park or "ALL").upper()

    # Проверяем кеш
    cached = _triad_cache.get(park_key)
    if cached:
        cached_time, cached_data = cached
        if time.time() - cached_time < _TRIAD_CACHE_TTL:
            return JSONResponse(content=cached_data)

    try:
        data = await AnalyticsEngine.get_triad_data(
            db, park=park_key, yandex_sync=yandex_sync
        )
        # Сохраняем в кеш
        _triad_cache[park_key] = (time.time(), data)
        return JSONResponse(content=data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=200,
            content={"error": "triad_failed", "detail": str(e),
                     "finance": {}, "performers": {}, "assets": {}, "ops_summary": {}},
        )

@app.get("/health")
async def health():
    """Проверка живости для nginx/мониторинга — без авторизации."""
    return {"status": "ok", "service": "dominion"}

# ============================================================
# 7. LOCKDOWN MIDDLEWARE — ПРОТОКОЛ «ЕДИНОВЛАСТИЕ ФРОНТЕНДА»
# SPA-пути пропускаем (React сам проверит auth)
# API-пути проверяем JWT → 401 JSON если нет токена
# ============================================================
@app.middleware("http")
async def lockdown_middleware(request: Request, call_next):
    path = request.url.path

    # Публичные пути — пропускаем без проверки
    # VERSHINA v200.16.3: добавлены /docs, /openapi.json, /redoc, /api/v1/auth/token,
    # /api/v1/telephony/webhook/ для Swagger UI и внешних ATS-систем
    public_prefixes = [
        "/static", "/storage", "/assets", "/health",
        "/docs", "/openapi.json", "/redoc",
        "/api/v1/auth/login", "/api/v1/auth/token",
        "/api/v1/telephony/webhook/",
    ]
    if any(path.startswith(p) for p in public_prefixes):
        return await call_next(request)

    # SPA пути (не API) — всегда пропускаем, React сам проверит auth
    if not path.startswith("/api/"):
        return await call_next(request)

    # API: YANDEX_ALLOW_SYNC_NOAUTH — пропускаем fleet/neural API без auth
    if settings.YANDEX_ALLOW_SYNC_NOAUTH:
        if path in _FLEET_API_NOAUTH:
            return await call_next(request)
        if path.startswith("/api/v1/fleet/") or path.startswith("/api/v1/neural/"):
            return await call_next(request)

    # API: публичный login endpoint
    if path == "/api/v1/auth/login":
        return await call_next(request)

    # API пути — проверяем auth (cookie token)
    token = request.cookies.get("access_token")
    if not token:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})

    # Токен есть — пропускаем дальше (валидация в Depends)
    return await call_next(request)

# 8. NEXUS RENDER ENGINE (Для HTMX-фрагментов — оставлен для API-виджетов)
@app.get("/api/v1/nexus/widget/{widget_name}", response_class=HTMLResponse)
async def render_nexus_widget(
    widget_name: str, 
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("core"))
):
    """
    Универсальный рендерер виджетов для Nexus Dashboard с автоматическим fallback.
    Ищет шаблон сначала в папке widgets/, потом в корне templates/.
    """
    try:
        # Авто-поиск шаблона (в папке widgets или в корне)
        template_path = f"widgets/{widget_name}.html"
        template_full_path = os.path.join(TEMPLATE_DIR, template_path)
        
        if not os.path.exists(template_full_path):
            # Fallback на корневую папку templates/
            template_path = f"{widget_name}.html"
            template_full_path = os.path.join(TEMPLATE_DIR, template_path)
        
        if not os.path.exists(template_full_path):
            # Если шаблон не найден, возвращаем пустой виджет
            logger.warning(f"Nexus Widget не найден: {widget_name}")
            return HTMLResponse(
                content="<div class='p-2 text-yellow-500'>⚠️ Widget Offline</div>",
                status_code=200
            )

        return templates.TemplateResponse(
            template_path, 
            {
                "request": request, 
                "data": {"status": "LIVE"}, 
                "current_user": current_user
            }
        )
    except Exception as e:
        logger.error(f"!!! КРИТИЧЕСКИЙ СБОЙ NEXUS ({widget_name}): {e}", exc_info=True)
        return HTMLResponse(
            content="<div class='p-2 text-red-500'>⚠️ Widget Offline</div>",
            status_code=200
        )

# 9. API ALIASES (совместимость)
@app.get("/api/v1/transactions", response_class=HTMLResponse)
async def transactions_alias(
    request: Request,
    limit: int = 10,
    offset: int = 0,
    category: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("kazna"))
):
    """
    Алиас для транзакций Казны (совместимость с /api/v1/transactions).
    """
    return await kazna_transactions_handler(
        request=request,
        limit=limit,
        offset=offset,
        category=category,
        from_date=from_date,
        to_date=to_date,
        db=db,
        current_user=current_user
    )

# ============================================================
# 10. SPA FRONTEND — ПРОТОКОЛ «ЕДИНОВЛАСТИЕ ФРОНТЕНДА»
# React SPA assets + catch-all fallback
# ============================================================

# React SPA assets (Vite build output)
_SPA_ASSETS_DIR = os.path.join("frontend", "dist", "assets")
if os.path.isdir(_SPA_ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=_SPA_ASSETS_DIR), name="spa_assets")

# SPA catch-all (ПОСЛЕДНИЙ роут — после всех API)
@app.get("/{full_path:path}")
async def spa_fallback(request: Request, full_path: str):
    """Все не-API пути → React SPA index.html"""
    index_path = os.path.join("frontend", "dist", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return JSONResponse(status_code=503, content={"detail": "Frontend not built. Run: cd frontend && npm run build"})

# ============================================================
# 11. EXCEPTION HANDLERS
# ============================================================
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """404: API → JSON, всё остальное → SPA index.html"""
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    # Всё остальное — SPA
    index_path = os.path.join("frontend", "dist", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return JSONResponse(status_code=404, content={"detail": "SPA not built"})

if __name__ == "__main__":
    # Запуск Ядра на порту 8001
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=False)
