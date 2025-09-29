"""Tests for utils module."""

import pytest
import time
from unittest.mock import patch

from app.utils import (
    WBURLParser,
    calculate_position,
    format_price,
    format_execution_time,
    truncate_string,
    validate_keyword,
    clean_keyword,
    extract_filename_from_url,
    is_google_drive_url,
    convert_google_drive_url,
    retry_with_backoff,
    create_progress_message,
)


class TestWBURLParser:
    """Test WBURLParser class."""
    
    def setup_method(self):
        """Setup test instance."""
        self.parser = WBURLParser()
    
    def test_extract_product_id_valid_urls(self):
        """Test extracting product ID from valid URLs."""
        test_cases = [
            ("https://www.wildberries.ru/catalog/279266291/detail.aspx", 279266291),
            ("https://wildberries.ru/catalog/123456789/detail.aspx", 123456789),
            ("https://www.wildberries.ru/catalog/987654321/detail.aspx?targetUrl=MI", 987654321),
            ("https://wildberries.ru/catalog/555666777/", 555666777),
        ]
        
        for url, expected_id in test_cases:
            assert self.parser.extract_product_id(url) == expected_id
    
    def test_extract_product_id_invalid_urls(self):
        """Test extracting product ID from invalid URLs."""
        invalid_urls = [
            "https://example.com/product/123",
            "https://www.wildberries.ru/catalog/",
            "https://wildberries.ru/catalog/abc/detail.aspx",
            "not-a-url",
            "",
            None,
        ]
        
        for url in invalid_urls:
            with pytest.raises(ValueError):
                self.parser.extract_product_id(url)
    
    def test_validate_wb_url_valid(self):
        """Test validating valid WB URLs."""
        valid_urls = [
            "https://www.wildberries.ru/catalog/279266291/detail.aspx",
            "https://wildberries.ru/catalog/123456789/detail.aspx",
            "http://www.wildberries.ru/catalog/987654321/",
            "https://wildberries.ru/catalog/555666777/detail.aspx?targetUrl=MI",
        ]
        
        for url in valid_urls:
            assert self.parser.validate_wb_url(url) is True
    
    def test_validate_wb_url_invalid(self):
        """Test validating invalid URLs."""
        invalid_urls = [
            "https://example.com/product/123",
            "https://www.wildberries.ru/",
            "https://wildberries.ru/catalog/",
            "not-a-url",
            "",
            None,
        ]
        
        for url in invalid_urls:
            assert self.parser.validate_wb_url(url) is False


class TestCalculatePosition:
    """Test position calculation."""
    
    def test_calculate_position_normal(self):
        """Test normal position calculation."""
        assert calculate_position(1, 0) == 1
        assert calculate_position(1, 5) == 6
        assert calculate_position(2, 0) == 101
        assert calculate_position(2, 5) == 106
        assert calculate_position(3, 10) == 211
    
    def test_calculate_position_custom_items_per_page(self):
        """Test position calculation with custom items per page."""
        assert calculate_position(1, 0, 50) == 1
        assert calculate_position(1, 5, 50) == 6
        assert calculate_position(2, 0, 50) == 51
        assert calculate_position(2, 5, 50) == 56
    
    def test_calculate_position_invalid_input(self):
        """Test position calculation with invalid input."""
        with pytest.raises(ValueError):
            calculate_position(0, 0)  # page < 1
        
        with pytest.raises(ValueError):
            calculate_position(1, -1)  # index < 0


class TestFormatPrice:
    """Test price formatting."""
    
    def test_format_price(self):
        """Test price conversion from kopecks to rubles."""
        assert format_price(1500) == 15.0
        assert format_price(150050) == 1500.50
        assert format_price(0) == 0.0
        assert format_price(1) == 0.01


class TestFormatExecutionTime:
    """Test execution time formatting."""
    
    def test_format_execution_time_seconds(self):
        """Test formatting seconds."""
        assert format_execution_time(5.5) == "5.5 сек"
        assert format_execution_time(30.0) == "30.0 сек"
        assert format_execution_time(59.9) == "59.9 сек"
    
    def test_format_execution_time_minutes(self):
        """Test formatting minutes."""
        assert format_execution_time(60.0) == "1 мин 0.0 сек"
        assert format_execution_time(90.5) == "1 мин 30.5 сек"
        assert format_execution_time(125.0) == "2 мин 5.0 сек"
    
    def test_format_execution_time_hours(self):
        """Test formatting hours."""
        assert format_execution_time(3600.0) == "1 ч 0 мин"
        assert format_execution_time(3665.0) == "1 ч 1 мин"
        assert format_execution_time(7200.0) == "2 ч 0 мин"


class TestTruncateString:
    """Test string truncation."""
    
    def test_truncate_string_normal(self):
        """Test normal string truncation."""
        assert truncate_string("Hello World", 5) == "He..."
        assert truncate_string("Hello World", 10) == "Hello W..."
        assert truncate_string("Hello World", 15) == "Hello World"
    
    def test_truncate_string_edge_cases(self):
        """Test edge cases."""
        assert truncate_string("", 5) == ""
        assert truncate_string(None, 5) == ""
        assert truncate_string("Hi", 5) == "Hi"


class TestValidateKeyword:
    """Test keyword validation."""
    
    def test_validate_keyword_valid(self):
        """Test valid keywords."""
        valid_keywords = [
            "телефон",
            "iPhone 15",
            "ноутбук gaming",
            "a" * 100,  # max length
        ]
        
        for keyword in valid_keywords:
            assert validate_keyword(keyword) is True
    
    def test_validate_keyword_invalid(self):
        """Test invalid keywords."""
        invalid_keywords = [
            "",
            None,
            "a" * 101,  # too long
            "keyword<tag>",
            'keyword"quote',
            "keyword'quote",
            "keyword&symbol",
            "keyword\nnewline",
            "keyword\ttab",
        ]
        
        for keyword in invalid_keywords:
            assert validate_keyword(keyword) is False


class TestCleanKeyword:
    """Test keyword cleaning."""
    
    def test_clean_keyword_normal(self):
        """Test normal keyword cleaning."""
        assert clean_keyword("  hello world  ") == "hello world"
        assert clean_keyword("hello    world") == "hello world"
        assert clean_keyword("hello\n\tworld") == "hello world"
    
    def test_clean_keyword_edge_cases(self):
        """Test edge cases."""
        assert clean_keyword("") == ""
        assert clean_keyword(None) == ""
        assert clean_keyword("hello") == "hello"


class TestExtractFilenameFromUrl:
    """Test filename extraction from URL."""
    
    def test_extract_filename_valid(self):
        """Test extracting filename from valid URLs."""
        assert extract_filename_from_url("https://example.com/file.csv") == "file.csv"
        assert extract_filename_from_url("https://example.com/path/to/file.xlsx") == "file.xlsx"
        assert extract_filename_from_url("https://example.com/file") is None
    
    def test_extract_filename_invalid(self):
        """Test extracting filename from invalid URLs."""
        assert extract_filename_from_url("") is None
        assert extract_filename_from_url("not-a-url") is None
        assert extract_filename_from_url("https://example.com/") is None


class TestGoogleDriveUrl:
    """Test Google Drive URL functions."""
    
    def test_is_google_drive_url(self):
        """Test Google Drive URL detection."""
        valid_urls = [
            "https://drive.google.com/file/d/123456789/view",
            "https://drive.google.com/open?id=123456789",
        ]
        
        for url in valid_urls:
            assert is_google_drive_url(url) is True
        
        invalid_urls = [
            "https://example.com/file",
            "https://dropbox.com/file",
            "",
            None,
        ]
        
        for url in invalid_urls:
            assert is_google_drive_url(url) is False
    
    def test_convert_google_drive_url(self):
        """Test Google Drive URL conversion."""
        test_cases = [
            (
                "https://drive.google.com/file/d/123456789/view",
                "https://drive.google.com/uc?export=download&id=123456789"
            ),
            (
                "https://drive.google.com/open?id=123456789",
                "https://drive.google.com/uc?export=download&id=123456789"
            ),
        ]
        
        for input_url, expected_url in test_cases:
            assert convert_google_drive_url(input_url) == expected_url
        
        # Test invalid URLs
        assert convert_google_drive_url("https://example.com/file") is None
        assert convert_google_drive_url("") is None


class TestRetryWithBackoff:
    """Test retry with backoff function."""
    
    def test_retry_success_first_attempt(self):
        """Test successful retry on first attempt."""
        def success_func():
            return "success"
        
        result = retry_with_backoff(success_func)
        assert result == "success"
    
    def test_retry_success_after_failures(self):
        """Test successful retry after failures."""
        call_count = 0
        
        def failing_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Failed")
            return "success"
        
        with patch('time.sleep'):  # Mock sleep to speed up test
            result = retry_with_backoff(failing_then_success, max_attempts=3)
            assert result == "success"
            assert call_count == 3
    
    def test_retry_all_attempts_fail(self):
        """Test retry when all attempts fail."""
        def always_fail():
            raise ValueError("Always fails")
        
        with patch('time.sleep'):  # Mock sleep to speed up test
            with pytest.raises(ValueError, match="Always fails"):
                retry_with_backoff(always_fail, max_attempts=2)


class TestCreateProgressMessage:
    """Test progress message creation."""
    
    def test_create_progress_message(self):
        """Test creating progress messages."""
        assert create_progress_message(5, 10) == "Прогресс: 5/10 (50.0%)"
        assert create_progress_message(0, 10) == "Прогресс: 0/10 (0.0%)"
        assert create_progress_message(10, 10) == "Прогресс: 10/10 (100.0%)"
    
    def test_create_progress_message_with_text(self):
        """Test creating progress messages with additional text."""
        result = create_progress_message(5, 10, "Обработка")
        assert result == "Прогресс: 5/10 (50.0%) - Обработка"
    
    def test_create_progress_message_zero_total(self):
        """Test creating progress messages with zero total."""
        assert create_progress_message(0, 0) == "Прогресс: 0/0 (0.0%)"
