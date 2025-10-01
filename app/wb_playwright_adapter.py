"""Simplified Wildberries adapter using Playwright."""

import asyncio
import random
from typing import Dict, List, Optional
from urllib.parse import urlencode

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from app.config import Settings
from app.ports import SearchClient, SearchResult, Product, Logger
from app.utils import format_price, calculate_position


class WBPlaywrightAdapter(SearchClient):
    """Simplified Wildberries adapter using Playwright."""
    
    def __init__(self, settings: Settings, logger: Logger):
        self.settings = settings
        self.logger = logger
        self._semaphore = asyncio.Semaphore(settings.wb_concurrency_limit)
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        try:
            self._playwright = await async_playwright().start()
            
            # Launch browser with minimal settings
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage']
            )
            
            # Create context
            self._context = await self._browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            return self
        except Exception as e:
            self.logger.error(f"Failed to initialize Playwright: {e}")
            raise
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            # Ignore errors during shutdown
            self.logger.debug(f"Error closing Playwright (ignored): {e}")
    
    async def search_product(
        self, 
        keyword: str, 
        product_id: int, 
        max_pages: int = 5
    ) -> SearchResult:
        """Search for a product by keyword."""
        async with self._semaphore:
            return await self._search_product_pages(keyword, product_id, max_pages)
    
    async def _search_product_pages(
        self, 
        keyword: str, 
        product_id: int, 
        max_pages: int
    ) -> SearchResult:
        """Search product across multiple pages."""
        self.logger.debug(f"Searching product {product_id} for keyword '{keyword}'")
        
        try:
            for page_num in range(1, max_pages + 1):
                try:
                    # Add delay between requests
                    if page_num > 1:
                        min_delay, max_delay = self.settings.wb_delay_between_requests
                        delay = random.uniform(min_delay, max_delay)
                        await asyncio.sleep(delay)
                    
                    # Search current page
                    products = await self._search_page_with_playwright(keyword, page_num)
                    
                    # Log page results
                    self.logger.info(f"Page {page_num}: found {len(products)} products")
                    if products:
                        first_5_ids = [p.id for p in products[:5]]
                        self.logger.info(f"First 5 product IDs on page {page_num}: {first_5_ids}")
                    
                    # Look for our product
                    self.logger.debug(f"Looking for product {product_id} among {len(products)} products on page {page_num}")
                    all_product_ids = [p.id for p in products]
                    self.logger.debug(f"All product IDs on page {page_num}: {all_product_ids}")
                    
                    for index, product in enumerate(products):
                        self.logger.debug(f"Checking product {product.id} (index {index}) against target {product_id}")
                        if product.id == product_id:
                            position = calculate_position(page_num, index)
                            
                            self.logger.info(f"✅ FOUND! Product {product_id} at position {position} (page {page_num}, index {index})")
                            self.logger.info(f"Product details: name='{product.name}', brand='{product.brand}', price={product.price_rub}")
                            
                            return SearchResult(
                                keyword=keyword,
                                product=product,
                                position=position,
                                page=page_num,
                                total_pages_searched=page_num
                            )
                    
                except Exception as e:
                    self.logger.error(f"Error searching page {page_num}: {e}")
                    continue
            
            # Product not found
            self.logger.info(f"Product {product_id} not found in {max_pages} pages")
            
            return SearchResult(
                keyword=keyword,
                product=None,
                position=None,
                page=None,
                total_pages_searched=max_pages
            )
            
        except Exception as e:
            self.logger.error(f"Error searching product {product_id}: {e}")
            return SearchResult(
                keyword=keyword,
                product=None,
                position=None,
                page=None,
                total_pages_searched=0,
                error=str(e)
            )
    
    async def _search_page_with_playwright(self, keyword: str, page_num: int) -> List[Product]:
        """Search a single page using Playwright."""
        page = await self._context.new_page()
        
        try:
            # Build search URL
            search_url = self._build_search_url(keyword, page_num)
            
            self.logger.info(f"🔍 Searching page {page_num} for keyword '{keyword}'")
            self.logger.info(f"🌐 URL: {search_url}")
            
            # Set realistic browser headers to avoid detection
            await page.set_extra_http_headers({
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            })
            
            # Navigate to search page with longer timeout
            self.logger.info(f"⏳ Loading page...")
            await page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
            self.logger.info(f"✅ Page loaded successfully")
            
            # Simulate human behavior - random delay
            import random
            delay = random.uniform(1.0, 3.0)
            self.logger.debug(f"⏸️ Waiting {delay:.1f}s to simulate human behavior...")
            await asyncio.sleep(delay)
            
            # Scroll down to trigger lazy loading
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
            # Wait for products to load with shorter timeout
            try:
                await page.wait_for_selector('[data-testid="product-card"]', timeout=5000)
            except:
                try:
                    # Try alternative selectors
                    await page.wait_for_selector('.product-card', timeout=3000)
                except:
                    # If no products found, continue anyway
                    pass
            
            # Extract product data
            products = await self._extract_products_from_page(page)
            
            # Debug: check if we got any products
            if not products:
                self.logger.warning(f"No products found on page {page_num} for keyword '{keyword}'")
                # Try to get page content for debugging
                try:
                    page_content = await page.content()
                    self.logger.debug(f"Page content length: {len(page_content)}")
                    if "captcha" in page_content.lower() or "проверка" in page_content.lower():
                        self.logger.error(f"CAPTCHA detected on page {page_num} for keyword '{keyword}'")
                    elif "товар" in page_content.lower() and "не найден" in page_content.lower():
                        self.logger.info(f"No products found message detected on page {page_num}")
                    else:
                        self.logger.debug(f"Page content preview: {page_content[:200]}...")
                except Exception as e:
                    self.logger.debug(f"Could not get page content: {e}")
            
            return products
            
        except Exception as e:
            self.logger.error(f"Error in Playwright search: {e}")
            return []
        finally:
            await page.close()
    
    def _build_search_url(self, keyword: str, page_num: int) -> str:
        """Build search URL for Wildberries."""
        params = {
            'query': keyword,
            'page': page_num,
            'sort': 'popular',
            'locale': 'ru',
            'lang': 'ru',
            'curr': 'rub',
            'dest': '-1257786',
            'appType': '1',
            'resultset': 'catalog'
        }
        
        query_string = urlencode(params)
        return f"https://www.wildberries.ru/catalog/0/search.aspx?{query_string}"
    
    async def _extract_products_from_page(self, page: Page) -> List[Product]:
        """Extract product information from the current page."""
        try:
            # Extract product data using JavaScript
            products_data = await page.evaluate("""
                () => {
                    const products = [];
                    
                    // Try multiple selectors
                    const selectors = [
                        '[data-testid="product-card"]',
                        '.product-card',
                        '.catalog-product-card'
                    ];
                    
                    let cards = [];
                    for (const selector of selectors) {
                        cards = document.querySelectorAll(selector);
                        if (cards.length > 0) break;
                    }
                    
                    cards.forEach((card, index) => {
                        try {
                            // Extract product ID from link
                            const link = card.querySelector('a[href*="/catalog/"]');
                            if (!link) return;
                            
                            const href = link.getAttribute('href');
                            const idMatch = href.match(/\\/catalog\\/(\\d+)/);
                            if (!idMatch) return;
                            
                            const productId = parseInt(idMatch[1]);
                            
                            // Extract product name
                            const nameElement = card.querySelector('[data-testid="product-name"]') || 
                                             card.querySelector('.product-card__name') ||
                                             card.querySelector('span[title]') ||
                                             card.querySelector('.product-card__link');
                            const name = nameElement ? nameElement.textContent.trim() : 'Unknown Product';
                            
                            // Extract price
                            const priceElement = card.querySelector('[data-testid="price-current"]') ||
                                              card.querySelector('.price__lower-price') ||
                                              card.querySelector('.price-current') ||
                                              card.querySelector('.product-card__price-current');
                            let price = 0;
                            if (priceElement) {
                                const priceText = priceElement.textContent.replace(/[^\\d]/g, '');
                                price = parseInt(priceText) || 0;
                            }
                            
                            // Extract brand
                            const brandElement = card.querySelector('[data-testid="product-brand"]') ||
                                              card.querySelector('.product-card__brand');
                            const brand = brandElement ? brandElement.textContent.trim() : '';
                            
                            // Extract rating
                            const ratingElement = card.querySelector('[data-testid="rating"]') ||
                                                card.querySelector('.product-card__rating');
                            let rating = 0.0;
                            if (ratingElement) {
                                const ratingText = ratingElement.textContent;
                                const ratingMatch = ratingText.match(/(\\d+(?:\\.\\d+)?)/);
                                if (ratingMatch) {
                                    rating = parseFloat(ratingMatch[1]);
                                }
                            }
                            
                            // Extract feedbacks count
                            const feedbacksElement = card.querySelector('[data-testid="feedbacks-count"]') ||
                                                   card.querySelector('.product-card__feedbacks');
                            let feedbacks = 0;
                            if (feedbacksElement) {
                                const feedbacksText = feedbacksElement.textContent.replace(/[^\\d]/g, '');
                                feedbacks = parseInt(feedbacksText) || 0;
                            }
                            
                            products.push({
                                id: productId,
                                name: name,
                                price: price,
                                brand: brand,
                                rating: rating,
                                feedbacks: feedbacks
                            });
                        } catch (error) {
                            console.error('Error extracting product data:', error);
                        }
                    });
                    
                    return products;
                }
            """)
            
            # Convert to Product objects
            products = []
            for product_data in products_data:
                try:
                    product = Product(
                        id=product_data['id'],
                        name=product_data['name'],
                        price_rub=format_price(product_data['price']),
                        brand=product_data['brand'],
                        rating=product_data['rating'],
                        feedbacks=product_data['feedbacks']
                    )
                    products.append(product)
                except Exception as e:
                    self.logger.warning(f"Failed to create Product object: {e}")
                    continue
            
            self.logger.debug(f"Extracted {len(products)} products from page")
            return products
            
        except Exception as e:
            self.logger.error(f"Error extracting products from page: {e}")
            return []
    
    async def health_check(self) -> bool:
        """Check if the adapter is healthy."""
        try:
            page = await self._context.new_page()
            await page.goto('https://www.wildberries.ru/', timeout=10000)
            await page.close()
            return True
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return False