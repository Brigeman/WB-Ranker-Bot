"""Wildberries API adapter implementation."""

import asyncio
import json
import random
from typing import Dict, List, Optional
from urllib.parse import urlencode

import aiohttp
from aiohttp import ClientTimeout, ClientError

from app.config import Settings
from app.ports import SearchClient, SearchResult, Product, Logger
from app.utils import format_price, calculate_position


class WBAPIAdapter(SearchClient):
    """Wildberries API adapter with retry logic and rate limiting."""
    
    def __init__(
        self,
        settings: Settings,
        logger: Logger,
        session: Optional[aiohttp.ClientSession] = None,
    ):
        self.settings = settings
        self.logger = logger
        self.session = session
        self._semaphore = asyncio.Semaphore(settings.wb_concurrency_limit)
        self._session_owner = session is None
    
    async def __aenter__(self):
        """Async context manager entry."""
        if self._session_owner:
            timeout = ClientTimeout(total=self.settings.wb_request_timeout)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._session_owner and self.session:
            await self.session.close()
    
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
        async with self._semaphore:
            return await self._search_with_retry(keyword, product_id, max_pages)
    
    async def _search_with_retry(
        self, 
        keyword: str, 
        product_id: int, 
        max_pages: int
    ) -> SearchResult:
        """Search with retry logic."""
        last_exception = None
        
        for attempt in range(self.settings.wb_retry_attempts):
            try:
                return await self._search_product_pages(keyword, product_id, max_pages)
            except Exception as e:
                last_exception = e
                self.logger.warning(
                    f"Search attempt {attempt + 1} failed for keyword '{keyword}': {e}"
                )
            
            if attempt < self.settings.wb_retry_attempts - 1:
                # Calculate backoff delay
                delay = self.settings.wb_backoff_factor ** attempt
                await asyncio.sleep(delay)
        
        # All attempts failed
        self.logger.error(
            f"All search attempts failed for keyword '{keyword}': {last_exception}"
        )
        
        return SearchResult(
            keyword=keyword,
            product=None,
            position=None,
            page=None,
            total_pages_searched=0,
            error=f"API error after {self.settings.wb_retry_attempts} attempts: {str(last_exception)}"
        )
    
    async def _search_product_pages(
        self, 
        keyword: str, 
        product_id: int, 
        max_pages: int
    ) -> SearchResult:
        """Search product across multiple pages."""
        self.logger.debug(
            f"Searching product {product_id} for keyword '{keyword}' (max_pages={max_pages})"
        )
        
        for page in range(1, max_pages + 1):
            try:
                # Add delay between requests
                if page > 1:
                    min_delay, max_delay = self.settings.wb_delay_between_requests
                    delay = random.uniform(min_delay, max_delay)
                    await asyncio.sleep(delay)
                
                # Search current page
                products = await self._search_page(keyword, page)
                
                # Log page results for debugging
                self.logger.info(f"Page {page}: found {len(products)} products")
                if products:
                    first_5_ids = [p.id for p in products[:5]]
                    self.logger.info(f"First 5 product IDs on page {page}: {first_5_ids}")
                
                # Look for our product
                for index, product in enumerate(products):
                    if product.id == product_id:
                        position = calculate_position(page, index)
                        
                        self.logger.info(
                            f"Found product {product_id} at position {position} (keyword='{keyword}', page={page}, index={index})"
                        )
                        
                        return SearchResult(
                            keyword=keyword,
                            product=product,
                            position=position,
                            page=page,
                            total_pages_searched=page
                        )
                
                self.logger.debug(
                    f"Product {product_id} not found on page {page} (keyword='{keyword}', products_found={len(products)})"
                )
                
            except Exception as e:
                self.logger.error(
                    f"Error searching page {page} for keyword '{keyword}' (product_id={product_id}): {e}"
                )
                raise
        
        # Product not found in any page
        self.logger.info(
            f"Product {product_id} not found in {max_pages} pages"
        )
        
        return SearchResult(
            keyword=keyword,
            product=None,
            position=None,
            page=None,
            total_pages_searched=max_pages
        )
    
    async def _search_page(self, keyword: str, page: int) -> List[Product]:
        """Search a single page."""
        url = self._build_search_url(keyword, page)
        
        self.logger.debug(
            f"Searching page {page} for keyword '{keyword}' (url={url})"
        )
        
        async with self.session.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Referer': 'https://www.wildberries.ru/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        }) as response:
            await self._handle_response_error(response)
            
            # Check content type
            content_type = response.headers.get('content-type', '').lower()
            self.logger.debug(f"Response content type: {content_type}")
            
            # Parse response as JSON (force parsing even if content-type is text/plain)
            try:
                text_content = await response.text()
                data = json.loads(text_content)
                self.logger.debug(f"Successfully parsed JSON response")
            except Exception as e:
                self.logger.error(f"Failed to parse response as JSON: {e}")
                # Log the actual response content for debugging
                try:
                    self.logger.info(f"Response content (first 500 chars): {text_content[:500]}")
                    # Check if it's a captcha or blocking page
                    if "captcha" in text_content.lower() or "проверка" in text_content.lower():
                        self.logger.error("CAPTCHA detected in API response")
                    elif "blocked" in text_content.lower() or "заблокирован" in text_content.lower():
                        self.logger.error("Request blocked by WB API")
                    elif "<!doctype html>" in text_content.lower() or "<html>" in text_content.lower():
                        self.logger.warning("HTML page returned instead of JSON - possible blocking")
                except Exception as log_e:
                    self.logger.error(f"Failed to get response content: {log_e}")
                # Return empty result
                return []
            
            return self._parse_products(data)
    
    def _build_search_url(self, keyword: str, page: int) -> str:
        """Build search URL with parameters."""
        # Use the working v5 search API endpoint
        params = {
            'query': keyword,
            'page': page,
            'sort': 'popular',
            'locale': 'ru',
            'lang': 'ru',
            'curr': 'rub',
            'dest': '-1257786',  # Working dest parameter
            'appType': '1',
            'resultset': 'catalog'
        }
        
        query_string = urlencode(params)
        # Use the working v5 search endpoint
        return f"https://search.wb.ru/exactmatch/ru/common/v5/search?{query_string}"
    
    async def _handle_response_error(self, response: aiohttp.ClientResponse):
        """Handle HTTP response errors."""
        if response.status == 200:
            return
        
        if response.status == 429:
            # Rate limit - wait and retry
            retry_after = response.headers.get('Retry-After', '60')
            wait_time = int(retry_after)
            
            self.logger.warning(
                f"Rate limited, waiting {wait_time} seconds (status={response.status})"
            )
            
            await asyncio.sleep(wait_time)
            raise ClientError(f"Rate limited: {response.status}")
        
        elif response.status >= 500:
            # Server error - retry
            self.logger.error(
                f"Server error: {response.status} (url={str(response.url)})"
            )
            raise ClientError(f"Server error: {response.status}")
        
        elif response.status >= 400:
            # Client error - don't retry
            self.logger.error(
                f"Client error: {response.status} (url={str(response.url)})"
            )
            raise ClientError(f"Client error: {response.status}")
        
        else:
            raise ClientError(f"Unexpected status: {response.status}")
    
    def _parse_products(self, data: Dict) -> List[Product]:
        """Parse products from API response."""
        try:
            products = []
            
            self.logger.debug(f"Parsing response data keys: {list(data.keys())}")
            
            # Navigate through the response structure
            data_section = data.get('data', {})
            self.logger.debug(f"Data section keys: {list(data_section.keys())}")
            
            products_data = data_section.get('products', [])
            self.logger.debug(f"Found {len(products_data)} products in response")
            
            # Log first few product IDs for debugging
            if products_data:
                first_5_ids = [p.get('id', 'N/A') for p in products_data[:5]]
                self.logger.debug(f"First 5 product IDs: {first_5_ids}")
            
            for product_data in products_data:
                try:
                    # Get price from sizes field
                    price_kopecks = 0
                    sizes = product_data.get('sizes', [])
                    if sizes and isinstance(sizes, list) and len(sizes) > 0:
                        first_size = sizes[0]
                        if isinstance(first_size, dict) and 'price' in first_size:
                            price_info = first_size['price']
                            # Prefer 'product' price, fallback to 'total', then 'basic'
                            price_kopecks = (price_info.get('product') or 
                                            price_info.get('total') or 
                                            price_info.get('basic') or 0)
                    
                    # Fallback to direct price fields if sizes don't have price
                    if price_kopecks == 0:
                        price_kopecks = product_data.get('salePriceU') or product_data.get('priceU', 0)
                    
                    product = Product(
                        id=product_data['id'],
                        name=product_data.get('name', ''),
                        price_rub=format_price(price_kopecks),
                        brand=product_data.get('brand', ''),
                        rating=product_data.get('reviewRating', 0.0),
                        feedbacks=product_data.get('feedbacks', 0)
                    )
                    products.append(product)
                    
                except (KeyError, ValueError, TypeError) as e:
                    self.logger.warning(
                        f"Failed to parse product data: {e} (product_data={product_data})"
                    )
                    continue
            
            self.logger.debug(
                f"Parsed {len(products)} products from API response"
            )
            
            return products
            
        except (KeyError, ValueError, TypeError) as e:
            self.logger.error(
                f"Failed to parse API response: {e} (data={data})"
            )
            raise ValueError(f"Invalid API response format: {e}")
    
    async def health_check(self) -> bool:
        """Check if WB API is accessible."""
        try:
            test_url = self._build_search_url("test", 1)
            
            async with self.session.get(test_url) as response:
                return response.status == 200
                
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return False
    
    def get_stats(self) -> Dict[str, int]:
        """Get adapter statistics."""
        return {
            "concurrency_limit": self.settings.wb_concurrency_limit,
            "retry_attempts": self.settings.wb_retry_attempts,
            "request_timeout": self.settings.wb_request_timeout,
            "max_pages": self.settings.wb_max_pages,
        }
