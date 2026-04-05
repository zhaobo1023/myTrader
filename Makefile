.PHONY: dev prod build down logs api-test redis-cli mysql-cli clean help

# ============================================================
# myTrader Makefile
# ============================================================

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ============================================================
# Development
# ============================================================

dev: ## Start all services in dev mode (redis + api + nginx)
	docker compose up -d redis api nginx

prod: ## Start all services in production mode
	docker compose up -d --build

build: ## Build all images
	docker compose build

down: ## Stop all services
	docker compose down

logs: ## Tail logs from all services
	docker compose logs -f

logs-api: ## Tail API logs
	docker compose logs -f api

logs-redis: ## Tail Redis logs
	docker compose logs -f redis

# ============================================================
# Individual Services
# ============================================================

redis: ## Start Redis only
	docker compose up -d redis

redis-cli: ## Open Redis CLI
	docker compose exec redis redis-cli

api-only: ## Start API only (requires Redis running)
	docker compose up -d api

# ============================================================
# API Development (local, without Docker)
# ============================================================

api-local: ## Run FastAPI locally with uvicorn
	uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

api-test: ## Run API tests
	PYTHONPATH=. pytest tests/unit/api/ -v

# ============================================================
# Database
# ============================================================

mysql-cli: ## Open MySQL CLI (local)
	docker exec -it quant-mysql mysql -uroot -p

migrate: ## Run Alembic migrations
	alembic upgrade head

migrate-create: ## Create a new migration (usage: make migrate-create msg="add users table")
	alembic revision --autogenerate -m "$(msg)"

# ============================================================
# Cleanup
# ============================================================

clean: ## Remove containers, volumes, and built images
	docker compose down -v --rmi local

# ============================================================
# Utilities
# ============================================================

check: ## Check all service health
	@echo "=== Docker Services ==="
	@docker compose ps
	@echo ""
	@echo "=== API Health ==="
	@curl -s http://localhost:8000/health | python3 -m json.tool 2>/dev/null || echo "API not reachable"
	@echo ""
	@echo "=== Nginx Health ==="
	@curl -s -o /dev/null -w "HTTP %{http_code}" http://localhost/health || echo "Nginx not reachable"
