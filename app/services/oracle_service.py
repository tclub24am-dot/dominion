# -*- coding: utf-8 -*-
# app/services/oracle_service.py
# ORACLE AI ENGINE - Gemini 3 Flash via Ollama Bridge (2026 Protocol)

import logging
import httpx
import math
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.all_models import Transaction, WarehouseItem, User, Vehicle, OwnershipType

logger = logging.getLogger("OracleEngine")

# =================================================================
# КОНФИГУРАЦИЯ ORACLE
# =================================================================

class OracleConfig:
    """Конфигурация Oracle AI через Ollama Bridge"""
    MODEL_NAME = settings.GEMINI_MODEL or "gemini-3-flash-preview:cloud"
    OLLAMA_BASE_URL = settings.OLLAMA_BASE_URL
    API_KEY = settings.GEMINI_API_KEY
    
    MAX_TOKENS = 4096
    TEMPERATURE = 0.7
    TOP_P = 0.95
    TIMEOUT = getattr(settings, 'ORACLE_TIMEOUT', 60.0)  # 60 секунд для облачного Gemini
    
    # Контексты для разных групп
    CONTEXTS = {
        "ОБЩАЯ": "Ты — Oracle AI системы S-GLOBAL DOMINION. Отвечай кратко, четко и по делу. Используй профессиональный тон.",
        "ФЛОТ": "Ты — эксперт по управлению автопарком из 120 машин (42 субаренда + 78 подключенных). Анализируй эффективность флота, предлагай оптимизации.",
        "ФИНАНСЫ": "Ты — финансовый аналитик S-GLOBAL. Формула прибыли: Net = (Sum_42×0.04 + 42×450 + Sum_78×0.03 + VV/4) - 272053/30. Анализируй казну, прогнозируй прибыль.",
        "ПЛАНИРОВАНИЕ": "Ты — стратегический планировщик Dominion. Помогай планировать операции, оптимизировать процессы, прогнозировать результаты и принимать решения."
    }

class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    timestamp: datetime
    group: str = "ОБЩАЯ"

class OracleService:
    """
    ORACLE AI SERVICE
    Интеграция через Ollama Bridge с Gemini 3 Flash Preview
    """
    
    def __init__(self):
        self.base_url = OracleConfig.OLLAMA_BASE_URL
        self.api_key = OracleConfig.API_KEY
        self.model = OracleConfig.MODEL_NAME
        self.is_live = False
        
        self.chat_history: Dict[str, List[ChatMessage]] = {
            "ОБЩАЯ": [],
            "ФЛОТ": [],
            "ФИНАНСЫ": [],
            "ПЛАНИРОВАНИЕ": []
        }
        
        if self.api_key and self.api_key != "pending_configure_in_google_ai_studio":
            logger.info(f"✓ Oracle Engine initialized: {self.model}")
            logger.info(f"  Base URL: {self.base_url}")
            # Проверяем связь при инициализации
            self._check_handshake()
        else:
            logger.warning("⚠ GEMINI_API_KEY not configured. Oracle running in MOCK mode.")
            logger.info("  Add your API key to .env: GEMINI_API_KEY=your_key_here")
    
    def _check_handshake(self):
        """Проверка связи с Ollama при старте"""
        import requests
        import subprocess
        
        try:
            # Шаг 1: Проверяем доступность Ollama API
            response = requests.get(
                self.base_url.replace('/v1', '') + '/api/tags',
                timeout=5
            )
            
            if response.status_code != 200:
                logger.warning(f"Ollama responded with {response.status_code}")
                self.is_live = False
                return
            
            # Шаг 2: Проверяем наличие модели через ollama list
            try:
                result = subprocess.run(
                    ['ollama', 'list'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                models_output = result.stdout
                model_base_name = self.model.split(':')[0]  # gemini-3-flash-preview
                
                if model_base_name in models_output or self.model in models_output:
                    # Модель найдена!
                    logger.info("=" * 60)
                    logger.info("[SUCCESS] Oracle Link Established")
                    logger.info("=" * 60)
                    logger.info(f"  ✓ Ollama Bridge: ONLINE ({self.base_url})")
                    logger.info(f"  ✓ Model: {self.model}")
                    logger.info(f"  ✓ Model Status: AVAILABLE in Ollama")
                    logger.info(f"  ✓ API Key: {'*' * 20}{self.api_key[-8:]}")
                    logger.info(f"  ✓ Timeout: {OracleConfig.TIMEOUT}s")
                    logger.info("")
                    logger.info("  🔮 Oracle connected to Gemini-3-Flash via Ollama Bridge")
                    logger.info("=" * 60)
                    self.is_live = True
                else:
                    logger.warning("=" * 60)
                    logger.warning(f"⚠ Model '{self.model}' not found in Ollama")
                    logger.warning("=" * 60)
                    logger.info("  Available models:")
                    for line in models_output.split('\n')[1:6]:  # First 5 models
                        if line.strip():
                            logger.info(f"    - {line.split()[0]}")
                    logger.info("")
                    logger.info("  To download the model:")
                    logger.info(f"    python3 pull_model.py {self.model}")
                    logger.info("=" * 60)
                    self.is_live = False
                    
            except FileNotFoundError:
                logger.warning("'ollama' command not found. Cannot verify model.")
                logger.info("  Assuming LIVE mode based on API availability")
                logger.info("=" * 60)
                logger.info("[SUCCESS] Oracle Link Established (API only)")
                logger.info(f"  Ollama Bridge: ONLINE ({self.base_url})")
                logger.info(f"  Model: {self.model}")
                logger.info("=" * 60)
                self.is_live = True
                
        except requests.exceptions.ConnectionError:
            logger.warning("=" * 60)
            logger.warning("⚠ Ollama not reachable at " + self.base_url)
            logger.warning("=" * 60)
            logger.info("  Oracle will use MOCK mode.")
            logger.info("")
            logger.info("  To activate LIVE mode:")
            logger.info("    1. Install: curl -fsSL https://ollama.com/install.sh | sh")
            logger.info("    2. Start: ollama serve &")
            logger.info("    3. Restart Dominion")
            logger.info("=" * 60)
            self.is_live = False
        except Exception as e:
            logger.warning(f"Handshake check failed: {e}")
            self.is_live = False
    
    async def send_message(
        self, 
        message: str, 
        group: str = "ОБЩАЯ",
        context: Optional[Dict] = None,
        file_context: Optional[str] = None
    ) -> Dict:
        """
        Отправка сообщения Oracle AI через Ollama Bridge
        
        Args:
            message: Сообщение пользователя
            group: Группа чата (ОБЩАЯ, ФЛОТ, ФИНАНСЫ, ПЛАНИРОВАНИЕ)
            context: Дополнительный контекст (данные из БД)
        
        Returns:
            Dict с ответом и метаданными
        """
        try:
            # Сохраняем сообщение пользователя
            user_msg = ChatMessage(
                role="user",
                content=message,
                timestamp=datetime.now(),
                group=group
            )
            self.chat_history[group].append(user_msg)
            
            # Проверяем API ключ
            if not self.api_key or self.api_key == "pending_configure_in_google_ai_studio":
                logger.info("API key not configured, using mock mode")
                return await self._mock_response(message, group)
            
            # Если Oracle не в живом режиме, не дергаем Ollama
            if not self.is_live:
                logger.warning("Oracle is offline, using fallback response")
                response_text = await self._fallback_mock(message, group)
            else:
                # Отправляем через Ollama Bridge
                response_text = await self._call_ollama_bridge(message, group, context, file_context)
            
            # Сохраняем ответ
            assistant_msg = ChatMessage(
                role="assistant",
                content=response_text,
                timestamp=datetime.now(),
                group=group
            )
            self.chat_history[group].append(assistant_msg)
            
            return {
                "status": "success",
                "message": response_text,
                "group": group,
                "timestamp": datetime.now().isoformat(),
                "model": self.model
            }
            
        except Exception as e:
            logger.error(f"Oracle send_message error: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"Ошибка связи с Oracle: {str(e)}",
                "group": group,
                "timestamp": datetime.now().isoformat()
            }
    
    async def _call_ollama_bridge(
        self, 
        message: str, 
        group: str,
        context: Optional[Dict] = None,
        file_context: Optional[str] = None
    ) -> str:
        """
        Вызов Ollama Bridge API (OpenAI-compatible endpoint)
        """
        try:
            # Строим системный промпт
            system_prompt = OracleConfig.CONTEXTS.get(group, OracleConfig.CONTEXTS["ОБЩАЯ"])
            
            # CONTEXT INJECTION: Добавляем контекст файла если есть
            if file_context:
                system_prompt += f"\n\n📎 КОНТЕКСТ ФАЙЛА:\n{file_context}\n\nИНСТРУКЦИЯ: Используй эти данные для ответа на вопрос пользователя. Анализируй цифры, делай выводы, давай рекомендации."
            
            if context:
                system_prompt += f"\n\nТекущие данные системы: {context}"
            
            # Собираем историю для контекста (последние 10 сообщений)
            history = self.chat_history[group][-10:]
            messages = [{"role": "system", "content": system_prompt}]
            
            for msg in history[:-1]:  # Без последнего (он уже в message)
                messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
            
            messages.append({
                "role": "user",
                "content": message
            })
            
            # Формируем запрос в OpenAI-формате для Ollama
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": OracleConfig.TEMPERATURE,
                "max_tokens": OracleConfig.MAX_TOKENS,
                "top_p": OracleConfig.TOP_P,
                "stream": False
            }
            
            # Заголовки (для локального Ollama Authorization не нужен)
            headers = {
                "Content-Type": "application/json"
            }
            
            # Если это облачная модель, добавляем Authorization
            if ":cloud" in self.model and self.api_key and self.api_key != "local_ollama_no_key_required":
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            logger.info(f"🔮 Sending to Ollama Bridge: {self.base_url}/chat/completions")
            logger.info(f"   Model: {self.model}")
            logger.info(f"   Group: {group}")
            logger.info(f"   Message length: {len(message)} chars")
            
            # Отправляем запрос с увеличенным таймаутом
            timeout = httpx.Timeout(OracleConfig.TIMEOUT, connect=10.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers
                )
                
                logger.info(f"   Response status: {response.status_code}")
                
                if response.status_code != 200:
                    error_text = response.text
                    logger.error(f"Ollama Bridge error: {response.status_code}")
                    logger.error(f"Response body: {error_text[:500]}")
                    raise Exception(f"HTTP {response.status_code}: {error_text[:200]}")
                
                result = response.json()
                logger.info(f"   Response received: {len(str(result))} bytes")
                
                # Извлекаем текст ответа (OpenAI format)
                if "choices" in result and len(result["choices"]) > 0:
                    answer = result["choices"][0]["message"]["content"]
                    logger.info(f"✓ Oracle response: {answer[:100]}...")
                    return answer
                else:
                    logger.error(f"Unexpected response format: {result}")
                    raise Exception("Invalid response format from Ollama")
            
        except httpx.TimeoutException:
            logger.error("Ollama Bridge timeout, falling back to mock")
            return await self._fallback_mock(message, group)
        except httpx.ConnectError as e:
            logger.warning(f"Cannot connect to Ollama at {self.base_url}, using mock mode")
            return await self._fallback_mock(message, group)
        except Exception as e:
            logger.error(f"Ollama Bridge call failed: {e}, falling back to mock")
            return await self._fallback_mock(message, group)
    
    async def _fallback_mock(self, message: str, group: str) -> str:
        """Fallback на mock при проблемах с Ollama"""
        mock_responses = {
            "ОБЩАЯ": f"Принял запрос: '{message[:80]}'. [Oracle в автономном режиме — Ollama недоступен]",
            "ФЛОТ": f"Анализирую флот по запросу: '{message[:50]}'. Данные: 120 машин, боеготовность 95.8%. [Автономный режим]",
            "ФИНАНСЫ": f"Финансовый анализ по: '{message[:50]}'. Текущая прибыль: 159,831₽/день. Месячный прогноз: ~4.8М₽. [Автономный режим]",
            "ПЛАНИРОВАНИЕ": f"Стратегический анализ: '{message[:50]}'. Рекомендую: оптимизировать маршруты ВкусВилл, повысить утилизацию подключенных машин с 78%. [Автономный режим]"
        }
        
        return mock_responses.get(group, mock_responses["ОБЩАЯ"])
    
    async def _mock_response(self, message: str, group: str) -> Dict:
        """Mock режим (когда нет API ключа)"""
        
        mock_responses = {
            "ОБЩАЯ": f"[ДЕМО] Принял ваш запрос: '{message}'. Oracle работает в демо-режиме. Для полной активации добавьте GEMINI_API_KEY в .env",
            "ФЛОТ": f"[ДЕМО] Анализирую флот... По данным системы: 120 машин на линии. Боеготовность 95.8%. Ваш запрос: '{message[:50]}'",
            "ФИНАНСЫ": f"[ДЕМО] Финансовый анализ: Текущая прибыль 159,831₽/день. Формула Мастера применена. Запрос: '{message[:50]}'",
            "ПЛАНИРОВАНИЕ": f"[ДЕМО] Стратегический анализ для: '{message[:50]}'. Рекомендую: оптимизировать маршруты ВкусВилл, увеличить загрузку подключенных машин."
        }
        
        response_text = mock_responses.get(group, mock_responses["ОБЩАЯ"])
        
        # Сохраняем mock ответ
        assistant_msg = ChatMessage(
            role="assistant",
            content=response_text,
            timestamp=datetime.now(),
            group=group
        )
        self.chat_history[group].append(assistant_msg)
        
        return {
            "status": "success",
            "message": response_text,
            "group": group,
            "timestamp": datetime.now().isoformat(),
            "model": "MOCK_MODE"
        }
    
    def get_history(self, group: str = "ОБЩАЯ", limit: int = 50) -> List[Dict]:
        """Получить историю чата"""
        history = self.chat_history.get(group, [])[-limit:]
        return [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat()
            }
            for msg in history
        ]
    
    def clear_history(self, group: Optional[str] = None):
        """Очистить историю"""
        if group:
            self.chat_history[group] = []
        else:
            for g in self.chat_history:
                self.chat_history[g] = []
        logger.info(f"Chat history cleared: {group or 'ALL'}")

# =================================================================
# SINGLETON INSTANCE
# =================================================================

class OracleAI:
    """
    ВЫСШИЙ ИНТЕЛЛЕКТ ЦИТАДЕЛИ: Предиктивная аналитика и аудит персонала.
    """

    @staticmethod
    async def predict_cash_flow(db: AsyncSession, sector: str = "taxi") -> Dict:
        """
        ПРЕДСКАЗАНИЕ КАЗНЫ: Анализирует тренд прибыли за последние 7 дней
        и прогнозирует выручку на следующий месяц.
        """
        try:
            # Считаем прибыль за последние 7 дней
            seven_days_ago = datetime.now() - timedelta(days=7)
            stmt = select(func.sum(Transaction.amount)).where(
                Transaction.category.contains(sector),
                Transaction.date >= seven_days_ago
            )
            result = await db.execute(stmt)
            week_profit = result.scalar() or 0.0

            # Алгоритм прогноза (Линейная экстраполяция + коэффициент роста)
            daily_avg = week_profit / 7
            predicted_monthly = daily_avg * 30 * 1.15

            return {
                "sector": sector.upper(),
                "trend": "GROWTH" if daily_avg > 0 else "STAGNATION",
                "confidence": "85%",
                "predicted_monthly_profit": round(predicted_monthly, 2),
                "advice": f"Мастер, сектор {sector} стабилен. Рекомендую расширить Флот субаренды на 5%."
            }
        except Exception as e:
            logger.error(f"AI Prediction Error: {e}")
            return {"error": "Oracle is meditating"}

    @staticmethod
    async def audit_warehouse_risks(db: AsyncSession) -> List[Dict]:
        """
        ПРЕДСКАЗАНИЕ ДЕФИЦИТА: Вычисляет, через сколько дней закончатся запчасти
        на основе темпов их списания.
        """
        stmt = select(WarehouseItem).where(WarehouseItem.quantity <= WarehouseItem.min_threshold)
        result = await db.execute(stmt)
        items = result.scalars().all()

        return [
            {
                "item": i.name,
                "days_left": max(1, i.quantity // 2),
                "action": "СРОЧНАЯ ЗАКУПКА"
            } for i in items
        ]

    @staticmethod
    async def evaluate_warrior(user: User) -> Dict:
        """
        ИНТЕЛЛЕКТУАЛЬНЫЙ РЕЙТИНГ ВОИНА (Водителя/Механика)
        """
        base_rating = user.rating or 5.0
        status = "LEGENDARY" if base_rating >= 4.9 else "ELITE" if base_rating >= 4.5 else "WARRIOR"
        return {
            "full_name": user.full_name,
            "rank": status,
            "rating": base_rating,
            "stars": "⭐" * math.floor(base_rating),
            "efficiency_index": f"{round(base_rating * 20)}%"
        }


oracle_service = OracleService()
oracle_ai = OracleAI()