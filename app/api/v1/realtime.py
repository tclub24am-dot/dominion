# -*- coding: utf-8 -*-
# app/routes/realtime.py
# REAL-TIME STATUS ENGINE - Live WebSocket/SSE (v2026.1)

import logging
import asyncio
from typing import Set
from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.database import get_db
from app.models.all_models import User, Vehicle
from app.services.security import get_current_user_optional

logger = logging.getLogger("RealtimeEngine")
router = APIRouter(tags=["Real-Time"])
ws_router = APIRouter(tags=["WebSocket"])  # Отдельный роутер без зависимостей

# Store active SSE connections
active_connections = set()

# WebSocket notifications manager
class NotificationsManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WS Notifications: клиент подключен ({len(self.active_connections)} активных)")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"WS Notifications: клиент отключен ({len(self.active_connections)} активных)")

    async def broadcast(self, message: dict):
        import json
        msg = json.dumps(message)
        for connection in list(self.active_connections):
            try:
                await connection.send_text(msg)
            except Exception:
                self.active_connections.discard(connection)

notifications_manager = NotificationsManager()


@ws_router.websocket("/api/v1/ws/notifications")
async def notifications_ws(websocket: WebSocket):
    """WebSocket для real-time уведомлений Neural Core"""
    await notifications_manager.connect(websocket)
    try:
        while True:
            # Держим соединение открытым, ждём сообщений от клиента (heartbeat)
            data = await websocket.receive_text()
            # Можно обрабатывать ping/pong если нужно
            if data == "ping":
                await websocket.send_text('{"type": "pong"}')
    except WebSocketDisconnect:
        notifications_manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WS Notifications error: {e}")
        notifications_manager.disconnect(websocket)

@router.get("/api/v1/realtime/status-stream")
async def status_stream(
    request: Request,
    current_user = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Server-Sent Events stream для real-time статусов водителей
    АБСОЛЮТНАЯ ТОЧНОСТЬ: Каждые 5 секунд отправляем актуальный снимок
    Мгновенное отражение offline/online без кэширования
    """
    async def event_generator():
        try:
            import json
            from datetime import datetime
            
            client_start_time = datetime.now()
            MAX_CONNECTION_TIME = 60  # 🔒 Timeout 60 сек
            
            while True:
                # 🔒 Проверяем timeout
                elapsed = (datetime.now() - client_start_time).total_seconds()
                if elapsed > MAX_CONNECTION_TIME:
                    logger.info(f"✓ SSE timeout ({elapsed:.0f}с) - соединение закрыто")
                    break
                
                # ⚡ СВЕЖИЙ СНИМОК БЕЗ КЭША - Каждые 5 сек свежее состояние из БД
                stmt = select(
                    User.id,
                    User.full_name,
                    User.yandex_driver_id,
                    User.park_name,
                    User.role,
                    User.is_active,
                    User.current_vehicle_id,
                    User.driver_balance,
                    Vehicle.id.label("vehicle_id"),
                    Vehicle.license_plate,
                    Vehicle.status.label("vehicle_status")
                ).outerjoin(
                    Vehicle,
                    and_(
                        Vehicle.current_driver_id == User.id,
                        Vehicle.park_name == User.park_name
                    )
                ).where(
                    and_(
                        User.role == "Driver",
                        User.is_active == True  # ⚡ Только активные водители
                    )
                )
                
                result = await db.execute(stmt)
                drivers = result.fetchall()
                
                # Подготавливаем РЕАЛЬНЫЕ данные для отправки
                drivers_data = []
                park_drivers_count = 0  # 🔥 РЕАЛЬНЫЙ счет из БД
                connected_drivers_count = 0  # 🔥 РЕАЛЬНЫЙ счет из БД
                
                for driver in drivers:
                    is_park_driver = driver.current_vehicle_id is not None
                    
                    # ⚡ ТОЧНАЯ ЛОГИКА СТАТУСА:
                    status = "OFFLINE"
                    if driver.current_vehicle_id:
                        # У водителя есть привязанная машина
                        if driver.vehicle_status == "WORKING":
                            status = "ACTIVE"  # Зелёная точка
                        elif driver.vehicle_status == "CONNECTED":
                            status = "CONNECTED"  # Жёлтая точка
                        else:
                            status = "ONLINE"
                        park_drivers_count += 1
                    elif driver.is_active:
                        status = "ONLINE"  # Свободный без машины
                        connected_drivers_count += 1
                    
                    drivers_data.append({
                        "id": driver.id,
                        "name": driver.full_name,
                        "yandex_id": driver.yandex_driver_id,
                        "park": driver.park_name,
                        "status": status,  # ONLINE / ACTIVE / CONNECTED / OFFLINE
                        "balance": driver.driver_balance or 0,
                        "is_park_driver": is_park_driver,  # 🔥 РЕАЛЬНОЕ значение из БД
                        "vehicle": {
                            "id": driver.vehicle_id,
                            "license_plate": driver.license_plate,
                            "vehicle_status": driver.vehicle_status
                        } if driver.vehicle_id else None
                    })
                
                # 🔥 РЕАЛЬНЫЕ ЦИФРЫ, НЕ КОНСТАНТЫ!
                from datetime import datetime
                payload = {
                    "timestamp": datetime.now().isoformat(),
                    "drivers": drivers_data,
                    "total": len(drivers_data),
                    "park_drivers": park_drivers_count,  # 🔥 РЕАЛЬНО из БД
                    "connected_drivers": connected_drivers_count,  # 🔥 РЕАЛЬНО из БД
                    "active": sum(1 for d in drivers_data if d["status"] in ["ACTIVE", "ONLINE"])
                }
                
                logger.info(
                    f"SSE: Total={payload['total']}, "
                    f"ParkDrivers={payload['park_drivers']}, "
                    f"Connected={payload['connected_drivers']}, "
                    f"Active={payload['active']}"
                )
                yield f"data: {json.dumps(payload)}\n\n"
                
                # ⚡ ЖДЕМ ПЕРЕД СЛЕДУЮЩЕЙ ОТПРАВКОЙ (5 сек)
                await asyncio.sleep(5)
                
        except asyncio.CancelledError:
            logger.info("✓ SSE stream отключен")
        except Exception as e:
            logger.error(f"SSE error: {e}")
            import json
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )

@router.get("/api/v1/realtime/matrix")
async def driver_matrix(
    park: str = None,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user_optional)
):
    """
    Матрица Исполнителей: Парковые (current_vehicle_id NOT NULL) vs Подключки (current_vehicle_id IS NULL)
    """
    try:
        # 1. ПАРКОВЫЕ ВОДИТЕЛИ: роль Driver + current_vehicle_id IS NOT NULL
        park_filter = [User.role == "Driver", User.is_active == True, User.current_vehicle_id.isnot(None)]
        if park:
            park_filter.append(User.park_name == park.upper())
        
        park_stmt = select(func.count(User.id)).where(and_(*park_filter))
        park_result = await db.execute(park_stmt)
        park_drivers = park_result.scalar() or 0
        
        # 2. ПОДКЛЮЧНЫЕ ВОДИТЕЛИ: роль Driver + current_vehicle_id IS NULL
        connected_filter = [User.role == "Driver", User.is_active == True, User.current_vehicle_id.is_(None)]
        if park:
            connected_filter.append(User.park_name == park.upper())
        
        connected_stmt = select(func.count(User.id)).where(and_(*connected_filter))
        connected_result = await db.execute(connected_stmt)
        connected_drivers = connected_result.scalar() or 0
        
        # 3. ВСЕГО НА ЛИНИИ
        total_drivers = park_drivers + connected_drivers
        
        return {
            "park": park or "ALL",
            "matrix": {
                "park_drivers": park_drivers,      # 🤖 Парковые (41) - 3% комиссия
                "connected_drivers": connected_drivers,  # 🛰️ Подключки (15) - собственные авто
                "total_online": total_drivers,
                "formula": f"{total_drivers} = 🤖{park_drivers} | 🛰️{connected_drivers}"
            },
            "commission": {
                "park_rate": "3%",
                "connected_rate": "Своя машина"
            },
            "status": "LIVE"
        }
    except Exception as e:
        logger.error(f"Matrix error: {e}")
        return {
            "error": str(e),
            "matrix": {"park_drivers": 0, "connected_drivers": 0}
        }


# Вспомогательная функция для JSON
def import_json():
    import json
    return json
