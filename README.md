# WB Ranker Bot

Telegram-бот для определения позиции товаров в поисковой выдаче Wildberries по ключевым словам.

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
# Клонируйте репозиторий
git clone <repository-url>
cd WB-Ranker-Bot

# Создайте виртуальное окружение
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# или
venv\Scripts\activate     # Windows

# Установите зависимости
pip install -r requirements.txt
```

### 2. Настройка

```bash
# Скопируйте пример конфигурации
cp env.example .env

# Отредактируйте .env файл и укажите токен бота
BOT_TOKEN=your_telegram_bot_token_here
```

### 3. Запуск

```bash
# Активируйте виртуальное окружение
source venv/bin/activate

# Запустите бота
python -m app.bot
```

## 📝 Использование

1. **Отправьте ссылку на товар Wildberries** (например: `https://www.wildberries.ru/catalog/35717482/detail.aspx`)
2. **Загрузите файл с ключевыми словами** (CSV/XLSX) или отправьте ссылку на Google Drive (https://drive.google.com/file/d/12OhUuANklqqtfyjZqleenFxG-DnPPIi6/view?usp=sharing)
3. **Дождитесь завершения анализа** - бот найдет товар, отфильтрует релевантные ключевые слова и проведет поиск
4. **Получите результаты** в виде Excel файла с позициями товара по ключевым словам

## 📊 Входные данные
- **Файл со списком ключевых слов** (CSV/XLSX или ссылка на Google Drive)
- **Ссылка на товар Wildberries** (например: `https://www.wildberries.ru/catalog/35717482/detail.aspx`)

### Пример файла с ключевыми словами (CSV)
```csv
keyword,frequency
смартфон,1000
iphone,500
телефон,800
```

## 🎯 Цель проекта

Создать Telegram-бота, который по списку ключевых слов определяет позицию заданного товара в поисковой выдаче Wildberries (до 5 страниц) и возвращает результат в виде таблицы (CSV/XLSX) с указанием:
- Номер строки
- Ключевое слово  
- Частотность
- Позиция товара
- Цена товара
- Время, затраченное на весь прогон

## ⚡ Возможности

- **Умная фильтрация ключевых слов** - автоматически отбирает релевантные ключевые слова для товара
- **Поддержка больших файлов** - обработка до 100,000 ключевых слов
- **Быстрый поиск** - параллельная обработка с настраиваемой конкуренцией (до 15 запросов одновременно)
- **Гибкие источники данных** - поддержка CSV, XLSX файлов и Google Drive ссылок
- **Детальная отчетность** - Excel файлы с полной статистикой
- **Docker поддержка** - готов к развертыванию в контейнерах
- **Мониторинг** - встроенная поддержка Prometheus и Grafana

## 🔧 Конфигурация

Основные настройки в файле `.env`:

```env
# Telegram Bot
BOT_TOKEN=your_telegram_bot_token_here

# Производительность
WB_CONCURRENCY_LIMIT=15      # Количество параллельных запросов
WB_MAX_PAGES=5               # Максимум страниц для поиска
MAX_KEYWORDS_LIMIT=100000    # Лимит ключевых слов

# Таймауты
WB_REQUEST_TIMEOUT=10        # Таймаут запроса в секундах
WB_DELAY_BETWEEN_REQUESTS=0.5,1.5  # Задержка между запросами
```

## 🐳 Docker

### Простой запуск

```bash
# Сборка образа
docker build -t wb-ranker-bot .

# Запуск с переменными окружения
docker run -d --name wb-bot \
  -e BOT_TOKEN=your_bot_token_here \
  -v $(pwd)/output:/app/output \
  wb-ranker-bot
```

### Docker Compose (рекомендуется)

```bash
# Запуск только бота
docker-compose up -d wb-ranker-bot

# Запуск с мониторингом
docker-compose up -d

# Просмотр логов
docker-compose logs -f wb-ranker-bot
```

### Тестирование Docker

```bash
# Проверка сборки
docker build -t wb-ranker-bot-test .

# Тест конфигурации
docker run --rm wb-ranker-bot-test python -c "from app.config import Settings; print('✅ Config OK')"
```

## 📋 Требования

- Python 3.11+
- Telegram Bot Token (получить у [@BotFather](https://t.me/BotFather))
- Доступ к интернету для работы с API Wildberries

## 🧪 Тестирование

```bash
# Запуск тестов
python -m pytest tests/ -v

# Тестирование с покрытием
python -m pytest tests/ --cov=app --cov-report=html

# Тестирование Docker
docker build -t wb-ranker-bot-test .
docker run --rm wb-ranker-bot-test python -c "from app.config import Settings; print('✅ Config OK')"
```

## 📁 Структура проекта

```
wb-ranker-bot/
├── app/                    # Основной код приложения
│   ├── bot.py             # Telegram бот
│   ├── config.py          # Конфигурация
│   ├── services.py        # Бизнес-логика
│   ├── wb_adapter.py      # Адаптер Wildberries API
│   ├── fileio.py          # Работа с файлами
│   ├── exporter.py        # Экспорт результатов
│   └── utils.py           # Утилиты
├── tests/                 # Тесты
├── monitoring/            # Мониторинг (Prometheus/Grafana)
├── Dockerfile            # Docker образ
├── docker-compose.yml    # Docker Compose
├── requirements.txt      # Python зависимости
└── README.md            # Документация
```

## 🔧 Разработка

### Архитектура
- **Clean Architecture** с портами и адаптерами
- **Dependency Injection** для тестируемости
- **Асинхронное программирование** для производительности

### Принципы
- **Single Responsibility** - каждый модуль отвечает за одну задачу
- **Error Handling** - обработка ошибок API с retry логикой
- **Type Safety** - строгая типизация с Pydantic
- **Observability** - подробное логирование

## 📊 Мониторинг

```bash
# Запуск с мониторингом
docker-compose up -d

# Доступ к Grafana
open http://localhost:3000
# Логин: admin, Пароль: admin

# Доступ к Prometheus
open http://localhost:9090
```

## 🚀 Деплой

### Docker
```bash
# Продакшн деплой
docker-compose -f docker-compose.yml up -d wb-ranker-bot
```

### Переменные окружения
```env
BOT_TOKEN=your_bot_token
WB_CONCURRENCY_LIMIT=15
WB_MAX_PAGES=5
MAX_KEYWORDS_LIMIT=100000
```

## 📝 Лицензия

MIT License