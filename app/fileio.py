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
            # First, check all sheets to find the one with keywords
            xl = pd.ExcelFile(file_path)
            self.logger.info(f"Excel file has {len(xl.sheet_names)} sheets: {xl.sheet_names}")
            
            keywords_sheet = None
            keywords_column = None
            
            # Look for sheet with keywords
            for sheet_name in xl.sheet_names:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                if df.empty:
                    continue
                
                # Check if this sheet has a column with keywords
                for col in df.columns:
                    col_str = str(col).strip().lower()
                    if any(keyword in col_str for keyword in ['поисковый', 'запрос', 'keyword', 'ключевое', 'слово']):
                        # Check if this column has actual keyword data (not just headers)
                        non_null_values = df[col].dropna()
                        if len(non_null_values) > 1:  # More than just header
                            # Check if values look like keywords
                            sample_values = non_null_values.head(10)
                            text_like_count = sum(1 for val in sample_values if isinstance(val, str) and len(str(val).strip()) > 2)
                            if text_like_count >= len(sample_values) * 0.7:  # 70% text-like
                                keywords_sheet = sheet_name
                                keywords_column = col
                                self.logger.info(f"Found keywords in sheet '{sheet_name}', column '{col}' with {len(non_null_values)} values")
                                break
                
                if keywords_sheet:
                    break
            
            # If no keywords sheet found, use first sheet
            if keywords_sheet is None:
                keywords_sheet = xl.sheet_names[0]
                self.logger.warning(f"No keywords sheet found, using first sheet: '{keywords_sheet}'")
            
            # Read the selected sheet
            df = pd.read_excel(file_path, sheet_name=keywords_sheet)
            
            if df.empty:
                self.logger.warning(f"Sheet '{keywords_sheet}' is empty")
                return []
            
            # If no keywords column found, try to find it
            if keywords_column is None:
                # First, try to find column with header "Ключевое слово" or similar
                for col in df.columns:
                    col_str = str(col).strip().lower()
                    if any(keyword in col_str for keyword in ['ключевое', 'keyword', 'слово', 'запрос']):
                        keywords_column = col
                        self.logger.info(f"Found keywords column: '{col}'")
                        break
                
                # If not found, look for the first column that contains text data
                if keywords_column is None:
                    for col in df.columns:
                        # Check if column contains mostly text data
                        non_null_count = df[col].notna().sum()
                        if non_null_count > 0:
                            # Check if values look like keywords (not numbers, not dates)
                            sample_values = df[col].dropna().head(5)
                            if len(sample_values) > 0:
                                text_like_count = sum(1 for val in sample_values if isinstance(val, str) and len(str(val).strip()) > 2)
                                if text_like_count >= len(sample_values) * 0.6:  # 60% text-like
                                    keywords_column = col
                                    self.logger.info(f"Using first text-like column: '{col}'")
                                    break
                
                # Fallback to first column
                if keywords_column is None:
                    keywords_column = df.columns[0]
                    self.logger.warning(f"No suitable keywords column found, using first column: '{keywords_column}'")
            
            # Extract keywords from the found column
            keywords = []
            for row_num, value in enumerate(df[keywords_column], 1):
                if pd.isna(value):
                    continue
                
                keyword = str(value).strip()
                
                # Skip obvious non-keywords (periods, headers, etc.)
                if any(skip_word in keyword.lower() for skip_word in ['период', 'period', 'выбранный', 'предыдущий', 'аналитика', 'сводка', 'статистика']):
                    self.logger.warning(f"Skipping non-keyword in row {row_num}: '{keyword}'")
                    continue
                
                if keyword and validate_keyword(keyword):
                    cleaned_keyword = clean_keyword(keyword)
                    keywords.append(cleaned_keyword)
                elif keyword:
                    self.logger.warning(
                        f"Invalid keyword in row {row_num}: '{keyword}'",
                        row_number=row_num,
                        keyword=keyword
                    )
            
            # Log first 5 keywords for debugging
            if keywords:
                first_5 = keywords[:5]
                self.logger.info(f"First 5 keywords loaded: {first_5}")
            else:
                self.logger.warning("No valid keywords found in Excel file!")
                # Log all values for debugging
                all_values = [str(val).strip() for val in df[keywords_column].dropna()]
                self.logger.warning(f"All values in column '{keywords_column}': {all_values}")
            
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
                return await self._load_from_excel_bytes(content)
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
                        excel_content = excel_data.read()
                        return await self._load_from_excel_bytes(excel_content)
            
        except Exception as e:
            raise ValueError(f"Failed to parse Excel content: {e}")
    
    async def _load_from_excel_bytes(self, content: bytes) -> List[str]:
        """Load keywords from Excel bytes using the new sheet detection logic."""
        try:
            # First, check all sheets to find the one with keywords
            xl = pd.ExcelFile(io.BytesIO(content))
            self.logger.info(f"Excel file has {len(xl.sheet_names)} sheets: {xl.sheet_names}")
            
            keywords_sheet = None
            keywords_column = None
            
            # Look for sheet with keywords
            for sheet_name in xl.sheet_names:
                df = pd.read_excel(io.BytesIO(content), sheet_name=sheet_name)
                if df.empty:
                    continue
                
                # Check if this sheet has a column with keywords
                for col in df.columns:
                    col_str = str(col).strip().lower()
                    if any(keyword in col_str for keyword in ['поисковый', 'запрос', 'keyword', 'ключевое', 'слово']):
                        # Check if this column has actual keyword data (not just headers)
                        non_null_values = df[col].dropna()
                        if len(non_null_values) > 1:  # More than just header
                            # Check if values look like keywords
                            sample_values = non_null_values.head(10)
                            text_like_count = sum(1 for val in sample_values if isinstance(val, str) and len(str(val).strip()) > 2)
                            if text_like_count >= len(sample_values) * 0.7:  # 70% text-like
                                keywords_sheet = sheet_name
                                keywords_column = col
                                self.logger.info(f"Found keywords in sheet '{sheet_name}', column '{col}' with {len(non_null_values)} values")
                                break
                
                if keywords_sheet:
                    break
            
            # If no keywords sheet found, use first sheet
            if keywords_sheet is None:
                keywords_sheet = xl.sheet_names[0]
                self.logger.warning(f"No keywords sheet found, using first sheet: '{keywords_sheet}'")
            
            # Read the selected sheet
            df = pd.read_excel(io.BytesIO(content), sheet_name=keywords_sheet)
            
            if df.empty:
                self.logger.warning(f"Sheet '{keywords_sheet}' is empty")
                return []
            
            # If no keywords column found, try to find it
            if keywords_column is None:
                # First, try to find column with header "Ключевое слово" or similar
                for col in df.columns:
                    col_str = str(col).strip().lower()
                    if any(keyword in col_str for keyword in ['ключевое', 'keyword', 'слово', 'запрос']):
                        keywords_column = col
                        self.logger.info(f"Found keywords column: '{col}'")
                        break
                
                # If not found, look for the first column that contains text data
                if keywords_column is None:
                    for col in df.columns:
                        # Check if column contains mostly text data
                        non_null_count = df[col].notna().sum()
                        if non_null_count > 0:
                            # Check if values look like keywords (not numbers, not dates)
                            sample_values = df[col].dropna().head(5)
                            if len(sample_values) > 0:
                                text_like_count = sum(1 for val in sample_values if isinstance(val, str) and len(str(val).strip()) > 2)
                                if text_like_count >= len(sample_values) * 0.6:  # 60% text-like
                                    keywords_column = col
                                    self.logger.info(f"Using first text-like column: '{col}'")
                                    break
                
                # Fallback to first column
                if keywords_column is None:
                    keywords_column = df.columns[0]
                    self.logger.warning(f"No suitable keywords column found, using first column: '{keywords_column}'")
            
            return await self._load_from_excel_dataframe(df)
            
        except Exception as e:
            raise ValueError(f"Failed to read Excel file: {e}")
    
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
