# -*- coding: utf-8 -*-

import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.core.config import settings
from app.models.all_models import User
from app.services.security import get_current_user_from_cookie
from app.services.miks_ai_link import miks_ai_link

logger = logging.getLogger("Dominion.MIKS")

router = APIRouter(tags=["MIKS"])


def _build_matrix_localpart(user: User) -> str:
    base = user.username or f"user-{user.id}"
    normalized = re.sub(r"[^a-z0-9._=-]", "-", base.lower()).strip("-")
    return normalized or f"user-{user.id}"


async def _ensure_matrix_account(current_user: User) -> dict[str, Any]:
    homeserver = settings.MATRIX_HOMESERVER_URL.rstrip("/")
    admin_token = settings.MATRIX_ADMIN_ACCESS_TOKEN or settings.MATRIX_ACCESS_TOKEN
    if not admin_token:
        raise HTTPException(status_code=503, detail="Matrix admin token is not configured")

    localpart = _build_matrix_localpart(current_user)
    user_id = f"@{localpart}:{settings.MATRIX_SERVER_NAME}"
    headers = {"Authorization": f"Bearer {admin_token}"}
    # VERSHINA v200.16.4: HMAC-генерация пароля — исключает детерминистический взлом.
    # Ключ = MATRIX_ADMIN_SHARED_SECRET (или SECRET_KEY), сообщение = user identity.
    hmac_key = (settings.MATRIX_ADMIN_SHARED_SECRET or settings.SECRET_KEY).encode("utf-8")
    password_msg = f"{current_user.id}:{current_user.username}:{current_user.tenant_id}".encode("utf-8")
    password = hmac.HMAC(hmac_key, password_msg, hashlib.sha256).hexdigest()[:32]

    async with httpx.AsyncClient(timeout=15.0) as client:
        check_response = await client.get(
            f"{homeserver}/_synapse/admin/v2/users/{user_id}",
            headers=headers,
        )
        if check_response.status_code == 404:
            create_response = await client.put(
                f"{homeserver}/_synapse/admin/v2/users/{user_id}",
                headers=headers,
                json={
                    "password": password,
                    "displayname": current_user.full_name,
                    "admin": False,
                    "deactivated": False,
                },
            )
            if create_response.status_code >= 400:
                # VERSHINA v200.16.4: Race condition — пользователь мог быть создан
                # между GET-проверкой и PUT-созданием. Обрабатываем M_USER_IN_USE.
                error_data = {}
                try:
                    error_data = create_response.json()
                except Exception:
                    pass
                errcode = error_data.get("errcode", "")
                if create_response.status_code == 400 and errcode == "M_USER_IN_USE":
                    logger.info(
                        f"Matrix user {user_id} already exists (race condition) — treating as success"
                    )
                    return {
                        "user_id": user_id,
                        "created": False,
                        "password_managed": True,
                    }
                raise HTTPException(
                    status_code=502,
                    detail=f"Matrix registration failed: {create_response.text}",
                )
            return {
                "user_id": user_id,
                "created": True,
                "password_managed": True,
            }

        if check_response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"Matrix health check failed: {check_response.text}",
            )

    return {
        "user_id": user_id,
        "created": False,
        "password_managed": True,
    }


def _miks_webrtc_payload() -> dict[str, Any]:
    return {
        "provider": "jssip",
        "wss_url": settings.ASTERISK_WS_URL,
        "sip_uri": settings.ASTERISK_SIP_WEBSOCKET_ENDPOINT,
        "realm": settings.ASTERISK_SIP_REALM,
        "ice_servers": [],
    }


@router.get("/bootstrap")
async def miks_bootstrap(current_user: User = Depends(get_current_user_from_cookie)):
    matrix_account = await _ensure_matrix_account(current_user)
    return {
        "status": "ok",
        "user": {
            "id": current_user.id,
            "full_name": current_user.full_name,
            "role": current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
            "park_name": current_user.park_name,
        },
        "matrix": {
            "homeserver_url": settings.MATRIX_HOMESERVER_URL,
            "server_name": settings.MATRIX_SERVER_NAME,
            "room_id": settings.MATRIX_MIKS_ROOM_ID,
            "ready": bool(settings.MATRIX_ACCESS_TOKEN and settings.MATRIX_MIKS_ROOM_ID),
            "user_id": matrix_account["user_id"],
            "created_now": matrix_account["created"],
        },
        "webrtc": _miks_webrtc_payload(),
        "features": {
            "matrix_chat": True,
            "webrtc_calling": True,
            "ai_tagging": True,
        },
    }


@router.post("/tag-message")
async def miks_tag_message(payload: dict[str, Any], current_user: User = Depends(get_current_user_from_cookie)):
    message = (payload.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    tags = await miks_ai_link.tag_message(message)
    return {
        "status": "ok",
        "tagging": tags,
        "tagged_by": current_user.full_name,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/matrix/health")
async def miks_matrix_health(current_user: User = Depends(get_current_user_from_cookie)):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{settings.MATRIX_HOMESERVER_URL.rstrip('/')}/_matrix/client/versions")
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Matrix unavailable: {exc}") from exc

    return {
        "status": "ok",
        "matrix": data,
        "checked_by": current_user.full_name,
    }


# ── Системный промпт для логиста ВкусВилл ──────────────────────────────────────
LOGIST_SYSTEM_PROMPT = """Ты — Mix, ИИ-советник S-GLOBAL DOMINION для логиста.
Твои задачи:
1. Помогать считать маржу рейсов ВкусВилл (тарифы: ДС 7622/7985₽, Магазин 6795₽, Шмель 4483₽, Жук 2434₽)
2. Следить за опозданиями водителей (Азат — Mercedes Atego, Группа Бнян — Шахзод/Зариф/Шавкат)
3. Рассчитывать выплаты: Азат 2000₽/точка, Бнян по тарифам (ДС 4900₽, М 4100₽, Ш 2570₽, Ж 1050₽)
4. Алгоритм 50/50: маржа делится поровну между ООО С-ГЛОБАЛ и ИП Мкртчян
Отвечай кратко, по делу, на русском языке."""

# ── URL локального Ollama ───────────────────────────────────────────────────────
OLLAMA_BASE_URL = "http://ollama:11434"  # Docker сервис dominion_ollama
# Модель по умолчанию — локальная, данные не уходят в облако
OLLAMA_DEFAULT_MODEL = "gpt-oss:20b"


@router.post("/ai-chat")
async def miks_ai_chat(
    payload: dict[str, Any],
    current_user: User = Depends(get_current_user_from_cookie),
):
    """
    AI-чат Mix — эндпоинт для чата с ИИ-помощником Mix.
    Приоритет 1: Gemini API (если GEMINI_API_KEY задан в .env)
    Приоритет 2: Локальный Ollama (http://172.27.192.1:11434)
    Приоритет 3: oracle_service (VseGPT/Ollama Bridge)
    Приоритет 4: Прямой запрос к VseGPT/Ollama через VSEGPT_BASE_URL
    """
    message = (payload.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    # Определяем системный промпт: для логиста — специализированный
    user_role = (current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)).lower()
    default_system_prompt = (
        LOGIST_SYSTEM_PROMPT
        if user_role == "logist" or (current_user.park_name or "").upper() == "EXPRESS"
        else (
            "Ты — Mix, эксперт-советник S-GLOBAL DOMINION. "
            "Помогай сотрудникам планировать рейсы, проверять штрафы и давать советы по логистике. "
            "Отвечай кратко, по делу, на русском языке. "
            "Тарифы ВкусВилл: ДС (7622/7985 ₽), Магазин (6795 ₽), Шмель (4483 ₽), Жук (2434 ₽)."
        )
    )
    system_prompt = payload.get("system_prompt") or default_system_prompt

    # ── Приоритет 1: Gemini API ─────────────────────────────────────────────────
    if settings.GEMINI_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"
                    f"?key={settings.GEMINI_API_KEY}",
                    json={
                        "contents": [
                            {
                                "parts": [
                                    {"text": f"{system_prompt}\n\nПользователь: {message}"}
                                ]
                            }
                        ],
                        "generationConfig": {
                            "temperature": 0.7,
                            "maxOutputTokens": 1024,
                        },
                    },
                )
                if resp.status_code == 200:
                    result = resp.json()
                    reply = result["candidates"][0]["content"]["parts"][0]["text"]
                    return {
                        "status": "ok",
                        "reply": reply,
                        "provider": "gemini",
                        "chat_id": payload.get("chat_id", "mix-ai"),
                        "timestamp": datetime.utcnow().isoformat(),
                        "answered_for": current_user.full_name,
                    }
                logger.warning(f"Gemini API returned {resp.status_code}: {resp.text[:200]}")
        except Exception as gemini_exc:
            logger.warning(f"Mix AI Gemini fallback: {gemini_exc}")

    # ── Приоритет 2: Локальный Ollama (172.27.192.1:11434) ─────────────────────
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": OLLAMA_DEFAULT_MODEL,
                    "prompt": f"{system_prompt}\n\nПользователь: {message}\nMix:",
                    "stream": False,
                    "options": {"temperature": 0.7, "num_predict": 512},
                },
            )
            if resp.status_code == 200:
                result = resp.json()
                reply = result.get("response", "").strip()
                if reply:
                    return {
                        "status": "ok",
                        "reply": reply,
                        "provider": "ollama",
                        "chat_id": payload.get("chat_id", "mix-ai"),
                        "timestamp": datetime.utcnow().isoformat(),
                        "answered_for": current_user.full_name,
                    }
            logger.warning(f"Ollama returned {resp.status_code}: {resp.text[:200]}")
    except Exception as ollama_exc:
        logger.warning(f"Mix AI Ollama fallback: {ollama_exc}")

    # ── Приоритет 3: oracle_service (VseGPT/Ollama Bridge) ─────────────────────
    try:
        from app.services.oracle_service import oracle_service

        result = await oracle_service.send_message(
            message=message,
            group="ОБЩАЯ",
            context={"system_override": system_prompt},
        )
        reply = result.get("message") or "Mix AI не смог сформировать ответ."
        return {
            "status": "ok",
            "reply": reply,
            "provider": "oracle",
            "chat_id": payload.get("chat_id", "mix-ai"),
            "timestamp": datetime.utcnow().isoformat(),
            "answered_for": current_user.full_name,
        }
    except Exception as exc:
        logger.warning(f"Mix AI oracle fallback: {exc}")

    # ── Приоритет 4: Прямой запрос к VseGPT/Ollama через VSEGPT_BASE_URL ───────
    try:
        vsegpt_url = getattr(settings, "VSEGPT_BASE_URL", None) or settings.OLLAMA_BASE_URL
        vsegpt_key = getattr(settings, "VSEGPT_API_KEY", None) or ""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{vsegpt_url.rstrip('/')}/api/chat",
                headers={"Authorization": f"Bearer {vsegpt_key}"} if vsegpt_key else {},
                json={
                    "model": settings.GEMINI_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message},
                    ],
                    "stream": False,
                },
            )
            resp_data = resp.json()
            reply = (
                resp_data.get("message", {}).get("content")
                or resp_data.get("choices", [{}])[0].get("message", {}).get("content")
                or "Mix AI временно недоступен."
            )
    except Exception as fallback_exc:
        logger.error(f"Mix AI fallback failed: {fallback_exc}")
        reply = "⚠️ Mix AI временно недоступен. Попробуйте позже."

    return {
        "status": "ok",
        "reply": reply,
        "provider": "fallback",
        "chat_id": payload.get("chat_id", "mix-ai"),
        "timestamp": datetime.utcnow().isoformat(),
        "answered_for": current_user.full_name,
    }
