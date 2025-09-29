"""Tests for WB API adapter."""

import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
import aiohttp
from aiohttp import ClientError

from app.config import Settings
from app.ports import Product, SearchResult, Logger
from app.wb_adapter import WBAPIAdapter


class MockLogger:
    """Mock logger for testing."""
    
    def __init__(self):
        self.logs = []
    
    def info(self, message: str, **kwargs):
        self.logs.append(("info", message, kwargs))
    
    def warning(self, message: str, **kwargs):
        self.logs.append(("warning", message, kwargs))
    
    def error(self, message: str, **kwargs):
        self.logs.append(("error", message, kwargs))
    
    def debug(self, message: str, **kwargs):
        self.logs.append(("debug", message, kwargs))


@pytest.fixture
def settings():
    """Create test settings."""
    return Settings(
        bot_token="test_token",
        wb_api_base_url="https://test.wb.ru/api",
        wb_max_pages=3,
        wb_concurrency_limit=2,
        wb_request_timeout=10,
        wb_retry_attempts=2,
        wb_backoff_factor=1.5,
        wb_delay_between_requests=(0.01, 0.02)
    )


@pytest.fixture
def mock_logger():
    """Create mock logger."""
    return MockLogger()


@pytest.fixture
def mock_session():
    """Create mock aiohttp session."""
    session = AsyncMock(spec=aiohttp.ClientSession)
    return session


@pytest.fixture
def sample_api_response():
    """Sample API response data."""
    return {
        "data": {
            "products": [
                {
                    "id": 12345,
                    "name": "Test Product 1",
                    "salePriceU": 150000,  # 1500 rubles
                    "brand": "Test Brand",
                    "reviewRating": 4.5,
                    "feedbacks": 100
                },
                {
                    "id": 67890,
                    "name": "Test Product 2",
                    "salePriceU": 200000,  # 2000 rubles
                    "brand": "Test Brand 2",
                    "reviewRating": 4.2,
                    "feedbacks": 50
                }
            ]
        }
    }


class TestWBAPIAdapter:
    """Test WBAPIAdapter class."""
    
    @pytest.mark.asyncio
    async def test_context_manager(self, settings, mock_logger):
        """Test async context manager."""
        async with WBAPIAdapter(settings, mock_logger) as adapter:
            assert adapter.session is not None
            assert adapter._session_owner is True
        
        # Session should be closed after context exit
        assert adapter.session.closed
    
    @pytest.mark.asyncio
    async def test_search_product_found(self, settings, mock_logger, mock_session, sample_api_response):
        """Test successful product search."""
        # Mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=sample_api_response)
        
        mock_session.get.return_value.__aenter__.return_value = mock_response
        
        adapter = WBAPIAdapter(settings, mock_logger, mock_session)
        
        result = await adapter.search_product("test keyword", 12345, 1)
        
        assert isinstance(result, SearchResult)
        assert result.keyword == "test keyword"
        assert result.product is not None
        assert result.product.id == 12345
        assert result.position == 1
        assert result.page == 1
        assert result.total_pages_searched == 1
        assert result.error is None
    
    @pytest.mark.asyncio
    async def test_search_product_not_found(self, settings, mock_logger, mock_session, sample_api_response):
        """Test product not found."""
        # Mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=sample_api_response)
        
        mock_session.get.return_value.__aenter__.return_value = mock_response
        
        adapter = WBAPIAdapter(settings, mock_logger, mock_session)
        
        result = await adapter.search_product("test keyword", 99999, 1)
        
        assert isinstance(result, SearchResult)
        assert result.keyword == "test keyword"
        assert result.product is None
        assert result.position is None
        assert result.page is None
        assert result.total_pages_searched == 1
        assert result.error is None
    
    @pytest.mark.asyncio
    async def test_search_multiple_pages(self, settings, mock_logger, mock_session):
        """Test search across multiple pages."""
        # Mock response with product on page 2
        page1_response = {
            "data": {
                "products": [
                    {"id": 1, "name": "Product 1", "salePriceU": 100000, "brand": "Brand", "reviewRating": 4.0, "feedbacks": 10}
                ]
            }
        }
        
        page2_response = {
            "data": {
                "products": [
                    {"id": 2, "name": "Product 2", "salePriceU": 200000, "brand": "Brand", "reviewRating": 4.0, "feedbacks": 10}
                ]
            }
        }
        
        # Create context managers
        cm1 = AsyncMock()
        cm1.__aenter__ = AsyncMock(return_value=AsyncMock(status=200, json=AsyncMock(return_value=page1_response)))
        cm1.__aexit__ = AsyncMock(return_value=None)
        
        cm2 = AsyncMock()
        cm2.__aenter__ = AsyncMock(return_value=AsyncMock(status=200, json=AsyncMock(return_value=page2_response)))
        cm2.__aexit__ = AsyncMock(return_value=None)
        
        mock_session.get.side_effect = [cm1, cm2]
        
        adapter = WBAPIAdapter(settings, mock_logger, mock_session)
        
        result = await adapter.search_product("test keyword", 2, 2)
        
        assert result.product.id == 2
        assert result.position == 101  # Page 2, index 0 = position 101
        assert result.page == 2
        assert result.total_pages_searched == 2
    
    @pytest.mark.asyncio
    async def test_rate_limit_handling(self, settings, mock_logger, mock_session):
        """Test rate limit handling."""
        # First response: rate limit
        rate_limit_response = AsyncMock()
        rate_limit_response.status = 429
        rate_limit_response.headers = {"Retry-After": "1"}
        
        # Second response: success
        success_response = AsyncMock()
        success_response.status = 200
        success_response.json = AsyncMock(return_value={
            "data": {
                "products": [
                    {"id": 12345, "name": "Test", "salePriceU": 100000, "brand": "Brand", "reviewRating": 4.0, "feedbacks": 10}
                ]
            }
        })
        
        # Create context managers for both responses
        rate_limit_cm = AsyncMock()
        rate_limit_cm.__aenter__ = AsyncMock(return_value=rate_limit_response)
        rate_limit_cm.__aexit__ = AsyncMock(return_value=None)
        
        success_cm = AsyncMock()
        success_cm.__aenter__ = AsyncMock(return_value=success_response)
        success_cm.__aexit__ = AsyncMock(return_value=None)
        
        mock_session.get.side_effect = [rate_limit_cm, success_cm]
        
        adapter = WBAPIAdapter(settings, mock_logger, mock_session)
        
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            result = await adapter.search_product("test keyword", 12345, 1)
            
            # Should have slept for rate limit
            mock_sleep.assert_called_with(1)
            
            assert result.product.id == 12345
    
    @pytest.mark.asyncio
    async def test_server_error_retry(self, settings, mock_logger, mock_session):
        """Test server error retry."""
        # First response: server error
        error_response = AsyncMock()
        error_response.status = 500
        
        # Second response: success
        success_response = AsyncMock()
        success_response.status = 200
        success_response.json = AsyncMock(return_value={
            "data": {
                "products": [
                    {"id": 12345, "name": "Test", "salePriceU": 100000, "brand": "Brand", "reviewRating": 4.0, "feedbacks": 10}
                ]
            }
        })
        
        # Create context managers for both responses
        error_cm = AsyncMock()
        error_cm.__aenter__ = AsyncMock(return_value=error_response)
        error_cm.__aexit__ = AsyncMock(return_value=None)
        
        success_cm = AsyncMock()
        success_cm.__aenter__ = AsyncMock(return_value=success_response)
        success_cm.__aexit__ = AsyncMock(return_value=None)
        
        mock_session.get.side_effect = [error_cm, success_cm]
        
        adapter = WBAPIAdapter(settings, mock_logger, mock_session)
        
        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await adapter.search_product("test keyword", 12345, 1)
            
            assert result.product.id == 12345
    
    @pytest.mark.asyncio
    async def test_all_retries_fail(self, settings, mock_logger, mock_session):
        """Test when all retry attempts fail."""
        # All responses: server error
        error_response = AsyncMock()
        error_response.status = 500
        
        mock_session.get.return_value.__aenter__.return_value = error_response
        
        adapter = WBAPIAdapter(settings, mock_logger, mock_session)
        
        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await adapter.search_product("test keyword", 12345, 1)
            
            assert result.product is None
            assert result.error is not None
            assert "API error after" in result.error
    
    @pytest.mark.asyncio
    async def test_concurrency_limit(self, settings, mock_logger, mock_session):
        """Test concurrency limiting."""
        adapter = WBAPIAdapter(settings, mock_logger, mock_session)
        
        assert adapter._semaphore._value == settings.wb_concurrency_limit
    
    @pytest.mark.asyncio
    async def test_health_check_success(self, settings, mock_logger, mock_session):
        """Test successful health check."""
        mock_response = AsyncMock()
        mock_response.status = 200
        
        mock_session.get.return_value.__aenter__.return_value = mock_response
        
        adapter = WBAPIAdapter(settings, mock_logger, mock_session)
        
        result = await adapter.health_check()
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_health_check_failure(self, settings, mock_logger, mock_session):
        """Test failed health check."""
        mock_response = AsyncMock()
        mock_response.status = 500
        
        mock_session.get.return_value.__aenter__.return_value = mock_response
        
        adapter = WBAPIAdapter(settings, mock_logger, mock_session)
        
        result = await adapter.health_check()
        
        assert result is False
    
    def test_get_stats(self, settings, mock_logger):
        """Test getting adapter statistics."""
        adapter = WBAPIAdapter(settings, mock_logger)
        
        stats = adapter.get_stats()
        
        assert stats["concurrency_limit"] == settings.wb_concurrency_limit
        assert stats["retry_attempts"] == settings.wb_retry_attempts
        assert stats["request_timeout"] == settings.wb_request_timeout
        assert stats["max_pages"] == settings.wb_max_pages
    
    def test_build_search_url(self, settings, mock_logger):
        """Test URL building."""
        adapter = WBAPIAdapter(settings, mock_logger)
        
        url = adapter._build_search_url("test keyword", 2)
        
        assert "query=test+keyword" in url
        assert "page=2" in url
        assert "resultset=catalog" in url
        assert "sort=popular" in url
        assert "curr=rub" in url
        assert "lang=ru" in url
        assert "locale=ru" in url
    
    def test_parse_products(self, settings, mock_logger, sample_api_response):
        """Test product parsing."""
        adapter = WBAPIAdapter(settings, mock_logger)
        
        products = adapter._parse_products(sample_api_response)
        
        assert len(products) == 2
        
        product1 = products[0]
        assert product1.id == 12345
        assert product1.name == "Test Product 1"
        assert product1.price_rub == 1500.0
        assert product1.brand == "Test Brand"
        assert product1.rating == 4.5
        assert product1.feedbacks == 100
        
        product2 = products[1]
        assert product2.id == 67890
        assert product2.name == "Test Product 2"
        assert product2.price_rub == 2000.0
        assert product2.brand == "Test Brand 2"
        assert product2.rating == 4.2
        assert product2.feedbacks == 50
