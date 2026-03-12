# -*- coding: utf-8 -*-

import json
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("MIKSAILink")


class MatrixOllamaTagger:
    async def tag_message(self, message: str) -> dict[str, Any]:
        content = (message or "").strip()
        if not content:
            return {"tags": [], "summary": ""}

        prompt = (
            "Верни JSON с ключами tags и summary. "
            "tags — массив из 1-5 коротких русских тегов для сообщения операционного мессенджера. "
            "summary — краткая строка до 120 символов. "
            f"Сообщение: {content}"
        )

        payload = {
            "model": settings.MATRIX_OLLAMA_TAG_MODEL,
            "prompt": prompt,
            "stream": False,
        }

        ollama_url = settings.OLLAMA_BASE_URL.rstrip("/")
        if ollama_url.endswith("/v1"):
            ollama_url = ollama_url[:-3]

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(f"{ollama_url}/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()
                raw_text = (data.get("response") or "").strip()
                parsed = json.loads(raw_text)
                return {
                    "tags": parsed.get("tags", []),
                    "summary": parsed.get("summary", ""),
                    "model": settings.MATRIX_OLLAMA_TAG_MODEL,
                }
        except Exception as exc:
            logger.warning("MIKS AI tagging failed: %s", exc)
            return {
                "tags": ["miks", "unclassified"],
                "summary": content[:120],
                "model": settings.MATRIX_OLLAMA_TAG_MODEL,
                "fallback": True,
            }


miks_ai_link = MatrixOllamaTagger()
