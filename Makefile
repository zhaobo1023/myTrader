.PHONY: dev prod build down logs api-test redis-cli mysql-cli clean help api-local api-https gen-cert trust-cert api-logs api-errors api-access

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

api-local: ## Run FastAPI locally (LOG_LEVEL=DEBUG, port 8001)
	PYTHONPATH=. LOG_LEVEL=$${LOG_LEVEL:-DEBUG} DB_ENV=$${DB_ENV:-online} \
	uvicorn api.main:app --reload --host 0.0.0.0 --port $${API_PORT:-8001} \
	--log-level $$(echo $${LOG_LEVEL:-debug} | tr '[:upper:]' '[:lower:]')

api-https: ## Run FastAPI locally with HTTPS (requires certs/localhost.key + certs/localhost.crt)
	@test -f certs/localhost.key || (echo "Run 'make gen-cert' first"; exit 1)
	PYTHONPATH=. LOG_LEVEL=$${LOG_LEVEL:-DEBUG} DB_ENV=$${DB_ENV:-local} \
	uvicorn api.main:app --reload --host 0.0.0.0 --port $${API_PORT:-8443} \
	--ssl-keyfile certs/localhost.key --ssl-certfile certs/localhost.crt \
	--log-level $$(echo $${LOG_LEVEL:-debug} | tr '[:upper:]' '[:lower:]')

gen-cert: ## Generate self-signed TLS cert for localhost (valid 825 days)
	@mkdir -p certs
	openssl req -x509 -nodes -days 825 -newkey rsa:2048 \
	  -keyout certs/localhost.key -out certs/localhost.crt \
	  -subj "/CN=localhost/O=myTrader Dev" \
	  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
	@echo "cert generated: certs/localhost.crt"

trust-cert: ## Add self-signed cert to macOS system trust store (requires sudo)
	@test -f certs/localhost.crt || (echo "Run 'make gen-cert' first"; exit 1)
	sudo security add-trusted-cert -d -r trustRoot \
	  -k /Library/Keychains/System.keychain certs/localhost.crt
	@echo "cert trusted. Restart browser to take effect."

api-logs: ## Tail the app log
	tail -f logs/app.log

api-errors: ## Tail only errors
	tail -f logs/error.log

api-access: ## Tail the access log
	tail -f logs/access.log

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
