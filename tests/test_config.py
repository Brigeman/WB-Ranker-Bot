"""Tests for configuration module."""

import pytest
from pydantic import ValidationError

from app.config import Settings


class TestSettings:
    """Test Settings class."""
    
    def test_default_settings(self):
        """Test default settings values."""
        settings = Settings(bot_token="test_token")
        
        assert settings.bot_token == "test_token"
        assert settings.wb_max_pages == 5
        assert settings.wb_concurrency_limit == 5
        assert settings.wb_request_timeout == 15
        assert settings.wb_retry_attempts == 3
        assert settings.wb_backoff_factor == 2.0
        assert settings.wb_delay_between_requests == (0.05, 0.2)
        assert settings.max_keywords_limit == 1000
        assert settings.max_execution_time_minutes == 30
        assert settings.log_level == "INFO"
        assert settings.log_format == "json"
        assert settings.output_directory == "output"
    
    def test_log_level_validation(self):
        """Test log level validation."""
        # Valid levels
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            settings = Settings(bot_token="test", log_level=level)
            assert settings.log_level == level
        
        # Case insensitive
        settings = Settings(bot_token="test", log_level="info")
        assert settings.log_level == "INFO"
        
        # Invalid level
        with pytest.raises(ValidationError):
            Settings(bot_token="test", log_level="INVALID")
    
    def test_log_format_validation(self):
        """Test log format validation."""
        # Valid formats
        for fmt in ["json", "text"]:
            settings = Settings(bot_token="test", log_format=fmt)
            assert settings.log_format == fmt
        
        # Case insensitive
        settings = Settings(bot_token="test", log_format="JSON")
        assert settings.log_format == "json"
        
        # Invalid format
        with pytest.raises(ValidationError):
            Settings(bot_token="test", log_format="invalid")
    
    def test_delay_range_validation(self):
        """Test delay range validation."""
        # Valid range
        settings = Settings(bot_token="test", wb_delay_between_requests=(0.1, 0.5))
        assert settings.wb_delay_between_requests == (0.1, 0.5)
        
        # Min >= Max
        with pytest.raises(ValidationError):
            Settings(bot_token="test", wb_delay_between_requests=(0.5, 0.1))
        
        # Negative values
        with pytest.raises(ValidationError):
            Settings(bot_token="test", wb_delay_between_requests=(-0.1, 0.5))
    
    def test_numeric_constraints(self):
        """Test numeric field constraints."""
        # Valid values
        settings = Settings(
            bot_token="test",
            wb_max_pages=3,
            wb_concurrency_limit=10,
            wb_request_timeout=30,
            wb_retry_attempts=5,
            wb_backoff_factor=1.5,
            max_keywords_limit=500,
            max_execution_time_minutes=15
        )
        
        assert settings.wb_max_pages == 3
        assert settings.wb_concurrency_limit == 10
        assert settings.wb_request_timeout == 30
        assert settings.wb_retry_attempts == 5
        assert settings.wb_backoff_factor == 1.5
        assert settings.max_keywords_limit == 500
        assert settings.max_execution_time_minutes == 15
        
        # Invalid values (out of range)
        with pytest.raises(ValidationError):
            Settings(bot_token="test", wb_max_pages=0)  # Below minimum
        
        with pytest.raises(ValidationError):
            Settings(bot_token="test", wb_max_pages=15)  # Above maximum
        
        with pytest.raises(ValidationError):
            Settings(bot_token="test", wb_concurrency_limit=0)  # Below minimum
        
        with pytest.raises(ValidationError):
            Settings(bot_token="test", wb_concurrency_limit=25)  # Above maximum
    
    def test_required_fields(self):
        """Test required fields."""
        # Missing bot_token
        with pytest.raises(ValidationError):
            Settings()
        
        # Valid with required field
        settings = Settings(bot_token="test_token")
        assert settings.bot_token == "test_token"
