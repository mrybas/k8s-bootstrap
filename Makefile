.PHONY: help dev build test clean test-unit test-integration test-e2e test-all test-shell test-e2e-debug update-versions update-versions-apply test-gitlab test-gitlab-start test-gitlab-stop test-gitlab-clean

# ============================================================================
# Help
# ============================================================================

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ============================================================================
# Developer Environment (Full Local Setup)
# ============================================================================

dev: ## 🚀 Start full dev environment (Git + K8s + Services)
	@chmod +x ./dev/dev.sh
	./dev/dev.sh start

dev-stop: ## Stop dev environment and remove volumes
	./dev/dev.sh clean -f

dev-stop-keep: ## Stop dev environment but keep volumes
	./dev/dev.sh stop

dev-status: ## Show dev environment status
	./dev/dev.sh status

dev-logs: ## Show dev environment logs
	./dev/dev.sh logs

dev-shell: ## 🐚 Open toolbox shell (kubectl, helm, git, k8s cluster)
	@chmod +x ./dev/dev.sh
	./dev/dev.sh shell

# ============================================================================
# Quick Development (Services Only, No K8s)
# ============================================================================

services: ## Start services only (no k8s cluster)
	docker-compose up -d

services-stop: ## Stop services
	docker-compose down

services-logs: ## Show services logs
	docker-compose logs -f

build: ## Build all containers
	docker-compose build

frontend-dev: ## Start frontend in dev mode (local)
	cd frontend && npm run dev

backend-dev: ## Start backend in dev mode (local)
	cd backend && uvicorn app.main:app --reload

install: ## Install dependencies locally
	cd backend && pip install -r requirements.txt
	cd frontend && npm install

lint: ## Run linters
	cd backend && python -m flake8 app/ || true
	cd frontend && npm run lint || true

format: ## Format code
	cd backend && python -m black app/ || true
	cd frontend && npm run lint -- --fix || true

# ============================================================================
# Testing (Docker-based, cross-platform)
# ============================================================================

test-build: ## Build test containers
	docker-compose -f tests/docker-compose.test.yml build

test-unit: test-build ## Run unit tests (fast, no cluster)
	@echo "🧪 Running unit tests..."
	docker-compose -f tests/docker-compose.test.yml up --exit-code-from test-unit test-unit

test-integration: test-build ## Run integration tests (needs backend)
	@echo "🔧 Running integration tests..."
	docker-compose -f tests/docker-compose.test.yml up -d backend
	@sleep 5
	docker-compose -f tests/docker-compose.test.yml up --exit-code-from test-integration test-integration
	docker-compose -f tests/docker-compose.test.yml stop backend

test-e2e: test-build ## Run E2E tests (creates kind cluster)
	@echo "🚀 Running E2E tests..."
	docker-compose -f tests/docker-compose.test.yml up -d backend
	@sleep 5
	docker-compose -f tests/docker-compose.test.yml up --exit-code-from test-e2e test-e2e
	docker-compose -f tests/docker-compose.test.yml stop backend

test-e2e-debug: test-build ## Run E2E tests and keep cluster for debugging
	@echo "🚀 Running E2E tests (debug mode)..."
	docker-compose -f tests/docker-compose.test.yml up -d backend
	@sleep 5
	KEEP_CLUSTER=1 docker-compose -f tests/docker-compose.test.yml up --exit-code-from test-e2e test-e2e || true
	@echo "⚠️  Cluster kept for debugging. Run 'kind get clusters' to list."

test-all: test-build ## Run all tests
	@echo "🧪 Running all tests..."
	docker-compose -f tests/docker-compose.test.yml up -d backend
	@sleep 5
	docker-compose -f tests/docker-compose.test.yml up --exit-code-from test-all test-all
	docker-compose -f tests/docker-compose.test.yml stop backend

test-shell: test-build ## Interactive test shell for debugging
	@echo "🐚 Starting interactive test shell..."
	docker-compose -f tests/docker-compose.test.yml up -d backend
	docker-compose -f tests/docker-compose.test.yml run --rm test-shell

test-file: test-build ## Run specific test file (FILE=path/to/test.py)
	@if [ -z "$(FILE)" ]; then echo "Usage: make test-file FILE=tests/unit/test_definitions.py"; exit 1; fi
	docker-compose -f tests/docker-compose.test.yml up -d backend
	@sleep 3
	docker-compose -f tests/docker-compose.test.yml run --rm test-integration pytest $(FILE) -v --tb=short

test-pattern: test-build ## Run tests matching pattern (PATTERN=pattern)
	@if [ -z "$(PATTERN)" ]; then echo "Usage: make test-pattern PATTERN=test_cert"; exit 1; fi
	docker-compose -f tests/docker-compose.test.yml up -d backend
	@sleep 3
	docker-compose -f tests/docker-compose.test.yml run --rm test-integration pytest tests/ -v -k "$(PATTERN)" --tb=short

test-coverage: test-build ## Run tests with coverage report
	docker-compose -f tests/docker-compose.test.yml up -d backend
	@sleep 3
	docker-compose -f tests/docker-compose.test.yml run --rm test-integration \
		pytest tests/unit tests/integration --cov=backend/app --cov-report=html --cov-report=term

test-clean: ## Clean up test containers and clusters
	docker-compose -f tests/docker-compose.test.yml down -v
	@echo "Cleaning up kind clusters..."
	@kind get clusters 2>/dev/null | grep "k8s-bootstrap-test" | xargs -r -I {} kind delete cluster --name {} || true
	@echo "✅ Test cleanup complete"

# Legacy test command (runs in container now)
test: test-unit ## Run unit tests (alias for test-unit)

# ============================================================================
# GitLab Tests (Resource-intensive, optional)
# ============================================================================

test-gitlab-start: ## 🦊 Start GitLab for testing (takes ~5 minutes)
	@echo "🦊 Starting GitLab (this takes ~5 minutes)..."
	docker compose -f tests/docker-compose.test.yml --profile gitlab up -d gitlab
	@echo "⏳ Waiting for GitLab to be ready..."
	@timeout 600 bash -c 'until docker compose -f tests/docker-compose.test.yml exec -T gitlab curl -sf http://localhost/-/health; do sleep 10; echo "Waiting..."; done'
	@echo "✅ GitLab is ready!"
	docker compose -f tests/docker-compose.test.yml --profile gitlab up gitlab-init

test-gitlab: test-build test-gitlab-start ## 🦊 Run GitLab E2E tests
	@echo "🧪 Running GitLab E2E tests..."
	docker compose -f tests/docker-compose.test.yml --profile gitlab up --exit-code-from test-e2e-gitlab test-e2e-gitlab

test-gitlab-stop: ## 🦊 Stop GitLab containers
	docker compose -f tests/docker-compose.test.yml --profile gitlab down

test-gitlab-clean: ## 🦊 Remove GitLab data volumes
	docker compose -f tests/docker-compose.test.yml --profile gitlab down -v

# ============================================================================
# Component Management
# ============================================================================

update-versions: ## 📦 Check for newer versions of Helm charts
	docker compose --profile tools build update-versions
	docker compose --profile tools run --rm update-versions

update-versions-apply: ## 📦 Update all charts to latest versions
	docker compose --profile tools build update-versions
	docker compose --profile tools run --rm update-versions --update

add-component: ## 🆕 Generate new component definition (interactive)
	@chmod +x ./scripts/add-component.sh
	./scripts/add-component.sh

add-component-quick: ## Generate component (REPO=url CHART=name VERSION=x.x.x)
	@if [ -z "$(REPO)" ] || [ -z "$(CHART)" ]; then \
		echo "Usage: make add-component-quick REPO=https://... CHART=my-chart VERSION=1.0.0"; \
		exit 1; \
	fi
	@chmod +x ./scripts/add-component.sh
	./scripts/add-component.sh --id $(CHART) --repo $(REPO) --chart $(CHART) --version $(VERSION)

list-components: ## List all component definitions
	@echo "📦 Components:"
	@ls -1 backend/definitions/components/*.yaml 2>/dev/null | xargs -I {} basename {} .yaml | sort

validate-component: ## Validate a component definition (COMPONENT=name)
	@if [ -z "$(COMPONENT)" ]; then echo "Usage: make validate-component COMPONENT=cert-manager"; exit 1; fi
	@echo "🔍 Validating component: $(COMPONENT)"
	@if [ ! -f "backend/definitions/components/$(COMPONENT).yaml" ]; then \
		echo "❌ Definition file not found: backend/definitions/components/$(COMPONENT).yaml"; \
		exit 1; \
	fi
	@echo "✅ Definition file exists"
	docker-compose -f tests/docker-compose.test.yml up -d backend
	@sleep 3
	docker-compose -f tests/docker-compose.test.yml run --rm test-unit \
		pytest tests/unit/test_definitions.py -v -k "$(COMPONENT)" --tb=short
	@echo "✅ Component validation complete!"

validate-all: test-build ## Validate all component definitions
	@echo "🔍 Validating all component definitions..."
	docker-compose -f tests/docker-compose.test.yml run --rm test-unit \
		pytest tests/unit/test_definitions.py -v --tb=short

# ============================================================================
# Cleanup
# ============================================================================

clean: ## Clean up containers and volumes
	docker-compose down -v
	docker-compose -f tests/docker-compose.test.yml down -v 2>/dev/null || true
	rm -rf backend/__pycache__ backend/.pytest_cache
	rm -rf frontend/.next frontend/node_modules
	rm -rf htmlcov .coverage
	@echo "Cleaning up kind clusters..."
	@kind get clusters 2>/dev/null | grep "k8s-bootstrap-test" | xargs -r -I {} kind delete cluster --name {} || true

clean-all: clean ## Deep clean including Docker images
	docker-compose down -v --rmi local
	docker-compose -f tests/docker-compose.test.yml down -v --rmi local 2>/dev/null || true
