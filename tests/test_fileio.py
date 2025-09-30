"""Tests for fileio module."""

import csv
import io
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pandas as pd
import pytest
import aiohttp

from app.config import Settings
from app.fileio import FileLoaderImpl
from app.ports import Logger


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
        max_keywords_limit=1000
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
def temp_csv_file():
    """Create temporary CSV file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['keyword1'])
        writer.writerow(['keyword2'])
        writer.writerow(['keyword3'])
        temp_file = f.name
    
    yield temp_file
    
    # Cleanup
    try:
        os.unlink(temp_file)
    except OSError:
        pass


@pytest.fixture
def temp_excel_file():
    """Create temporary Excel file for testing."""
    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f:
        df = pd.DataFrame({'keywords': ['excel_keyword1', 'excel_keyword2', 'excel_keyword3']})
        df.to_excel(f.name, index=False)
        temp_file = f.name
    
    yield temp_file
    
    # Cleanup
    try:
        os.unlink(temp_file)
    except OSError:
        pass


class TestFileLoaderImpl:
    """Test FileLoaderImpl class."""
    
    @pytest.mark.asyncio
    async def test_context_manager(self, settings, mock_logger):
        """Test FileLoaderImpl instantiation."""
        loader = FileLoaderImpl(settings, mock_logger)
        assert loader is not None
        assert loader.settings == settings
        assert loader.logger == mock_logger
    
    @pytest.mark.asyncio
    async def test_load_keywords_from_csv_file(self, settings, mock_logger, temp_csv_file):
        """Test loading keywords from CSV file."""
        loader = FileLoaderImpl(settings, mock_logger)
        keywords = await loader.load_keywords_from_file(temp_csv_file)
        
        assert len(keywords) == 3
        assert 'keyword1' in keywords
        assert 'keyword2' in keywords
        assert 'keyword3' in keywords
    
    @pytest.mark.asyncio
    async def test_load_keywords_from_excel_file(self, settings, mock_logger, temp_excel_file):
        """Test loading keywords from Excel file."""
        async with FileLoaderImpl(settings, mock_logger) as loader:
            keywords = await loader.load_keywords_from_file(temp_excel_file)
            
            assert len(keywords) == 3
            assert 'excel_keyword1' in keywords
            assert 'excel_keyword2' in keywords
            assert 'excel_keyword3' in keywords
    
    @pytest.mark.asyncio
    async def test_load_keywords_from_nonexistent_file(self, settings, mock_logger):
        """Test loading keywords from non-existent file."""
        async with FileLoaderImpl(settings, mock_logger) as loader:
            with pytest.raises(FileNotFoundError):
                await loader.load_keywords_from_file("nonexistent.csv")
    
    @pytest.mark.asyncio
    async def test_load_keywords_from_unsupported_format(self, settings, mock_logger):
        """Test loading keywords from unsupported file format."""
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            f.write(b"test content")
            temp_file = f.name
        
        try:
            async with FileLoaderImpl(settings, mock_logger) as loader:
                with pytest.raises(ValueError, match="Unsupported file format"):
                    await loader.load_keywords_from_file(temp_file)
        finally:
            os.unlink(temp_file)
    
    @pytest.mark.asyncio
    async def test_load_keywords_from_url_csv(self, settings, mock_logger, mock_session):
        """Test loading keywords from CSV URL."""
        # Mock CSV content
        csv_content = b"keyword1\nkeyword2\nkeyword3"
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=csv_content)
        
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=None)
        
        mock_session.get.return_value = cm
        
        loader = FileLoaderImpl(settings, mock_logger)
        loader._session = mock_session
        
        keywords = await loader.load_keywords_from_url("https://example.com/file.csv")
        
        assert len(keywords) == 3
        assert 'keyword1' in keywords
        assert 'keyword2' in keywords
        assert 'keyword3' in keywords
    
    @pytest.mark.asyncio
    async def test_load_keywords_from_url_excel(self, settings, mock_logger, mock_session):
        """Test loading keywords from Excel URL."""
        # Create Excel content in memory
        df = pd.DataFrame({'keywords': ['url_keyword1', 'url_keyword2']})
        excel_content = io.BytesIO()
        df.to_excel(excel_content, index=False)
        excel_bytes = excel_content.getvalue()
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.read = AsyncMock(return_value=excel_bytes)
        
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=None)
        
        mock_session.get.return_value = cm
        
        loader = FileLoaderImpl(settings, mock_logger)
        loader._session = mock_session
        
        keywords = await loader.load_keywords_from_url("https://example.com/file.xlsx")
        
        assert len(keywords) == 2
        assert 'url_keyword1' in keywords
        assert 'url_keyword2' in keywords
    
    @pytest.mark.asyncio
    async def test_load_keywords_from_url_download_failure(self, settings, mock_logger, mock_session):
        """Test loading keywords from URL with download failure."""
        mock_response = AsyncMock()
        mock_response.status = 404
        
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=mock_response)
        cm.__aexit__ = AsyncMock(return_value=None)
        
        mock_session.get.return_value = cm
        
        loader = FileLoaderImpl(settings, mock_logger)
        loader._session = mock_session
        
        with pytest.raises(ValueError, match="Failed to download or parse file"):
            await loader.load_keywords_from_url("https://example.com/file.csv")
    
    @pytest.mark.asyncio
    async def test_load_keywords_with_invalid_keywords(self, settings, mock_logger):
        """Test loading keywords with invalid entries."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['valid_keyword'])
            writer.writerow([''])  # Empty
            writer.writerow(['keyword<tag>'])  # Invalid characters
            writer.writerow(['another_valid'])
            temp_file = f.name
        
        try:
            async with FileLoaderImpl(settings, mock_logger) as loader:
                keywords = await loader.load_keywords_from_file(temp_file)
                
                assert len(keywords) == 2
                assert 'valid_keyword' in keywords
                assert 'another_valid' in keywords
                
                # Check that warnings were logged
                warning_logs = [log for log in mock_logger.logs if log[0] == 'warning']
                assert len(warning_logs) == 1
                assert 'Invalid keyword' in warning_logs[0][1]
        finally:
            os.unlink(temp_file)
    
    @pytest.mark.asyncio
    async def test_load_keywords_with_different_encodings(self, settings, mock_logger):
        """Test loading keywords with different encodings."""
        # Test UTF-8 with BOM
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['utf8_keyword'])
            temp_file = f.name
        
        try:
            async with FileLoaderImpl(settings, mock_logger) as loader:
                keywords = await loader.load_keywords_from_file(temp_file)
                
                assert len(keywords) == 1
                assert 'utf8_keyword' in keywords
        finally:
            os.unlink(temp_file)
    
    def test_validate_file_size(self, settings, mock_logger):
        """Test file size validation."""
        loader = FileLoaderImpl(settings, mock_logger)
        
        # Create a small file
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"small content")
            temp_file = f.name
        
        try:
            assert loader.validate_file_size(temp_file) is True
            
            # Test non-existent file
            assert loader.validate_file_size("nonexistent.txt") is False
        finally:
            os.unlink(temp_file)
    
    def test_validate_keywords_count(self, settings, mock_logger):
        """Test keywords count validation."""
        loader = FileLoaderImpl(settings, mock_logger)
        
        # Valid count
        keywords = ['keyword' + str(i) for i in range(100)]
        assert loader.validate_keywords_count(keywords) is True
        
        # Invalid count (exceeds limit)
        settings.max_keywords_limit = 50
        assert loader.validate_keywords_count(keywords) is False
    
    def test_get_file_info(self, settings, mock_logger):
        """Test getting file information."""
        loader = FileLoaderImpl(settings, mock_logger)
        
        # Create a test file
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as f:
            f.write(b"test content")
            temp_file = f.name
        
        try:
            info = loader.get_file_info(temp_file)
            
            assert info['exists'] is True
            assert info['size'] > 0
            assert info['extension'] == '.csv'
            assert info['modified'] > 0
            
            # Test non-existent file
            info = loader.get_file_info("nonexistent.txt")
            assert info['exists'] is False
            assert info['size'] == 0
        finally:
            os.unlink(temp_file)
    
    def test_detect_file_type(self, settings, mock_logger):
        """Test file type detection."""
        loader = FileLoaderImpl(settings, mock_logger)
        
        # Test CSV detection
        csv_content = b"keyword1,keyword2\nkeyword3,keyword4"
        assert loader._detect_file_type("https://example.com/file.csv", csv_content) == 'csv'
        
        # Test Excel detection
        excel_content = b'\x50\x4b\x03\x04'  # ZIP signature
        assert loader._detect_file_type("https://example.com/file.xlsx", excel_content) == 'excel'
        
        # Test default to CSV
        unknown_content = b"some content"
        assert loader._detect_file_type("https://example.com/file.unknown", unknown_content) == 'csv'
    
    @pytest.mark.asyncio
    async def test_parse_csv_content(self, settings, mock_logger):
        """Test parsing CSV content from bytes."""
        loader = FileLoaderImpl(settings, mock_logger)
        
        csv_content = b"keyword1\nkeyword2\nkeyword3"
        keywords = await loader._parse_csv_content(csv_content)
        
        assert len(keywords) == 3
        assert 'keyword1' in keywords
        assert 'keyword2' in keywords
        assert 'keyword3' in keywords
    
    @pytest.mark.asyncio
    async def test_parse_excel_content(self, settings, mock_logger):
        """Test parsing Excel content from bytes."""
        loader = FileLoaderImpl(settings, mock_logger)
        
        # Create Excel content in memory
        df = pd.DataFrame({'keywords': ['excel1', 'excel2']})
        excel_content = io.BytesIO()
        df.to_excel(excel_content, index=False)
        excel_bytes = excel_content.getvalue()
        
        keywords = await loader._parse_excel_content(excel_bytes)
        
        assert len(keywords) == 2
        assert 'excel1' in keywords
        assert 'excel2' in keywords
