"""Configuration module for WB Ranker Bot."""

from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with validation."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        validate_assignment=True,
    )
    
    # Telegram Bot Configuration
    bot_token: str = Field(..., description="Telegram bot token")
    
    # WB API Configuration
    wb_api_base_url: str = Field(
        default="https://search.wb.ru/exactmatch/ru/common/v4/search",
        description="Wildberries API base URL"
    )
    wb_max_pages: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum pages to search per keyword"
    )
    wb_concurrency_limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum concurrent requests to WB API"
    )
    wb_request_timeout: int = Field(
        default=15,
        ge=5,
        le=60,
        description="Request timeout in seconds"
    )
    wb_retry_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of retry attempts for failed requests"
    )
    wb_backoff_factor: float = Field(
        default=2.0,
        ge=1.0,
        le=5.0,
        description="Exponential backoff factor for retries"
    )
    wb_delay_between_requests: tuple[float, float] = Field(
        default=(0.05, 0.2),
        description="Delay range between requests in seconds (min, max)"
    )
    
    # File Processing Configuration
    max_keywords_limit: int = Field(
        default=1000,
        ge=1,
        le=10000,
        description="Maximum number of keywords to process"
    )
    max_execution_time_minutes: int = Field(
        default=30,
        ge=1,
        le=120,
        description="Maximum execution time in minutes"
    )
    
    # Logging Configuration
    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )
    log_format: str = Field(
        default="json",
        description="Log format (json or text)"
    )
    
    # Output Configuration
    output_directory: str = Field(
        default="output",
        description="Directory for output files"
    )
    
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v.upper()
    
    @field_validator("log_format")
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        """Validate log format."""
        valid_formats = {"json", "text"}
        if v.lower() not in valid_formats:
            raise ValueError(f"Log format must be one of {valid_formats}")
        return v.lower()
    
    @field_validator("wb_delay_between_requests")
    @classmethod
    def validate_delay_range(cls, v: tuple[float, float]) -> tuple[float, float]:
        """Validate delay range."""
        min_delay, max_delay = v
        if min_delay >= max_delay:
            raise ValueError("Min delay must be less than max delay")
        if min_delay < 0 or max_delay < 0:
            raise ValueError("Delays must be non-negative")
        return v


def get_settings() -> Settings:
    """Get application settings instance."""
    return Settings()