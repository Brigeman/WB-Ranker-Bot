"""Tests for exporter module."""

import csv
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from app.config import Settings
from app.exporter import FileExporterImpl
from app.ports import Logger, Product, RankingResult, SearchResult


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
        output_directory="test_output"
    )


@pytest.fixture
def mock_logger():
    """Create mock logger."""
    return MockLogger()


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
def sample_ranking_result(sample_product):
    """Create sample ranking result."""
    search_results = [
        SearchResult(
            keyword="keyword1",
            product=sample_product,
            position=5,
            page=1,
            total_pages_searched=3
        ),
        SearchResult(
            keyword="keyword2",
            product=sample_product,
            position=15,
            page=2,
            total_pages_searched=3
        ),
        SearchResult(
            keyword="keyword3",
            product=None,
            position=None,
            page=None,
            total_pages_searched=3
        )
    ]
    
    return RankingResult(
        product_id=12345,
        product_name="Test Product",
        results=search_results,
        total_keywords=3,
        found_keywords=2,
        execution_time_seconds=10.5
    )


class TestFileExporterImpl:
    """Test FileExporterImpl class."""
    
    @pytest.mark.asyncio
    async def test_export_to_csv(self, settings, mock_logger, sample_ranking_result):
        """Test CSV export."""
        exporter = FileExporterImpl(settings, mock_logger)
        
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as f:
            temp_file = f.name
        
        try:
            result_path = await exporter.export_to_csv(sample_ranking_result, temp_file)
            
            assert result_path == temp_file
            assert os.path.exists(temp_file)
            
            # Verify CSV content
            with open(temp_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                rows = list(reader)
            
            # Check header
            assert rows[0] == [
                'Номер строки',
                'Ключевое слово',
                'Частотность',
                'Позиция товара',
                'Цена товара',
                'Страница',
                'Статус'
            ]
            
            # Check data rows
            assert len(rows) == 4  # Header + 3 data rows
            
            # Check first result (found)
            assert rows[1][1] == 'keyword1'  # keyword
            assert rows[1][2] == 'Найден'   # frequency
            assert rows[1][3] == '5'         # position
            assert rows[1][4] == '1500.50 ₽'  # price
            assert rows[1][5] == '1'         # page
            assert rows[1][6] == 'Найден'   # status
            
            # Check third result (not found)
            assert rows[3][1] == 'keyword3'  # keyword
            assert rows[3][2] == 'Не найден'  # frequency
            assert rows[3][3] == '-'          # position
            assert rows[3][4] == '-'          # price
            assert rows[3][5] == '-'          # page
            assert rows[3][6] == 'Не найден'  # status
            
        finally:
            os.unlink(temp_file)
    
    @pytest.mark.asyncio
    async def test_export_to_xlsx(self, settings, mock_logger, sample_ranking_result):
        """Test XLSX export."""
        exporter = FileExporterImpl(settings, mock_logger)
        
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f:
            temp_file = f.name
        
        try:
            result_path = await exporter.export_to_xlsx(sample_ranking_result, temp_file)
            
            assert result_path == temp_file
            assert os.path.exists(temp_file)
            
            # Verify Excel content
            with pd.ExcelFile(temp_file) as xls:
                # Check sheet names
                assert 'Результаты поиска' in xls.sheet_names
                assert 'Сводка' in xls.sheet_names
                assert 'Статистика' in xls.sheet_names
                
                # Check results sheet
                df_results = pd.read_excel(xls, 'Результаты поиска')
                assert len(df_results) == 3
                assert 'Ключевое слово' in df_results.columns
                assert 'Позиция товара' in df_results.columns
                
                # Check summary sheet
                df_summary = pd.read_excel(xls, 'Сводка')
                assert len(df_summary) == 7  # Number of summary fields
                assert 'Параметр' in df_summary.columns
                assert 'Значение' in df_summary.columns
                
                # Check statistics sheet
                df_stats = pd.read_excel(xls, 'Статистика')
                assert 'Метрика' in df_stats.columns
                assert 'Значение' in df_stats.columns
            
        finally:
            os.unlink(temp_file)
    
    @pytest.mark.asyncio
    async def test_export_to_csv_with_errors(self, settings, mock_logger):
        """Test CSV export with error results."""
        # Create result with error
        error_result = SearchResult(
            keyword="error_keyword",
            product=None,
            position=None,
            page=None,
            total_pages_searched=1,
            error="API timeout"
        )
        
        ranking_result = RankingResult(
            product_id=12345,
            product_name="Test Product",
            results=[error_result],
            total_keywords=1,
            found_keywords=0,
            execution_time_seconds=5.0
        )
        
        exporter = FileExporterImpl(settings, mock_logger)
        
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as f:
            temp_file = f.name
        
        try:
            await exporter.export_to_csv(ranking_result, temp_file)
            
            # Verify error handling in CSV
            with open(temp_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                rows = list(reader)
            
            assert len(rows) == 2  # Header + 1 data row
            assert rows[1][6] == 'Ошибка: API timeout'
            
        finally:
            os.unlink(temp_file)
    
    @pytest.mark.asyncio
    async def test_export_creates_directory(self, settings, mock_logger, sample_ranking_result):
        """Test that export creates output directory."""
        exporter = FileExporterImpl(settings, mock_logger)
        
        # Use a path in a non-existent directory
        output_path = "test_output/subdir/test_file.csv"
        
        try:
            result_path = await exporter.export_to_csv(sample_ranking_result, output_path)
            
            assert result_path == output_path
            assert os.path.exists(output_path)
            assert os.path.exists("test_output/subdir")
            
        finally:
            # Cleanup
            if os.path.exists(output_path):
                os.unlink(output_path)
            if os.path.exists("test_output/subdir"):
                os.rmdir("test_output/subdir")
            if os.path.exists("test_output"):
                os.rmdir("test_output")
    
    def test_generate_filename(self, settings, mock_logger):
        """Test filename generation."""
        exporter = FileExporterImpl(settings, mock_logger)
        
        # Test CSV filename
        filename = exporter.generate_filename(12345, 'csv')
        assert filename.startswith('wb_ranking_12345_')
        assert filename.endswith('.csv')
        
        # Test XLSX filename
        filename = exporter.generate_filename(12345, 'xlsx')
        assert filename.startswith('wb_ranking_12345_')
        assert filename.endswith('.xlsx')
        
        # Test with custom timestamp
        timestamp = datetime(2024, 1, 15, 12, 30, 45)
        filename = exporter.generate_filename(12345, 'csv', timestamp)
        assert '20240115_123045' in filename
    
    def test_get_export_path(self, settings, mock_logger):
        """Test export path generation."""
        exporter = FileExporterImpl(settings, mock_logger)
        
        # Test basic path
        path = exporter.get_export_path("test.csv")
        assert path == "test_output/test.csv"
        
        # Test with subdirectory
        path = exporter.get_export_path("test.csv", "subdir")
        assert path == "test_output/subdir/test.csv"
        
        # Cleanup
        if os.path.exists("test_output"):
            import shutil
            shutil.rmtree("test_output")
    
    def test_validate_export_path(self, settings, mock_logger):
        """Test export path validation."""
        exporter = FileExporterImpl(settings, mock_logger)
        
        # Test valid path
        assert exporter.validate_export_path("test_output/valid.csv") is True
        
        # Test invalid path (non-writable directory)
        assert exporter.validate_export_path("/root/test.csv") is False
        
        # Cleanup
        if os.path.exists("test_output"):
            import shutil
            shutil.rmtree("test_output")
    
    def test_get_file_size(self, settings, mock_logger):
        """Test file size retrieval."""
        exporter = FileExporterImpl(settings, mock_logger)
        
        # Create a test file
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content")
            temp_file = f.name
        
        try:
            size = exporter.get_file_size(temp_file)
            assert size > 0
            
            # Test non-existent file
            size = exporter.get_file_size("nonexistent.txt")
            assert size == 0
            
        finally:
            os.unlink(temp_file)
    
    def test_cleanup_old_files(self, settings, mock_logger):
        """Test cleanup of old files."""
        exporter = FileExporterImpl(settings, mock_logger)
        
        # Create test directory with old file
        test_dir = "test_cleanup"
        os.makedirs(test_dir, exist_ok=True)
        
        try:
            # Create a file with old timestamp
            old_file = os.path.join(test_dir, "wb_ranking_12345_20200101_000000.csv")
            with open(old_file, 'w') as f:
                f.write("test")
            
            # Modify file timestamp to be old
            old_timestamp = datetime.now().timestamp() - (10 * 24 * 60 * 60)  # 10 days ago
            os.utime(old_file, (old_timestamp, old_timestamp))
            
            # Run cleanup
            deleted_count = exporter.cleanup_old_files(test_dir, max_age_days=7)
            
            assert deleted_count == 1
            assert not os.path.exists(old_file)
            
        finally:
            # Cleanup
            if os.path.exists(test_dir):
                import shutil
                shutil.rmtree(test_dir)
    
    def test_prepare_csv_data(self, settings, mock_logger, sample_ranking_result):
        """Test CSV data preparation."""
        exporter = FileExporterImpl(settings, mock_logger)
        
        data = exporter._prepare_csv_data(sample_ranking_result)
        
        # Check headers
        expected_headers = [
            'Номер строки',
            'Ключевое слово',
            'Частотность',
            'Позиция товара',
            'Цена товара',
            'Страница',
            'Статус'
        ]
        assert data['headers'] == expected_headers
        
        # Check rows
        assert len(data['rows']) == 3
        
        # Check first row (found product)
        first_row = data['rows'][0]
        assert first_row[0] == 1  # row number
        assert first_row[1] == 'keyword1'  # keyword
        assert first_row[2] == 'Найден'  # frequency
        assert first_row[3] == 5  # position
        assert first_row[4] == '1500.50 ₽'  # price
        assert first_row[5] == 1  # page
        assert first_row[6] == 'Найден'  # status
    
    def test_prepare_excel_data(self, settings, mock_logger, sample_ranking_result):
        """Test Excel data preparation."""
        exporter = FileExporterImpl(settings, mock_logger)
        
        data = exporter._prepare_excel_data(sample_ranking_result)
        
        # Check results data
        assert len(data['results']) == 3
        
        # Check summary data
        assert len(data['summary']) == 7
        
        # Check statistics data
        assert len(data['statistics']) > 0
        
        # Verify summary contains expected fields
        summary_params = [item['Параметр'] for item in data['summary']]
        assert 'ID товара' in summary_params
        assert 'Название товара' in summary_params
        assert 'Общее количество ключевых слов' in summary_params
        assert 'Найдено товаров' in summary_params
        assert 'Время выполнения' in summary_params
