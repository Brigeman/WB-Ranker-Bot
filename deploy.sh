#!/bin/bash

# WB Ranker Bot Deployment Script
# This script helps deploy the WB Ranker Bot using Docker

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if .env file exists
check_env_file() {
    if [ ! -f ".env" ]; then
        log_error ".env file not found!"
        log_info "Please create a .env file with the following variables:"
        echo "BOT_TOKEN=your_telegram_bot_token"
        echo "WB_API_BASE_URL=https://search.wb.ru/exactmatch/ru/common/v4/search"
        echo "WB_MAX_PAGES=5"
        echo "WB_CONCURRENCY_LIMIT=5"
        echo "WB_REQUEST_TIMEOUT=15"
        echo "WB_RETRY_ATTEMPTS=3"
        echo "WB_BACKOFF_FACTOR=2.0"
        echo "WB_DELAY_BETWEEN_REQUESTS=0.05,0.2"
        echo "MAX_KEYWORDS_LIMIT=1000"
        echo "MAX_EXECUTION_TIME_MINUTES=30"
        echo "LOG_LEVEL=INFO"
        echo "LOG_FORMAT=json"
        echo "OUTPUT_DIRECTORY=/app/output"
        exit 1
    fi
    log_success ".env file found"
}

# Create necessary directories
create_directories() {
    log_info "Creating necessary directories..."
    mkdir -p output logs
    log_success "Directories created"
}

# Build Docker image
build_image() {
    log_info "Building Docker image..."
    docker-compose build
    log_success "Docker image built successfully"
}

# Start services
start_services() {
    log_info "Starting services..."
    docker-compose up -d
    log_success "Services started"
}

# Check service health
check_health() {
    log_info "Checking service health..."
    sleep 10
    
    if docker-compose ps | grep -q "Up"; then
        log_success "Services are running"
    else
        log_error "Some services failed to start"
        docker-compose logs
        exit 1
    fi
}

# Show service status
show_status() {
    log_info "Service status:"
    docker-compose ps
}

# Show logs
show_logs() {
    log_info "Showing logs (press Ctrl+C to exit):"
    docker-compose logs -f wb-ranker-bot
}

# Main deployment function
deploy() {
    log_info "Starting WB Ranker Bot deployment..."
    
    check_env_file
    create_directories
    build_image
    start_services
    check_health
    show_status
    
    log_success "Deployment completed successfully!"
    log_info "To view logs, run: make logs"
    log_info "To stop services, run: make down"
    log_info "To restart services, run: make restart"
}

# Development deployment
deploy_dev() {
    log_info "Starting WB Ranker Bot development deployment..."
    
    check_env_file
    create_directories
    
    log_info "Building development image..."
    docker-compose -f docker-compose.dev.yml build
    
    log_info "Starting development services..."
    docker-compose -f docker-compose.dev.yml up -d
    
    log_success "Development deployment completed!"
    log_info "To view logs, run: make dev-logs"
    log_info "To stop services, run: make dev-down"
}

# Cleanup function
cleanup() {
    log_info "Cleaning up..."
    docker-compose down -v --remove-orphans
    docker system prune -f
    log_success "Cleanup completed"
}

# Show help
show_help() {
    echo "WB Ranker Bot Deployment Script"
    echo ""
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  deploy      Deploy production environment"
    echo "  dev         Deploy development environment"
    echo "  status      Show service status"
    echo "  logs        Show service logs"
    echo "  stop        Stop all services"
    echo "  restart     Restart services"
    echo "  cleanup     Clean up containers and volumes"
    echo "  help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 deploy   # Deploy production"
    echo "  $0 dev      # Deploy development"
    echo "  $0 logs     # View logs"
}

# Main script logic
case "${1:-deploy}" in
    deploy)
        deploy
        ;;
    dev)
        deploy_dev
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    stop)
        docker-compose down
        ;;
    restart)
        docker-compose restart
        ;;
    cleanup)
        cleanup
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        log_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
