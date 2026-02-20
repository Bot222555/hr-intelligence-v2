.PHONY: help dev up down build test lint migrate seed

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

dev: ## Start development environment
	docker compose up -d db redis
	@echo "Waiting for PostgreSQL..."
	@sleep 3
	@echo "Run: uvicorn backend.main:app --reload --port 8000"

up: ## Start all services
	docker compose up -d

down: ## Stop all services
	docker compose down

build: ## Build Docker images
	docker compose build

test: ## Run tests
	pytest --cov=backend --cov-report=term-missing -v

lint: ## Run linter
	ruff check backend/ tests/
	ruff format --check backend/ tests/

format: ## Format code
	ruff format backend/ tests/

migrate: ## Run database migrations
	alembic upgrade head

migrate-create: ## Create a new migration (usage: make migrate-create msg="description")
	alembic revision --autogenerate -m "$(msg)"

seed: ## Seed initial data
	python -m migration.seed

migrate-data: ## Run Keka data migration
	python -m migration.migrate_all

deploy: ## Deploy to production
	./scripts/deploy.sh

backup: ## Backup database
	./scripts/backup.sh
