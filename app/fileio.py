"""File I/O operations for loading and parsing keyword files."""

import asyncio
import csv
import io
import os
from pathlib import Path
from typing import List, Optional, Union
from urllib.parse import urlparse

import aiohttp
import pandas as pd

from app.config import Settings
from app.ports import FileLoader, Logger
from app.utils import (
    clean_keyword,
    convert_google_drive_url,
    extract_filename_from_url,
    is_google_drive_url,
    retry_with_backoff,
    validate_keyword,
)


class FileLoaderImpl(FileLoader):
    """File loader implementation supporting CSV, XLSX, and URL downloads."""
    
    def __init__(self, settings: Settings, logger: Logger):
        self.settings = settings
        self.logger = logger
    
    async def load_keywords_from_file(self, file_path: str) -> List[str]:
        """
        Load keywords from file (CSV/XLSX).
        
        Args:
            file_path: Path to the file
            
        Returns:
            List of keywords
            
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file format is invalid
        """
        self.logger.info(f"Loading keywords from file: {file_path}")
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        file_extension = Path(file_path).suffix.lower()
        
        try:
            if file_extension == '.csv':
                return await self._load_from_csv(file_path)
            elif file_extension in ['.xlsx', '.xls']:
                return await self._load_from_excel(file_path)
            else:
                raise ValueError(f"Unsupported file format: {file_extension}")
                
        except Exception as e:
            self.logger.error(f"Failed to load keywords from file {file_path}: {e}")
            raise ValueError(f"Failed to parse file {file_path}: {e}")
    
    async def load_keywords_from_url(self, url: str) -> List[str]:
        """
        Load keywords from URL (Google Drive, etc.).
        
        Args:
            url: URL to the file
            
        Returns:
            List of keywords
            
        Raises:
            ValueError: If URL is invalid or file cannot be downloaded
        """
        self.logger.info(f"Loading keywords from URL: {url}")
        
        try:
            # Download file content
            content = await self._download_file(url)
            
            # Determine file type from URL or content
            file_type = self._detect_file_type(url, content)
            
            # Parse content based on file type
            if file_type == 'csv':
                return await self._parse_csv_content(content)
            elif file_type == 'excel':
                return await self._parse_excel_content(content)
            else:
                raise ValueError(f"Unsupported file type: {file_type}")
                
        except Exception as e:
            self.logger.error(f"Failed to load keywords from URL {url}: {e}")
            raise ValueError(f"Failed to download or parse file from URL {url}: {e}")
    
    async def _load_from_csv(self, file_path: str) -> List[str]:
        """Load keywords from CSV file."""
        keywords = []
        
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as file:
                reader = csv.reader(file)
                
                for row_num, row in enumerate(reader, 1):
                    if not row:  # Skip empty rows
                        continue
                    
                    # Take the first column as keyword
                    keyword = row[0].strip()
                    
                    if keyword and validate_keyword(keyword):
                        cleaned_keyword = clean_keyword(keyword)
                        keywords.append(cleaned_keyword)
                    elif keyword:
                        self.logger.warning(
                            f"Invalid keyword in row {row_num}: '{keyword}'",
                            row_number=row_num,
                            keyword=keyword
                        )
            
            self.logger.info(f"Loaded {len(keywords)} keywords from CSV file")
            return keywords
            
        except UnicodeDecodeError:
            # Try with different encoding
            with open(file_path, 'r', encoding='cp1251') as file:
                reader = csv.reader(file)
                
                for row_num, row in enumerate(reader, 1):
                    if not row:
                        continue
                    
                    keyword = row[0].strip()
                    if keyword and validate_keyword(keyword):
                        cleaned_keyword = clean_keyword(keyword)
                        keywords.append(cleaned_keyword)
            
            self.logger.info(f"Loaded {len(keywords)} keywords from CSV file (cp1251)")
            return keywords
    
    async def _load_from_excel(self, file_path: str) -> List[str]:
        """Load keywords from Excel file."""
        try:
            # Read Excel file
            df = pd.read_excel(file_path)
            
            if df.empty:
                self.logger.warning("Excel file is empty")
                return []
            
            # Get the first column
            first_column = df.iloc[:, 0]
            
            keywords = []
            for row_num, value in enumerate(first_column, 1):
                if pd.isna(value):
                    continue
                
                keyword = str(value).strip()
                
                if keyword and validate_keyword(keyword):
                    cleaned_keyword = clean_keyword(keyword)
                    keywords.append(cleaned_keyword)
                elif keyword:
                    self.logger.warning(
                        f"Invalid keyword in row {row_num}: '{keyword}'",
                        row_number=row_num,
                        keyword=keyword
                    )
            
            self.logger.info(f"Loaded {len(keywords)} keywords from Excel file")
            return keywords
            
        except Exception as e:
            raise ValueError(f"Failed to read Excel file: {e}")
    
    async def _download_file(self, url: str) -> bytes:
        """Download file content from URL."""
        # Convert Google Drive URL if needed
        if is_google_drive_url(url):
            direct_url = convert_google_drive_url(url)
            if not direct_url:
                raise ValueError("Failed to convert Google Drive URL to direct download")
            url = direct_url
        
        def download():
            async def _download():
                # Create a new session for this request to avoid event loop issues
                timeout = aiohttp.ClientTimeout(total=30)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as response:
                        if response.status != 200:
                            raise ValueError(f"Failed to download file: HTTP {response.status}")
                        
                        return await response.read()
            
            return _download()
        
        # Use retry logic for download
        return await retry_with_backoff(
            download,
            max_attempts=3,
            base_delay=1.0,
            backoff_factor=2.0
        )
    
    def _detect_file_type(self, url: str, content: bytes) -> str:
        """Detect file type from URL or content."""
        # Try to detect from URL first
        filename = extract_filename_from_url(url)
        if filename:
            extension = Path(filename).suffix.lower()
            if extension == '.csv':
                return 'csv'
            elif extension in ['.xlsx', '.xls']:
                return 'excel'
        
        # Try to detect from content
        if content.startswith(b'\x50\x4b'):  # ZIP signature (XLSX)
            return 'excel'
        elif b',' in content[:1000] or b';' in content[:1000]:  # CSV-like
            return 'csv'
        
        # Default to CSV
        return 'csv'
    
    async def _parse_csv_content(self, content: bytes) -> List[str]:
        """Parse CSV content from bytes."""
        keywords = []
        
        try:
            # Try UTF-8 first
            text = content.decode('utf-8-sig')
        except UnicodeDecodeError:
            try:
                # Try cp1251
                text = content.decode('cp1251')
            except UnicodeDecodeError:
                # Fallback to utf-8 with errors='ignore'
                text = content.decode('utf-8', errors='ignore')
        
        # Parse CSV content
        csv_reader = csv.reader(io.StringIO(text))
        
        for row_num, row in enumerate(csv_reader, 1):
            if not row:
                continue
            
            keyword = row[0].strip()
            if keyword and validate_keyword(keyword):
                cleaned_keyword = clean_keyword(keyword)
                keywords.append(cleaned_keyword)
            elif keyword:
                self.logger.warning(
                    f"Invalid keyword in row {row_num}: '{keyword}'",
                    row_number=row_num,
                    keyword=keyword
                )
        
        self.logger.info(f"Parsed {len(keywords)} keywords from CSV content")
        return keywords
    
    async def _parse_excel_content(self, content: bytes) -> List[str]:
        """Parse Excel content from bytes."""
        try:
            # Try to read as Excel directly first
            try:
                df = pd.read_excel(io.BytesIO(content))
            except Exception as excel_error:
                # If direct Excel read fails, try to extract from ZIP
                self.logger.info(f"Direct Excel read failed, trying ZIP extraction: {excel_error}")
                
                import zipfile
                with zipfile.ZipFile(io.BytesIO(content)) as zip_file:
                    # Find Excel files in the ZIP
                    excel_files = [f for f in zip_file.namelist() if f.endswith(('.xlsx', '.xls'))]
                    
                    if not excel_files:
                        raise ValueError("No Excel files found in ZIP archive")
                    
                    # Use the first Excel file
                    excel_file = excel_files[0]
                    self.logger.info(f"Extracting Excel file from ZIP: {excel_file}")
                    
                    with zip_file.open(excel_file) as excel_data:
                        df = pd.read_excel(excel_data)
            
            if df.empty:
                return []
            
            # Get the first column
            first_column = df.iloc[:, 0]
            
            keywords = []
            for row_num, value in enumerate(first_column, 1):
                if pd.isna(value):
                    continue
                
                keyword = str(value).strip()
                if keyword and validate_keyword(keyword):
                    cleaned_keyword = clean_keyword(keyword)
                    keywords.append(cleaned_keyword)
                elif keyword:
                    self.logger.warning(
                        f"Invalid keyword in row {row_num}: '{keyword}'",
                        row_number=row_num,
                        keyword=keyword
                    )
            
            self.logger.info(f"Parsed {len(keywords)} keywords from Excel content")
            return keywords
            
        except Exception as e:
            raise ValueError(f"Failed to parse Excel content: {e}")
    
    def validate_file_size(self, file_path: str) -> bool:
        """Validate file size is within limits."""
        try:
            file_size = os.path.getsize(file_path)
            max_size = 10 * 1024 * 1024  # 10MB limit
            
            if file_size > max_size:
                self.logger.warning(
                    f"File size {file_size} exceeds limit {max_size}",
                    file_size=file_size,
                    max_size=max_size
                )
                return False
            
            return True
            
        except OSError:
            return False
    
    def validate_keywords_count(self, keywords: List[str]) -> bool:
        """Validate keywords count is within limits."""
        count = len(keywords)
        max_count = self.settings.max_keywords_limit
        
        if count > max_count:
            self.logger.warning(
                f"Keywords count {count} exceeds limit {max_count}",
                count=count,
                max_count=max_count
            )
            return False
        
        return True
    
    def get_file_info(self, file_path: str) -> dict:
        """Get file information."""
        try:
            stat = os.stat(file_path)
            return {
                'size': stat.st_size,
                'modified': stat.st_mtime,
                'extension': Path(file_path).suffix.lower(),
                'exists': True
            }
        except OSError:
            return {
                'size': 0,
                'modified': 0,
                'extension': '',
                'exists': False
            }
