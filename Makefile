# Makefile

.PHONY: dev down logs shell db-migrate db-revision clean

dev: ## Start development environment
	@docker compose -f docker-compose.dev.yml up --build -d
	@echo "✅ Development environment ready at http://localhost:8010"

down: ## Stop development environment
	@docker compose -f docker-compose.dev.yml down

logs: ## Show logs
	@docker compose -f docker-compose.dev.yml logs -f

shell: ## API container shell
	@docker compose -f docker-compose.dev.yml exec api bash

db-migrate: ## Run database migrations
	@echo "🔄 Running database migrations..."
	@docker compose -f docker-compose.dev.yml exec api uv run alembic upgrade head

db-revision: ## Autogenerate a new migration - usage: make db-revision m="message"
	@docker compose -f docker-compose.dev.yml exec api uv run alembic revision --autogenerate -m "$(m)"

clean: ## Clean everything
	@docker compose -f docker-compose.dev.yml down -v
	@docker system prune -f
