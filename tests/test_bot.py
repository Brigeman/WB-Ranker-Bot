"""Tests for Telegram bot module."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

import pytest
from telegram import Update, Message, User, Chat, Document, File, CallbackQuery
from telegram.ext import ContextTypes

from app.config import Settings
from app.bot import (
    TelegramProgressTracker, TelegramLogger, WBRankerBot,
    main
)


class MockUpdate:
    """Mock Telegram Update for testing."""
    
    def __init__(self, user_id: int = 12345, chat_id: int = 12345, text: str = None, document: Document = None):
        self.effective_user = User(id=user_id, is_bot=False, first_name="Test")
        self.effective_chat = Chat(id=chat_id, type="private")
        
        # Create message with proper bot association
        self.message = Message(
            message_id=1,
            date=datetime.now(),
            chat=self.effective_chat,
            from_user=self.effective_user,
            text=text,
            document=document
        )
        
        # Mock bot for message
        self.message._bot = AsyncMock()
        self.message._bot.defaults = None
        self.message._bot.send_message = AsyncMock()
        
        self.callback_query = None


class MockContext:
    """Mock Telegram Context for testing."""
    
    def __init__(self):
        self.bot = AsyncMock()
        self.bot.send_message = AsyncMock()
        self.bot.edit_message_text = AsyncMock()
        self.bot.get_file = AsyncMock()
        self.bot.send_document = AsyncMock()


@pytest.fixture
def settings():
    """Create test settings."""
    return Settings(
        bot_token="test_token",
        wb_max_pages=3,
        wb_delay_between_requests=(0.05, 0.2),
        max_keywords_limit=1000
    )


@pytest.fixture
def mock_update():
    """Create mock update."""
    return MockUpdate()


@pytest.fixture
def mock_context():
    """Create mock context."""
    return MockContext()


@pytest.fixture
def mock_document():
    """Create mock document."""
    document = Document(
        file_id="test_file_id",
        file_unique_id="test_unique_id",
        file_name="test_keywords.csv",
        file_size=1024,
        mime_type="text/csv"
    )
    return document


class TestTelegramProgressTracker:
    """Test TelegramProgressTracker class."""
    
    @pytest.mark.asyncio
    async def test_update_progress_new_message(self, mock_update, mock_context):
        """Test progress update with new message."""
        tracker = TelegramProgressTracker(mock_update, mock_context)
        
        await tracker.update_progress(5, 10, "Test message", "2m")
        
        # Verify message was sent
        mock_context.bot.send_message.assert_called_once()
        call_args = mock_context.bot.send_message.call_args
        assert call_args[1]['chat_id'] == mock_update.effective_chat.id
        assert "Обработано: 5/10" in call_args[1]['text']
        assert "Test message" in call_args[1]['text']
        assert "ETA: 2m" in call_args[1]['text']
        assert "█████░░░░░" in call_args[1]['text']  # Progress bar
    
    @pytest.mark.asyncio
    async def test_update_progress_edit_message(self, mock_update, mock_context):
        """Test progress update with message edit."""
        tracker = TelegramProgressTracker(mock_update, mock_context)
        
        # First update (creates message)
        await tracker.update_progress(5, 10, "Test message")
        assert tracker.last_message_id is not None
        
        # Second update (edits message)
        await tracker.update_progress(8, 10, "Updated message")
        
        # Verify edit was called
        mock_context.bot.edit_message_text.assert_called_once()
        call_args = mock_context.bot.edit_message_text.call_args
        assert call_args[1]['chat_id'] == mock_update.effective_chat.id
        assert call_args[1]['message_id'] == tracker.last_message_id
        assert "Обработано: 8/10" in call_args[1]['text']
    
    @pytest.mark.asyncio
    async def test_send_message(self, mock_update, mock_context):
        """Test sending general message."""
        tracker = TelegramProgressTracker(mock_update, mock_context)
        
        await tracker.send_message("Test message")
        
        mock_context.bot.send_message.assert_called_once_with(
            chat_id=mock_update.effective_chat.id,
            text="Test message"
        )
    
    @pytest.mark.asyncio
    async def test_send_error(self, mock_update, mock_context):
        """Test sending error message."""
        tracker = TelegramProgressTracker(mock_update, mock_context)
        
        await tracker.send_error("Test error")
        
        mock_context.bot.send_message.assert_called_once_with(
            chat_id=mock_update.effective_chat.id,
            text="❌ Test error",
            parse_mode='HTML'
        )
    
    @pytest.mark.asyncio
    async def test_send_success(self, mock_update, mock_context):
        """Test sending success message."""
        tracker = TelegramProgressTracker(mock_update, mock_context)
        
        await tracker.send_success("Test success")
        
        mock_context.bot.send_message.assert_called_once_with(
            chat_id=mock_update.effective_chat.id,
            text="✅ Test success",
            parse_mode='HTML'
        )
    
    def test_create_progress_bar(self, mock_update, mock_context):
        """Test progress bar creation."""
        tracker = TelegramProgressTracker(mock_update, mock_context)
        
        # Test different progress values
        assert tracker._create_progress_bar(0, 10) == "░░░░░░░░░░ 0.0%"
        assert tracker._create_progress_bar(5, 10) == "█████░░░░░ 50.0%"
        assert tracker._create_progress_bar(10, 10) == "██████████ 100.0%"
        assert tracker._create_progress_bar(0, 0) == "░░░░░░░░░░"  # Edge case


class TestTelegramLogger:
    """Test TelegramLogger class."""
    
    def test_info_logging(self, mock_context):
        """Test info logging."""
        logger = TelegramLogger(mock_context, 12345)
        
        # Mock the logger attribute directly
        logger.logger = Mock()
        
        # Test without event loop (should not create task)
        logger.info("Test info message")
        
        # Verify local logging
        logger.logger.info.assert_called_once_with("Test info message")
    
    def test_error_logging(self, mock_context):
        """Test error logging."""
        logger = TelegramLogger(mock_context, 12345)
        
        # Mock the logger attribute directly
        logger.logger = Mock()
        
        # Test without event loop (should not create task)
        logger.error("Test error message")
        
        # Verify local logging
        logger.logger.error.assert_called_once_with("Test error message")


class TestWBRankerBot:
    """Test WBRankerBot class."""
    
    @pytest.fixture
    def bot(self, settings):
        """Create bot instance."""
        return WBRankerBot(settings)
    
    @pytest.mark.asyncio
    async def test_start_command(self, bot, mock_update, mock_context):
        """Test /start command."""
        await bot.start_command(mock_update, mock_context)
        
        # Verify welcome message was sent via message.reply_text
        mock_update.message._bot.send_message.assert_called_once()
        call_args = mock_update.message._bot.send_message.call_args
        assert "WB Ranker Bot" in call_args[1]['text']
        assert call_args[1]['parse_mode'] == 'HTML'
        assert call_args[1]['reply_markup'] is not None
    
    @pytest.mark.asyncio
    async def test_help_command(self, bot, mock_update, mock_context):
        """Test /help command."""
        await bot.help_command(mock_update, mock_context)
        
        # Verify help message was sent via message.reply_text
        mock_update.message._bot.send_message.assert_called_once()
        call_args = mock_update.message._bot.send_message.call_args
        assert "Справка по использованию" in call_args[1]['text']
        assert call_args[1]['parse_mode'] == 'HTML'
    
    @pytest.mark.asyncio
    async def test_status_command(self, bot, mock_update, mock_context):
        """Test /status command."""
        with patch('app.bot.WBAPIAdapter') as mock_adapter_class:
            mock_adapter = AsyncMock()
            mock_adapter.health_check = AsyncMock(return_value=True)
            mock_adapter_class.return_value.__aenter__ = AsyncMock(return_value=mock_adapter)
            mock_adapter_class.return_value.__aexit__ = AsyncMock(return_value=None)
            
            await bot.status_command(mock_update, mock_context)
            
            # Verify status message was sent via message.reply_text
            mock_update.message._bot.send_message.assert_called_once()
            call_args = mock_update.message._bot.send_message.call_args
            assert "Статус WB Ranker Bot" in call_args[1]['text']
            assert "Активен" in call_args[1]['text']
    
    @pytest.mark.asyncio
    async def test_cancel_command(self, bot, mock_update, mock_context):
        """Test /cancel command."""
        user_id = mock_update.effective_user.id
        
        # Test cancel with no active session
        await bot.cancel_command(mock_update, mock_context)
        mock_update.message._bot.send_message.assert_called_once()
        call_args = mock_update.message._bot.send_message.call_args
        assert call_args[1]['chat_id'] == mock_update.effective_chat.id
        assert call_args[1]['text'] == "ℹ️ Нет активных операций для отмены"
        assert call_args[1]['parse_mode'] == 'HTML'
        
        # Reset mock for second test
        mock_update.message._bot.send_message.reset_mock()
        
        # Test cancel with active session
        bot.active_sessions[user_id] = {'test': 'data'}
        await bot.cancel_command(mock_update, mock_context)
        
        # Verify session was cleared
        assert user_id not in bot.active_sessions
    
    @pytest.mark.asyncio
    async def test_handle_url_message_valid(self, bot, mock_context):
        """Test handling valid WB URL."""
        # Create update with URL text
        mock_update = MockUpdate(text="https://wildberries.ru/catalog/12345/detail.aspx")
        
        with patch('app.bot.WBURLParser') as mock_parser_class:
            mock_parser = Mock()
            mock_parser.validate_wb_url.return_value = True
            mock_parser.extract_product_id.return_value = 12345
            mock_parser_class.return_value = mock_parser
            
            await bot.handle_url_message(mock_update, mock_context)
            
            # Verify URL was processed
            user_id = mock_update.effective_user.id
            assert user_id in bot.active_sessions
            assert bot.active_sessions[user_id]['product_url'] == mock_update.message.text
            assert bot.active_sessions[user_id]['product_id'] == 12345
            
            # Verify success message
            mock_update.message._bot.send_message.assert_called_once()
            call_args = mock_update.message._bot.send_message.call_args
            assert "Ссылка на товар принята" in call_args[1]['text']
    
    @pytest.mark.asyncio
    async def test_handle_url_message_invalid(self, bot, mock_context):
        """Test handling invalid WB URL."""
        # Create update with invalid URL text
        mock_update = MockUpdate(text="https://invalid-url.com/product")
        
        with patch('app.bot.WBURLParser') as mock_parser_class:
            mock_parser = Mock()
            mock_parser.validate_wb_url.return_value = False
            mock_parser_class.return_value = mock_parser
            
            await bot.handle_url_message(mock_update, mock_context)
            
            # Verify error message
            mock_update.message._bot.send_message.assert_called_once()
            call_args = mock_update.message._bot.send_message.call_args
            assert "Неверная ссылка на товар" in call_args[1]['text']
    
    @pytest.mark.asyncio
    async def test_handle_document_no_session(self, bot, mock_context, mock_document):
        """Test handling document without active session."""
        # Create update with document
        mock_update = MockUpdate(document=mock_document)
        
        await bot.handle_document(mock_update, mock_context)
        
        # Verify error message
        mock_update.message._bot.send_message.assert_called_once()
        call_args = mock_update.message._bot.send_message.call_args
        assert "Сначала отправьте ссылку на товар" in call_args[1]['text']
    
    @pytest.mark.asyncio
    async def test_handle_document_with_session(self, bot, mock_context, mock_document):
        """Test handling document with active session."""
        user_id = 12345
        bot.active_sessions[user_id] = {
            'product_url': 'https://wildberries.ru/catalog/12345/detail.aspx',
            'product_id': 12345
        }
        
        # Create update with document
        mock_update = MockUpdate(user_id=user_id, document=mock_document)
        
        # Mock file download
        mock_file = AsyncMock()
        mock_file.download_to_drive = AsyncMock()
        mock_context.bot.get_file.return_value = mock_file
        
        # Mock the ranking process to avoid complex setup
        with patch.object(bot, '_start_ranking_process') as mock_start_ranking:
            await bot.handle_document(mock_update, mock_context)
            
            # Verify ranking process was started
            mock_start_ranking.assert_called_once_with(mock_update, mock_context, user_id)
    
    @pytest.mark.asyncio
    async def test_handle_text_message_url(self, bot, mock_context):
        """Test handling text message that is a URL."""
        # Create update with URL text
        mock_update = MockUpdate(text="https://wildberries.ru/catalog/12345/detail.aspx")
        
        with patch.object(bot, 'handle_url_message') as mock_handle_url:
            await bot.handle_text_message(mock_update, mock_context)
            mock_handle_url.assert_called_once_with(mock_update, mock_context)
    
    @pytest.mark.asyncio
    async def test_handle_text_message_non_url(self, bot, mock_context):
        """Test handling text message that is not a URL."""
        # Create update with non-URL text
        mock_update = MockUpdate(text="Hello world")
        
        await bot.handle_text_message(mock_update, mock_context)
        
        # Verify help message
        mock_update.message._bot.send_message.assert_called_once()
        call_args = mock_update.message._bot.send_message.call_args
        assert "Не понимаю команду" in call_args[1]['text']
    
    @pytest.mark.asyncio
    async def test_callback_query_handler(self, bot, mock_context):
        """Test callback query handler."""
        # Create update with callback query
        mock_update = MockUpdate()
        callback_query = CallbackQuery(
            id="test_query_id",
            from_user=mock_update.effective_user,
            chat_instance="test_chat_instance",
            data="help"
        )
        callback_query._bot = AsyncMock()
        callback_query._bot.answer_callback_query = AsyncMock()
        mock_update.callback_query = callback_query
        
        with patch.object(bot, 'help_command') as mock_help:
            await bot.callback_query_handler(mock_update, mock_context)
            mock_help.assert_called_once_with(mock_update, mock_context)
    
    def test_setup_handlers(self, bot):
        """Test handler setup."""
        bot.application = Mock()
        
        bot.setup_handlers()
        
        # Verify handlers were added
        assert bot.application.add_handler.call_count >= 6  # At least 6 handlers


@pytest.mark.asyncio
async def test_main_function():
    """Test main function."""
    with patch('app.bot.Settings') as mock_settings_class, \
         patch('app.bot.WBRankerBot') as mock_bot_class, \
         patch('asyncio.run') as mock_run:
        
        mock_settings = Mock()
        mock_settings_class.return_value = mock_settings
        
        mock_bot = AsyncMock()
        mock_bot_class.return_value = mock_bot
        
        await main()
        
        # Verify bot was created and run
        mock_bot_class.assert_called_once_with(mock_settings)
        mock_bot.run.assert_called_once()
