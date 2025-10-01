"""Business logic services for ranking operations."""

import asyncio
import time
from typing import List, Optional

from app.config import Settings
from app.ports import (
    RankingService, SearchClient, FileLoader, FileExporter, 
    Logger, ProgressTracker, RankingResult, SearchResult, Product
)
from app.utils import WBURLParser, format_execution_time


class RankingServiceImpl(RankingService):
    """Main ranking service implementation."""
    
    def __init__(
        self,
        settings: Settings,
        search_client: SearchClient,
        file_loader: FileLoader,
        file_exporter: FileExporter,
        logger: Logger,
        progress_tracker: Optional[ProgressTracker] = None
    ):
        self.settings = settings
        self.search_client = search_client
        self.file_loader = file_loader
        self.file_exporter = file_exporter
        self.logger = logger
        self.progress_tracker = progress_tracker
        
        # Statistics tracking
        self._stats = {
            "total_keywords_processed": 0,
            "successful_searches": 0,
            "failed_searches": 0,
            "total_execution_time": 0.0,
            "total_position": 0,
            "average_position": 0.0,
            "best_position": None,
            "worst_position": None
        }
    
    async def rank_product(
        self,
        product_url: str,
        keywords: List[str],
        max_pages: int = 5,
        max_execution_time_minutes: int = 30,
    ) -> RankingResult:
        """
        Rank product by keywords (abstract method implementation).
        
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
        start_time = time.time()
        
        try:
            self.logger.info(f"Starting ranking process for URL: {product_url}")
            
            # Step 1: Validate and extract product ID
            product_id = await self._validate_and_extract_product_id(product_url)
            
            # Step 2: Validate keywords count
            if not self.file_loader.validate_keywords_count(keywords):
                raise ValueError(
                    f"Too many keywords: {len(keywords)} > {self.settings.max_keywords_limit}"
                )
            
            # Step 3: Get product information
            product_info = await self._get_product_info(product_id)
            
            # Step 4: Search for product by keywords
            search_results = await self._search_product_by_keywords(
                product_id, keywords, max_pages
            )
            
            # Step 5: Calculate statistics
            self._calculate_statistics(search_results)
            
            # Step 6: Create ranking result
            execution_time = time.time() - start_time
            ranking_result = RankingResult(
                product_id=product_id,
                product_name=product_info.get("name", "Unknown Product"),
                results=search_results,
                total_keywords=len(keywords),
                found_keywords=self._stats["successful_searches"],
                execution_time_seconds=execution_time
            )
            
            self.logger.info(
                f"Ranking completed successfully. "
                f"Processed {len(keywords)} keywords in {format_execution_time(execution_time)}"
            )
            
            return ranking_result
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Ranking process failed after {format_execution_time(execution_time)}: {e}")
            
            if self.progress_tracker:
                await self.progress_tracker.send_error(f"Ошибка ранжирования: {e}")
            
            raise RuntimeError(f"Ranking process failed: {e}")
    
    async def rank_product_by_keywords(
        self,
        product_url: str,
        keywords_source: str,
        output_format: str = "xlsx"
    ) -> RankingResult:
        """
        Main ranking method that orchestrates the entire process.
        
        Args:
            product_url: Wildberries product URL
            keywords_source: Path to keywords file or URL
            output_format: Output format ('csv' or 'xlsx')
            
        Returns:
            RankingResult with all search results
            
        Raises:
            ValueError: If input validation fails
            RuntimeError: If ranking process fails
        """
        start_time = time.time()
        
        try:
            self.logger.info(f"Starting ranking process for URL: {product_url}")
            
            # Step 1: Validate and extract product ID
            product_id = await self._validate_and_extract_product_id(product_url)
            
            # Step 2: Load keywords
            keywords = await self._load_keywords(keywords_source)
            
            # Step 3: Validate keywords count
            if not self.file_loader.validate_keywords_count(keywords):
                raise ValueError(
                    f"Too many keywords: {len(keywords)} > {self.settings.max_keywords_limit}"
                )
            
            # Step 4: Get product information
            product_info = await self._get_product_info(product_id)
            
            # Step 5: Search for product by keywords
            search_results = await self._search_product_by_keywords(
                product_id, keywords
            )
            
            # Step 6: Calculate statistics
            self._calculate_statistics(search_results)
            
            # Check if any products were found
            if self._stats["successful_searches"] == 0:
                self.logger.warning("No products found for any keywords!")
                if self.progress_tracker:
                    await self.progress_tracker.send_message(
                        "⚠️ Товар не найден ни по одному ключевому слову.\n"
                        "Возможные причины:\n"
                        "• Неправильные ключевые слова в файле\n"
                        "• Товар не продается на WB\n"
                        "• Проблемы с API WB"
                    )
            
            # Step 7: Create ranking result
            execution_time = time.time() - start_time
            ranking_result = RankingResult(
                product_id=product_id,
                product_name=product_info.get("name", "Unknown Product"),
                results=search_results,
                total_keywords=len(keywords),
                found_keywords=self._stats["successful_searches"],
                execution_time_seconds=execution_time,
                export_file_path=None  # Will be set after export
            )
            
            # Step 8: Export results
            export_path = await self._export_results(ranking_result, output_format)
            
            # Update ranking result with export path
            ranking_result.export_file_path = export_path
            
            self.logger.info(
                f"Ranking completed successfully. "
                f"Processed {len(keywords)} keywords in {format_execution_time(execution_time)}"
            )
            
            return ranking_result
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.logger.error(f"Ranking process failed after {format_execution_time(execution_time)}: {e}")
            
            if self.progress_tracker:
                await self.progress_tracker.send_error(f"Ошибка ранжирования: {e}")
            
            raise RuntimeError(f"Ranking process failed: {e}")
    
    async def _validate_and_extract_product_id(self, product_url: str) -> int:
        """Validate URL and extract product ID."""
        self.logger.info(f"Validating product URL: {product_url}")
        
        parser = WBURLParser()
        if not parser.validate_wb_url(product_url):
            raise ValueError(f"Invalid Wildberries URL: {product_url}")
        
        product_id = parser.extract_product_id(product_url)
        if not product_id:
            raise ValueError(f"Could not extract product ID from URL: {product_url}")
        
        self.logger.info(f"Extracted product ID: {product_id}")
        
        if self.progress_tracker:
            await self.progress_tracker.send_message(f"✅ Товар найден: ID {product_id}")
        
        return product_id
    
    async def _load_keywords(self, keywords_source: str) -> List[str]:
        """Load keywords from file or URL."""
        self.logger.info(f"Loading keywords from: {keywords_source}")
        
        if self.progress_tracker:
            await self.progress_tracker.send_message("📁 Загружаем ключевые слова...")
        
        try:
            # Determine if source is URL or file path
            if keywords_source.startswith(('http://', 'https://')):
                keywords = await self.file_loader.load_keywords_from_url(keywords_source)
            else:
                keywords = await self.file_loader.load_keywords_from_file(keywords_source)
            
            self.logger.info(f"Loaded {len(keywords)} keywords")
            
            if self.progress_tracker:
                await self.progress_tracker.send_message(f"✅ Загружено {len(keywords)} ключевых слов")
            
            return keywords
            
        except Exception as e:
            self.logger.error(f"Failed to load keywords: {e}")
            raise ValueError(f"Failed to load keywords: {e}")
    
    async def _get_product_info(self, product_id: int) -> dict:
        """Get basic product information."""
        self.logger.info(f"Getting product info for ID: {product_id}")
        
        if self.progress_tracker:
            await self.progress_tracker.send_message("🔍 Получаем информацию о товаре...")
        
        try:
            # For now, return basic info without searching
            # The actual product info will be retrieved during keyword search
            self.logger.info(f"Using basic product info for ID: {product_id}")
            product_info = {
                "id": product_id,
                "name": f"Product {product_id}",
                "brand": "Unknown",
                "price": 0.0
            }
            
            if self.progress_tracker:
                await self.progress_tracker.send_message(f"ℹ️ Используем базовую информацию для товара {product_id}")
            
            return product_info
            
        except Exception as e:
            self.logger.warning(f"Could not get product info: {e}")
            return {
                "id": product_id,
                "name": f"Product {product_id}",
                "brand": "Unknown",
                "price": 0.0
            }
    
    async def _search_product_by_keywords(
        self, 
        product_id: int, 
        keywords: List[str], 
        max_pages: int = None
    ) -> List[SearchResult]:
        """Search for product using all keywords."""
        self.logger.info(f"Starting search for {len(keywords)} keywords")
        
        if self.progress_tracker:
            await self.progress_tracker.send_message(
                f"🔍 Начинаем поиск по {len(keywords)} ключевым словам..."
            )
        
        search_results = []
        total_keywords = len(keywords)
        
        # Process keywords in parallel batches
        batch_size = self.settings.wb_concurrency_limit
        completed = 0
        
        for batch_start in range(0, total_keywords, batch_size):
            batch_end = min(batch_start + batch_size, total_keywords)
            batch_keywords = keywords[batch_start:batch_end]
            
            # Process batch in parallel
            batch_tasks = []
            for keyword in batch_keywords:
                pages_to_search = max_pages if max_pages is not None else self.settings.wb_max_pages
                task = self.search_client.search_product(
                    keyword=keyword,
                    product_id=product_id,
                    max_pages=pages_to_search
                )
                batch_tasks.append(task)
            
            # Wait for batch completion
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            # Process results
            for result in batch_results:
                if isinstance(result, Exception):
                    self.logger.error(f"Batch search error: {result}")
                    # Create error result
                    error_result = SearchResult(
                        keyword="error",
                        product=None,
                        position=0,
                        page=0,
                        error=str(result)
                    )
                    search_results.append(error_result)
                    self._stats["failed_searches"] += 1
                else:
                    search_results.append(result)
                    if result.product:
                        self.logger.info(
                            f"Found product for '{result.keyword}' at position {result.position} "
                            f"(page {result.page})"
                        )
                        self._stats["successful_searches"] += 1
                        if result.position is not None:
                            self.logger.debug(f"Adding position {result.position} to total_position (current: {self._stats.get('total_position', 'NOT_INITIALIZED')})")
                            self._stats["total_position"] += result.position
                            self.logger.debug(f"Updated total_position to: {self._stats['total_position']}")
                    else:
                        self.logger.info(f"Product not found for keyword: '{result.keyword}'")
                        if result.error:
                            self.logger.warning(f"Search error for '{result.keyword}': {result.error}")
                        self._stats["failed_searches"] += 1
            
            completed += len(batch_keywords)
            
            # Update progress
            if self.progress_tracker:
                eta = self._calculate_eta(completed, total_keywords)
                await self.progress_tracker.update_progress(
                    current=completed,
                    total=total_keywords,
                    message=f"Обработано: {completed}/{total_keywords}",
                    eta=eta
                )
            
            # Small delay between batches
            if batch_end < total_keywords:
                await asyncio.sleep(0.1)
        
        self._stats["total_keywords_processed"] = total_keywords
        
        self.logger.info(
            f"Search completed: {self._stats['successful_searches']} found, "
            f"{self._stats['failed_searches']} not found"
        )
        
        if self.progress_tracker:
            await self.progress_tracker.send_success(
                f"✅ Поиск завершен: найдено {self._stats['successful_searches']} из {total_keywords}"
            )
        
        return search_results
    
    def _calculate_statistics(self, search_results: List[SearchResult]) -> None:
        """Calculate ranking statistics."""
        positions = [r.position for r in search_results if r.position is not None]
        
        self.logger.debug(f"Calculating statistics from {len(search_results)} results, {len(positions)} with positions")
        self.logger.debug(f"Current total_position: {self._stats.get('total_position', 'NOT_INITIALIZED')}")
        
        if positions:
            self._stats["average_position"] = sum(positions) / len(positions)
            self._stats["best_position"] = min(positions)
            self._stats["worst_position"] = max(positions)
        
        self.logger.info(
            f"Statistics: avg_pos={self._stats['average_position']:.1f}, "
            f"best={self._stats['best_position']}, worst={self._stats['worst_position']}, "
            f"total_pos={self._stats.get('total_position', 'N/A')}"
        )
    
    async def _export_results(self, ranking_result: RankingResult, output_format: str) -> str:
        """Export ranking results to file and return the file path."""
        self.logger.info(f"Exporting results to {output_format.upper()}")
        
        if self.progress_tracker:
            await self.progress_tracker.send_message("📊 Экспортируем результаты...")
        
        try:
            # Generate filename
            filename = self.file_exporter.generate_filename(
                ranking_result.product_id, 
                output_format
            )
            
            # Get export path
            export_path = self.file_exporter.get_export_path(filename)
            
            # Export based on format
            if output_format.lower() == 'csv':
                await self.file_exporter.export_to_csv(ranking_result, export_path)
            else:
                await self.file_exporter.export_to_xlsx(ranking_result, export_path)
            
            self.logger.info(f"Results exported to: {export_path}")
            
            if self.progress_tracker:
                await self.progress_tracker.send_success(f"✅ Результаты сохранены: {filename}")
            
            return export_path
            
        except Exception as e:
            self.logger.error(f"Failed to export results: {e}")
            if self.progress_tracker:
                await self.progress_tracker.send_error(f"Ошибка экспорта: {e}")
            raise
    
    def _calculate_eta(self, current: int, total: int) -> str:
        """Calculate estimated time remaining."""
        if current == 0:
            return "calculating..."
        
        # More accurate ETA calculation based on batch processing
        remaining = total - current
        batch_size = self.settings.wb_concurrency_limit
        
        # Estimate: 2 seconds per batch (parallel processing)
        estimated_seconds = (remaining / batch_size) * 2
        
        if estimated_seconds < 60:
            return f"{estimated_seconds:.0f}s"
        elif estimated_seconds < 3600:
            minutes = estimated_seconds // 60
            return f"{minutes:.0f}m"
        else:
            hours = estimated_seconds // 3600
            minutes = (estimated_seconds % 3600) // 60
            return f"{hours:.0f}h {minutes:.0f}m"
    
    def get_statistics(self) -> dict:
        """Get current ranking statistics."""
        return self._stats.copy()
    
    def reset_statistics(self) -> None:
        """Reset statistics counters."""
        self._stats = {
            "total_keywords_processed": 0,
            "successful_searches": 0,
            "failed_searches": 0,
            "total_execution_time": 0.0,
            "total_position": 0,
            "average_position": 0.0,
            "best_position": None,
            "worst_position": None
        }
        self.logger.info("Statistics reset")
    
    async def health_check(self) -> bool:
        """Perform health check on all dependencies."""
        try:
            # Check search client
            if hasattr(self.search_client, 'health_check'):
                if not await self.search_client.health_check():
                    return False
            
            # Check file loader (basic validation)
            if not hasattr(self.file_loader, 'validate_keywords_count'):
                return False
            
            # Check file exporter (basic validation)
            if not hasattr(self.file_exporter, 'generate_filename'):
                return False
            
            self.logger.info("Health check passed")
            return True
            
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return False
