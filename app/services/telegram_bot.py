# -*- coding: utf-8 -*-
# app/services/telegram_bot.py
# DOMINION BRIDGE - Telegram Integration

import logging
import os
import asyncio
from typing import Optional
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, Voice, Document, FSInputFile
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from app.core.config import settings
from app.services.oracle_service import oracle_service
try:
    from app.services.file_analyzer import file_analyzer
except Exception:
    class _FileAnalyzerStub:
        async def analyze_file(self, *args, **kwargs):
            return "Analyzer disabled"
    file_analyzer = _FileAnalyzerStub()
from app.models.all_models import ChatMessage
from app.database import AsyncSessionLocal
from datetime import datetime

logger = logging.getLogger("TelegramBridge")

# =================================================================
# КОНФИГУРАЦИЯ
# =================================================================

class TelegramConfig:
    BOT_TOKEN = settings.SGLOBAL_BOT_TOKEN
    ADMIN_ID = settings.ADMIN_ID  # ID Мастера из .env
    
    COMMANDS = {
        "start": "Запуск Dominion Bridge",
        "status": "Статус системы",
        "kazna": "Финансы (Формула Мастера)",
        "fleet": "Статус флота (Tension Index)",
        "audit": "Последний аудит",
        "help": "Помощь"
    }

# =================================================================
# BOT INITIALIZATION
# =================================================================

class DominionTelegramBot:
    """
    DOMINION BRIDGE для Telegram
    """
    
    def __init__(self):
        if not TelegramConfig.BOT_TOKEN:
            logger.warning("SGLOBAL_BOT_TOKEN not configured")
            self.bot = None
            self.dp = None
            return
        
        self.bot = Bot(
            token=TelegramConfig.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        self.dp = Dispatcher()
        
        # Регистрируем обработчики
        self._register_handlers()
        
        logger.info("✓ Dominion Telegram Bridge initialized")
    
    def _register_handlers(self):
        """Регистрация обработчиков команд и сообщений"""
        
        @self.dp.message(Command("start"))
        async def cmd_start(message: Message):
            await self._handle_start(message)
        
        @self.dp.message(Command("status"))
        async def cmd_status(message: Message):
            await self._handle_status(message)
        
        @self.dp.message(Command("kazna"))
        async def cmd_kazna(message: Message):
            await self._handle_kazna(message)
        
        @self.dp.message(Command("fleet"))
        async def cmd_fleet(message: Message):
            await self._handle_fleet(message)
        
        @self.dp.message(Command("audit"))
        async def cmd_audit(message: Message):
            await self._handle_audit(message)
        
        @self.dp.message(Command("help"))
        async def cmd_help(message: Message):
            await self._handle_help(message)
        
        # Обработчик текстовых сообщений
        @self.dp.message(lambda m: m.text and not m.text.startswith('/'))
        async def handle_text(message: Message):
            await self._handle_text_message(message)
        
        # Обработчик голосовых сообщений
        @self.dp.message(lambda m: m.voice is not None)
        async def handle_voice(message: Message):
            await self._handle_voice_message(message)
        
        # Обработчик файлов (документов)
        @self.dp.message(lambda m: m.document is not None)
        async def handle_document(message: Message):
            await self._handle_document(message)
        
        # Обработчик фото
        @self.dp.message(lambda m: m.photo is not None)
        async def handle_photo(message: Message):
            await self._handle_photo(message)
        
        # Команда /alerts
        @self.dp.message(Command("alerts"))
        async def cmd_alerts(message: Message):
            await self._handle_alerts(message)
    
    def _check_admin(self, user_id: int) -> bool:
        """Проверка доступа (только Мастер)"""
        return user_id == TelegramConfig.ADMIN_ID
    
    async def _handle_start(self, message: Message):
        """Команда /start"""
        if not self._check_admin(message.from_user.id):
            await message.answer("⚠️ Доступ запрещён. Только для Мастера Dominion.")
            return
        
        welcome_text = """
🏛️ <b>DOMINION BRIDGE</b> активирован

Вы подключены к S-GLOBAL Dominion v18.5

<b>Возможности:</b>
• Текстовые сообщения → Oracle AI
• Голосовые сообщения → транскрипция + анализ
• Файлы (Excel, PDF, Word) → интеллект-анализ
• Команды управления системой

<b>Команды:</b>
/status — Статус Dominion
/kazna — Финансы (Формула Мастера)
/fleet — Флот (Tension Index)
/audit — Последний аудит
/help — Помощь

Просто напишите сообщение — Oracle ответит.
"""
        await message.answer(welcome_text)
        logger.info(f"✓ /start from {message.from_user.username} (ID: {message.from_user.id})")
    
    async def _handle_status(self, message: Message):
        """Статус системы"""
        if not self._check_admin(message.from_user.id):
            return
        
        status_text = f"""
📊 <b>DOMINION STATUS</b>

🤖 Oracle AI: {"LIVE" if oracle_service.is_live else "MOCK"}
🔮 Model: {oracle_service.model}
⏰ Время: {datetime.now().strftime('%H:%M:%S')}

Система работает в штатном режиме.
"""
        await message.answer(status_text)
    
    async def _handle_kazna(self, message: Message):
        """Финансы"""
        if not self._check_admin(message.from_user.id):
            return
        
        from app.services.finance_engine import finance_engine
        data = finance_engine.generate_demo_data()
        
        kazna_text = f"""
💰 <b>КАЗНА ИМПЕРИИ</b>

<b>Формула Мастера:</b>
Чистая прибыль: <b>{data['net_profit']:,.0f}₽/день</b>

<b>Источники:</b>
• Субаренда (42): {data['sublease_income']:,.0f}₽
• Подключенные (78): {data['connected_income']:,.0f}₽
• ВкусВилл (1/4): {data['vv_share']:,.0f}₽

<b>Расходы:</b>
• День: -{data['daily_expenses']:,.0f}₽

<b>Месячная проекция:</b> ~{data['net_profit'] * 30:,.0f}₽
"""
        await message.answer(kazna_text)
    
    async def _handle_fleet(self, message: Message):
        """Статус флота"""
        if not self._check_admin(message.from_user.id):
            return
        
        from app.services.fleet_engine import fleet_engine
        data = fleet_engine.generate_demo_fleet()
        
        fleet_text = f"""
🚗 <b>ИМПЕРИЯ КОЛЁС</b>

<b>Автопарк:</b> {data['total']} машин
• Субаренда: {data['sublease']}
• Подключенные: {data['connected']}

<b>Статус:</b>
• На линии: {data['working']} 🟢
• Сервис: {data['service']} 🟡
• Долги: {data['debt']} 🔴
• Критических: {data['critical']} ⚠️

<b>Боеготовность:</b> {data['readiness']}%

{"⚠️ <b>TENSION ALERT!</b> Критические задолженности." if data['tension_alert'] else ""}
"""
        await message.answer(fleet_text)
    
    async def _handle_audit(self, message: Message):
        """Последний аудит"""
        if not self._check_admin(message.from_user.id):
            return
        
        # Получаем последний аудит из БД
        try:
            async with AsyncSessionLocal() as session:
                from sqlalchemy import select
                stmt = select(ChatMessage).where(
                    ChatMessage.role == "system",
                    ChatMessage.group_name == "ПЛАНИРОВАНИЕ"
                ).order_by(ChatMessage.created_at.desc()).limit(1)
                
                result = await session.execute(stmt)
                audit = result.scalar_one_or_none()
                
                if audit:
                    await message.answer(f"🕘 <b>ПОСЛЕДНИЙ АУДИТ</b>\n\n{audit.content}")
                else:
                    await message.answer("Аудиты пока не проводились.\n\nЗапустите: <code>python3 app/tasks/evening_audit.py</code>")
        except Exception as e:
            await message.answer(f"⚠️ Ошибка получения аудита: {str(e)}")
    
    async def _handle_help(self, message: Message):
        """Помощь"""
        help_text = """
📖 <b>DOMINION BRIDGE — Помощь</b>

<b>Команды:</b>
/status — Статус системы
/kazna — Финансовая сводка
/fleet — Статус автопарка
/audit — Последний вечерний аудит
/help — Это сообщение

<b>Возможности:</b>
• Отправьте текст — Oracle ответит
• Отправьте голосовое — транскрипция + анализ
• Отправьте файл — интеллект-анализ

<b>Доступ:</b> Только для Мастера (ID: {TelegramConfig.ADMIN_ID})
"""
        await message.answer(help_text)
    
    async def _handle_text_message(self, message: Message):
        """Обработка текстовых сообщений"""
        if not self._check_admin(message.from_user.id):
            await message.answer("⚠️ Доступ запрещён")
            return
        
        user_text = message.text
        logger.info(f"📨 Text from TG: {user_text[:50]}...")
        
        # Сохраняем в историю
        await self._save_to_history(
            role="user",
            content=user_text,
            source="telegram",
            group="ОБЩАЯ",
            user_id=message.from_user.id
        )
        
        # Отправляем Oracle
        thinking = await message.answer("🔮 Oracle думает...")
        
        try:
            response = await oracle_service.send_message(
                message=user_text,
                group="ОБЩАЯ"
            )
            
            if response["status"] == "success":
                await thinking.edit_text(f"🤖 <b>Oracle:</b>\n\n{response['message']}")
                
                # Сохраняем ответ в историю
                await self._save_to_history(
                    role="assistant",
                    content=response['message'],
                    source="telegram",
                    group="ОБЩАЯ"
                )
            else:
                await thinking.edit_text("⚠️ Oracle временно недоступен")
                
        except Exception as e:
            await thinking.edit_text(f"⚠️ Ошибка: {str(e)}")
            logger.error(f"Oracle error: {e}")
    
    async def _handle_voice_message(self, message: Message):
        """Обработка голосовых сообщений"""
        if not self._check_admin(message.from_user.id):
            return
        
        logger.info(f"🎤 Voice message from TG")
        
        status_msg = await message.answer("🎤 Транскрибирую голос...")
        
        try:
            # Скачиваем голосовое
            voice: Voice = message.voice
            file = await self.bot.get_file(voice.file_id)
            file_path = f"/tmp/voice_{message.message_id}.ogg"
            await self.bot.download_file(file.file_path, file_path)
            
            # TODO: Транскрипция через Whisper API или Google Speech
            transcription = "[Транскрипция требует Whisper API - pending]"
            
            await status_msg.edit_text(f"📝 Распознано:\n{transcription}\n\n🔮 Oracle анализирует...")
            
            # Отправляем Oracle
            response = await oracle_service.send_message(
                message=transcription,
                group="ОБЩАЯ"
            )
            
            if response["status"] == "success":
                await message.answer(f"🤖 <b>Oracle:</b>\n\n{response['message']}")
            
            # Сохраняем в историю
            await self._save_to_history(
                role="user",
                content=f"[Голосовое] {transcription}",
                source="telegram"
            )
            
        except Exception as e:
            await status_msg.edit_text(f"⚠️ Ошибка обработки голоса: {str(e)}")
            logger.error(f"Voice error: {e}")
    
    async def _handle_document(self, message: Message):
        """Обработка файлов"""
        if not self._check_admin(message.from_user.id):
            return
        
        logger.info(f"📎 Document from TG: {message.document.file_name}")
        
        status_msg = await message.answer("📎 Анализирую файл...")
        
        try:
            # Скачиваем файл
            doc: Document = message.document
            file = await self.bot.get_file(doc.file_id)
            
            # Сохраняем в storage
            from pathlib import Path
            upload_dir = Path("/root/dominion/storage/uploads")
            upload_dir.mkdir(parents=True, exist_ok=True)
            
            file_path = upload_dir / doc.file_name
            await self.bot.download_file(file.file_path, file_path)
            
            # Анализируем через File Analyzer
            analysis = await file_analyzer.analyze_file(file_path, doc.file_name)
            
            if analysis["status"] == "success":
                await status_msg.edit_text(
                    f"📊 <b>Анализ завершён</b>\n\n{analysis['summary']}"
                )
            else:
                await status_msg.edit_text(
                    f"📎 Файл загружен: {doc.file_name}\n\n⚠️ Частичный анализ"
                )
            
            # Сохраняем в историю
            await self._save_to_history(
                role="user",
                content=f"[Файл] {doc.file_name}",
                source="telegram",
                file_path=str(file_path)
            )
            
        except Exception as e:
            await status_msg.edit_text(f"⚠️ Ошибка обработки файла: {str(e)}")
            logger.error(f"Document error: {e}")
    
    async def _handle_photo(self, message: Message):
        """Обработка фото (Gemini Vision)"""
        if not self._check_admin(message.from_user.id):
            return
        
        logger.info(f"📷 Photo from TG")
        
        status_msg = await message.answer("📷 Анализирую изображение...")
        
        try:
            # Получаем фото максимального качества
            photo = message.photo[-1]
            file = await self.bot.get_file(photo.file_id)
            
            # Скачиваем
            from pathlib import Path
            upload_dir = Path("/root/dominion/storage/uploads")
            upload_dir.mkdir(parents=True, exist_ok=True)
            
            file_path = upload_dir / f"photo_{message.message_id}.jpg"
            await self.bot.download_file(file.file_path, file_path)
            
            # Базовый анализ через Pillow
            analysis = await file_analyzer.analyze_file(file_path, file_path.name)
            
            # TODO: Gemini Vision API для описания содержимого
            # Требует отдельный endpoint с vision capabilities
            
            caption = message.caption or "Без подписи"
            
            vision_text = f"""
📷 <b>Фото получено</b>

{analysis.get('summary', '')}

💡 <b>Gemini Vision анализ:</b>
[Vision API в разработке - требует gemini-pro-vision]

Подпись: {caption}

Для полного анализа чеков/документов на фото требуется:
1. Модель gemini-pro-vision в Ollama
2. Интеграция с Vision API
"""
            
            await status_msg.edit_text(vision_text)
            
            # Сохраняем в историю
            await self._save_to_history(
                role="user",
                content=f"[Фото] {caption}",
                source="telegram",
                file_path=str(file_path)
            )
            
        except Exception as e:
            await status_msg.edit_text(f"⚠️ Ошибка обработки фото: {str(e)}")
            logger.error(f"Photo error: {e}")
    
    async def _handle_alerts(self, message: Message):
        """Команда /alerts - Критические уведомления (Tension Index)"""
        if not self._check_admin(message.from_user.id):
            return
        
        logger.info("/alerts command from TG")
        
        try:
            from app.services.fleet_engine import fleet_engine
            from app.database import AsyncSessionLocal
            from sqlalchemy import select
            from app.models.all_models import FineInstallment, User
            
            async with AsyncSessionLocal() as session:
                # Получаем критические задолженности
                stmt = select(FineInstallment, User).join(
                    User, User.id == FineInstallment.driver_id
                ).where(FineInstallment.remaining_debt > 3000)
                
                result = await session.execute(stmt)
                critical = result.all()
                
                if len(critical) == 0:
                    await message.answer("✅ Критических задолженностей нет.\n\nTension Index в норме.")
                    return
                
                alerts_text = f"⚠️ <b>TENSION INDEX ALERTS</b>\n\n<b>Критических задолженностей: {len(critical)}</b>\n\n"
                
                for installment, user in critical[:10]:  # Первые 10
                    alerts_text += f"• {user.full_name}\n"
                    alerts_text += f"  Долг: <b>{installment.remaining_debt:,.0f}₽</b>\n"
                    alerts_text += f"  Статус: {installment.status}\n\n"
                
                if len(critical) > 10:
                    alerts_text += f"\n...и ещё {len(critical) - 10} водителей"
                
                await message.answer(alerts_text)
                
        except Exception as e:
            await message.answer(f"⚠️ Ошибка получения alerts: {str(e)}")
            logger.error(f"Alerts error: {e}")
    
    async def _save_to_history(
        self, 
        role: str, 
        content: str, 
        source: str,
        group: str = "ОБЩАЯ",
        user_id: Optional[int] = None,
        file_path: Optional[str] = None
    ):
        """Сохранение сообщения в Библиотеку Историй с ФИЗИЧЕСКИМ commit"""
        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():  # Явная транзакция
                    msg = ChatMessage(
                        role=role,
                        content=f"[{source.upper()}] {content}",
                        group_name=group,
                        user_id=user_id,
                        file_path=file_path,
                        is_read=False,  # Новое сообщение извне — непрочитано
                        timestamp=datetime.now(),
                        created_at=datetime.now()
                    )
                    
                    session.add(msg)
                    # Commit происходит автоматически при выходе из begin()
                
                logger.info(f"✓ Message COMMITTED to DB: {role} from {source} → {group} (unread)")
                logger.info(f"  Content: {content[:50]}...")
                
        except Exception as e:
            logger.error(f"History save CRITICAL error: {e}", exc_info=True)
    
    async def start_polling(self):
        """Запуск бота в режиме polling"""
        if not self.bot:
            logger.warning("Bot not initialized (no token)")
            return
        
        logger.info("=" * 60)
        logger.info("DOMINION TELEGRAM BRIDGE — Starting...")
        logger.info(f"Admin ID: {TelegramConfig.ADMIN_ID}")
        logger.info("=" * 60)
        
        await self.dp.start_polling(self.bot)
    
    async def process_webhook(self, update_data: dict):
        """Обработка webhook от Telegram"""
        if not self.bot:
            raise Exception("Bot not initialized")
        
        update = types.Update(**update_data)
        await self.dp.feed_update(self.bot, update)

    async def send_to_user(self, telegram_id: Optional[str], text: str) -> bool:
        """Отправить сообщение пользователю по telegram_id"""
        if not self.bot or not telegram_id:
            return False
        try:
            await self.bot.send_message(chat_id=int(telegram_id), text=text)
            return True
        except Exception as e:
            logger.warning(f"Telegram send error: {e}")
            return False

# =================================================================
# SINGLETON INSTANCE
# =================================================================

telegram_bot = DominionTelegramBot()

async def send_master_msg(text: str) -> bool:
    """Унифицированная отправка сообщений Мастеру"""
    if not TelegramConfig.ADMIN_ID:
        return False
    return await telegram_bot.send_to_user(str(TelegramConfig.ADMIN_ID), text)


class BotManager:
    """
    UNIFIED BOT MANAGER
    """

    def __init__(self):
        self.master_bot = telegram_bot
        self.staff_bot = None
        self.driver_bot = None

        logger.info("=" * 60)
        logger.info("BOT MANAGER — Initialization")
        logger.info("=" * 60)
        logger.info(f"Master Bot: {'✓ Ready' if self.master_bot.bot else '✗ Not configured'}")
        logger.info("Staff Bot: ✗ Not configured")
        logger.info(f"Driver Bot: {'⏳ Pending' if not self.driver_bot else '✓ Ready'}")
        logger.info("=" * 60)

    async def start_all_bots(self):
        tasks = []
        if self.master_bot.bot:
            logger.info("🚀 Starting Master Bot...")
            tasks.append(asyncio.create_task(self.master_bot.start_polling()))
        if self.driver_bot:
            logger.info("🚀 Starting Driver Bot...")
        if not tasks:
            logger.warning("⚠️ No bots configured. Check tokens in .env")
            return
        await asyncio.gather(*tasks, return_exceptions=True)

    def get_bot_status(self) -> dict:
        return {
            "master": self.master_bot.bot is not None,
            "staff": False,
            "driver": self.driver_bot is not None
        }


bot_manager = BotManager()
