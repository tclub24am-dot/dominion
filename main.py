# -*- coding: utf-8 -*-
# main.py

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
from contextlib import asynccontextmanager
from typing import Dict, Optional

# Импорт базы и настроек
from app.database import engine, Base, AsyncSessionLocal
from app.core.config import settings
from sqlalchemy import text, select, and_, or_, func

# Импорт роутеров
from app.api.v1 import auth, kazna, fleet, logistics, warehouse, analytics
from app.api.v1.fleet import pages_router as fleet_pages
from app.api.v1.kazna import get_transactions as kazna_transactions_handler
from app.api.v1.partner import router as partners
from app.api.v1.cashflow import router as cashflow_router
from app.api.v1.realtime import router as realtime, ws_router as realtime_ws
from app.api.v1.neural_core import router as neural_core_router
from app.api.v1.messenger import router as messenger_router, ws_router as messenger_ws

# Импорт security
from app.services.security import get_current_user_from_cookie, get_current_user_optional
from app.services.auth import hash_password
from app.services.ledger_engine import ledger_engine
from app.core.permissions import require_module, has_module_access
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

# 2. ИНИЦИАЛИЗАЦИЯ ШАБЛОНОВ NEXUS (Jinja2)
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
                        "VALUES (:u, :p, :n, 'master', TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, 5.0, 'PRO', 'ru', 'ivory')"
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

app = FastAPI(
    title="S-GLOBAL Dominion", 
    version="17.0.Nexus", 
    lifespan=lifespan
)

# 4. ПРОТОКОЛ CORS (Связи между мирами)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 5. МОНТАЖ СТАТИЧЕСКИХ МИРОВ
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/storage", StaticFiles(directory="storage"), name="storage")  # PDF путевые листы

# 6. ПОДКЛЮЧЕНИЕ МОДУЛЕЙ УПРАВЛЕНИЯ (API v1)
app.include_router(auth, prefix="/api/v1/auth", tags=["Врата"])
app.include_router(realtime, tags=["Real-Time Engine: Вездещее Око 2026"], dependencies=[Depends(require_module("fleet"))])
app.include_router(realtime_ws, tags=["WebSocket Endpoints"])  # WebSocket без зависимостей
app.include_router(fleet, prefix="/api/v1/fleet", tags=["Флот"], dependencies=[Depends(require_module("fleet"))])

# РЕЕСТРЫ: регистрируем ДО fleet_pages, иначе /fleet/vehicles-list матчится как /fleet/vehicle/{id} с vehicle_id="list"
@app.get("/fleet/vehicles-list", response_class=HTMLResponse)
async def fleet_vehicles_list_page(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    if current_user and not has_module_access(current_user, "fleet"):
        raise HTTPException(status_code=403, detail="Нет доступа к Флоту")
    return templates.TemplateResponse(
        "modules/fleet_vehicles_list.html",
        {"request": request, "current_user": current_user}
    )

@app.get("/fleet/drivers-list", response_class=HTMLResponse)
async def fleet_drivers_list_page(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    if current_user and not has_module_access(current_user, "fleet"):
        raise HTTPException(status_code=403, detail="Нет доступа к Флоту")
    return templates.TemplateResponse(
        "modules/fleet_drivers_list.html",
        {"request": request, "current_user": current_user}
    )

@app.get("/fleet/calendar", response_class=HTMLResponse)
async def fleet_calendar_page(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    if current_user and not has_module_access(current_user, "fleet"):
        raise HTTPException(status_code=403, detail="Нет доступа к Флоту")
    return templates.TemplateResponse(
        "modules/fleet_calendar.html",
        {"request": request, "current_user": current_user}
    )

@app.get("/fleet/periodic-charges", response_class=HTMLResponse)
async def fleet_periodic_charges_page(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    if current_user and not has_module_access(current_user, "fleet"):
        raise HTTPException(status_code=403, detail="Нет доступа к Флоту")
    return templates.TemplateResponse(
        "modules/fleet_periodic_charges.html",
        {"request": request, "current_user": current_user}
    )

@app.get("/fleet/legion", response_class=HTMLResponse)
async def fleet_legion_page(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    if current_user and not has_module_access(current_user, "fleet"):
        raise HTTPException(status_code=403, detail="Нет доступа к Флоту")
    return templates.TemplateResponse(
        "modules/fleet_legion.html",
        {"request": request, "current_user": current_user}
    )

app.include_router(fleet_pages, tags=["Fleet Pages"])
app.include_router(kazna, prefix="/api/v1/kazna", tags=["Казна"], dependencies=[Depends(require_module("kazna"))])
app.include_router(logistics, prefix="/api/v1/logistics", tags=["Логистика"], dependencies=[Depends(require_module("logistics"))])
app.include_router(warehouse, prefix="/api/v1/warehouse", tags=["Склад"], dependencies=[Depends(require_module("warehouse"))])
app.include_router(analytics, prefix="/api/v1/analytics", tags=["Аналитика"], dependencies=[Depends(require_module("kazna"))])
app.include_router(partners, prefix="/api/v1/partners", tags=["Партнёры"], dependencies=[Depends(require_module("partners"))])
app.include_router(cashflow_router, prefix="/api/v1/cashflow", tags=["CashFlow: Календарь будущих обязательств v30.0"], dependencies=[Depends(require_module("kazna"))])
app.include_router(neural_core_router, tags=["Neural Core"])
app.include_router(messenger_router, tags=["Imperial Messenger"], dependencies=[Depends(require_module("messenger"))])
app.include_router(messenger_ws, tags=["WebSocket Messenger"])  # WebSocket без зависимостей

# Новые страницы флота и API триады: без редиректа при YANDEX_ALLOW_SYNC_NOAUTH
_FLEET_PAGES_NOAUTH = {
    "/fleet/vehicles-list", "/fleet/drivers-list", "/fleet/legion",
    "/fleet/calendar", "/fleet/periodic-charges",
}
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

@app.middleware("http")
async def lockdown_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/static") or path.startswith("/storage"):
        return await call_next(request)
    if path == "/health":
        return await call_next(request)
    if path.startswith("/fleet/drivers") and settings.YANDEX_ALLOW_SYNC_NOAUTH:
        return await call_next(request)
    if path in _FLEET_PAGES_NOAUTH and settings.YANDEX_ALLOW_SYNC_NOAUTH:
        return await call_next(request)
    if path in _FLEET_API_NOAUTH and settings.YANDEX_ALLOW_SYNC_NOAUTH:
        return await call_next(request)
    if path.startswith("/api/v1/fleet/") and settings.YANDEX_ALLOW_SYNC_NOAUTH:
        return await call_next(request)
    if path.startswith("/api/v1/neural/") and settings.YANDEX_ALLOW_SYNC_NOAUTH:
        return await call_next(request)
    if path == "/" and settings.YANDEX_ALLOW_SYNC_NOAUTH:
        return await call_next(request)
    if path in ("/login", "/api/v1/auth/login"):
        return await call_next(request)
    if request.cookies.get("access_token") is None:
        from urllib.parse import quote
        next_path = (request.url.path or "/").strip("/") or ""
        qs = getattr(request, "query_string", None) or getattr(request.url, "query", "") or ""
        if qs:
            next_path = next_path + "?" + (qs if isinstance(qs, str) else qs.decode("utf-8"))
        return RedirectResponse("/login" + ("?next=" + quote(next_path) if next_path else ""))
    return await call_next(request)

# 7. NEXUS RENDER ENGINE (Для HTMX-фрагментов)
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

# 8. AUTH & PUBLIC PAGES
@app.get("/", response_class=HTMLResponse)
async def root(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Главная страница — Neural Core (только после логина)"""
    if current_user is None and not getattr(settings, "YANDEX_ALLOW_SYNC_NOAUTH", False):
        return RedirectResponse(url="/login", status_code=307)
    response = templates.TemplateResponse(
        "neural_core.html",
        {"request": request, "current_user": current_user}
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.get("/archive-v1", response_class=HTMLResponse)
async def archive_v1(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("core"))
):
    """Архив удален — ведем в Neural Core"""
    return RedirectResponse(url="/neural-core", status_code=302)

@app.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    access_token: Optional[str] = Cookie(None)
):
    """Врата Цитадели — страница входа"""
    # Если уже авторизован - редирект на dashboard
    if access_token:
        try:
            user = await get_current_user_optional(request, access_token)
            if user:
                return RedirectResponse(url="/", status_code=302)
        except:
            pass
    
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("core"))
):
    """Dashboard (Protected)"""
    response = templates.TemplateResponse(
        "index.html", 
        {"request": request, "current_user": current_user}
    )
    if current_user and current_user.role == "master":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

@app.get("/logout")
async def logout(response: Response):
    """Выход из системы — удаление токена"""
    logger.info("User logged out")
    
    # Удаляем Cookie
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(
        key="access_token",
        path="/"
    )
    
    return response

# =================================================================
# МОДУЛЬНЫЕ СТРАНИЦЫ (Full Page Routes)
# =================================================================

# =================================================================
# МОДУЛЬНЫЕ СТРАНИЦЫ (Full Page Routes)
# =================================================================

@app.get("/garage", response_class=HTMLResponse)
async def garage_page(
    request: Request, 
    park: str = "PRO", 
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("fleet")),
    db: AsyncSession = Depends(get_db)
):
    from app.models.all_models import Vehicle
    from sqlalchemy import select, func, and_
    from sqlalchemy.orm import joinedload
    from app.services.cache_service import cache_service
    from app.services.analytics_engine import AnalyticsEngine
    import logging

    logger = logging.getLogger("Dominion.Garage")
    target_park = park.upper()
    bypass_cache = bool(current_user and current_user.role == "master")

    try:
        # 🔥 ПРОВЕРЯЕМ КЭШ (используем только stats, не список машин)
        cached_stats = None
        if not bypass_cache:
            cached_stats = await cache_service.get_garage_stats(target_park)
        cached_stats_data = None
        if cached_stats and isinstance(cached_stats, dict):
            cached_stats_data = cached_stats.get("stats")
            if cached_stats_data:
                logger.info(f"✓ Статистика гаража из кэша ({target_park})")
        
        # 1. Запрос машин для этого парка (EAGER LOADING ВОДИТЕЛЕЙ)
        stmt = (
            select(Vehicle)
            .options(joinedload(Vehicle.driver))
            .where(Vehicle.park_name == target_park)
        )
        result = await db.execute(stmt)
        vehicles = result.scalars().unique().all()
        
        # 2. Живые данные парка (через AnalyticsEngine)
        park_stats = await AnalyticsEngine.get_fleet_park_stats(db, target_park)
        cars_count = len(vehicles) if vehicles else 0
        active_count = park_stats["vehicles_working"]
        drivers_count = park_stats["drivers_live"]

        # 6. Безопасные переменные для шаблона
        stats_data = cached_stats_data or {
            "cars": cars_count,              # Общее количество машин парка
            "drivers": drivers_count,        # Живые водители (48ч)
            "active": active_count,          # 🔥 ИСПРАВЛЕНО: Активные машины в рейсе
            "service": park_stats["vehicles_service"],
            "reserve": park_stats["vehicles_reserve"],
            "profit": 0                      # Прибыль за 24ч (резерв)
        }

        # 🔥 КЭШИРУЕМ (только stats, без списка машин)
        if not bypass_cache:
            await cache_service.set_garage_stats(
                {"stats": stats_data},
                target_park
            )

        logger.info(f"✓ ГАРАЖ {target_park}: {stats_data['cars']} машин, {stats_data['active']} в рейсе, {stats_data['drivers']} водителей")

        response = templates.TemplateResponse(
            "garage_professional.html", 
            {
                "request": request, 
                "vehicles": vehicles or [], 
                "park": target_park,
                "stats": stats_data,
                "current_user": current_user
            }
        )
        if bypass_cache:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response
    except Exception as e:
        logger.error(f"!!! КРИТИЧЕСКАЯ ОШИБКА ГАРАЖА ({target_park}): {e}", exc_info=True)
        return HTMLResponse(content=f"Ошибка в секторе {target_park}: {e}", status_code=500)


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


@app.get("/garage/{vehicle_id}", response_class=HTMLResponse)
async def garage_detail_page(
    vehicle_id: int,
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("fleet")),
    db: AsyncSession = Depends(get_db)
):
    """ДЕТАЛИ АВТОМОБИЛЯ: Центр управления (v30.1)"""
    from app.models.all_models import Vehicle, VehicleStatusHistory
    from app.services.analytics_engine import AnalyticsEngine
    from sqlalchemy import select, desc
    
    try:
        # Получаем машину
        vehicle = await db.get(Vehicle, vehicle_id)
        if not vehicle:
            return HTMLResponse(content="<h1>Машина не найдена</h1>", status_code=404)
        
        finance = await AnalyticsEngine.get_vehicle_finance(
            db, vehicle_id, vehicle.license_plate
        )
        
        # История статусов
        history_stmt = select(VehicleStatusHistory).where(
            VehicleStatusHistory.vehicle_id == vehicle_id
        ).order_by(desc(VehicleStatusHistory.changed_at)).limit(20)
        
        history_result = await db.execute(history_stmt)
        status_history = history_result.scalars().all()
        
        return templates.TemplateResponse(
            "vehicle_360.html",
            {
                "request": request,
                "current_user": current_user,
                "vehicle": vehicle,
                "finance": {
                    "income": finance["income"],
                    "repair_cost": finance["repair_cost"],
                    "profit": finance["profit"]
                },
                "status_history": status_history,
                "get_status_text": lambda s: {
                    "working": "Работает",
                    "service": "В ремонте",
                    "preparing": "Подготовка",
                    "no_driver": "Нет водителя",
                    "offline": "Не работает"
                }.get(s, s)
            }
        )
        
    except Exception as e:
        logger.error(f"Garage detail error: {e}", exc_info=True)
        return HTMLResponse(content=f"<h1>Ошибка: {str(e)}</h1>", status_code=500)

@app.get("/partners", response_class=HTMLResponse)
async def partners_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("partners"))
):
    """ПАРТНЁРЫ И ВЫПЛАТЫ: B2B и FIRE PAY"""
    return templates.TemplateResponse(
        "modules/partners.html",
        {"request": request, "current_user": current_user}
    )

@app.get("/warehouse", response_class=HTMLResponse)
async def warehouse_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("warehouse"))
):
    """АВТОСЕРВИС И СКЛАД"""
    return templates.TemplateResponse(
        "modules/warehouse.html",
        {"request": request, "current_user": current_user}
    )

@app.get("/warehouse/suppliers", response_class=HTMLResponse)
async def suppliers_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("warehouse"))
):
    """Страница управления поставщиками"""
    return templates.TemplateResponse(
        "warehouse_suppliers.html",
        {"request": request, "current_user": current_user}
    )

@app.get("/service/create", response_class=HTMLResponse)
async def service_create_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("autoservice"))
):
    """Создание заказ-наряда (адаптивный интерфейс)"""
    return templates.TemplateResponse(
        "service_create.html",
        {"request": request, "current_user": current_user}
    )

# v30.0 - 23 АКТИВНЫХ СТРАНИЦЫ
@app.get("/kazna/transactions", response_class=HTMLResponse)
async def kazna_transactions_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("kazna"))
):
    return templates.TemplateResponse("pages/kazna_transactions.html", {"request": request, "current_user": current_user})

@app.get("/kazna/cashflow", response_class=HTMLResponse)
async def kazna_cashflow_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("kazna"))
):
    return templates.TemplateResponse("pages/kazna_cashflow.html", {"request": request, "current_user": current_user})

@app.get("/fleet/maintenance", response_class=HTMLResponse)
async def fleet_maintenance_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("fleet"))
):
    return templates.TemplateResponse("pages/fleet_maintenance.html", {"request": request, "current_user": current_user})

@app.get("/fleet/analytics", response_class=HTMLResponse)
async def fleet_analytics_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("fleet"))
):
    return templates.TemplateResponse("pages/fleet_analytics.html", {"request": request, "current_user": current_user})

@app.get("/hr/drivers", response_class=HTMLResponse)
async def hr_drivers_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("fleet"))
):
    return templates.TemplateResponse("pages/hr_drivers.html", {"request": request, "current_user": current_user})

@app.get("/hr/scoring", response_class=HTMLResponse)
async def hr_scoring_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("fleet"))
):
    return templates.TemplateResponse("pages/hr_scoring.html", {"request": request, "current_user": current_user})

@app.get("/hr/blacklist", response_class=HTMLResponse)
async def hr_blacklist_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("security"))
):
    return templates.TemplateResponse("pages/hr_blacklist.html", {"request": request, "current_user": current_user})

@app.get("/hr/documents", response_class=HTMLResponse)
async def hr_documents_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("fleet"))
):
    return templates.TemplateResponse("pages/hr_documents.html", {"request": request, "current_user": current_user})

@app.get("/consulting/clients", response_class=HTMLResponse)
async def consulting_clients_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("consulting"))
):
    return templates.TemplateResponse("pages/consulting_clients.html", {"request": request, "current_user": current_user})

@app.get("/consulting/pipeline", response_class=HTMLResponse)
async def consulting_pipeline_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("consulting"))
):
    return templates.TemplateResponse("pages/consulting_pipeline.html", {"request": request, "current_user": current_user})

@app.get("/system/status", response_class=HTMLResponse)
async def system_status_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("core"))
):
    return templates.TemplateResponse("pages/system_status.html", {"request": request, "current_user": current_user})


@app.get("/consulting", response_class=HTMLResponse)
async def consulting_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("consulting"))
):
    """КОНСАЛТИНГ И IT"""
    return templates.TemplateResponse(
        "modules/consulting.html",
        {"request": request, "current_user": current_user}
    )

@app.get("/logbook", response_class=HTMLResponse)
async def logbook_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("fleet"))
):
    """ЖУРНАЛ: Путевые листы"""
    return templates.TemplateResponse(
        "logbook.html",
        {"request": request, "current_user": current_user}
    )

@app.get("/kazna", response_class=HTMLResponse)
async def kazna_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("kazna"))
):
    """КАЗНА: Финансовый центр"""
    return templates.TemplateResponse(
        "widgets/kazna.html",
        {"request": request, "current_user": current_user}
    )

@app.get("/fleet", response_class=HTMLResponse)
async def fleet_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("fleet"))
):
    """ТАКСОПАРК T-CLUB24"""
    return templates.TemplateResponse(
        "modules/fleet.html",
        {"request": request, "current_user": current_user}
    )

@app.get("/fleet/drivers/{driver_id}", response_class=HTMLResponse)
async def fleet_driver_page(
    driver_id: int,
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("fleet")),
    db: AsyncSession = Depends(get_db),
):
    from app.services.yandex_sync_service import yandex_sync
    from app.models.all_models import User as UserModel, Vehicle, Transaction
    user_stmt = select(UserModel).where(
        and_(
            UserModel.id == driver_id,
            UserModel.park_name == current_user.park_name
        )
    )
    user = (await db.execute(user_stmt)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Водитель не найден")
    contractor_id = user.yandex_contractor_id or user.yandex_driver_id
    yandex_profile = {}
    if contractor_id:
        try:
            yandex_profile = await yandex_sync.fetch_driver_profile(user.park_name or "PRO", str(contractor_id))
        except Exception:
            yandex_profile = {}
    vehicle = None
    if user.current_vehicle_id:
        vehicle = await db.get(Vehicle, user.current_vehicle_id)
    reserve_stmt = select(Vehicle).where(
        and_(Vehicle.is_free == True, Vehicle.park_name == (user.park_name or "PRO").upper())
    ).order_by(Vehicle.license_plate)
    reserve_vehicles = (await db.execute(reserve_stmt)).scalars().all()
    driver_ids = [user.yandex_driver_id]
    if user.yandex_contractor_id:
        driver_ids.append(user.yandex_contractor_id)
    tx_stmt = select(Transaction).where(
        and_(
            Transaction.yandex_driver_id.in_([d for d in driver_ids if d]),
            Transaction.park_name == user.park_name
        )
    ).order_by(Transaction.date.desc()).limit(10)
    transactions = (await db.execute(tx_stmt)).scalars().all()
    return templates.TemplateResponse(
        "modules/driver_profile.html",
        {
            "request": request,
            "current_user": current_user,
            "driver": user,
            "vehicle": vehicle,
            "yandex_profile": yandex_profile,
            "transactions": transactions,
            "reserve_vehicles": reserve_vehicles,
        },
    )

@app.get("/fleet/vehicles/{vehicle_id}", response_class=HTMLResponse)
async def fleet_vehicle_page(
    vehicle_id: int,
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("fleet")),
    db: AsyncSession = Depends(get_db),
):
    from app.models.all_models import Vehicle, VehicleRepairHistory, Transaction, User as UserModel
    vehicle_stmt = select(Vehicle).where(
        and_(
            Vehicle.id == vehicle_id,
            Vehicle.park_name == current_user.park_name
        )
    )
    vehicle = (await db.execute(vehicle_stmt)).scalar_one_or_none()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Автомобиль не найден")
    repairs_stmt = select(VehicleRepairHistory).where(
        and_(
            VehicleRepairHistory.vehicle_id == vehicle.id,
            VehicleRepairHistory.park_name == vehicle.park_name
        )
    ).order_by(VehicleRepairHistory.created_at.desc())
    repairs = (await db.execute(repairs_stmt)).scalars().all()
    plate = (vehicle.license_plate or "").upper()
    history_stmt = (
        select(
            Transaction.yandex_driver_id,
            func.max(Transaction.date),
        )
        .where(
            and_(
                Transaction.yandex_driver_id.isnot(None),
                or_(
                    Transaction.plate_info == plate,
                    Transaction.description.ilike(f"%{plate}%"),
                ),
                Transaction.park_name == vehicle.park_name
            )
        )
        .group_by(Transaction.yandex_driver_id)
        .order_by(func.max(Transaction.date).desc())
        .limit(10)
    )
    driver_rows = (await db.execute(history_stmt)).all()
    driver_ids = [row[0] for row in driver_rows if row[0]]
    users_stmt = select(UserModel).where(
        and_(
            or_(
                UserModel.yandex_driver_id.in_(driver_ids),
                UserModel.yandex_contractor_id.in_(driver_ids),
            ),
            UserModel.park_name == vehicle.park_name
        )
    )
    users = {u.yandex_driver_id or u.yandex_contractor_id: u for u in (await db.execute(users_stmt)).scalars().all()}
    driver_history = [
        {"driver_id": driver_id, "last_seen": last_seen, "driver": users.get(driver_id)}
        for driver_id, last_seen in driver_rows
    ]
    return templates.TemplateResponse(
        "modules/vehicle_profile.html",
        {
            "request": request,
            "current_user": current_user,
            "vehicle": vehicle,
            "repairs": repairs,
            "driver_history": driver_history,
        },
    )

@app.get("/fleet/contract-matrix", response_class=HTMLResponse)
async def contract_matrix_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("fleet"))
):
    return templates.TemplateResponse(
        "modules/contract_matrix.html",
        {"request": request, "current_user": current_user}
    )

@app.get("/analytics/pl", response_class=HTMLResponse)
async def analytics_pl_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("kazna"))
):
    """P&L ОТЧЁТ: Прибыли и Убытки"""
    return templates.TemplateResponse(
        "analytics_pl.html",
        {"request": request, "current_user": current_user}
    )

@app.get("/analytics", response_class=HTMLResponse)
async def analytics_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("kazna"))
):
    """АНАЛИТИКА: Дашборд метрик"""
    return templates.TemplateResponse(
        "analytics.html",
        {"request": request, "current_user": current_user}
    )

@app.get("/logistics", response_class=HTMLResponse)
async def logistics_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("logistics"))
):
    """ЛОГИСТИКА И МАРШРУТЫ"""
    return templates.TemplateResponse(
        "modules/logistics.html",
        {"request": request, "current_user": current_user}
    )

@app.get("/ai-analyst", response_class=HTMLResponse)
async def ai_analyst_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("ai_analyst"))
):
    """AI АНАЛИТИК"""
    return templates.TemplateResponse(
        "modules/ai_analyst.html",
        {"request": request, "current_user": current_user}
    )

@app.get("/messenger", response_class=HTMLResponse)
async def messenger_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("messenger"))
):
    """IMPERIAL MESSENGER"""
    return templates.TemplateResponse(
        "modules/messenger.html",
        {"request": request, "current_user": current_user}
    )

@app.get("/gps", response_class=HTMLResponse)
async def gps_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("gps"))
):
    """GPS МОНИТОРИНГ"""
    return templates.TemplateResponse(
        "modules/gps.html",
        {"request": request, "current_user": current_user}
    )

@app.get("/tasks", response_class=HTMLResponse)
async def tasks_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("tasks"))
):
    """AI ОТЧЕТЫ И ЗАДАЧИ"""
    return templates.TemplateResponse(
        "modules/tasks.html",
        {"request": request, "current_user": current_user}
    )

@app.get("/merit", response_class=HTMLResponse)
async def merit_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("merit"))
):
    """ГАРНИЗОН ПОЧЕТА"""
    return templates.TemplateResponse(
        "modules/merit.html",
        {"request": request, "current_user": current_user}
    )

@app.get("/investments", response_class=HTMLResponse)
async def investments_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("investments"))
):
    """ИНВЕСТИЦИИ И БЛАГОТВОРИТЕЛЬНОСТЬ"""
    return templates.TemplateResponse(
        "modules/investments.html",
        {"request": request, "current_user": current_user}
    )

@app.get("/academy", response_class=HTMLResponse)
async def academy_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("academy"))
):
    """S-GLOBAL ACADEMY & LEGAL"""
    return templates.TemplateResponse(
        "modules/academy.html",
        {"request": request, "current_user": current_user}
    )

@app.get("/admin/debug", response_class=HTMLResponse)
async def admin_debug(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    module_guard: User = Depends(require_module("core"))
):
    """ADMIN DEBUG: Техническая панель"""
    return templates.TemplateResponse(
        "admin_debug.html",
        {"request": request, "current_user": current_user}
    )

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return RedirectResponse(url="/neural-core", status_code=302)

if __name__ == "__main__":
    # Запуск Ядра на порту 8001
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=False)
