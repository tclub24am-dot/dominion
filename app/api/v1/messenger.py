# -*- coding: utf-8 -*-
# app/routes/messenger.py

import uuid
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Set
import asyncio
from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_

from app.database import get_db
from app.models.all_models import ChatMessage, User, Vehicle, Transaction, OracleArchive
from app.services.security import get_current_user_from_cookie, get_current_user_from_ws
from app.core.permissions import has_module_access
from app.core.modules import MODULES, get_enabled_modules, module_access
from app.core.config import settings
from app.services.oracle_service import oracle_service
from app.services.analytics_engine import AnalyticsEngine

router = APIRouter(tags=["Imperial Messenger"])
ws_router = APIRouter(tags=["WebSocket Messenger"])  # Отдельный роутер для WebSocket без зависимостей
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger("ImperialMessenger")


class MessengerManager:
    def __init__(self):
        self.channels: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, channel: str):
        await websocket.accept()
        self.channels.setdefault(channel, set()).add(websocket)

    def disconnect(self, websocket: WebSocket, channel: str):
        if channel in self.channels:
            self.channels[channel].discard(websocket)

    async def broadcast(self, channel: str, payload: dict):
        if channel not in self.channels:
            return
        dead = set()
        for ws in self.channels[channel]:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.channels[channel].discard(ws)


messenger_manager = MessengerManager()


@router.get("/imperial-messenger", response_class=HTMLResponse)
async def messenger_page(
    request: Request,
    current_user: User = Depends(get_current_user_from_cookie)
):
    return templates.TemplateResponse(
        "modules/messenger.html",
        {"request": request, "current_user": current_user}
    )


@router.get("/api/v1/messenger/channels")
async def messenger_channels(
    current_user: User = Depends(get_current_user_from_cookie)
):
    channels = [{"id": "ОБЩАЯ", "label": "ОБЩАЯ"}, {"id": "MASTER", "label": "MASTER"}]
    if current_user.role == "Master":
        channels.append({"id": "ORACLE ARCHIVE", "label": "ORACLE ARCHIVE"})
    enabled_modules = set(get_enabled_modules())
    for module_id, module in MODULES.items():
        if module_id == "core":
            continue
        if module_id not in enabled_modules:
            continue
        if not module_access(current_user.role, module_id):
            continue
        channels.append({"id": module["label"], "label": module["label"]})
    return {"channels": channels}


@router.get("/api/v1/messenger/messages")
async def messenger_messages(
    channel: str = "ОБЩАЯ",
    limit: int = 50,
    thread_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_cookie)
):
    stmt = select(ChatMessage).where(ChatMessage.group_name == channel)
    if thread_id:
        stmt = stmt.where(ChatMessage.thread_id == thread_id)
    else:
        stmt = stmt.where(ChatMessage.parent_id.is_(None))
    stmt = stmt.order_by(desc(ChatMessage.created_at)).limit(limit)
    result = await db.execute(stmt)
    messages = list(reversed(result.scalars().all()))

    return {
        "channel": channel,
        "thread_id": thread_id,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "thread_id": m.thread_id,
                "parent_id": m.parent_id,
                "user_id": m.user_id,
                "file_path": m.file_path,
                "attachments": m.attachments or [],
                "created_at": m.created_at.isoformat() if m.created_at else None
            }
            for m in messages
        ]
    }


@router.get("/api/v1/messenger/thread")
async def messenger_thread(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_cookie)
):
    stmt = select(ChatMessage).where(
        ChatMessage.thread_id == thread_id
    ).order_by(ChatMessage.created_at.asc())
    result = await db.execute(stmt)
    messages = result.scalars().all()
    return {
        "thread_id": thread_id,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "thread_id": m.thread_id,
                "parent_id": m.parent_id,
                "user_id": m.user_id,
                "file_path": m.file_path,
                "attachments": m.attachments or [],
                "created_at": m.created_at.isoformat() if m.created_at else None
            }
            for m in messages
        ]
    }


@router.get("/api/v1/messenger/oracle-archive")
async def messenger_oracle_archive(
    days: int = 7,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_cookie)
):
    if current_user.role != "Master":
        raise HTTPException(status_code=403, detail="Доступ только для Мастера")
    cutoff = datetime.now() - timedelta(days=days)
    stmt = select(OracleArchive).where(
        OracleArchive.created_at >= cutoff
    ).order_by(desc(OracleArchive.created_at))
    result = await db.execute(stmt)
    items = result.scalars().all()
    return {
        "items": [
            {
                "id": item.id,
                "title": item.title,
                "content": item.content,
                "severity": item.severity,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "meta": item.meta or {}
            }
            for item in items
        ]
    }


@router.post("/api/v1/messenger/messages")
async def post_message(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_cookie)
):
    channel = payload.get("channel", "ОБЩАЯ")
    content = (payload.get("content") or "").strip()
    parent_id = payload.get("parent_id")
    thread_id = payload.get("thread_id")

    if not content:
        raise HTTPException(status_code=400, detail="Пустое сообщение")

    # Определяем тред
    if parent_id and not thread_id:
        parent_stmt = select(ChatMessage).where(ChatMessage.id == parent_id)
        parent_result = await db.execute(parent_stmt)
        parent = parent_result.scalar_one_or_none()
        if parent:
            thread_id = parent.thread_id or str(parent.id)
            if not parent.thread_id:
                parent.thread_id = thread_id
                await db.commit()

    # Объектные привязки
    attachments = []
    vehicle_match = re.search(r"\[Машина\s+([A-Za-zА-Яа-я0-9\-]+)\]", content)
    if vehicle_match:
        plate = vehicle_match.group(1).upper()
        vehicle_stmt = select(Vehicle).where(Vehicle.license_plate == plate)
        vehicle_result = await db.execute(vehicle_stmt)
        vehicle = vehicle_result.scalar_one_or_none()
        if vehicle:
            attachments.append({
                "type": "vehicle",
                "label": plate,
                "url": f"/garage/{vehicle.id}",
                "status": vehicle.status or "unknown",
                "brand": vehicle.brand,
                "model": vehicle.model
            })

    tx_match = re.search(r"\[Транзакция\s+(\d+)\]", content)
    if tx_match:
        tx_id = int(tx_match.group(1))
        tx_stmt = select(Transaction).where(Transaction.id == tx_id)
        tx_result = await db.execute(tx_stmt)
        tx = tx_result.scalar_one_or_none()
        if tx:
            attachments.append({
                "type": "transaction",
                "label": f"Транзакция #{tx_id}",
                "url": "/kazna/transactions"
            })

    msg = ChatMessage(
        role="user",
        content=content,
        group_name=channel,
        user_id=current_user.id,
        parent_id=parent_id,
        thread_id=thread_id,
        attachments=attachments
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    response_payload = {
        "id": msg.id,
        "role": msg.role,
        "content": msg.content,
        "channel": channel,
        "thread_id": msg.thread_id,
        "parent_id": msg.parent_id,
        "attachments": msg.attachments or [],
        "created_at": msg.created_at.isoformat() if msg.created_at else None
    }

    await messenger_manager.broadcast(channel, {"type": "message", "message": response_payload})

    # Oracle AI: всегда отвечает в каждом канале
    group = "ОБЩАЯ"
    name = channel.upper()
    if "КАЗН" in name or "ФИН" in name:
        group = "ФИНАНСЫ"
    elif "ФЛОТ" in name or "ТАКСО" in name:
        group = "ФЛОТ"
    elif "ПЛАН" in name:
        group = "ПЛАНИРОВАНИЕ"

    context = {}
    try:
        context["overlay"] = await AnalyticsEngine.get_overlay_metrics(db)
        if group == "ФИНАНСЫ":
            context["kazna_summary_7d"] = await AnalyticsEngine.get_kazna_summary(db, days=7)
    except Exception as exc:
        # Roll back failed context queries to avoid aborting the AI insert
        await db.rollback()
        logger.warning("Oracle context query failed: %s", exc)
        context = {}

    try:
        ai_response = await asyncio.wait_for(
            oracle_service.send_message(message=content, group=group, context=context),
            timeout=3.0
        )
    except asyncio.TimeoutError:
        ai_response = {"message": "Oracle готовит ответ. Пожалуйста, повторите запрос через секунду."}
    ai_msg = ChatMessage(
        role="assistant",
        content=ai_response.get("message") if isinstance(ai_response, dict) else str(ai_response),
        group_name=channel,
        user_id=None,
        thread_id=thread_id,
        parent_id=msg.id,
        attachments=[]
    )
    db.add(ai_msg)
    await db.commit()
    await db.refresh(ai_msg)
    ai_payload = {
        "id": ai_msg.id,
        "role": ai_msg.role,
        "content": ai_msg.content,
        "channel": channel,
        "thread_id": ai_msg.thread_id,
        "parent_id": ai_msg.parent_id,
        "attachments": ai_msg.attachments or [],
        "created_at": ai_msg.created_at.isoformat() if ai_msg.created_at else None,
        "author": "Oracle AI"
    }
    await messenger_manager.broadcast(channel, {"type": "message", "message": ai_payload})

    return {"status": "ok", "message": response_payload, "oracle": ai_payload}


@router.post("/api/v1/messenger/upload")
async def messenger_upload(
    file: UploadFile = File(...),
    channel: str = "ОБЩАЯ",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_cookie)
):
    os.makedirs(settings.ORACLE_UPLOAD_DIR, exist_ok=True)
    filename = f"{uuid.uuid4().hex}_{file.filename}"
    file_path = os.path.join(settings.ORACLE_UPLOAD_DIR, filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())

    msg = ChatMessage(
        role="user",
        content=f"📎 Файл: {file.filename}",
        group_name=channel,
        user_id=current_user.id,
        file_path=file_path,
        attachments=[]
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    await messenger_manager.broadcast(channel, {
        "type": "message",
        "message": {
            "id": msg.id,
            "role": msg.role,
            "content": msg.content,
            "channel": channel,
            "file_path": msg.file_path,
            "attachments": msg.attachments or [],
            "created_at": msg.created_at.isoformat() if msg.created_at else None
        }
    })

    return {"status": "ok", "file_path": file_path}

@router.post("/api/v1/messenger/driver-summary")
async def messenger_driver_summary(
    driver_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_cookie)
):
    """
    AI-сводка по водителю (Oracle/Ollama)
    """
    brief = await AnalyticsEngine.get_driver_brief(db, driver_id)
    if brief.get("status") != "ok":
        raise HTTPException(status_code=404, detail="Водитель не найден")

    context = {
        "driver_name": brief["driver_name"],
        "kpi": brief["kpi"],
        "stars": brief["stars"],
        "golden_star": brief["golden_star"],
        "revenue_48h": brief["revenue_48h"],
        "online_hours": brief["online_hours"],
        "risk_reason": brief["risk_reason"],
        "driver_balance": brief["driver_balance"],
    }
    prompt = (
        "Сформируй краткую сводку для Мастера (1-2 предложения) по водителю. "
        "Если KPI высок и нет штрафов — предложи Золотую Звезду. "
        "Если есть риск — упомяни причину. "
        "Формат: 'Мастер, ...'."
    )
    ai_response = await oracle_service.send_message(
        message=prompt,
        group="ФЛОТ",
        context=context
    )
    message = ai_response.get("message") if isinstance(ai_response, dict) else str(ai_response)
    return {"status": "ok", "message": message, "brief": brief}


@ws_router.websocket("/api/v1/ws/messenger")
async def messenger_ws(
    websocket: WebSocket
):
    channel = websocket.query_params.get("channel", "ОБЩАЯ")
    if channel == "ORACLE ARCHIVE":
        await websocket.close(code=4403)
        return
    access_token = websocket.cookies.get("access_token")
    current_user = await get_current_user_from_ws(access_token)
    if not current_user or not has_module_access(current_user, "messenger"):
        await websocket.close(code=4403)
        return
    await messenger_manager.connect(websocket, channel)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        messenger_manager.disconnect(websocket, channel)
