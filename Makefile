# Makefile for WB Ranker Bot Docker management

.PHONY: help build up down logs shell test clean dev-up dev-down dev-logs dev-shell

# Default target
help:
	@echo "Available commands:"
	@echo "  build      - Build Docker image"
	@echo "  up         - Start production containers"
	@echo "  down       - Stop production containers"
	@echo "  logs       - Show production logs"
	@echo "  shell      - Open shell in production container"
	@echo "  test       - Run tests in container"
	@echo "  clean      - Clean up containers and volumes"
	@echo "  dev-up     - Start development containers"
	@echo "  dev-down   - Stop development containers"
	@echo "  dev-logs   - Show development logs"
	@echo "  dev-shell  - Open shell in development container"

# Production commands
build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f wb-ranker-bot

shell:
	docker-compose exec wb-ranker-bot /bin/bash

test:
	docker-compose exec wb-ranker-bot python -m pytest tests/ -v

clean:
	docker-compose down -v --remove-orphans
	docker system prune -f

# Development commands
dev-up:
	docker-compose -f docker-compose.dev.yml up -d

dev-down:
	docker-compose -f docker-compose.dev.yml down

dev-logs:
	docker-compose -f docker-compose.dev.yml logs -f wb-ranker-bot-dev

dev-shell:
	docker-compose -f docker-compose.dev.yml exec wb-ranker-bot-dev /bin/bash

dev-test:
	docker-compose -f docker-compose.dev.yml exec wb-ranker-bot-dev python -m pytest tests/ -v

dev-clean:
	docker-compose -f docker-compose.dev.yml down -v --remove-orphans

# Utility commands
status:
	docker-compose ps

restart:
	docker-compose restart wb-ranker-bot

# Monitoring commands
monitor-up:
	docker-compose up -d prometheus grafana

monitor-down:
	docker-compose stop prometheus grafana

# Backup commands
backup:
	mkdir -p backups
	docker-compose exec wb-ranker-bot tar -czf /tmp/backup.tar.gz /app/output
	docker cp wb-ranker-bot:/tmp/backup.tar.gz backups/backup-$(shell date +%Y%m%d-%H%M%S).tar.gz

# Health check
health:
	docker-compose exec wb-ranker-bot python -c "import requests; print('Bot is healthy' if requests.get('http://localhost:8000/health', timeout=5).status_code == 200 else 'Bot is unhealthy')"
