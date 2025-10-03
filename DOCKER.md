# WB Ranker Bot - Docker Deployment

Этот документ описывает развертывание WB Ranker Bot с использованием Docker и Docker Compose.

## Быстрый старт

### 1. Подготовка окружения

Создайте файл `.env` в корне проекта:

```bash
# Bot configuration
BOT_TOKEN=your_telegram_bot_token

# WB API configuration
WB_API_BASE_URL=https://search.wb.ru/exactmatch/ru/common/v5/search
WB_MAX_PAGES=5
WB_CONCURRENCY_LIMIT=15
WB_REQUEST_TIMEOUT=10
WB_RETRY_ATTEMPTS=3
WB_BACKOFF_FACTOR=2.0
WB_DELAY_BETWEEN_REQUESTS=0.5,1.5

# File processing configuration
MAX_KEYWORDS_LIMIT=100000
MAX_EXECUTION_TIME_MINUTES=30

# Logging configuration
LOG_LEVEL=INFO
LOG_FORMAT=json

# Output configuration
OUTPUT_DIRECTORY=/app/output
```

### 2. Развертывание

#### Производственное окружение

```bash
# Автоматическое развертывание
./deploy.sh deploy

# Или вручную
make build
make up
```

#### Разработка

```bash
# Развертывание для разработки
./deploy.sh dev

# Или вручную
make dev-up
```

## Управление сервисами

### Основные команды

```bash
# Просмотр статуса
make status

# Просмотр логов
make logs

# Остановка сервисов
make down

# Перезапуск
make restart

# Очистка
make clean
```

### Команды для разработки

```bash
# Просмотр логов разработки
make dev-logs

# Открыть shell в контейнере разработки
make dev-shell

# Запустить тесты
make dev-test

# Остановить сервисы разработки
make dev-down
```

## Мониторинг

### Prometheus и Grafana

```bash
# Запуск мониторинга
make monitor-up

# Остановка мониторинга
make monitor-down
```

- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)

### Проверка здоровья

```bash
# Проверка состояния бота
make health
```

### Тестирование Docker

```bash
# Проверка сборки образа
docker build -t wb-ranker-bot-test .

# Тест конфигурации
docker run --rm wb-ranker-bot-test python -c "from app.config import Settings; print('✅ Config OK')"

# Тест с переменными окружения
docker run --rm -e BOT_TOKEN=test wb-ranker-bot-test python -c "from app.config import Settings; s = Settings(); print(f'✅ Bot token: {s.bot_token[:10]}...')"

# Тест асинхронных функций
docker run --rm wb-ranker-bot-test python -c "
import asyncio
from app.utils import get_product_info

async def test():
    result = await get_product_info(999999999)
    print(f'✅ Fallback result: {result.get(\"is_fallback\", False)}')

asyncio.run(test())
"
```

## Структура проекта

```
├── Dockerfile              # Production image
├── Dockerfile.dev          # Development image
├── docker-compose.yml      # Production services
├── docker-compose.dev.yml  # Development services
├── .dockerignore           # Docker ignore file
├── Makefile               # Management commands
├── deploy.sh              # Deployment script
├── monitoring/            # Monitoring configuration
│   ├── prometheus.yml
│   └── grafana/
│       ├── datasources/
│       └── dashboards/
├── output/                # Output files (mounted)
└── logs/                  # Log files (mounted)
```

## Сервисы

### Основные сервисы

- **wb-ranker-bot**: Основное приложение
- **redis**: Кэширование и управление сессиями
- **prometheus**: Сбор метрик
- **grafana**: Визуализация метрик

### Сервисы разработки

- **wb-ranker-bot-dev**: Приложение для разработки
- **postgres-dev**: База данных для разработки
- **redis-dev**: Redis для разработки

## Конфигурация

### Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `BOT_TOKEN` | Токен Telegram бота | - |
| `WB_MAX_PAGES` | Максимум страниц для поиска | 5 |
| `WB_CONCURRENCY_LIMIT` | Лимит одновременных запросов | 15 |
| `WB_REQUEST_TIMEOUT` | Таймаут запросов (сек) | 10 |
| `MAX_KEYWORDS_LIMIT` | Максимум ключевых слов | 100000 |
| `LOG_LEVEL` | Уровень логирования | INFO |
| `OUTPUT_DIRECTORY` | Директория для файлов | /app/output |

### Ресурсы

#### Production
- **Memory**: 512MB limit, 256MB reserved
- **CPU**: 0.5 cores limit, 0.25 cores reserved
- **Concurrency**: 15 параллельных запросов к WB API
- **Keywords**: до 100,000 ключевых слов
- **Performance**: ~5.8 секунд для 8 ключевых слов

#### Development
- **Memory**: No limits
- **CPU**: No limits

## Troubleshooting

### Проблемы с запуском

1. **Проверьте .env файл**:
   ```bash
   cat .env
   ```

2. **Проверьте логи**:
   ```bash
   make logs
   ```

3. **Проверьте статус**:
   ```bash
   make status
   ```

### Проблемы с производительностью

1. **Увеличьте ресурсы** в `docker-compose.yml`
2. **Настройте лимиты** WB API
3. **Проверьте мониторинг** в Grafana

### Очистка

```bash
# Полная очистка
make clean

# Очистка только контейнеров
docker-compose down

# Очистка с удалением volumes
docker-compose down -v
```

## Безопасность

- Приложение запускается под непривилегированным пользователем
- Используются секреты из переменных окружения
- Ограничены ресурсы контейнеров
- Изолированная сеть для сервисов

## Обновление

```bash
# Остановить сервисы
make down

# Обновить код
git pull

# Пересобрать и запустить
make build
make up
```
