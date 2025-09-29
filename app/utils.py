"""Utility functions for WB Ranker Bot."""

import re
import time
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs

from app.ports import URLParser


class WBURLParser(URLParser):
    """Wildberries URL parser implementation."""
    
    # Regex patterns for different WB URL formats
    URL_PATTERNS = [
        r'https?://www\.wildberries\.ru/catalog/(\d+)/detail\.aspx.*',
        r'https?://www\.wildberries\.ru/catalog/(\d+)/.*',
        r'https?://wildberries\.ru/catalog/(\d+)/detail\.aspx.*',
        r'https?://wildberries\.ru/catalog/(\d+)/.*',
    ]
    
    def extract_product_id(self, url: str) -> int:
        """
        Extract product ID from WB URL.
        
        Args:
            url: WB product URL
            
        Returns:
            Product ID
            
        Raises:
            ValueError: If URL is invalid or ID cannot be extracted
        """
        if not self.validate_wb_url(url):
            raise ValueError(f"Invalid Wildberries URL: {url}")
        
        for pattern in self.URL_PATTERNS:
            match = re.match(pattern, url)
            if match:
                try:
                    return int(match.group(1))
                except (ValueError, IndexError):
                    continue
        
        raise ValueError(f"Cannot extract product ID from URL: {url}")
    
    def validate_wb_url(self, url: str) -> bool:
        """
        Validate if URL is a valid WB product URL.
        
        Args:
            url: URL to validate
            
        Returns:
            True if valid WB product URL
        """
        if not url or not isinstance(url, str):
            return False
        
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return False
            
            # Check if it's a WB domain
            if not any(domain in parsed.netloc.lower() for domain in ['wildberries.ru', 'www.wildberries.ru']):
                return False
            
            # Check if it has catalog path
            if not parsed.path.startswith('/catalog/'):
                return False
            
            # Try to extract ID to validate format
            for pattern in self.URL_PATTERNS:
                if re.match(pattern, url):
                    return True
            
            return False
            
        except Exception:
            return False


def calculate_position(page: int, index_on_page: int, items_per_page: int = 100) -> int:
    """
    Calculate absolute position from page and index.
    
    Args:
        page: Page number (1-based)
        index_on_page: Index on the page (0-based)
        items_per_page: Number of items per page
        
    Returns:
        Absolute position (1-based)
    """
    if page < 1 or index_on_page < 0:
        raise ValueError("Page must be >= 1 and index must be >= 0")
    
    return (page - 1) * items_per_page + index_on_page + 1


def format_price(price_kopecks: int) -> float:
    """
    Convert price from kopecks to rubles.
    
    Args:
        price_kopecks: Price in kopecks
        
    Returns:
        Price in rubles
    """
    return price_kopecks / 100.0


def format_execution_time(seconds: float) -> str:
    """
    Format execution time in human-readable format.
    
    Args:
        seconds: Execution time in seconds
        
    Returns:
        Formatted time string
    """
    if seconds < 60:
        return f"{seconds:.1f} сек"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        remaining_seconds = seconds % 60
        return f"{minutes} мин {remaining_seconds:.1f} сек"
    else:
        hours = int(seconds // 3600)
        remaining_minutes = int((seconds % 3600) // 60)
        return f"{hours} ч {remaining_minutes} мин"


def truncate_string(text: str, max_length: int = 50) -> str:
    """
    Truncate string to maximum length with ellipsis.
    
    Args:
        text: Text to truncate
        max_length: Maximum length
        
    Returns:
        Truncated string
    """
    if not text:
        return ""
    
    if len(text) <= max_length:
        return text
    
    return text[:max_length - 3] + "..."


def validate_keyword(keyword: str) -> bool:
    """
    Validate keyword format.
    
    Args:
        keyword: Keyword to validate
        
    Returns:
        True if valid keyword
    """
    if not keyword or not isinstance(keyword, str):
        return False
    
    # Remove whitespace
    keyword = keyword.strip()
    
    # Check length
    if len(keyword) < 1 or len(keyword) > 100:
        return False
    
    # Check for invalid characters
    invalid_chars = ['<', '>', '"', "'", '&', '\n', '\r', '\t']
    if any(char in keyword for char in invalid_chars):
        return False
    
    return True


def clean_keyword(keyword: str) -> str:
    """
    Clean and normalize keyword.
    
    Args:
        keyword: Raw keyword
        
    Returns:
        Cleaned keyword
    """
    if not keyword:
        return ""
    
    # Strip whitespace
    keyword = keyword.strip()
    
    # Remove extra spaces
    keyword = re.sub(r'\s+', ' ', keyword)
    
    return keyword


def extract_filename_from_url(url: str) -> Optional[str]:
    """
    Extract filename from URL.
    
    Args:
        url: URL to extract filename from
        
    Returns:
        Filename or None if not found
    """
    try:
        parsed = urlparse(url)
        path = parsed.path
        
        if not path:
            return None
        
        # Get the last part of the path
        filename = path.split('/')[-1]
        
        if not filename or '.' not in filename:
            return None
        
        return filename
        
    except Exception:
        return None


def is_google_drive_url(url: str) -> bool:
    """
    Check if URL is a Google Drive link.
    
    Args:
        url: URL to check
        
    Returns:
        True if Google Drive URL
    """
    if not url:
        return False
    
    try:
        parsed = urlparse(url)
        return 'drive.google.com' in parsed.netloc.lower()
    except Exception:
        return False


def convert_google_drive_url(url: str) -> Optional[str]:
    """
    Convert Google Drive sharing URL to direct download URL.
    
    Args:
        url: Google Drive sharing URL
        
    Returns:
        Direct download URL or None if conversion failed
    """
    if not is_google_drive_url(url):
        return None
    
    try:
        # Extract file ID from different Google Drive URL formats
        file_id_patterns = [
            r'/file/d/([a-zA-Z0-9_-]+)',
            r'id=([a-zA-Z0-9_-]+)',
            r'/open\?id=([a-zA-Z0-9_-]+)',
        ]
        
        for pattern in file_id_patterns:
            match = re.search(pattern, url)
            if match:
                file_id = match.group(1)
                return f"https://drive.google.com/uc?export=download&id={file_id}"
        
        return None
        
    except Exception:
        return None


def retry_with_backoff(
    func,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 60.0
):
    """
    Retry function with exponential backoff.
    
    Args:
        func: Function to retry
        max_attempts: Maximum number of attempts
        base_delay: Base delay in seconds
        backoff_factor: Backoff multiplication factor
        max_delay: Maximum delay in seconds
        
    Returns:
        Function result
        
    Raises:
        Last exception if all attempts failed
    """
    last_exception = None
    
    for attempt in range(max_attempts):
        try:
            return func()
        except Exception as e:
            last_exception = e
            
            if attempt == max_attempts - 1:
                break
            
            # Calculate delay with exponential backoff
            delay = min(base_delay * (backoff_factor ** attempt), max_delay)
            time.sleep(delay)
    
    raise last_exception


def create_progress_message(current: int, total: int, message: str = "") -> str:
    """
    Create progress message.
    
    Args:
        current: Current progress
        total: Total items
        message: Additional message
        
    Returns:
        Formatted progress message
    """
    percentage = (current / total * 100) if total > 0 else 0
    
    progress_msg = f"Прогресс: {current}/{total} ({percentage:.1f}%)"
    
    if message:
        progress_msg += f" - {message}"
    
    return progress_msg
