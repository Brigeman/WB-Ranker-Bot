"""Ports (interfaces) for Clean Architecture implementation."""

from abc import ABC, abstractmethod
from typing import List, Optional, Protocol, runtime_checkable

from pydantic import BaseModel


class Product(BaseModel):
    """Product model from WB API."""
    
    id: int
    name: str
    price_rub: float
    brand: str
    rating: float
    feedbacks: int


class SearchResult(BaseModel):
    """Search result for a single keyword."""
    
    keyword: str
    product: Optional[Product]
    position: Optional[int]  # None if not found
    page: Optional[int]  # None if not found
    total_pages_searched: int
    error: Optional[str] = None


class RankingResult(BaseModel):
    """Complete ranking result."""
    
    product_id: int
    product_name: str
    results: List[SearchResult]
    total_keywords: int
    found_keywords: int
    execution_time_seconds: float
    export_file_path: Optional[str] = None


@runtime_checkable
class SearchClient(Protocol):
    """Protocol for search clients (WB API adapters)."""
    
    async def search_product(
        self, 
        keyword: str, 
        product_id: int, 
        max_pages: int = 5
    ) -> SearchResult:
        """
        Search for a product by keyword.
        
        Args:
            keyword: Search keyword
            product_id: Product ID to find
            max_pages: Maximum pages to search
            
        Returns:
            SearchResult with product position or None if not found
        """
        ...


@runtime_checkable
class FileLoader(Protocol):
    """Protocol for file loading operations."""
    
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
        ...
    
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
        ...


@runtime_checkable
class FileExporter(Protocol):
    """Protocol for file export operations."""
    
    async def export_to_csv(
        self, 
        result: RankingResult, 
        file_path: str
    ) -> str:
        """
        Export ranking result to CSV file.
        
        Args:
            result: Ranking result to export
            file_path: Output file path
            
        Returns:
            Path to the created file
        """
        ...
    
    async def export_to_xlsx(
        self, 
        result: RankingResult, 
        file_path: str
    ) -> str:
        """
        Export ranking result to XLSX file.
        
        Args:
            result: Ranking result to export
            file_path: Output file path
            
        Returns:
            Path to the created file
        """
        ...


@runtime_checkable
class Logger(Protocol):
    """Protocol for logging operations."""
    
    def info(self, message: str, **kwargs) -> None:
        """Log info message."""
        ...
    
    def warning(self, message: str, **kwargs) -> None:
        """Log warning message."""
        ...
    
    def error(self, message: str, **kwargs) -> None:
        """Log error message."""
        ...
    
    def debug(self, message: str, **kwargs) -> None:
        """Log debug message."""
        ...


class RankingService(ABC):
    """Abstract ranking service."""
    
    def __init__(
        self,
        search_client: SearchClient,
        logger: Logger,
    ):
        self.search_client = search_client
        self.logger = logger
    
    @abstractmethod
    async def rank_product(
        self,
        product_url: str,
        keywords: List[str],
        max_pages: int = 5,
        max_execution_time_minutes: int = 30,
    ) -> RankingResult:
        """
        Rank product by keywords.
        
        Args:
            product_url: WB product URL
            keywords: List of keywords to search
            max_pages: Maximum pages per keyword
            max_execution_time_minutes: Maximum execution time
            
        Returns:
            RankingResult with all search results
            
        Raises:
            ValueError: If product URL is invalid
            TimeoutError: If execution time exceeded
        """
        ...


class URLParser(ABC):
    """Abstract URL parser for extracting product information."""
    
    @abstractmethod
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
        ...
    
    @abstractmethod
    def validate_wb_url(self, url: str) -> bool:
        """
        Validate if URL is a valid WB product URL.
        
        Args:
            url: URL to validate
            
        Returns:
            True if valid WB product URL
        """
        ...


@runtime_checkable
class ProgressTracker(Protocol):
    """Protocol for progress tracking."""
    
    async def update_progress(
        self, 
        current: int, 
        total: int, 
        message: str = ""
    ) -> None:
        """
        Update progress.
        
        Args:
            current: Current progress
            total: Total items
            message: Optional progress message
        """
        ...
    
    async def complete(self, message: str = "") -> None:
        """
        Mark progress as complete.
        
        Args:
            message: Optional completion message
        """
        ...
    
    async def error(self, message: str) -> None:
        """
        Mark progress as error.
        
        Args:
            message: Error message
        """
        ...
