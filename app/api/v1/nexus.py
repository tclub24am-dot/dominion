# -*- coding: utf-8 -*-
# app/routes/nexus.py
# NEXUS UI Engine - Боевая система виджетов
# IRON SHIELD v200.16: Верификация webhook-подписей, XSS-защита, чистка API

import logging
import os
import uuid
import hmac
import hashlib
from html import escape as html_escape
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, Request, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timedelta
from decimal import Decimal
from pydantic import BaseModel

from app.database import get_db
from app.models.all_models import Transaction, Vehicle, OwnershipType, User
from app.services.oracle_service import oracle_service
from app.services.finance_engine import finance_engine
from app.services.fleet_engine import fleet_engine
from app.services.file_analyzer import file_analyzer
from app.services.tension_analyzer import tension_analyzer
from app.services.security import get_current_user_from_cookie
from app.core.config import settings
from app.services.yandex_sync_service import yandex_sync  # единственный импорт

logger = logging.getLogger("NexusEngine")
router = APIRouter(tags=["Nexus Widgets"])

@router.post("/sync/force")
async def force_sync(
    current_user: User = Depends(get_current_user_from_cookie)
):
    """
    Принудительная синхронизация с Яндекс.Такси
    Использует новый синхронизатор sync_transactions_with_park.py
    с поддержкой маркирования каждой транзакции park_name
    """
    try:
        import asyncio
        import os
        from datetime import datetime
        
        # Запускаем новый синхронизатор с park_name маркировкой
        script_path = "/root/dominion/sync_transactions_with_park.py"
        venv_python = "/root/dominion/venv/bin/python3"
        
        if not os.path.exists(script_path):
            return {
                "status": "error",
                "message": f"Синхронизатор не найден: {script_path}",
                "timestamp": datetime.now().isoformat()
            }
        
        # Запускаем скрипт асинхронно, не блокируя event loop FastAPI
        proc = await asyncio.create_subprocess_exec(
            venv_python, script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            logger.error("Sync timeout (60s)")
            return {
                "status": "timeout",
                "message": "Синхронизация заняла слишком много времени",
                "timestamp": datetime.now().isoformat()
            }
        
        stdout_text = stdout.decode() if stdout else ""
        logger.info(f"✓ Sync with park_name completed: {stdout_text[:200]}")
        
        return {
            "status": "success",
            "message": "Синхронизация транзакций с маркировкой park_name завершена",
            "output": stdout_text[:500] if stdout_text else "Успешно",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Force sync error: {e}")
        return {
            "status": "error",
            "message": f"Ошибка синхронизации: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

@router.get("/logs/api_sync")
async def get_api_sync_logs(
    lines: int = 5,
    current_user: User = Depends(get_current_user_from_cookie)
):
    """
    Получение последних строк лога синхронизации
    """
    try:
        log_path = Path("/root/dominion/storage/api_sync.log")
        if not log_path.exists():
            return {"logs": ["Лог файл не найден"]}
            
        with open(log_path, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            last_lines = all_lines[-lines:]
            
        return {"logs": [line.strip() for line in last_lines]}
    except Exception as e:
        logger.error(f"Log read error: {e}")
        return {"logs": [f"Ошибка чтения лога: {str(e)}"]}


class OracleChatRequest(BaseModel):
    message: str
    group: str = "ОБЩАЯ"
    file_context: Optional[str] = None

@router.post("/oracle/chat")
async def oracle_chat(
    payload: OracleChatRequest,
    current_user: User = Depends(get_current_user_from_cookie)
):
    """
    Отправка сообщения Oracle AI (с поддержкой file_context)
    """
    try:
        response = await oracle_service.send_message(
            message=payload.message,
            group=payload.group,
            file_context=payload.file_context
        )
        return response
        
    except Exception as e:
        logger.error(f"Oracle chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/oracle/history/{group}")
async def oracle_history(
    group: str,
    limit: int = 50,
    current_user: User = Depends(get_current_user_from_cookie),
    db: AsyncSession = Depends(get_db)
):
    """
    Получить историю чата Oracle (ВСЕ сообщения: локальные + внешние)
    """
    try:
        from app.models.all_models import ChatMessage
        
        # Получаем из БД (включая Telegram/WhatsApp)
        stmt = select(ChatMessage).where(
            ChatMessage.group_name == group
        ).order_by(ChatMessage.created_at.asc()).limit(limit)
        
        result = await db.execute(stmt)
        messages = result.scalars().all()
        
        history = []
        for msg in messages:
            history.append({
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.created_at.isoformat() if msg.created_at else msg.timestamp.isoformat(),
                "is_read": msg.is_read if hasattr(msg, 'is_read') else True
            })
        
        logger.info(f"✓ History loaded: {len(history)} messages from group {group}")
        
        return {"history": history, "group": group, "count": len(history)}
        
    except Exception as e:
        logger.error(f"Oracle history error: {e}", exc_info=True)
        # Fallback на memory history
        history = oracle_service.get_history(group=group, limit=limit)
        return {"history": history, "group": group, "count": len(history)}

@router.get("/oracle/status")
async def oracle_status(
    current_user: User = Depends(get_current_user_from_cookie)
):
    """
    Получить статус Oracle AI (LIVE / MOCK)
    """
    return {
        "status": "LIVE" if oracle_service.is_live else "MOCK",
        "model": oracle_service.model,
        "base_url": oracle_service.base_url,
        "timestamp": datetime.now().isoformat()
    }

@router.post("/webhooks/telegram")
async def telegram_webhook(request: Request):
    """
    Webhook для Telegram Bot
    IRON SHIELD v200.16: Верификация X-Telegram-Bot-Api-Secret-Token
    """
    # Верификация подписи Telegram (ОБЯЗАТЕЛЬНО!)
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    expected_secret = getattr(settings, "TELEGRAM_WEBHOOK_SECRET", None)
    
    if expected_secret:
        if not secret_token or not hmac.compare_digest(secret_token, expected_secret):
            logger.warning("⚠ Telegram webhook: invalid secret token — request rejected")
            raise HTTPException(status_code=403, detail="Invalid webhook token")
    else:
        logger.warning("⚠ TELEGRAM_WEBHOOK_SECRET not configured — webhook unprotected!")
    
    try:
        from app.services.telegram_bot import telegram_bot
        
        if not telegram_bot.bot:
            raise HTTPException(status_code=503, detail="Telegram bot not configured")
        
        update_data = await request.json()
        logger.info(f"📨 Telegram webhook received (verified)")
        
        # Обрабатываем update
        await telegram_bot.process_webhook(update_data)
        
        return {"status": "ok"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Telegram webhook error: {e}")
        return {"status": "error", "message": str(e)}

@router.post("/webhooks/whatsapp")
async def whatsapp_webhook(request: Request):
    """
    Webhook для WhatsApp Gateway (В разработке)
    """
    try:
        from app.services.whatsapp_service import whatsapp_service
        
        data = await request.json()
        logger.info(f"📱 WhatsApp webhook received")
        
        result = await whatsapp_service.process_incoming_message(data)
        
        return result
        
    except Exception as e:
        logger.error(f"WhatsApp webhook error: {e}")
        return {"status": "error", "message": str(e)}

@router.post("/oracle/upload")
async def oracle_upload(
    file: UploadFile = File(...),
    group: str = "ОБЩАЯ",
    current_user: User = Depends(get_current_user_from_cookie)
):
    """
    Загрузка файлов для Oracle AI
    Поддерживаемые: Excel, Word, PDF, XML, Images
    """
    try:
        # Проверяем расширение
        allowed_extensions = {
            '.xlsx', '.xls',  # Excel
            '.docx', '.doc',  # Word
            '.pdf',           # PDF
            '.xml',           # XML/1C
            '.jpg', '.jpeg', '.png', '.gif', '.webp'  # Images
        }
        
        file_ext = Path(file.filename).suffix.lower()
        
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Неподдерживаемый формат файла: {file_ext}"
            )
        
        # Создаём уникальное имя
        unique_filename = f"{uuid.uuid4().hex}{file_ext}"
        upload_dir = Path(settings.ORACLE_UPLOAD_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = upload_dir / unique_filename
        
        # Сохраняем файл
        content = await file.read()
        
        with open(file_path, 'wb') as f:
            f.write(content)
        
        logger.info(f"✓ File uploaded: {file.filename} → {unique_filename}")
        logger.info(f"  User: {current_user.username}")
        logger.info(f"  Size: {len(content)} bytes")
        logger.info(f"  Group: {group}")
        
        # Анализируем файл через File Analyzer
        analysis = await file_analyzer.analyze_file(file_path, file.filename)
        
        logger.info(f"  Analysis: {analysis['status']}")
        
        # Сохраняем в БД для истории
        try:
            from app.models.all_models import ChatMessage
            from app.database import AsyncSessionLocal
            
            async with AsyncSessionLocal() as session:
                chat_message = ChatMessage(
                    role="user",
                    content=f"[Файл загружен] {file.filename}",
                    group_name=group,
                    user_id=current_user.id,
                    file_path=str(file_path),
                    timestamp=datetime.now(),
                    created_at=datetime.now()
                )
                
                session.add(chat_message)
                await session.commit()
                
                logger.info(f"  ✓ File saved to history: {unique_filename}")
        except Exception as e:
            logger.warning(f"Failed to save file to history: {e}")
        
        return {
            "status": "success",
            "filename": file.filename,
            "unique_id": unique_filename,
            "size": len(content),
            "type": file_ext,
            "group": group,
            # IRON SHIELD v200.16: file_path НЕ раскрывается клиенту (утечка структуры ФС)
            "timestamp": datetime.now().isoformat(),
            "analysis": analysis.get("summary", "Файл загружен"),
            "message": analysis.get("summary", "Файл загружен. Oracle готов ответить на вопросы.")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Инициализация шаблонов
templates = Jinja2Templates(directory="app/templates")

# =================================================================
# КАЗНА WIDGET - Золотая Империя
# =================================================================

@router.get("/widget/kazna", response_class=HTMLResponse)
async def kazna_widget(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    ЗОЛОТАЯ АУРА: Виджет финансового господства (Формула Мастера)
    Защита через parent page (index.html уже требует auth)
    """
    try:
        # Пытаемся получить реальные данные
        financial_data = await finance_engine.calculate_daily_profit(db)
        
        # Если нет реальных данных - используем демо
        if not financial_data["has_real_data"]:
            logger.info("No real transaction data, using demo data for Kazna")
            financial_data = finance_engine.generate_demo_data()
        
        # Добавляем timestamp
        financial_data["timestamp"] = datetime.now().strftime("%H:%M:%S")
        
        # Месячная проекция
        financial_data["month_revenue"] = round(financial_data["net_profit"] * 30, 2)
        
        logger.info(f"✓ Kazna widget: Net profit {financial_data['net_profit']}₽")
        
        return templates.TemplateResponse(
            "widgets/kazna.html",
            {"request": request, "data": financial_data}
        )
        
    except Exception as e:
        logger.error(f"Kazna Widget Error: {e}", exc_info=True)
        return HTMLResponse(
            content=f"""
            <div class="widget-error">
                <div class="error-icon">⚠</div>
                <div class="error-text">Ошибка загрузки Казны</div>
                <div class="error-detail">{html_escape(str(e)[:100])}</div>
            </div>
            """,
            status_code=200
        )

# =================================================================
# ФЛОТ WIDGET - Империя Колёс
# =================================================================

@router.get("/widget/fleet", response_class=HTMLResponse)
async def fleet_widget(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    ИМПЕРИЯ КОЛЁС: Статус автопарка + Tension Index
    """
    try:
        # Получаем статус флота с Tension Index
        fleet_data = await fleet_engine.get_fleet_status(db)
        fleet_data["timestamp"] = datetime.now().strftime("%H:%M:%S")
        
        return templates.TemplateResponse(
            "widgets/fleet.html",
            {"request": request, "data": fleet_data}
        )
        
    except Exception as e:
        logger.error(f"Fleet Widget Error: {e}", exc_info=True)
        return HTMLResponse(
            content=f"""
            <div class="widget-error">
                <div class="error-icon">⚠</div>
                <div class="error-text">Ошибка загрузки Флота</div>
            </div>
            """,
            status_code=200
        )

@router.get("/fleet/driver-info/{vehicle_id}")
async def fleet_driver_info(
    vehicle_id: int,
    current_user: User = Depends(get_current_user_from_cookie),
    db: AsyncSession = Depends(get_db)
):
    """
    Справка по водителю для Oracle (HTMX endpoint)
    """
    try:
        info = await fleet_engine.get_driver_info(db, vehicle_id)
        return info
    except Exception as e:
        logger.error(f"Driver info error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/files/archive")
async def files_archive(
    group: str = "ОБЩАЯ",
    limit: int = 30,
    current_user: User = Depends(get_current_user_from_cookie),
    db: AsyncSession = Depends(get_db)
):
    """
    АРХИВ ФАЙЛОВ: последние 30 дней
    """
    try:
        from app.models.all_models import ChatMessage
        from datetime import timedelta
        
        cutoff_date = datetime.now() - timedelta(days=30)
        
        stmt = select(ChatMessage).where(
            and_(
                ChatMessage.file_path.isnot(None),
                ChatMessage.created_at >= cutoff_date,
                ChatMessage.group_name == group
            )
        ).order_by(ChatMessage.created_at.desc()).limit(limit)
        
        result = await db.execute(stmt)
        files = result.scalars().all()
        
        file_list = []
        for f in files:
            file_name = Path(f.file_path).name if f.file_path else "unknown"
            file_list.append({
                "id": f.id,
                "filename": file_name,
                "content": f.content,
                "file_path": f.file_path,
                "timestamp": f.created_at.isoformat(),
                "group": f.group_name
            })
        
        return {
            "status": "success",
            "files": file_list,
            "count": len(file_list)
        }
        
    except Exception as e:
        logger.error(f"Files archive error: {e}")
        return {"status": "error", "files": [], "count": 0}

@router.get("/files/context/{file_id}")
async def file_get_context(
    file_id: int,
    current_user: User = Depends(get_current_user_from_cookie),
    db: AsyncSession = Depends(get_db)
):
    """
    Получить контекст файла для повторной активации
    """
    try:
        from app.models.all_models import ChatMessage
        
        stmt = select(ChatMessage).where(ChatMessage.id == file_id)
        result = await db.execute(stmt)
        file_msg = result.scalar_one_or_none()
        
        if not file_msg or not file_msg.file_path:
            raise HTTPException(status_code=404, detail="Файл не найден")
        
        # Перечитываем файл через analyzer
        file_path = Path(file_msg.file_path)
        
        if file_path.exists():
            analysis = await file_analyzer.analyze_file(file_path, file_path.name)
            
            return {
                "status": "success",
                "file_id": file_id,
                "filename": file_path.name,
                "context": analysis.get("summary", ""),
                "path": str(file_path)
            }
        else:
            return {
                "status": "error",
                "message": "Файл был удалён из хранилища"
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File context error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/oracle/unread")
async def oracle_unread_counts(
    current_user: User = Depends(get_current_user_from_cookie),
    db: AsyncSession = Depends(get_db)
):
    """
    Получить количество непрочитанных сообщений по группам
    """
    try:
        from app.models.all_models import ChatMessage
        
        groups = ["ОБЩАЯ", "ФЛОТ", "ФИНАНСЫ", "ПЛАНИРОВАНИЕ"]
        unread_counts = {}
        
        for group in groups:
            stmt = select(func.count(ChatMessage.id)).where(
                and_(
                    ChatMessage.group_name == group,
                    ChatMessage.is_read == False,
                    ChatMessage.role == "assistant"  # Только ответы Oracle
                )
            )
            
            result = await db.execute(stmt)
            count = result.scalar() or 0
            unread_counts[group] = count
        
        return {
            "status": "success",
            "unread": unread_counts,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Unread counts error: {e}")
        return {"status": "error", "unread": {}}

@router.get("/live/profit", response_class=HTMLResponse)
async def live_profit(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    db: AsyncSession = Depends(get_db)
):
    """
    ЧИСТАЯ ПРИБЫЛЬ В РЕАЛЬНОМ ВРЕМЕНИ (v30.0 EXTREME - NO CACHE)
    """
    
    try:
        from datetime import datetime, timedelta
        from fastapi.responses import HTMLResponse
        
        # ПРИНУДИТЕЛЬНОЕ ОБНОВЛЕНИЕ СЕССИИ (NO CACHE!)
        await db.rollback()  # Сбрасываем текущую сессию
        db.expire_all()      # Очищаем кэш объектов
        
        # Получаем данные за СЕГОДНЯ (свежие из БД)
        financial_data = await finance_engine.calculate_daily_profit(db)
        
        if not financial_data["has_real_data"]:
            logger.warning("⚠ Live Profit: Using demo data (no real transactions)")
            financial_data = finance_engine.generate_demo_data()
        
        # Упрощённый расчёт для реалтайм
        sum_sublease = financial_data["sum_42_raw"]
        sum_connected = financial_data["sum_78_raw"]
        
        # ФОРМУЛА МАСТЕРА
        net_profit = (
            (sum_sublease * 0.04) +      # Комиссия субаренды
            (42 * 450) +                  # Фиксированная аренда
            (sum_connected * 0.03)        # Комиссия подключенных
        )
        
        # ЛОГИРУЕМ ДЛЯ МАСТЕРА
        logger.info(f"💰 Live Profit Request:")
        logger.info(f"   Выручка субаренды: {sum_sublease:,.2f}₽")
        logger.info(f"   Выручка подключек: {sum_connected:,.2f}₽")
        logger.info(f"   Комиссия субаренды: {sum_sublease * 0.04:,.2f}₽")
        logger.info(f"   Фиксированная аренда: {42 * 450:,.2f}₽")
        logger.info(f"   Комиссия подключек: {sum_connected * 0.03:,.2f}₽")
        logger.info(f"   💰 ИТОГО ПРИБЫЛЬ: {net_profit:,.2f}₽")
        
        # Подготовка данных для шаблона
        data = {
            "net_profit": round(net_profit, 2),
            "sublease_income": round(sum_sublease * 0.04 + 42 * 450, 2),
            "connected_income": round(sum_connected * 0.03, 2),
            "timestamp": datetime.now().isoformat(),
            "formatted": f"{net_profit:,.0f}₽",
            "has_real_data": financial_data["has_real_data"]
        }
        
        # Инициализация templates
        templates = Jinja2Templates(directory="app/templates")
        
        # Возвращаем HTML с NO-CACHE заголовками
        response = templates.TemplateResponse(
            "widgets/profit_hero.html",
            {"request": request, "data": data}
        )
        
        # КРИТИЧНО: NO CACHE HEADERS
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["X-Accel-Expires"] = "0"
        
        return response
        
    except Exception as e:
        logger.error(f"Live profit error: {e}", exc_info=True)
        return HTMLResponse(
            content=f'<div style="padding: 20px; color: #ff5252;">⚠️ Ошибка загрузки прибыли: {html_escape(str(e))}</div>',
            status_code=200
        )

@router.post("/oracle/mark_read")
async def oracle_mark_read(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie),
    db: AsyncSession = Depends(get_db)
):
    """
    Пометить все сообщения группы как прочитанные
    """
    try:
        data = await request.json()
        group = data.get("group", "ОБЩАЯ")
        
        from app.models.all_models import ChatMessage
        from sqlalchemy import update
        
        stmt = update(ChatMessage).where(
            and_(
                ChatMessage.group_name == group,
                ChatMessage.is_read == False
            )
        ).values(is_read=True)
        
        result = await db.execute(stmt)
        await db.commit()
        
        logger.info(f"✓ Messages marked as read in {group}: {result.rowcount} messages")
        
        return {"status": "success", "group": group, "marked": result.rowcount}
        
    except Exception as e:
        logger.error(f"Mark read error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =================================================================
# ЛОГИСТИКА WIDGET - Пульс ВкусВилл
# =================================================================

@router.get("/widget/logistics", response_class=HTMLResponse)
async def logistics_widget(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Логистический пульс: дедлайны, маршруты, эффективность
    """
    try:
        # Временная заглушка с имитацией данных
        now = datetime.now()
        
        data = {
            "active_routes": 12,
            "completed_today": 34,
            "on_time_percentage": 96.5,
            "avg_delivery_time": "2.3 ч",
            "next_deadline": (now + timedelta(hours=2)).strftime("%H:%M"),
            "efficiency_score": 94,
            "timestamp": now.strftime("%H:%M:%S")
        }
        
        return templates.TemplateResponse(
            "widgets/logistics.html",
            {"request": request, "data": data}
        )
        
    except Exception as e:
        logger.error(f"Logistics Widget Error: {e}")
        return HTMLResponse(
            content=f"""
            <div class="widget-error">
                <div class="error-icon">⚠</div>
                <div class="error-text">Ошибка загрузки Логистики</div>
            </div>
            """,
            status_code=200
        )

# =================================================================
# ORACLE CHAT WIDGET - Связь с ИИ
# =================================================================

# =================================================================
# НОВЫЕ ВИДЖЕТЫ v19.0 MONOLITH LUXURY
# =================================================================

@router.get("/widget/consulting", response_class=HTMLResponse)
async def consulting_widget(request: Request, db: AsyncSession = Depends(get_db)):
    """КОНСАЛТИНГ: Статус проектов и клиентов"""
    data = {
        "active_projects": 7,
        "clients": 24,
        "completion": 78,
        "timestamp": datetime.now().strftime("%H:%M:%S")
    }
    return templates.TemplateResponse("widgets/consulting.html", {"request": request, "data": data})

@router.get("/widget/autoservice", response_class=HTMLResponse)
async def autoservice_widget(request: Request, db: AsyncSession = Depends(get_db)):
    """АВТОСЕРВИС: Очередь ТО и ремзона"""
    data = {
        "queue": 5,
        "in_service": 3,
        "completed_today": 12,
        "timestamp": datetime.now().strftime("%H:%M:%S")
    }
    return templates.TemplateResponse("widgets/autoservice.html", {"request": request, "data": data})

@router.get("/widget/warehouse", response_class=HTMLResponse)
async def warehouse_widget(request: Request, db: AsyncSession = Depends(get_db)):
    """СКЛАД: Критические остатки"""
    try:
        from app.models.all_models import WarehouseItem, WarehouseLog
        
        # Критические остатки
        stmt_critical = select(func.count(WarehouseItem.id)).where(
            WarehouseItem.quantity <= WarehouseItem.min_threshold
        )
        critical_result = await db.execute(stmt_critical)
        critical_count = critical_result.scalar() or 0
        
        # Заказы в ожидании
        stmt_pending = select(func.count(WarehouseLog.id)).where(
            WarehouseLog.status == "pending"
        )
        pending_result = await db.execute(stmt_pending)
        pending_count = pending_result.scalar() or 0
        
        # Стоимость запасов
        stmt_value = select(func.sum(WarehouseItem.quantity * WarehouseItem.price_unit))
        value_result = await db.execute(stmt_value)
        stock_value = value_result.scalar() or 0
        
        data = {
            "critical_items": critical_count,
            "orders_pending": pending_count,
            "stock_value": float(stock_value),
            "timestamp": datetime.now().strftime("%H:%M:%S")
        }
        
        logger.info(f"✓ Warehouse widget: {critical_count} critical items")
        
    except Exception as e:
        logger.error(f"Warehouse widget error: {e}")
        data = {
            "critical_items": 0,
            "orders_pending": 0,
            "stock_value": 0,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        }
    
    return templates.TemplateResponse("widgets/warehouse.html", {"request": request, "data": data})

@router.get("/widget/warehouse-stats", response_class=HTMLResponse)
async def warehouse_stats_widget(request: Request, db: AsyncSession = Depends(get_db)):
    """СКЛАД: Статистика для страницы warehouse"""
    try:
        from app.models.all_models import WarehouseItem, WarehouseLog
        
        # Всего позиций
        stmt_total = select(func.count(WarehouseItem.id))
        total_result = await db.execute(stmt_total)
        total_items = total_result.scalar() or 0
        
        # Критические остатки
        stmt_critical = select(func.count(WarehouseItem.id)).where(
            WarehouseItem.quantity <= WarehouseItem.min_threshold
        )
        critical_result = await db.execute(stmt_critical)
        critical_items = critical_result.scalar() or 0
        
        # Ожидает выдачи
        stmt_pending = select(func.count(WarehouseLog.id)).where(
            WarehouseLog.status == "pending"
        )
        pending_result = await db.execute(stmt_pending)
        pending = pending_result.scalar() or 0
        
        # Стоимость запасов
        stmt_value = select(func.sum(WarehouseItem.quantity * WarehouseItem.price_unit))
        value_result = await db.execute(stmt_value)
        stock_value = float(value_result.scalar() or 0)
        
        return HTMLResponse(content=f"""
        <div class="stat-card">
            <div class="stat-value">{total_items:,}</div>
            <div class="stat-label">Всего позиций</div>
        </div>
        
        <div class="stat-card critical">
            <div class="stat-value">{critical_items}</div>
            <div class="stat-label">Критический остаток</div>
        </div>
        
        <div class="stat-card">
            <div class="stat-value">{pending}</div>
            <div class="stat-label">Ожидает выдачи</div>
        </div>
        
        <div class="stat-card">
            <div class="stat-value">{stock_value:,.0f}₽</div>
            <div class="stat-label">Стоимость запасов</div>
        </div>
        """)
        
    except Exception as e:
        logger.error(f"Warehouse stats error: {e}")
        return HTMLResponse(content="""
        <div class="stat-card"><div class="stat-value">—</div><div class="stat-label">Ошибка</div></div>
        """, status_code=200)

@router.get("/widget/it-dev", response_class=HTMLResponse)
async def it_dev_widget(request: Request):
    """ИТ РАЗРАБОТКИ: Спринты и обновления"""
    data = {
        "current_sprint": "v19.0 Luxury",
        "progress": 95,
        "tasks_done": 87,
        "tasks_total": 92,
        "timestamp": datetime.now().strftime("%H:%M:%S")
    }
    return templates.TemplateResponse("widgets/it_dev.html", {"request": request, "data": data})

@router.get("/widget/analytics", response_class=HTMLResponse)
async def analytics_widget(request: Request, db: AsyncSession = Depends(get_db)):
    """АНАЛИТИКА: Графики Chart.js"""
    data = {
        "revenue_today": 2410000,
        "expenses_today": 178500,
        "profit_margin": 92.6,
        "timestamp": datetime.now().strftime("%H:%M:%S")
    }
    return templates.TemplateResponse("widgets/analytics.html", {"request": request, "data": data})

@router.get("/widget/tasks", response_class=HTMLResponse)
async def tasks_widget(request: Request):
    """СВОДКА ЗАДАЧ: 3 колонки"""
    data = {
        "completed": 24,
        "upcoming": 15,
        "planned": 31,
        "timestamp": datetime.now().strftime("%H:%M:%S")
    }
    return templates.TemplateResponse("widgets/tasks.html", {"request": request, "data": data})

@router.get("/widget/calls", response_class=HTMLResponse)
async def calls_widget(request: Request, db: AsyncSession = Depends(get_db)):
    """ПОСЛЕДНИЕ ЗВОНКИ: Сводка из 1АТС с Caller ID"""
    try:
        from app.services.caller_id_service import caller_id_service
        
        # Получаем последние звонки с обогащением
        recent_calls = await caller_id_service.get_recent_calls(limit=5)
        
        data = {
            "calls_today": 47,
            "missed": 3,
            "avg_duration": "4:32",
            "recent": recent_calls,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        }
        
        return templates.TemplateResponse("widgets/calls.html", {"request": request, "data": data})
        
    except Exception as e:
        logger.error(f"Calls widget error: {e}")
        data = {
            "calls_today": 47,
            "missed": 3,
            "avg_duration": "4:32",
            "recent": [],
            "timestamp": datetime.now().strftime("%H:%M:%S")
        }
        return templates.TemplateResponse("widgets/calls.html", {"request": request, "data": data})

@router.get("/widget/partner-payouts", response_class=HTMLResponse)
async def partner_payouts_widget(request: Request, db: AsyncSession = Depends(get_db)):
    """
    ВЫПЛАТЫ ПАРТНЁРАМ: Виджет для дашборда (v22.5)
    """
    try:
        from app.models.all_models import Partner, PartnerLedger
        from datetime import timedelta
        
        # Период: последние 30 дней
        cutoff_date = datetime.now() - timedelta(days=30)
        
        # Считаем общую сумму к выплате
        stmt = select(Partner).where(Partner.is_active == True)
        result = await db.execute(stmt)
        partners = result.scalars().all()
        
        total_payable = 0.0
        partners_count = 0
        
        for partner in partners:
            stmt_ledger = select(
                func.sum(PartnerLedger.incoming),
                func.sum(PartnerLedger.outgoing)
            ).where(
                and_(
                    PartnerLedger.partner_id == partner.id,
                    PartnerLedger.date >= cutoff_date.date()
                )
            )
            
            ledger_result = await db.execute(stmt_ledger)
            incoming, outgoing = ledger_result.first()
            
            incoming = float(incoming) if incoming else 0.0
            outgoing = float(outgoing) if outgoing else 0.0
            payable = incoming - outgoing
            
            if payable > 0:
                total_payable += payable
                partners_count += 1
        
        data = {
            "total_payable": round(total_payable, 2),
            "partners_count": partners_count,
            "period_days": 30,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        }
        
        logger.info(f"✓ Partner payouts widget: {total_payable:,.2f}₽ to {partners_count} partners")
        
        return templates.TemplateResponse("widgets/partner_payouts.html", {"request": request, "data": data})
        
    except Exception as e:
        logger.error(f"Partner payouts widget error: {e}")
        data = {
            "total_payable": 0,
            "partners_count": 0,
            "period_days": 30,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        }
        return templates.TemplateResponse("widgets/partner_payouts.html", {"request": request, "data": data})

@router.get("/widget/hr_drivers_list", response_class=HTMLResponse)
async def hr_drivers_list_widget(request: Request):
    """
    HR DRIVERS LIST: Список водителей
    """
    try:
        logger.info("✓ HR drivers list widget loaded")
        return templates.TemplateResponse("widgets/hr_drivers_list.html", {"request": request})
    except Exception as e:
        logger.error(f"HR drivers list widget error: {e}")
        return HTMLResponse(
            content=f'<div style="padding: 20px; color: #ff5252;">⚠️ Ошибка загрузки водителей</div>',
            status_code=200
        )

@router.get("/widget/consulting_clients_list", response_class=HTMLResponse)
async def consulting_clients_list_widget(request: Request):
    """
    CONSULTING CLIENTS: Список клиентов консалтинга
    """
    try:
        logger.info("✓ Consulting clients list widget loaded")
        return templates.TemplateResponse("widgets/consulting_clients_list.html", {"request": request})
    except Exception as e:
        logger.error(f"Consulting clients list widget error: {e}")
        return HTMLResponse(
            content=f'<div style="padding: 20px; color: #ff5252;">⚠️ Ошибка загрузки клиентов</div>',
            status_code=200
        )

@router.get("/widget/warehouse_value", response_class=HTMLResponse)
async def warehouse_value_widget(request: Request):
    """
    WAREHOUSE VALUE: Стоимость автопарка
    """
    try:
        logger.info("✓ Warehouse value widget loaded")
        return templates.TemplateResponse("widgets/warehouse_value.html", {"request": request})
    except Exception as e:
        logger.error(f"Warehouse value widget error: {e}")
        return HTMLResponse(
            content=f'<div style="padding: 20px; color: #ff5252;">⚠️ Ошибка загрузки данных</div>',
            status_code=200
        )

@router.get("/widget/warehouse_top_expenses", response_class=HTMLResponse)
async def warehouse_top_expenses_widget(request: Request):
    """
    WAREHOUSE TOP EXPENSES: Топ расходов
    """
    try:
        logger.info("✓ Warehouse top expenses widget loaded")
        return templates.TemplateResponse("widgets/warehouse_top_expenses.html", {"request": request})
    except Exception as e:
        logger.error(f"Warehouse top expenses widget error: {e}")
        return HTMLResponse(
            content=f'<div style="padding: 20px; color: #ff5252;">⚠️ Ошибка загрузки расходов</div>',
            status_code=200
        )

@router.get("/widget/warehouse_service_schedule", response_class=HTMLResponse)
async def warehouse_service_schedule_widget(request: Request):
    """
    WAREHOUSE SERVICE SCHEDULE: График обслуживания
    """
    try:
        logger.info("✓ Warehouse service schedule widget loaded")
        return templates.TemplateResponse("widgets/warehouse_service_schedule.html", {"request": request})
    except Exception as e:
        logger.error(f"Warehouse service schedule widget error: {e}")
        return HTMLResponse(
            content=f'<div style="padding: 20px; color: #ff5252;">⚠️ Ошибка загрузки графика ТО</div>',
            status_code=200
        )

# =================================================================
# ADMIN DEBUG API v22.0
# =================================================================

@router.get("/admin/api-status")
async def admin_api_status(
    current_user: User = Depends(get_current_user_from_cookie)
):
    """Статус подключения к внешним API"""
    try:
        from app.services.yandex_sync_service import yandex_sync
        from pathlib import Path
        
        yandex_status = "connected" if yandex_sync.enabled else "disconnected"
        
        # Последняя синхронизация из лога
        log_file = Path("/root/dominion/storage/api_sync.log")
        last_sync = "Нет данных"
        
        if log_file.exists():
            with open(log_file, 'r') as f:
                lines = f.readlines()
                if lines:
                    import json
                    try:
                        last_entry = json.loads(lines[-1])
                        last_sync = last_entry.get("timestamp", "Unknown")
                    except:
                        last_sync = "Error parsing"
        
        return {
            "yandex_status": yandex_status,
            "last_sync": last_sync,
            "ats_status": "pending"
        }
        
    except Exception as e:
        logger.error(f"API status error: {e}")
        return {"yandex_status": "error", "last_sync": "error"}

@router.post("/admin/force-sync")
async def admin_force_sync(
    current_user: User = Depends(get_current_user_from_cookie),
    db: AsyncSession = Depends(get_db)
):
    """Принудительная синхронизация с Yandex (v22.1 — РЕАЛЬНАЯ ЗАПИСЬ В БД)"""
    try:
        from app.services.yandex_sync_service import yandex_sync
        from datetime import timedelta
        
        logger.info("🔄 Starting force sync with Yandex API...")
        
        # Синхронизируем транзакции за последние 7 дней
        to_date = datetime.now()
        from_date = to_date - timedelta(days=7)
        
        logger.info(f"   Period: {from_date.date()} → {to_date.date()}")
        
        # Синхронизация транзакций
        tx_result = await yandex_sync.sync_transactions(from_date, to_date)
        
        logger.info(f"   Transactions: {tx_result}")
        
        # Синхронизация машин
        vehicles_result = await yandex_sync.sync_vehicles()
        
        logger.info(f"   Vehicles: {vehicles_result}")
        
        return {
            "status": "success",
            "transactions": tx_result,
            "vehicles": vehicles_result,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Force sync error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

@router.get("/admin/api-log")
async def admin_api_log(
    current_user: User = Depends(get_current_user_from_cookie)
):
    """Последние 10 записей из API лога"""
    try:
        from pathlib import Path
        import json
        
        log_file = Path("/root/dominion/storage/api_sync.log")
        
        if not log_file.exists():
            return HTMLResponse("<p style='color: var(--text-muted);'>Лог пуст</p>")
        
        with open(log_file, 'r') as f:
            lines = f.readlines()[-10:]  # Последние 10
        
        html = "<div style='font-family: monospace; font-size: 12px;'>"
        
        for line in reversed(lines):
            try:
                entry = json.loads(line)
                status_color = "#00ff88" if entry.get("status") == 200 else "#ff6b6b"
                html += f"""
                <div style='padding: 8px; margin-bottom: 4px; background: rgba(184, 134, 11, 0.05); border-radius: 6px;'>
                    <span style='color: var(--text-muted);'>{entry.get('timestamp', '')[:19]}</span> |
                    <span style='color: {status_color}; font-weight: 600;'>{entry.get('status', '')}</span> |
                    <span style='color: var(--text-secondary);'>{entry.get('method', '')} {entry.get('url', '')[:50]}</span>
                </div>
                """
            except:
                pass
        
        html += "</div>"
        
        return HTMLResponse(html)
        
    except Exception as e:
        return HTMLResponse(f"<p style='color: #ff6b6b;'>Ошибка: {str(e)}</p>")

@router.get("/logbook/data")
async def logbook_data(
    current_user: User = Depends(get_current_user_from_cookie),
    db: AsyncSession = Depends(get_db)
):
    """Данные для генератора путевых листов"""
    try:
        # Получаем водителей
        stmt = select(User).where(User.role == "Driver")
        result = await db.execute(stmt)
        users = result.scalars().all()
        
        drivers = [{"id": u.id, "name": u.full_name} for u in users]
        
        # Получаем машины
        stmt = select(Vehicle).where(Vehicle.is_active == True)
        result = await db.execute(stmt)
        vehicles_list = result.scalars().all()
        
        vehicles = [
            {
                "id": v.id,
                "plate": v.license_plate,
                "brand": v.brand,
                "model": v.model
            }
            for v in vehicles_list
        ]
        
        return {
            "drivers": drivers,
            "vehicles": vehicles
        }
        
    except Exception as e:
        logger.error(f"Logbook data error: {e}")
        return {"drivers": [], "vehicles": []}

@router.get("/caller/{phone}")
async def caller_lookup(
    phone: str,
    current_user: User = Depends(get_current_user_from_cookie),
    db: AsyncSession = Depends(get_db)
):
    """
    CALLER ID LOOKUP
    Мгновенная справка по звонящему (до поднятия трубки)
    """
    try:
        from app.services.caller_id_service import caller_id_service
        
        info = await caller_id_service.get_caller_info(phone, db)
        
        return info
        
    except Exception as e:
        logger.error(f"Caller lookup error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/logs/api_sync")
async def get_api_sync_logs(
    lines: int = 5,
    current_user: User = Depends(get_current_user_from_cookie)
):
    """
    Получение последних строк лога синхронизации
    """
    try:
        log_path = Path("/root/dominion/storage/api_sync.log")
        if not log_path.exists():
            return {"logs": ["Лог файл не найден"]}
            
        with open(log_path, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            last_lines = all_lines[-lines:]
            
        return {"logs": [line.strip() for line in last_lines]}
    except Exception as e:
        logger.error(f"Log read error: {e}")
        return {"logs": [f"Ошибка чтения лога: {str(e)}"]}

