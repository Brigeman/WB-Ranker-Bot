#!/usr/bin/env python3
"""
Тестовый скрипт для проверки поиска на Wildberries
"""

import asyncio
import logging
from app.config import Settings
from app.wb_playwright_adapter import WBPlaywrightAdapter

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_search():
    """Тестируем поиск на WB"""
    
    # Создаем настройки
    settings = Settings()
    
    # Создаем адаптер
    adapter = WBPlaywrightAdapter(settings, logging.getLogger("test"))
    
    try:
        async with adapter:
            print("🚀 Запускаем тест поиска...")
            print("✅ Браузер инициализирован")
            
            # Тестируем поиск по популярному ключевому слову
            keyword = "телефон"
            product_id = 527860183  # ID товара для поиска
            
            print(f"🔍 Ищем товар {product_id} по ключевому слову '{keyword}'")
            
            result = await adapter.search_product(
                keyword=keyword,
                product_id=product_id,
                max_pages=1  # Только первая страница для теста
            )
            
            print(f"📊 Результат поиска:")
            print(f"   - Найден: {result.product is not None}")
            print(f"   - Позиция: {result.position}")
            print(f"   - Страница: {result.page}")
            print(f"   - Всего страниц: {result.total_pages_searched}")
            
            if result.product:
                print(f"   - Название: {result.product.name}")
                print(f"   - Бренд: {result.product.brand}")
                print(f"   - Цена: {result.product.price_rub} ₽")
            
            print("✅ Тест завершен!")
            
    except Exception as e:
        print(f"❌ Ошибка в тесте: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_search())