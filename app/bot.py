"""Telegram bot implementation for WB Ranker Bot."""

import asyncio
import logging
import os
from typing import Dict, Any, Optional, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

from app.config import Settings
from app.ports import Logger, ProgressTracker
from app.services import RankingServiceImpl
from app.wb_adapter import WBAPIAdapter
from app.fileio import FileLoaderImpl
from app.exporter import FileExporterImpl
from app.utils import (
    WBURLParser, format_price,
    get_product_info, extract_keywords_from_product, 
    filter_keywords_by_relevance, categorize_keywords
)


class TelegramProgressTracker(ProgressTracker):
    """Progress tracker implementation for Telegram bot."""
    
    def __init__(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.update = update
        self.context = context
        self.last_message_id: Optional[int] = None
    
    async def update_progress(
        self, 
        current: int, 
        total: int, 
        message: str = None, 
        eta: str = None
    ) -> None:
        """Update progress in Telegram."""
        progress_text = f"🔄 Обработано: {current}/{total}"
        if message:
            progress_text += f"\n📝 {message}"
        if eta:
            progress_text += f"\n⏱️ ETA: {eta}"
        
        # Create progress bar
        progress_bar = self._create_progress_bar(current, total)
        progress_text += f"\n{progress_bar}"
        
        try:
            if self.last_message_id:
                await self.context.bot.edit_message_text(
                    chat_id=self.update.effective_chat.id,
                    message_id=self.last_message_id,
                    text=progress_text
                )
            else:
                sent_message = await self.context.bot.send_message(
                    chat_id=self.update.effective_chat.id,
                    text=progress_text
                )
                self.last_message_id = sent_message.message_id
        except Exception as e:
            logging.warning(f"Failed to update progress: {e}")
    
    async def send_message(self, message: str) -> None:
        """Send a general message to the user."""
        try:
            await self.context.bot.send_message(
                chat_id=self.update.effective_chat.id,
                text=message
            )
        except Exception as e:
            logging.warning(f"Failed to send message: {e}")
    
    async def send_error(self, error_message: str) -> None:
        """Send an error message to the user."""
        try:
            await self.context.bot.send_message(
                chat_id=self.update.effective_chat.id,
                text=f"❌ {error_message}",
                parse_mode='HTML'
            )
        except Exception as e:
            logging.warning(f"Failed to send error message: {e}")
    
    async def send_success(self, success_message: str) -> None:
        """Send a success message to the user."""
        try:
            await self.context.bot.send_message(
                chat_id=self.update.effective_chat.id,
                text=f"✅ {success_message}",
                parse_mode='HTML'
            )
        except Exception as e:
            logging.warning(f"Failed to send success message: {e}")
    
    def _create_progress_bar(self, current: int, total: int) -> str:
        """Create a visual progress bar."""
        if total == 0:
            return "░░░░░░░░░░"
        
        progress = current / total
        filled = int(progress * 10)
        empty = 10 - filled
        
        return "█" * filled + "░" * empty + f" {progress:.1%}"
    
    async def complete(self, message: str = "") -> None:
        """Mark progress as complete."""
        try:
            completion_text = f"✅ Завершено!"
            if message:
                completion_text += f"\n📝 {message}"
            
            if self.last_message_id:
                await self.context.bot.edit_message_text(
                    chat_id=self.update.effective_chat.id,
                    message_id=self.last_message_id,
                    text=completion_text
                )
            else:
                await self.context.bot.send_message(
                    chat_id=self.update.effective_chat.id,
                    text=completion_text
                )
        except Exception as e:
            logging.warning(f"Failed to send completion message: {e}")
    
    async def error(self, message: str) -> None:
        """Mark progress as error."""
        try:
            error_text = f"❌ Ошибка: {message}"
            
            if self.last_message_id:
                await self.context.bot.edit_message_text(
                    chat_id=self.update.effective_chat.id,
                    message_id=self.last_message_id,
                    text=error_text
                )
            else:
                await self.context.bot.send_message(
                    chat_id=self.update.effective_chat.id,
                    text=error_text
                )
        except Exception as e:
            logging.warning(f"Failed to send error message: {e}")


class TelegramLogger(Logger):
    """Logger implementation that also logs to Telegram."""
    
    def __init__(self, bot_context: Optional[ContextTypes.DEFAULT_TYPE] = None, 
                 chat_id: Optional[int] = None):
        self.bot_context = bot_context
        self.chat_id = chat_id
        self.logger = logging.getLogger(__name__)
    
    def info(self, message: str, **kwargs) -> None:
        """Log info message."""
        self.logger.info(message)
        if self.bot_context and self.chat_id:
            try:
                # Check if we're in an async context
                loop = asyncio.get_running_loop()
                if loop and not loop.is_closed():
                    asyncio.create_task(self._send_to_telegram(f"ℹ️ {message}"))
            except RuntimeError:
                # No event loop running, skip Telegram logging
                pass
    
    def warning(self, message: str, **kwargs) -> None:
        """Log warning message."""
        self.logger.warning(message)
        if self.bot_context and self.chat_id:
            try:
                # Check if we're in an async context
                loop = asyncio.get_running_loop()
                if loop and not loop.is_closed():
                    asyncio.create_task(self._send_to_telegram(f"⚠️ {message}"))
            except RuntimeError:
                # No event loop running, skip Telegram logging
                pass
    
    def error(self, message: str, **kwargs) -> None:
        """Log error message."""
        self.logger.error(message)
        if self.bot_context and self.chat_id:
            try:
                # Check if we're in an async context
                loop = asyncio.get_running_loop()
                if loop and not loop.is_closed():
                    asyncio.create_task(self._send_to_telegram(f"❌ {message}"))
            except RuntimeError:
                # No event loop running, skip Telegram logging
                pass
    
    def debug(self, message: str, **kwargs) -> None:
        """Log debug message."""
        self.logger.debug(message)
    
    async def _send_to_telegram(self, message: str) -> None:
        """Send message to Telegram."""
        try:
            await self.bot_context.bot.send_message(
                chat_id=self.chat_id,
                text=message[:4000]  # Telegram message limit
            )
        except Exception as e:
            self.logger.warning(f"Failed to send log to Telegram: {e}")


class WBRankerBot:
    """Main Telegram bot class."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = TelegramLogger()
        self.application = None
        self.ranking_service = None
        self.active_sessions: Dict[int, Dict[str, Any]] = {}
    
    async def initialize(self) -> None:
        """Initialize bot components."""
        try:
            # Initialize components
            self.file_loader = FileLoaderImpl(self.settings, self.logger)
            self.file_exporter = FileExporterImpl(self.settings, self.logger)
            
            # Initialize ranking service
            self.ranking_service = RankingServiceImpl(
                settings=self.settings,
                search_client=None,  # Will be set per request
                file_loader=self.file_loader,
                file_exporter=self.file_exporter,
                logger=self.logger
            )
            
            self.logger.info("Bot components initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize bot: {e}")
            raise
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        welcome_text = """
🤖 <b>WB Ranker Bot</b>

Добро пожаловать! Этот бот поможет вам проанализировать позиции товаров на Wildberries.

<b>Как использовать:</b>
1. Отправьте ссылку на товар WB
2. Загрузите файл с ключевыми словами (CSV/XLSX) или отправьте ссылку на файл
3. Получите отчет с позициями товара

<b>Команды:</b>
/start - Начать работу
/help - Помощь
/status - Статус бота
/cancel - Отменить текущую операцию

<b>Поддерживаемые форматы файлов:</b>
• CSV (.csv)
• Excel (.xlsx, .xls)
• Google Drive ссылки

Начните с отправки ссылки на товар! 🚀
        """
        
        keyboard = [
            [InlineKeyboardButton("📖 Помощь", callback_data="help")],
            [InlineKeyboardButton("📊 Статус", callback_data="status")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_text,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        help_text = """
📖 <b>Справка по использованию WB Ranker Bot</b>

<b>Пошаговая инструкция:</b>

1️⃣ <b>Отправьте ссылку на товар</b>
   Пример: https://wildberries.ru/catalog/12345/detail.aspx

2️⃣ <b>Загрузите файл с ключевыми словами</b>
   • CSV файл с ключевыми словами в первой колонке
   • Excel файл (.xlsx, .xls)
   • Или отправьте ссылку на файл (Google Drive, Dropbox, Яндекс.Диск)

3️⃣ <b>Получите отчет</b>
   • Позиции товара по каждому ключевому слову
   • Статистика и анализ
   • Экспорт в CSV/XLSX

<b>Ограничения:</b>
• Максимум 1000 ключевых слов за раз
• Максимум 5 страниц поиска на ключевое слово
• Время выполнения до 30 минут

<b>Поддерживаемые форматы ссылок WB:</b>
• https://wildberries.ru/catalog/ID/detail.aspx
• https://www.wildberries.ru/catalog/ID/detail.aspx

<b>Команды:</b>
/start - Главное меню
/help - Эта справка
/status - Статус бота
/cancel - Отменить операцию

Нужна помощь? Отправьте /start для начала! 🚀
        """
        
        await update.message.reply_text(help_text, parse_mode='HTML')
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command."""
        try:
            # Check WB API health
            async with WBAPIAdapter(self.settings, self.logger) as wb_adapter:
                api_healthy = await wb_adapter.health_check()
            
            status_text = f"""
📊 <b>Статус WB Ranker Bot</b>

🤖 <b>Бот:</b> Активен
🌐 <b>WB API:</b> {'✅ Доступен' if api_healthy else '❌ Недоступен'}
📁 <b>Файловая система:</b> ✅ Доступна
💾 <b>Экспорт:</b> ✅ Доступен

<b>Настройки:</b>
• Максимум страниц: {self.settings.wb_max_pages}
• Лимит ключевых слов: {self.settings.max_keywords_limit}
• Таймаут запросов: {self.settings.wb_request_timeout}с
• Директория вывода: {self.settings.output_directory}

<b>Активные сессии:</b> {len(self.active_sessions)}
            """
            
            await update.message.reply_text(status_text, parse_mode='HTML')
            
        except Exception as e:
            await update.message.reply_text(
                f"❌ Ошибка при проверке статуса: {e}",
                parse_mode='HTML'
            )
    
    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /cancel command."""
        user_id = update.effective_user.id
        
        if user_id in self.active_sessions:
            del self.active_sessions[user_id]
            await update.message.reply_text(
                "✅ Операция отменена",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(
                "ℹ️ Нет активных операций для отмены",
                parse_mode='HTML'
            )
    
    async def handle_url_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle WB product URL messages."""
        user_id = update.effective_user.id
        url = update.message.text.strip()
        
        self.logger.info(f"URL handler - User ID: {user_id}, URL: {url[:50]}...")
        
        try:
            # Validate URL
            parser = WBURLParser()
            if not parser.validate_wb_url(url):
                await update.message.reply_text(
                    f"❌ <b>Неверная ссылка!</b>\n\n"
                    f"🔗 <b>Вы отправили:</b> {url[:50]}...\n\n"
                    f"📝 <b>Пожалуйста, отправьте ссылку на товар Wildberries:</b>\n"
                    f"• https://www.wildberries.ru/catalog/123456/detail.aspx\n"
                    f"• https://wildberries.ru/catalog/123456/detail.aspx\n\n"
                    f"⚠️ <b>Не отправляйте:</b>\n"
                    f"• Ссылки на Google Drive\n"
                    f"• Ссылки на другие сайты\n"
                    f"• Файлы с ключевыми словами (их нужно отправить после ссылки на товар)",
                    parse_mode='HTML'
                )
                return
            
            # Extract product ID
            try:
                product_id = parser.extract_product_id(url)
            except ValueError as e:
                await update.message.reply_text(
                    f"❌ <b>Ошибка извлечения ID товара!</b>\n\n"
                    f"📝 <b>Ошибка:</b> {str(e)}\n\n"
                    f"🔗 <b>Проверьте правильность ссылки на товар Wildberries</b>",
                    parse_mode='HTML'
                )
                return
            
            # Store URL in user session
            if user_id not in self.active_sessions:
                self.active_sessions[user_id] = {}
            
            self.active_sessions[user_id]['product_url'] = url
            self.active_sessions[user_id]['product_id'] = product_id
            
            self.logger.info(f"Session created/updated for user {user_id}: {list(self.active_sessions[user_id].keys())}")
            
            await update.message.reply_text(
                f"✅ Ссылка на товар принята!\n"
                f"🆔 ID товара: {product_id}\n\n"
                f"Теперь отправьте файл с ключевыми словами или ссылку на файл.",
                parse_mode='HTML'
            )
            
        except Exception as e:
            self.logger.error(f"Error handling URL: {e}")
            await update.message.reply_text(
                f"❌ Ошибка при обработке ссылки: {e}",
                parse_mode='HTML'
            )
    
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle document uploads."""
        user_id = update.effective_user.id
        
        if user_id not in self.active_sessions:
            await update.message.reply_text(
                "❌ Сначала отправьте ссылку на товар WB",
                parse_mode='HTML'
            )
            return
        
        try:
            document = update.message.document
            file_name = document.file_name
            
            # Check file extension
            if not file_name.lower().endswith(('.csv', '.xlsx', '.xls')):
                await update.message.reply_text(
                    "❌ Неподдерживаемый формат файла.\n"
                    "Поддерживаются: CSV, XLSX, XLS",
                    parse_mode='HTML'
                )
                return
            
            # Download file
            file = await context.bot.get_file(document.file_id)
            file_path = f"temp_{user_id}_{file_name}"
            
            await file.download_to_drive(file_path)
            
            # Store file path in session
            self.active_sessions[user_id]['keywords_file'] = file_path
            
            await update.message.reply_text(
                f"✅ Файл загружен: {file_name}\n\n"
                f"Начинаем анализ...",
                parse_mode='HTML'
            )
            
            # Start ranking process with filtering
            await self._start_ranking_process_with_file(update, context, user_id)
            
        except Exception as e:
            self.logger.error(f"Error handling document: {e}")
            await update.message.reply_text(
                f"❌ Ошибка при обработке файла: {e}",
                parse_mode='HTML'
            )
    
    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle text messages (URLs or other text)."""
        text = update.message.text.strip()
        
        # Debug: log message processing
        self.logger.info(f"Text message handler - Text: {text[:50]}...")
        
        # Check if it's a URL
        if text.startswith(('http://', 'https://')):
            # Check if it's a Google Drive or other file URL
            is_file_url = self._is_file_url(text)
            self.logger.info(f"URL detected - Is file URL: {is_file_url}")
            
            if is_file_url:
                await self.handle_file_url_message(update, context)
            else:
                await self.handle_url_message(update, context)
        else:
            await update.message.reply_text(
                "❓ Не понимаю команду.\n\n"
                "Отправьте:\n"
                "• Ссылку на товар WB\n"
                "• Файл с ключевыми словами\n"
                "• Ссылку на файл (Google Drive)\n"
                "• Команду /help для справки",
                parse_mode='HTML'
            )
    
    def _is_file_url(self, url: str) -> bool:
        """Check if URL is a file URL (Google Drive, etc.)."""
        file_domains = [
            'drive.google.com',
            'docs.google.com',
            'dropbox.com',
            'yandex.ru/disk',
            'cloud.mail.ru'
        ]
        is_file = any(domain in url.lower() for domain in file_domains)
        self.logger.info(f"URL check: {url[:50]}... -> is_file: {is_file}")
        return is_file
    
    async def handle_file_url_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle file URL messages (Google Drive, etc.)."""
        user_id = update.effective_user.id
        url = update.message.text.strip()
        
        try:
            # Debug: log session state
            self.logger.info(f"File URL handler - User ID: {user_id}, Active sessions: {list(self.active_sessions.keys())}")
            if user_id in self.active_sessions:
                self.logger.info(f"User session keys: {list(self.active_sessions[user_id].keys())}")
            
            # Check if user has a product URL in session
            if user_id not in self.active_sessions or 'product_url' not in self.active_sessions[user_id]:
                await update.message.reply_text(
                    "❌ Сначала отправьте ссылку на товар WB",
                    parse_mode='HTML'
                )
                return
            
            # Store file URL in session
            self.active_sessions[user_id]['file_url'] = url
            
            await update.message.reply_text(
                f"✅ Ссылка на файл принята!\n"
                f"🔗 URL: {url}\n\n"
                f"Начинаем загрузку и анализ...",
                parse_mode='HTML'
            )
            
            # Start ranking process with file URL
            await self._start_ranking_process_with_url(update, context, user_id)
            
        except Exception as e:
            self.logger.error(f"Error handling file URL: {e}")
            await update.message.reply_text(
                f"❌ Ошибка при обработке ссылки на файл: {e}",
                parse_mode='HTML'
            )
    
    async def callback_query_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle callback queries from inline keyboards."""
        query = update.callback_query
        await query.answer()
        
        if query.data == "help":
            await self.help_command(update, context)
        elif query.data == "status":
            await self.status_command(update, context)
    
    async def _start_ranking_process(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
        """Start the ranking process."""
        try:
            session = self.active_sessions[user_id]
            product_url = session['product_url']
            keywords_file = session['keywords_file']
            
            # Create progress tracker
            progress_tracker = TelegramProgressTracker(update, context)
            
            # Initialize search client
            async with WBAPIAdapter(self.settings, self.logger) as search_client:
                # Update ranking service with search client
                self.ranking_service.search_client = search_client
                self.ranking_service.progress_tracker = progress_tracker
                
                # Start ranking
                result = await self.ranking_service.rank_product_by_keywords(
                    product_url=product_url,
                    keywords_source=keywords_file,
                    output_format="xlsx"
                )
                
                # Send results
                await self._send_ranking_results(update, context, result)
                
        except Exception as e:
            self.logger.error(f"Error in ranking process: {e}")
            await update.message.reply_text(
                f"❌ Ошибка при анализе: {e}",
                parse_mode='HTML'
            )
        finally:
            # Cleanup
            if user_id in self.active_sessions:
                session = self.active_sessions[user_id]
                if 'keywords_file' in session:
                    try:
                        os.remove(session['keywords_file'])
                    except OSError:
                        pass
                del self.active_sessions[user_id]
    
    async def _analyze_and_filter_keywords(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                         product_url: str, file_source: str) -> List[str]:
        """Analyze product and filter keywords from file."""
        try:
            # Extract product ID from URL
            parser = WBURLParser()
            try:
                product_id = parser.extract_product_id(product_url)
            except ValueError as e:
                await update.message.reply_text(
                    f"❌ <b>Неверная ссылка!</b>\n\n"
                    f"📝 <b>Ошибка:</b> {str(e)}\n\n"
                    f"🔗 <b>Пожалуйста, отправьте ссылку на товар Wildberries:</b>\n"
                    f"• https://www.wildberries.ru/catalog/123456/detail.aspx\n"
                    f"• https://wildberries.ru/catalog/123456/detail.aspx\n\n"
                    f"📁 <b>После этого отправьте файл с ключевыми словами</b>",
                    parse_mode='HTML'
                )
                return []
            
            # Send analysis start message
            analysis_msg = await update.message.reply_text(
                "🔍 <b>Анализируем товар и фильтруем ключевые слова...</b>\n\n"
                f"📦 ID товара: {product_id}\n"
                "⏳ Получаем информацию о товаре...",
                parse_mode='HTML'
            )
            
            # Get product information
            self.logger.info(f"Getting product info for ID: {product_id}")
            product_info = await get_product_info(product_id)
            
            # Check if we got real product info or fallback
            is_fallback = product_info.get('is_fallback', False) or (
                product_info.get('name', '').startswith('Товар ') and 
                product_info.get('brand') == 'Неизвестно'
            )
            
            if is_fallback:
                self.logger.warning(f"Using fallback product info for ID: {product_id}")
                await analysis_msg.edit_text(
                    f"⚠️ <b>Товар не найден в популярных категориях</b>\n\n"
                    f"📦 ID товара: {product_id}\n"
                    f"🔄 <b>Используем все ключевые слова без фильтрации</b>\n\n"
                    f"⏳ Загружаем файл с ключевыми словами...",
                    parse_mode='HTML'
                )
            else:
                self.logger.info(f"Product info retrieved: {product_info.get('name', 'N/A')}")
                
                await analysis_msg.edit_text(
                    f"✅ <b>Товар найден!</b>\n\n"
                    f"📦 <b>Название:</b> {product_info.get('name', 'N/A')}\n"
                    f"🏷️ <b>Бренд:</b> {product_info.get('brand', 'N/A')}\n"
                    f"📂 <b>Категория:</b> {product_info.get('subject', 'N/A')}\n\n"
                    f"⏳ Загружаем файл с ключевыми словами...",
                    parse_mode='HTML'
                )
            
            # Load keywords from file or URL
            if file_source.startswith(('http://', 'https://')):
                keywords = await self.file_loader.load_keywords_from_url(file_source)
            else:
                keywords = await self.file_loader.load_keywords_from_file(file_source)
            
            if not keywords:
                await analysis_msg.edit_text(
                    "❌ Не удалось загрузить ключевые слова из файла",
                    parse_mode='HTML'
                )
                return []
            
            # Handle filtering based on whether we have real product info
            if is_fallback:
                # Use limited keywords without filtering to avoid long processing
                max_fallback_keywords = 1000  # Ограничиваем количество ключевых слов
                relevant_keywords = keywords[:max_fallback_keywords]
                
                await analysis_msg.edit_text(
                    f"📁 <b>Файл загружен!</b>\n\n"
                    f"📊 <b>Всего ключевых слов:</b> {len(keywords)}\n"
                    f"⚠️ <b>Товар не найден в популярных категориях</b>\n"
                    f"🔄 <b>Используем первые {max_fallback_keywords} ключевых слов</b>\n"
                    f"⏱️ <b>Это займет примерно {max_fallback_keywords * 0.5 / 60:.1f} минут</b>\n\n"
                    f"🚀 <b>Начинаем поиск...</b>",
                    parse_mode='HTML'
                )
            else:
                # Extract keywords from product and filter
                product_keywords = extract_keywords_from_product(product_info)
                
                await analysis_msg.edit_text(
                    f"📁 <b>Файл загружен!</b>\n\n"
                    f"📊 <b>Всего ключевых слов:</b> {len(keywords)}\n"
                    f"🔑 <b>Ключевые слова товара:</b> {', '.join(product_keywords[:5])}...\n"
                    f"🔍 <b>Фильтруем по релевантности...</b>",
                    parse_mode='HTML'
                )
                
                # Filter keywords by relevance
                self.logger.info(f"Filtering {len(keywords)} keywords against product keywords: {product_keywords}")
                relevant_keywords = filter_keywords_by_relevance(keywords, product_keywords)
                self.logger.info(f"After filtering: {len(relevant_keywords)} relevant keywords")
                
                # Calculate efficiency
                efficiency = ((len(keywords) - len(relevant_keywords)) / len(keywords) * 100) if keywords else 0
                
                await analysis_msg.edit_text(
                    f"🎯 <b>Фильтрация завершена!</b>\n\n"
                    f"📊 <b>Статистика:</b>\n"
                    f"   • Исходно: {len(keywords)} ключевых слов\n"
                    f"   • После фильтрации: {len(relevant_keywords)} ключевых слов\n"
                    f"   • Сокращение: {efficiency:.1f}%\n\n"
                    f"🚀 <b>Начинаем поиск по релевантным ключевым словам...</b>",
                    parse_mode='HTML'
                )
            
            return relevant_keywords
            
        except Exception as e:
            self.logger.error(f"Error in keyword analysis and filtering: {e}")
            await update.message.reply_text(
                f"❌ Ошибка при анализе и фильтрации: {e}",
                parse_mode='HTML'
            )
            return []
    
    async def _start_ranking_process_with_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
        """Start the ranking process with file filtering."""
        try:
            session = self.active_sessions[user_id]
            product_url = session['product_url']
            keywords_file = session['keywords_file']
            
            # Analyze product and filter keywords
            relevant_keywords = await self._analyze_and_filter_keywords(update, context, product_url, keywords_file)
            
            if not relevant_keywords:
                await update.message.reply_text(
                    "❌ Не удалось получить релевантные ключевые слова",
                    parse_mode='HTML'
                )
                return
            
            # Create progress tracker
            progress_tracker = TelegramProgressTracker(update, context)
            
            # Initialize search client
            async with WBAPIAdapter(self.settings, self.logger) as search_client:
                # Update ranking service with search client
                self.ranking_service.search_client = search_client
                self.ranking_service.progress_tracker = progress_tracker
                
                # Start ranking with filtered keywords
                result = await self.ranking_service.rank_product_by_keywords(
                    product_url=product_url,
                    keywords_source=relevant_keywords,  # Use filtered keywords instead of file path
                    output_format="xlsx"
                )
                
                # Send results
                await self._send_ranking_results(update, context, result)
                
        except Exception as e:
            self.logger.error(f"Error in ranking process with file: {e}")
            await update.message.reply_text(
                f"❌ Ошибка при анализе: {e}",
                parse_mode='HTML'
            )
        finally:
            # Cleanup
            if user_id in self.active_sessions:
                del self.active_sessions[user_id]

    async def _start_ranking_process_with_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
        """Start the ranking process with file URL."""
        try:
            session = self.active_sessions[user_id]
            product_url = session['product_url']
            file_url = session['file_url']
            
            # Analyze product and filter keywords
            relevant_keywords = await self._analyze_and_filter_keywords(update, context, product_url, file_url)
            
            if not relevant_keywords:
                await update.message.reply_text(
                    "❌ Не удалось получить релевантные ключевые слова",
                    parse_mode='HTML'
                )
                return
            
            # Create progress tracker
            progress_tracker = TelegramProgressTracker(update, context)
            
            # Initialize search client
            async with WBAPIAdapter(self.settings, self.logger) as search_client:
                # Update ranking service with search client
                self.ranking_service.search_client = search_client
                self.ranking_service.progress_tracker = progress_tracker
                
                # Start ranking with filtered keywords
                result = await self.ranking_service.rank_product_by_keywords(
                    product_url=product_url,
                    keywords_source=relevant_keywords,  # Use filtered keywords instead of file URL
                    output_format="xlsx"
                )
                
                # Send results
                await self._send_ranking_results(update, context, result)
                
        except Exception as e:
            self.logger.error(f"Error in ranking process with URL: {e}")
            await update.message.reply_text(
                f"❌ Ошибка при анализе: {e}",
                parse_mode='HTML'
            )
        finally:
            # Cleanup
            if user_id in self.active_sessions:
                del self.active_sessions[user_id]
    
    async def _send_ranking_results(self, update: Update, context: ContextTypes.DEFAULT_TYPE, result) -> None:
        """Send ranking results to user."""
        try:
            # Create summary message
            summary_text = f"""
📊 <b>Результаты анализа</b>

🆔 <b>ID товара:</b> {result.product_id}
📦 <b>Название:</b> {result.product_name}
🔍 <b>Всего ключевых слов:</b> {result.total_keywords}
✅ <b>Найдено:</b> {result.found_keywords}
    📈 <b>Процент найденных:</b> {(result.found_keywords / result.total_keywords * 100):.1f}% if result.total_keywords > 0 else "0%"
⏱️ <b>Время выполнения:</b> {result.execution_time_seconds:.1f}с

<b>Статистика:</b>
• Средняя позиция: {self.ranking_service.get_statistics().get('average_position', 0):.1f}
• Лучшая позиция: {self.ranking_service.get_statistics().get('best_position', 'N/A')}
• Худшая позиция: {self.ranking_service.get_statistics().get('worst_position', 'N/A')}
            """
            
            await update.message.reply_text(summary_text, parse_mode='HTML')
            
            # Send file if available
            if result.export_file_path and os.path.exists(result.export_file_path):
                try:
                    # Determine file type and caption
                    file_extension = os.path.splitext(result.export_file_path)[1].lower()
                    if file_extension == '.csv':
                        caption = "📊 Результаты анализа в формате CSV"
                    else:
                        caption = "📊 Результаты анализа в формате Excel"
                    
                    # Send the file
                    with open(result.export_file_path, 'rb') as file:
                        await update.message.reply_document(
                            document=file,
                            filename=os.path.basename(result.export_file_path),
                            caption=caption,
                            parse_mode='HTML'
                        )
                    
                    self.logger.info(f"Sent results file to user: {result.export_file_path}")
                    
                except Exception as e:
                    self.logger.error(f"Error sending file: {e}")
                    await update.message.reply_text(
                        f"❌ Ошибка при отправке файла: {e}\n"
                        f"Файл сохранен по пути: {result.export_file_path}",
                        parse_mode='HTML'
                    )
            else:
                await update.message.reply_text(
                    "📁 Отчет сохранен локально.\n"
                    "Файл не найден для отправки.",
                    parse_mode='HTML'
                )
            
        except Exception as e:
            self.logger.error(f"Error sending results: {e}")
            await update.message.reply_text(
                f"❌ Ошибка при отправке результатов: {e}",
                parse_mode='HTML'
            )
    
    def setup_handlers(self) -> None:
        """Setup bot handlers."""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("cancel", self.cancel_command))
        
        # Message handlers
        self.application.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))
        
        # Callback query handler
        self.application.add_handler(CallbackQueryHandler(self.callback_query_handler))
    
    def run(self) -> None:
        """Run the bot (synchronously)."""
        try:
            # Initialize bot (no awaits needed here)
            asyncio.run(self.initialize())

            # Create application
            self.application = Application.builder().token(self.settings.bot_token).build()

            # Setup handlers
            self.setup_handlers()

            # Start bot (blocking call manages its own event loop)
            self.logger.info("Starting WB Ranker Bot...")
            self.application.run_polling(
                drop_pending_updates=True,  # Drop pending updates to avoid conflicts
                allowed_updates=["message", "callback_query"]  # Only handle these types
            )

        except Exception as e:
            self.logger.error(f"Failed to run bot: {e}")
            raise


def main():
    """Main function to run the bot."""
    # Load settings
    settings = Settings()

    # Create and run bot
    bot = WBRankerBot(settings)
    bot.run()


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run bot
    main()
