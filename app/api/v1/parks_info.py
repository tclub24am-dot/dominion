# -*- coding: utf-8 -*-
"""
Справочник таксопарков S-GLOBAL DOMINION
VERSHINA v200.18 — Сектор FL
"""

from fastapi import APIRouter

router = APIRouter(tags=["Parks Info"])

# ── Справочник парков ──────────────────────────────────────────────────────────

PARKS = {
    "EXPRESS": {
        "name": "EXPRESS",
        "full_name": "ООО С-ГЛОБАЛ EXPRESS",
        "type": "logistics",
        "partner": "ВкусВилл",
        "description": "Логистика и доставка",
        "color": "#f59e0b",
    },
    "PRO": {
        "name": "PRO",
        "full_name": "t-club24 PRO",
        "type": "taxi",
        "partner": "Яндекс Такси",
        "description": "Профессиональный таксопарк",
        "color": "#d4a843",
    },
    "GO": {
        "name": "GO",
        "full_name": "t-club24 GO",
        "type": "taxi",
        "partner": "Яндекс Такси",
        "description": "Эконом-сегмент",
        "color": "#00ff88",
    },
    "PLUS": {
        "name": "PLUS",
        "full_name": "t-club24 PLUS",
        "type": "taxi",
        "partner": "Яндекс Такси",
        "description": "Комфорт-сегмент",
        "color": "#00f5ff",
    },
}


@router.get("/parks")
async def get_parks():
    """Возвращает справочник всех таксопарков S-GLOBAL DOMINION."""
    return {
        "status": "ok",
        "parks": list(PARKS.values()),
        "total": len(PARKS),
    }


@router.get("/parks/{park_name}")
async def get_park(park_name: str):
    """Возвращает информацию о конкретном парке."""
    key = park_name.upper()
    if key not in PARKS:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=404,
            detail=f"Парк '{park_name}' не найден. Доступные: {', '.join(PARKS.keys())}",
        )
    return {"status": "ok", "park": PARKS[key]}
