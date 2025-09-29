"""Tests for services module."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from app.config import Settings
from app.ports import (
    Logger, ProgressTracker, SearchClient, FileLoader, FileExporter,
    Product, SearchResult, RankingResult
)
from app.services import RankingServiceImpl


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


class MockProgressTracker:
    """Mock progress tracker for testing."""
    
    def __init__(self):
        self.messages = []
        self.progress_updates = []
        self.errors = []
        self.successes = []
    
    def update_progress(self, current: int, total: int, message: str = None, eta: str = None):
        self.progress_updates.append({
            "current": current,
            "total": total,
            "message": message,
            "eta": eta
        })
    
    def send_message(self, message: str):
        self.messages.append(message)
    
    def send_error(self, error_message: str):
        self.errors.append(error_message)
    
    def send_success(self, success_message: str):
        self.successes.append(success_message)


class MockSearchClient:
    """Mock search client for testing."""
    
    def __init__(self):
        self.search_results = {}
        self.health_check_result = True
    
    async def search_product(self, keyword: str, product_id: int, max_pages: int):
        """Mock search product method."""
        if keyword in self.search_results:
            return self.search_results[keyword]
        
        # Default mock result
        return SearchResult(
            keyword=keyword,
            product=None,
            position=None,
            page=None,
            total_pages_searched=1
        )
    
    async def health_check(self):
        return self.health_check_result


class MockFileLoader:
    """Mock file loader for testing."""
    
    def __init__(self):
        self.keywords = ["keyword1", "keyword2", "keyword3"]
        self.load_error = None
    
    async def load_keywords_from_file(self, file_path: str):
        if self.load_error:
            raise self.load_error
        return self.keywords
    
    async def load_keywords_from_url(self, url: str):
        if self.load_error:
            raise self.load_error
        return self.keywords
    
    def validate_keywords_count(self, keywords):
        return len(keywords) <= 1000


class MockFileExporter:
    """Mock file exporter for testing."""
    
    def __init__(self):
        self.exported_files = []
        self.export_error = None
    
    async def export_to_csv(self, result, file_path: str):
        if self.export_error:
            raise self.export_error
        self.exported_files.append(("csv", file_path, result))
        return file_path
    
    async def export_to_xlsx(self, result, file_path: str):
        if self.export_error:
            raise self.export_error
        self.exported_files.append(("xlsx", file_path, result))
        return file_path
    
    def generate_filename(self, product_id: int, format_type: str = "csv"):
        return f"test_ranking_{product_id}.{format_type}"
    
    def get_export_path(self, filename: str):
        return f"output/{filename}"


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
def mock_logger():
    """Create mock logger."""
    return MockLogger()


@pytest.fixture
def mock_progress_tracker():
    """Create mock progress tracker."""
    return MockProgressTracker()


@pytest.fixture
def mock_search_client():
    """Create mock search client."""
    return MockSearchClient()


@pytest.fixture
def mock_file_loader():
    """Create mock file loader."""
    return MockFileLoader()


@pytest.fixture
def mock_file_exporter():
    """Create mock file exporter."""
    return MockFileExporter()


@pytest.fixture
def sample_product():
    """Create sample product."""
    return Product(
        id=12345,
        name="Test Product",
        price_rub=1500.50,
        brand="Test Brand",
        rating=4.5,
        feedbacks=100
    )


@pytest.fixture
def ranking_service(
    settings, mock_logger, mock_progress_tracker, 
    mock_search_client, mock_file_loader, mock_file_exporter
):
    """Create ranking service with mocked dependencies."""
    return RankingServiceImpl(
        settings=settings,
        search_client=mock_search_client,
        file_loader=mock_file_loader,
        file_exporter=mock_file_exporter,
        logger=mock_logger,
        progress_tracker=mock_progress_tracker
    )


class TestRankingServiceImpl:
    """Test RankingServiceImpl class."""
    
    @pytest.mark.asyncio
    async def test_rank_product_by_keywords_success(
        self, ranking_service, mock_search_client, sample_product
    ):
        """Test successful ranking process."""
        # Setup mock search results
        mock_search_client.search_results = {
            "keyword1": SearchResult(
                keyword="keyword1",
                product=sample_product,
                position=5,
                page=1,
                total_pages_searched=2
            ),
            "keyword2": SearchResult(
                keyword="keyword2",
                product=sample_product,
                position=15,
                page=2,
                total_pages_searched=2
            ),
            "keyword3": SearchResult(
                keyword="keyword3",
                product=None,
                position=None,
                page=None,
                total_pages_searched=2
            )
        }
        
        # Run ranking
        result = await ranking_service.rank_product_by_keywords(
            product_url="https://wildberries.ru/catalog/12345/detail.aspx",
            keywords_source="test_keywords.csv",
            output_format="xlsx"
        )
        
        # Verify result
        assert result.product_id == 12345
        assert result.product_name == "Product 12345"  # From mock fallback
        assert result.total_keywords == 3
        assert result.found_keywords == 2
        assert len(result.results) == 3
        assert result.execution_time_seconds > 0
        
        # Verify statistics
        stats = ranking_service.get_statistics()
        assert stats["total_keywords_processed"] == 3
        assert stats["successful_searches"] == 2
        assert stats["failed_searches"] == 1
        assert stats["average_position"] == 10.0  # (5 + 15) / 2
        assert stats["best_position"] == 5
        assert stats["worst_position"] == 15
    
    @pytest.mark.asyncio
    async def test_rank_product_by_keywords_with_url_source(
        self, ranking_service, mock_search_client, sample_product
    ):
        """Test ranking with URL keywords source."""
        # Setup mock search results
        mock_search_client.search_results = {
            "keyword1": SearchResult(
                keyword="keyword1",
                product=sample_product,
                position=5,
                page=1,
                total_pages_searched=1
            )
        }
        
        # Run ranking with URL source
        result = await ranking_service.rank_product_by_keywords(
            product_url="https://wildberries.ru/catalog/12345/detail.aspx",
            keywords_source="https://example.com/keywords.csv",
            output_format="csv"
        )
        
        # Verify result
        assert result.product_id == 12345
        assert result.total_keywords == 3  # From mock file loader
        assert result.found_keywords == 1
    
    @pytest.mark.asyncio
    async def test_rank_product_by_keywords_invalid_url(
        self, ranking_service
    ):
        """Test ranking with invalid product URL."""
        with pytest.raises(RuntimeError, match="Ranking process failed"):
            await ranking_service.rank_product_by_keywords(
                product_url="https://invalid-url.com/product",
                keywords_source="test_keywords.csv"
            )
    
    @pytest.mark.asyncio
    async def test_rank_product_by_keywords_load_error(
        self, ranking_service, mock_file_loader
    ):
        """Test ranking with file load error."""
        mock_file_loader.load_error = ValueError("File not found")
        
        with pytest.raises(RuntimeError, match="Ranking process failed"):
            await ranking_service.rank_product_by_keywords(
                product_url="https://wildberries.ru/catalog/12345/detail.aspx",
                keywords_source="nonexistent.csv"
            )
    
    @pytest.mark.asyncio
    async def test_rank_product_by_keywords_too_many_keywords(
        self, ranking_service, mock_file_loader
    ):
        """Test ranking with too many keywords."""
        # Set up mock to return too many keywords
        mock_file_loader.keywords = ["keyword"] * 1500
        
        with pytest.raises(RuntimeError, match="Ranking process failed"):
            await ranking_service.rank_product_by_keywords(
                product_url="https://wildberries.ru/catalog/12345/detail.aspx",
                keywords_source="test_keywords.csv"
            )
    
    @pytest.mark.asyncio
    async def test_rank_product_by_keywords_export_error(
        self, ranking_service, mock_file_exporter, sample_product
    ):
        """Test ranking with export error."""
        # Setup mock search results
        mock_search_client = ranking_service.search_client
        mock_search_client.search_results = {
            "keyword1": SearchResult(
                keyword="keyword1",
                product=sample_product,
                position=5,
                page=1,
                total_pages_searched=1
            )
        }
        
        # Setup export error
        mock_file_exporter.export_error = ValueError("Export failed")
        
        with pytest.raises(RuntimeError, match="Ranking process failed"):
            await ranking_service.rank_product_by_keywords(
                product_url="https://wildberries.ru/catalog/12345/detail.aspx",
                keywords_source="test_keywords.csv"
            )
    
    @pytest.mark.asyncio
    async def test_progress_tracking(
        self, ranking_service, mock_progress_tracker, sample_product
    ):
        """Test progress tracking during ranking."""
        # Setup mock search results
        mock_search_client = ranking_service.search_client
        mock_search_client.search_results = {
            "keyword1": SearchResult(
                keyword="keyword1",
                product=sample_product,
                position=5,
                page=1,
                total_pages_searched=1
            ),
            "keyword2": SearchResult(
                keyword="keyword2",
                product=sample_product,
                position=10,
                page=1,
                total_pages_searched=1
            ),
            "keyword3": SearchResult(
                keyword="keyword3",
                product=None,
                position=None,
                page=None,
                total_pages_searched=1
            )
        }
        
        # Run ranking
        await ranking_service.rank_product_by_keywords(
            product_url="https://wildberries.ru/catalog/12345/detail.aspx",
            keywords_source="test_keywords.csv"
        )
        
        # Verify progress tracking
        assert len(mock_progress_tracker.messages) > 0
        assert len(mock_progress_tracker.progress_updates) == 3
        assert len(mock_progress_tracker.successes) > 0
        
        # Check that progress updates have correct values
        for update in mock_progress_tracker.progress_updates:
            assert update["current"] <= update["total"]
            assert update["total"] == 3
    
    @pytest.mark.asyncio
    async def test_statistics_calculation(
        self, ranking_service, sample_product
    ):
        """Test statistics calculation."""
        # Setup mock search results with known positions
        mock_search_client = ranking_service.search_client
        mock_search_client.search_results = {
            "keyword1": SearchResult(
                keyword="keyword1",
                product=sample_product,
                position=5,
                page=1,
                total_pages_searched=1
            ),
            "keyword2": SearchResult(
                keyword="keyword2",
                product=sample_product,
                position=15,
                page=2,
                total_pages_searched=2
            ),
            "keyword3": SearchResult(
                keyword="keyword3",
                product=sample_product,
                position=25,
                page=3,
                total_pages_searched=3
            )
        }
        
        # Run ranking
        await ranking_service.rank_product_by_keywords(
            product_url="https://wildberries.ru/catalog/12345/detail.aspx",
            keywords_source="test_keywords.csv"
        )
        
        # Verify statistics
        stats = ranking_service.get_statistics()
        assert stats["total_keywords_processed"] == 3
        assert stats["successful_searches"] == 3
        assert stats["failed_searches"] == 0
        assert stats["average_position"] == 15.0  # (5 + 15 + 25) / 3
        assert stats["best_position"] == 5
        assert stats["worst_position"] == 25
    
    def test_reset_statistics(self, ranking_service):
        """Test statistics reset."""
        # Set some statistics
        ranking_service._stats["total_keywords_processed"] = 10
        ranking_service._stats["successful_searches"] = 8
        
        # Reset statistics
        ranking_service.reset_statistics()
        
        # Verify reset
        stats = ranking_service.get_statistics()
        assert stats["total_keywords_processed"] == 0
        assert stats["successful_searches"] == 0
        assert stats["failed_searches"] == 0
    
    @pytest.mark.asyncio
    async def test_health_check_success(self, ranking_service):
        """Test successful health check."""
        result = await ranking_service.health_check()
        assert result is True
    
    @pytest.mark.asyncio
    async def test_health_check_failure(self, ranking_service, mock_search_client):
        """Test failed health check."""
        mock_search_client.health_check_result = False
        
        result = await ranking_service.health_check()
        assert result is False
    
    @pytest.mark.asyncio
    async def test_calculate_eta(self, ranking_service):
        """Test ETA calculation."""
        # Test with current = 0
        eta = ranking_service._calculate_eta(0, 10)
        assert eta == "calculating..."
        
        # Test with small remaining time
        eta = ranking_service._calculate_eta(5, 10)
        assert eta.endswith("s")
        
        # Test with medium remaining time
        eta = ranking_service._calculate_eta(1, 100)
        assert eta.endswith("m")
        
        # Test with large remaining time
        eta = ranking_service._calculate_eta(1, 2000)
        assert "h" in eta and "m" in eta
