# -*- coding: utf-8 -*-
# app/api/v1/telephony.py
# S-GLOBAL DOMINION — Телефония 1ATS / Asterisk Integration
# VERSHINA v200.15: HMAC Lockdown + DoS Protection + IDOR Fix
# v200.15 CHANGES:
#   - urllib.parse.parse_qs для form-body (body уже прочитан)
#   - IntegrityError вместо SELECT-дедупликации (race condition fix)
#   - tenant_id ТОЛЬКО из middleware/SIP-конфига, не из payload (SAAS INTEGRITY)

import logging
import re
import hmac
import hashlib
import urllib.parse
from datetime import datetime, timezone
from typing import Optional

import json
from sqlalchemy.exc import IntegrityError

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Request, HTTPException, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_

from app.database import get_db, AsyncSessionLocal
from app.models.all_models import User, CallLog, ChatMessage
from app.services.telegram_bot import telegram_bot
from app.services.auth import get_current_user
from app.core.config import settings
from app.core.tenant_middleware import _is_valid_tenant_id

# Fix #2: prefix убран — добавляется в main.py при include_router()
# VERSHINA v200.16.3: Два роутера — webhook (без JWT) и api (с require_module)
webhook_router = APIRouter(tags=["Telephony Webhooks"])
api_router = APIRouter(tags=["Telephony"])
# Legacy alias для обратной совместимости импортов
router = api_router
logger = logging.getLogger("TelephonyBridge")


# =================================================================
# PYDANTIC MODELS
# =================================================================

class OneATSWebhookPayload(BaseModel):
    """Валидация payload от 1ATS webhook"""
    event: str = Field(..., description="new_call | call_answered | call_ended | call_missed")
    caller: str = Field(..., description="Номер звонящего")
    callee: str = Field(default="", description="Номер принимающего")
    duration: int = Field(default=0, ge=0, description="Длительность в секундах")
    timestamp: Optional[str] = Field(default=None, description="Время события")


class AsteriskWebhookPayload(BaseModel):
    """Валидация payload от Asterisk webhook"""
    Channel: Optional[str] = Field(default="", description="Канал (содержит номер)")
    Event: Optional[str] = Field(default="", description="Событие звонка")
    CallerIDNum: Optional[str] = Field(default="", description="Номер caller")
    Duration: Optional[int] = Field(default=0, ge=0, description="Длительность")
    # Альтернативные имена полей
    caller_id: Optional[str] = Field(default="", description="Альтернативный номер caller")
    duration: Optional[int] = Field(default=0, ge=0, description="Длительность (альтернативное)")


# =================================================================
# SECURITY: WEBHOOK TOKEN VERIFICATION
# =================================================================

def _verify_simple_token(request: Request) -> bool:
    """
    Проверяет Bearer-токен или X-Webhook-Token.
    Возвращает True если токен валиден, False если заголовок отсутствует.
    Бросает HTTPException(401) если заголовок есть, но токен неверный.

    SECURITY FIX v200.14: Если ATS_WEBHOOK_SECRET не задан (None/пустая строка),
    функция возвращает False вместо TypeError при hmac.compare_digest(token, None).
    """
    secret = settings.ATS_WEBHOOK_SECRET

    # GUARD: секрет не задан — не можем проверить токен, возвращаем False
    # (вышестоящий _verify_webhook_auth сам решит: пропустить или заблокировать)
    if not secret:
        return False

    # Метод 1: Bearer token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            if hmac.compare_digest(token, secret):
                return True
        except TypeError:
            pass
        raise HTTPException(status_code=401, detail="Invalid webhook Bearer token")

    # Метод 2: X-Webhook-Token (простой токен)
    token_header = request.headers.get("X-Webhook-Token", "")
    if token_header:
        try:
            if hmac.compare_digest(token_header, secret):
                return True
        except TypeError:
            pass
        raise HTTPException(status_code=401, detail="Invalid X-Webhook-Token")

    return False


async def _verify_webhook_auth(request: Request, body: bytes) -> bool:
    """
    v200.15.3 HMAC LOCKDOWN: Полная верификация входящих webhook-запросов.

    Приоритет методов:
    1. Bearer-токен в заголовке Authorization
    2. X-Webhook-Token (простой токен)
    3. X-Webhook-Signature (HMAC-SHA256 подпись тела) — РЕАЛЬНАЯ проверка

    Если ATS_WEBHOOK_SECRET не задан — пропускаем (режим разработки).

    Возвращает True если токен явно валиден (методы 1 или 2),
    False если секрет не задан (dev-режим) или прошла HMAC-проверка.
    Это позволяет вызывающему коду доверять tenant_id из payload при явном токене.
    """
    secret = settings.ATS_WEBHOOK_SECRET
    if not secret:
        logger.warning(
            "ATS_WEBHOOK_SECRET not configured — webhook endpoint is UNPROTECTED. "
            "Set ATS_WEBHOOK_SECRET in .env for production."
        )
        return False

    # Методы 1 и 2: простые токены — явная аутентификация, доверяем payload
    if _verify_simple_token(request):
        return True

    # Метод 3: X-Webhook-Signature (HMAC-SHA256) — РЕАЛЬНАЯ проверка подписи тела
    sig_header = request.headers.get("X-Webhook-Signature", "")
    if sig_header:
        expected = hmac.HMAC(
            secret.encode("utf-8"),
            body,
            hashlib.sha256
        ).hexdigest()
        expected_full = f"sha256={expected}"
        if not hmac.compare_digest(expected_full, sig_header):
            logger.warning(
                f"HMAC signature mismatch: expected={expected_full[:20]}..., "
                f"got={sig_header[:20]}..."
            )
            raise HTTPException(status_code=401, detail="Invalid HMAC-SHA256 webhook signature")
        return False

    raise HTTPException(
        status_code=401,
        detail=(
            "Webhook authentication required. "
            "Provide: Authorization: Bearer <token>, X-Webhook-Token: <token>, "
            "or X-Webhook-Signature: sha256=<hmac_sha256_of_body>"
        )
    )


# =================================================================
# HELPER FUNCTIONS
# =================================================================

def normalize_phone(phone: str) -> str:
    """Нормализация номера телефона к формату +7XXXXXXXXXX"""
    if not phone:
        return ""
    digits = re.sub(r'\D', '', phone)
    if digits.startswith('8') and len(digits) == 11:
        digits = '7' + digits[1:]
    if len(digits) == 10:
        digits = '7' + digits
    return f"+{digits}"


async def find_driver_by_phone(
    db: AsyncSession,
    phone: str,
    tenant_id: str = "s-global"
) -> Optional[User]:
    """
    Поиск водителя по номеру телефона с фильтрацией по tenant_id.
    Ищет в: User.phone, User.yandex_phones.
    """
    normalized = normalize_phone(phone)
    # normalize_phone() уже возвращает +7XXXXXXXXXX — дополнительный + не нужен
    last_10 = normalized[-10:] if len(normalized) >= 10 else normalized

    # 1. Поиск по основному номеру
    query = select(User).where(
        and_(
            User.tenant_id == tenant_id,
            or_(
                User.phone == normalized,
                User.phone.like(f"%{last_10}%")
            )
        )
    )
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if user:
        logger.info(f"Found driver by phone: {user.full_name} (ID: {user.id})")
        return user

    # 2. Поиск в JSONB поле yandex_phones (массив строк)
    # ИСПРАВЛЕНИЕ: .contains() для JSONB-массива требует список, а не строку.
    # Ищем как полный номер (+7...), так и последние 10 цифр.
    query = select(User).where(
        and_(
            User.tenant_id == tenant_id,
            or_(
                User.yandex_phones.contains([normalized]),
                User.yandex_phones.contains([last_10]),
            )
        )
    )
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if user:
        logger.info(f"Found driver by yandex_phones: {user.full_name} (ID: {user.id})")
        return user

    logger.warning(f"Driver not found for phone: {phone}")
    return None


async def notify_master_about_call(
    caller_phone: str,
    driver_id: Optional[int],
    driver_name: Optional[str],
    driver_park: Optional[str],
    call_status: str,
    call_duration: Optional[int] = None
) -> None:
    """
    Fix #5: Фоновая задача уведомления Мастера о входящем звонке.

    ВАЖНО: Создаёт СОБСТВЕННУЮ сессию БД через AsyncSessionLocal(),
    т.к. основная сессия из Depends(get_db) закрывается после ответа.
    Принимает только сериализуемые данные (не ORM-объекты).
    """
    driver_info = f"🚗 {driver_name}" if driver_name else "❓ Неизвестный"
    if driver_id:
        driver_info += f" (ID: {driver_id}, Park: {driver_park or 'N/A'})"

    status_emoji = {
        "answered": "✅",
        "missed": "❌",
        "busy": "⏳",
        "failed": "💥",
        "ended": "📴",
        "new": "📞",
    }.get(call_status, "📞")

    message = (
        f"{status_emoji} ВХОДЯЩИЙ ЗВОНОК\n\n"
        f"📱 Номер: {caller_phone}\n"
        f"👤 {driver_info}\n"
        f"⏱️ Длительность: {call_duration or 0} сек\n"
        f"🕐 Время: {datetime.now(timezone.utc).strftime('%H:%M:%S')}"
    )

    # Telegram-уведомление Мастеру
    if settings.ADMIN_ID:
        try:
            await telegram_bot.send_to_user(str(settings.ADMIN_ID), message)
        except Exception as e:
            logger.warning(f"Telegram notification failed: {e}")

    # Запись в чат "ОБЩАЯ" через собственную сессию
    # ИСПРАВЛЕНИЕ: поле называется group_name (не group), поля source нет в модели.
    try:
        async with AsyncSessionLocal() as db:
            chat_msg = ChatMessage(
                content=message,
                role="assistant",
                group_name="ОБЩАЯ",
            )
            db.add(chat_msg)
            await db.commit()
    except Exception as e:
        logger.error(f"Failed to write chat message: {e}", exc_info=True)


async def notify_driver_telegram(
    telegram_id: str,
    driver_name: str,
    caller_phone: str,
    call_status: str
) -> None:
    """
    Fix #5: Фоновая задача уведомления водителя в Telegram.
    Принимает только сериализуемые данные (не ORM-объекты).
    """
    status_text = {
        "answered": "Вам позвонили",
        "missed": "Вам звонили (пропущенный)",
        "busy": "Линия занята",
    }.get(call_status, "Вам звонят")

    message = (
        f"📞 S-GLOBAL DOMINION\n\n"
        f"{status_text}\n"
        f"📱 Номер: {caller_phone}\n"
        f"🕐 Время: {datetime.now(timezone.utc).strftime('%H:%M:%S')}"
    )
    try:
        await telegram_bot.send_to_user(telegram_id, message)
    except Exception as e:
        logger.warning(f"Driver telegram notification failed for {driver_name}: {e}")


# =================================================================
# WEBHOOK ENDPOINTS (1ATS / Asterisk)
# =================================================================

@webhook_router.post("/webhook/1ats")
async def webhook_1ats(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    Webhook для приёма событий от 1ATS.

    v200.14 HMAC LOCKDOWN: Bearer-токен, X-Webhook-Token или HMAC-SHA256 подпись тела.
    Поля payload:
    - event: new_call | call_answered | call_ended | call_missed
    - caller: номер звонящего
    - callee: номер принимающего
    - duration: длительность в секундах
    - timestamp: время события
    """
    # v200.15: Читаем body ОДИН РАЗ, передаём в верификатор и парсер
    body = await request.body()
    await _verify_webhook_auth(request, body)

    try:
        payload = json.loads(body)
    except Exception:
        # v200.15 FIX: body уже прочитан — request.form() повторно не работает.
        # Используем urllib.parse.parse_qs для разбора application/x-www-form-urlencoded
        try:
            raw = urllib.parse.parse_qs(body.decode("utf-8", errors="replace"))
            payload = {k: v[0] for k, v in raw.items()}
        except Exception:
            payload = {}

    event = payload.get("event", "")
    caller = payload.get("caller", "")
    callee = payload.get("callee", "")
    duration = int(payload.get("duration", 0) or 0)

    call_status = {
        "call_missed": "missed",
        "call_answered": "answered",
        "call_busy": "busy",
        "call_ended": "ended",
    }.get(event, "unknown")

    # tenant_id из middleware (Hard Isolation)
    tenant_id = getattr(request.state, "tenant_id", "s-global")

    logger.info(
        f"[1ATS] event={event!r} caller={caller!r} callee={callee!r} "
        f"duration={duration}s status={call_status!r} tenant={tenant_id!r}"
    )

    # Поиск водителя по номеру телефона
    driver = await find_driver_by_phone(db, caller, tenant_id=tenant_id)
    if driver:
        logger.info(f"[1ATS] Driver matched: id={driver.id} name={driver.full_name!r} park={driver.park_name!r}")
    else:
        logger.warning(f"[1ATS] No driver found for caller={caller!r} tenant={tenant_id!r}")

    # Сохраняем звонок в БД
    call_log = CallLog(
        user_id=driver.id if driver else None,
        tenant_id=tenant_id,
        caller_phone=normalize_phone(caller),
        callee_phone=normalize_phone(callee) if callee else None,
        call_status=call_status,
        duration=duration,
        recording_url=None,
        ai_rating=5,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(call_log)
    try:
        await db.commit()
        await db.refresh(call_log)
        logger.info(f"[1ATS] CallLog saved: id={call_log.id} tenant={tenant_id!r}")
    except Exception as db_err:
        await db.rollback()
        logger.error(f"[1ATS] DB commit failed for caller={caller!r}: {db_err}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save call log")

    # Уведомления через background tasks (сериализуемые данные)
    background_tasks.add_task(
        notify_master_about_call,
        caller,
        driver.id if driver else None,
        driver.full_name if driver else None,
        driver.park_name if driver else None,
        call_status,
        duration,
    )

    if driver and driver.telegram_id:
        background_tasks.add_task(
            notify_driver_telegram,
            driver.telegram_id,
            driver.full_name,
            caller,
            call_status,
        )

    return JSONResponse({"status": "ok", "event": event, "call_status": call_status})


@webhook_router.post("/webhook/asterisk")
async def webhook_asterisk(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    Webhook для приёма событий от Asterisk (S-АТС / AMI / Dialplan CURL).

    v200.14 HMAC LOCKDOWN: Bearer-токен, X-Webhook-Token или HMAC-SHA256 подпись тела.

    Поля payload (от S-АТС dialplan):
    - Event: new_call | call_answered | call_ended | call_missed (из extensions.conf)
    - CallerIDNum: номер caller
    - Channel: callee / внутренний номер
    - Duration: длительность в секундах
    - tenant_id: изоляция парка (pro | go | plus | express) — ПРИОРИТЕТ над middleware
    - timestamp: ISO8601 время события
    - uniqueid: уникальный ID звонка Asterisk

    Поля payload (от Asterisk AMI — legacy):
    - Event: Newchannel | Hangup | Answer | DialBegin | DialEnd
    - CallerIDNum: номер caller
    - Duration: длительность
    """
    # v200.15.3: Читаем body ОДИН РАЗ, передаём в верификатор и парсер
    # _verify_webhook_auth возвращает True если токен явно валиден (Bearer/X-Webhook-Token)
    body = await request.body()
    token_trusted = await _verify_webhook_auth(request, body)

    try:
        payload = json.loads(body)
    except Exception:
        # v200.15 FIX: body уже прочитан — request.form() повторно не работает.
        # Используем urllib.parse.parse_qs для разбора application/x-www-form-urlencoded
        try:
            raw = urllib.parse.parse_qs(body.decode("utf-8", errors="replace"))
            payload = {k: v[0] for k, v in raw.items()}
        except Exception:
            payload = {}

    caller_id = payload.get("CallerIDNum", "") or payload.get("caller_id", "")
    event = payload.get("Event", "")
    asterisk_duration = int(payload.get("Duration", 0) or 0)
    # Уникальный ID звонка (для дедупликации)
    unique_id = payload.get("uniqueid", "") or payload.get("Uniqueid", "")

    if not caller_id:
        logger.warning(f"[Asterisk] Ignored event={event!r}: no CallerIDNum in payload")
        return JSONResponse({"status": "ignored", "reason": "no_caller_id"})

    # =================================================================
    # МАППИНГ СОБЫТИЙ: S-АТС dialplan (приоритет) + AMI legacy
    # =================================================================
    # S-АТС dialplan события (из extensions.conf macro-dominion-webhook)
    _SATS_STATUS_MAP = {
        "new_call": "new",
        "call_answered": "answered",
        "call_ended": "ended",
        "call_missed": "missed",
    }
    # Asterisk AMI события (legacy / прямая интеграция)
    _AMI_STATUS_MAP = {
        "Hangup": "ended",
        "HangupRequest": "ended",
        "SoftHangupRequest": "ended",
        "HangupHandlerRun": "ended",
        "Answer": "answered",
        "Newchannel": "new",
        "DialBegin": "new",
        "DialEnd": "ended",
    }
    call_status = _SATS_STATUS_MAP.get(event) or _AMI_STATUS_MAP.get(event, "new")

    # =================================================================
    # TENANT ISOLATION v200.15.3: ASTERISK TRUST
    # Если X-Webhook-Token валиден (token_trusted=True) — ДОВЕРЯЕМ tenant_id из payload.
    # Это позволяет звонкам из парков PRO, GO, PLUS попадать в свои разделы.
    # Если токен не предъявлен (HMAC или dev-режим) — берём tenant из middleware.
    # =================================================================
    middleware_tenant = getattr(request.state, "tenant_id", "s-global")
    payload_tenant = payload.get("tenant_id", "").strip()

    if token_trusted and payload_tenant:
        # VERSHINA v200.16.4: Даже при доверенном токене — валидируем tenant_id regex
        if _is_valid_tenant_id(payload_tenant):
            tenant_id = payload_tenant
            logger.info(
                f"[Asterisk] tenant_id={tenant_id!r} принят из payload (токен валиден, regex OK)"
            )
        else:
            tenant_id = middleware_tenant
            logger.warning(
                f"[Asterisk] tenant_id={payload_tenant!r} из payload ОТКЛОНЁН "
                f"(не прошёл regex-валидацию). Используется middleware: {tenant_id!r}"
            )
    else:
        # Fallback: middleware или дефолт
        tenant_id = middleware_tenant
        if payload_tenant and not token_trusted:
            logger.warning(
                f"[Asterisk] tenant_id={payload_tenant!r} в payload ПРОИГНОРИРОВАН "
                f"(токен не предъявлен). Используется tenant из middleware: {tenant_id!r}"
            )

    logger.info(
        f"[Asterisk] event={event!r} caller={caller_id!r} "
        f"duration={asterisk_duration}s status={call_status!r} "
        f"tenant={tenant_id!r} uniqueid={unique_id!r}"
    )

    # Поиск водителя по номеру телефона
    driver = await find_driver_by_phone(db, caller_id, tenant_id=tenant_id)
    if driver:
        logger.info(f"[Asterisk] Driver matched: id={driver.id} name={driver.full_name!r} park={driver.park_name!r}")
    else:
        logger.warning(f"[Asterisk] No driver found for caller={caller_id!r} tenant={tenant_id!r}")

    # =================================================================
    # ДЕДУПЛИКАЦИЯ v200.15: Race Condition Fix
    # Используем try/except IntegrityError вместо SELECT-проверки.
    # unique=True на asterisk_unique_id гарантирует атомарность на уровне БД.
    # SELECT-подход имеет race condition при параллельных запросах.
    # =================================================================
    callee_channel = payload.get("Channel", "") or ""
    call_log = CallLog(
        user_id=driver.id if driver else None,
        tenant_id=tenant_id,
        caller_phone=normalize_phone(caller_id),
        callee_phone=normalize_phone(callee_channel) if callee_channel else None,
        call_status=call_status,
        duration=asterisk_duration,
        recording_url=None,
        ai_rating=5,
        timestamp=datetime.now(timezone.utc),
        asterisk_unique_id=unique_id or None,
    )
    db.add(call_log)
    try:
        await db.commit()
        await db.refresh(call_log)
        logger.info(
            f"[Asterisk] CallLog saved: id={call_log.id} "
            f"tenant={tenant_id!r} uniqueid={unique_id!r}"
        )
    except IntegrityError:
        # Дубль по unique asterisk_unique_id — нормальная ситуация при retry от Asterisk
        await db.rollback()
        logger.info(
            f"[Asterisk] Duplicate event (IntegrityError): uniqueid={unique_id!r} "
            f"event={event!r} status={call_status!r} — skipped"
        )
        return JSONResponse({"status": "duplicate", "uniqueid": unique_id})
    except Exception as db_err:
        await db.rollback()
        logger.error(f"[Asterisk] DB commit failed for caller={caller_id!r}: {db_err}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save call log")

    # Уведомления через background tasks (сериализуемые данные)
    background_tasks.add_task(
        notify_master_about_call,
        caller_id,
        driver.id if driver else None,
        driver.full_name if driver else None,
        driver.park_name if driver else None,
        call_status,
        asterisk_duration,
    )

    return JSONResponse({"status": "ok", "event": event, "call_status": call_status})


# =================================================================
# CALL LOG ENDPOINTS
# =================================================================

@router.get("/calls")
async def get_recent_calls(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500, description="Количество записей (макс. 500)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    История звонков текущего тенанта.

    Fix #4: WHERE CallLog.tenant_id == tenant_id применяется к самой таблице CallLog,
    а не только к JOIN-условию. Тенант А никогда не видит звонки Тенанта Б.
    """
    tenant_id = getattr(request.state, "tenant_id", "s-global")

    query = (
        select(CallLog, User)
        .where(CallLog.tenant_id == tenant_id)  # Fix #4: Hard isolation
        .outerjoin(
            User,
            and_(
                CallLog.user_id == User.id,
                User.tenant_id == tenant_id,
            ),
        )
        .order_by(CallLog.timestamp.desc())
        .limit(limit)
    )
    result = await db.execute(query)
    rows = result.all()

    calls = [
        {
            "id": call_log.id,
            "phone": call_log.caller_phone,          # v200.13: переименовано из phone_number
            "callee_phone": call_log.callee_phone,
            "call_status": call_log.call_status,
            "duration": call_log.duration,
            "recording_url": call_log.recording_url,
            "driver_name": user.full_name if user else None,
            "driver_id": user.id if user else None,
            "timestamp": call_log.timestamp.isoformat() if call_log.timestamp else None,
            "ai_rating": call_log.ai_rating,
        }
        for call_log, user in rows
    ]

    return {"calls": calls, "total": len(calls)}


@router.get("/calls/{call_id}")
async def get_call_details(
    call_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Детали конкретного звонка.

    Fix #4: WHERE CallLog.tenant_id == tenant_id гарантирует,
    что тенант не может получить чужой звонок по ID.
    """
    tenant_id = getattr(request.state, "tenant_id", "s-global")

    query = (
        select(CallLog, User)
        .where(
            and_(
                CallLog.id == call_id,
                CallLog.tenant_id == tenant_id,  # Fix #4: Hard isolation
            )
        )
        .outerjoin(
            User,
            and_(
                CallLog.user_id == User.id,
                User.tenant_id == tenant_id,
            ),
        )
    )
    result = await db.execute(query)
    row = result.one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="Call not found")

    call_log, user = row

    return {
        "id": call_log.id,
        "phone": call_log.caller_phone,              # v200.13: переименовано из phone_number
        "callee_phone": call_log.callee_phone,
        "call_status": call_log.call_status,
        "duration": call_log.duration,
        "recording_url": call_log.recording_url,
        "driver": {
            "id": user.id,
            "full_name": user.full_name,
            "park_name": user.park_name,
            # telegram_id УДАЛЁН (PII-защита)
        } if user else None,
        "timestamp": call_log.timestamp.isoformat() if call_log.timestamp else None,
        "ai_rating": call_log.ai_rating,
    }


# =================================================================
# DRIVER PHONE LOOKUP
# =================================================================

@router.get("/lookup/{phone}")
async def lookup_driver_by_phone(
    phone: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Поиск водителя по номеру телефона.
    ТРЕБУЕТСЯ авторизация (защита PII).
    """
    tenant_id = getattr(request.state, "tenant_id", "s-global")
    driver = await find_driver_by_phone(db, phone, tenant_id=tenant_id)

    if not driver:
        return {
            "found": False,
            "phone": phone,
            "message": "Водитель не найден в системе",
        }

    return {
        "found": True,
        "driver": {
            "id": driver.id,
            "full_name": driver.full_name,
            "park_name": driver.park_name,
            "rating": driver.rating,
            "current_vehicle": (
                driver.current_vehicle.license_plate
                if driver.current_vehicle
                else None
            ),
        },
    }


# =================================================================
# STATUS ENDPOINT
# =================================================================

@router.get("/status")
async def get_telephony_status() -> dict:
    """Статус модуля телефонии"""
    return {
        "status": "online",
        "provider": "1ATS / Asterisk",
        "configured": bool(settings.ATS_API_KEY),
        "webhook_secret_set": bool(settings.ATS_WEBHOOK_SECRET),
        "admin_notifications": bool(settings.ADMIN_ID),
        "webhook_endpoints": [
            "/api/v1/telephony/webhook/1ats",
            "/api/v1/telephony/webhook/asterisk",
        ],
    }
