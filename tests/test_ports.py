"""Tests for ports (interfaces) module."""

import pytest
from unittest.mock import Mock

from app.ports import (
    Product,
    SearchResult,
    RankingResult,
    SearchClient,
    FileLoader,
    FileExporter,
    Logger,
    RankingService,
    URLParser,
    ProgressTracker,
)


class TestModels:
    """Test Pydantic models."""
    
    def test_product_model(self):
        """Test Product model."""
        product = Product(
            id=12345,
            name="Test Product",
            price_rub=1500.50,
            brand="Test Brand",
            rating=4.5,
            feedbacks=100
        )
        
        assert product.id == 12345
        assert product.name == "Test Product"
        assert product.price_rub == 1500.50
        assert product.brand == "Test Brand"
        assert product.rating == 4.5
        assert product.feedbacks == 100
    
    def test_search_result_model(self):
        """Test SearchResult model."""
        product = Product(
            id=12345,
            name="Test Product",
            price_rub=1500.50,
            brand="Test Brand",
            rating=4.5,
            feedbacks=100
        )
        
        result = SearchResult(
            keyword="test keyword",
            product=product,
            position=5,
            page=1,
            total_pages_searched=3
        )
        
        assert result.keyword == "test keyword"
        assert result.product == product
        assert result.position == 5
        assert result.page == 1
        assert result.total_pages_searched == 3
        assert result.error is None
    
    def test_search_result_not_found(self):
        """Test SearchResult when product not found."""
        result = SearchResult(
            keyword="test keyword",
            product=None,
            position=None,
            page=None,
            total_pages_searched=5
        )
        
        assert result.keyword == "test keyword"
        assert result.product is None
        assert result.position is None
        assert result.page is None
        assert result.total_pages_searched == 5
    
    def test_ranking_result_model(self):
        """Test RankingResult model."""
        product = Product(
            id=12345,
            name="Test Product",
            price_rub=1500.50,
            brand="Test Brand",
            rating=4.5,
            feedbacks=100
        )
        
        search_result = SearchResult(
            keyword="test keyword",
            product=product,
            position=5,
            page=1,
            total_pages_searched=3
        )
        
        ranking_result = RankingResult(
            product_id=12345,
            product_name="Test Product",
            results=[search_result],
            total_keywords=1,
            found_keywords=1,
            execution_time_seconds=10.5
        )
        
        assert ranking_result.product_id == 12345
        assert ranking_result.product_name == "Test Product"
        assert len(ranking_result.results) == 1
        assert ranking_result.total_keywords == 1
        assert ranking_result.found_keywords == 1
        assert ranking_result.execution_time_seconds == 10.5


class TestProtocols:
    """Test Protocol implementations."""
    
    def test_search_client_protocol(self):
        """Test SearchClient protocol compliance."""
        
        class MockSearchClient:
            async def search_product(self, keyword: str, product_id: int, max_pages: int = 5):
                return SearchResult(
                    keyword=keyword,
                    product=None,
                    position=None,
                    page=None,
                    total_pages_searched=max_pages
                )
        
        client = MockSearchClient()
        assert isinstance(client, SearchClient)
    
    def test_file_loader_protocol(self):
        """Test FileLoader protocol compliance."""
        
        class MockFileLoader:
            async def load_keywords_from_file(self, file_path: str):
                return ["keyword1", "keyword2"]
            
            async def load_keywords_from_url(self, url: str):
                return ["keyword1", "keyword2"]
        
        loader = MockFileLoader()
        assert isinstance(loader, FileLoader)
    
    def test_file_exporter_protocol(self):
        """Test FileExporter protocol compliance."""
        
        class MockFileExporter:
            async def export_to_csv(self, result: RankingResult, file_path: str):
                return file_path
            
            async def export_to_xlsx(self, result: RankingResult, file_path: str):
                return file_path
        
        exporter = MockFileExporter()
        assert isinstance(exporter, FileExporter)
    
    def test_logger_protocol(self):
        """Test Logger protocol compliance."""
        
        class MockLogger:
            def info(self, message: str, **kwargs):
                pass
            
            def warning(self, message: str, **kwargs):
                pass
            
            def error(self, message: str, **kwargs):
                pass
            
            def debug(self, message: str, **kwargs):
                pass
        
        logger = MockLogger()
        assert isinstance(logger, Logger)
    
    def test_progress_tracker_protocol(self):
        """Test ProgressTracker protocol compliance."""
        
        class MockProgressTracker:
            def update_progress(self, current: int, total: int, message: str = ""):
                pass
            
            def complete(self, message: str = ""):
                pass
            
            def error(self, message: str):
                pass
        
        tracker = MockProgressTracker()
        assert isinstance(tracker, ProgressTracker)


class TestAbstractClasses:
    """Test abstract classes."""
    
    def test_ranking_service_abstract(self):
        """Test RankingService is abstract."""
        with pytest.raises(TypeError):
            RankingService(Mock(), Mock())
    
    def test_url_parser_abstract(self):
        """Test URLParser is abstract."""
        with pytest.raises(TypeError):
            URLParser()
    
    def test_concrete_ranking_service(self):
        """Test concrete RankingService implementation."""
        
        class ConcreteRankingService(RankingService):
            async def rank_product(self, product_url: str, keywords: list, max_pages: int = 5, max_execution_time_minutes: int = 30):
                return RankingResult(
                    product_id=12345,
                    product_name="Test Product",
                    results=[],
                    total_keywords=0,
                    found_keywords=0,
                    execution_time_seconds=0.0
                )
        
        service = ConcreteRankingService(Mock(), Mock())
        assert isinstance(service, RankingService)
    
    def test_concrete_url_parser(self):
        """Test concrete URLParser implementation."""
        
        class ConcreteURLParser(URLParser):
            def extract_product_id(self, url: str) -> int:
                return 12345
            
            def validate_wb_url(self, url: str) -> bool:
                return True
        
        parser = ConcreteURLParser()
        assert isinstance(parser, URLParser)
        assert parser.extract_product_id("test") == 12345
        assert parser.validate_wb_url("test") is True
