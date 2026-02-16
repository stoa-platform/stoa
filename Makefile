# STOA Platform — Developer Makefile
# Usage: make <target>

.PHONY: setup test lint run-api run-ui run-portal run-gateway \
	test-api test-ui test-portal test-gateway test-cli \
	lint-api lint-ui lint-portal lint-gateway lint-cli \
	check-docs \
	seed-demo test-demo demo-federation-setup demo-federation-test \
	demo-federation-live demo-federation-cleanup demo-opensearch-seed \
	demo-opensearch-test demo-opensearch-live \
	migrate-kong migrate-kong-dry-run test-migrate-kong test-migrate-kong-integration \
	help

# ── Setup ────────────────────────────────────────────────────────────────────

setup: ## Install dependencies for all components
	@echo "==> Setting up control-plane-api..."
	cd control-plane-api && pip install -r requirements.txt
	@echo "==> Setting up control-plane-ui..."
	cd control-plane-ui && npm install
	@echo "==> Setting up portal..."
	cd portal && npm install
	@echo "==> Setting up stoa-gateway..."
	cd stoa-gateway && cargo check
	@echo "==> Setting up cli..."
	cd cli && pip install -e ".[dev]"
	@echo "✓ All components installed"

# ── Run ──────────────────────────────────────────────────────────────────────

run-api: ## Start Control Plane API (port 8000)
	cd control-plane-api && uvicorn src.main:app --reload --port 8000

run-ui: ## Start Console UI dev server (port 5173)
	cd control-plane-ui && npm start

run-portal: ## Start Developer Portal dev server (port 5174)
	cd portal && npm run dev

run-gateway: ## Start STOA Gateway (port 8080)
	cd stoa-gateway && cargo run

# ── Test ─────────────────────────────────────────────────────────────────────

test: test-api test-ui test-portal test-gateway test-cli ## Run all tests

test-api: ## Run control-plane-api tests
	cd control-plane-api && pytest tests/ --cov=src --cov-fail-under=58 --ignore=tests/test_opensearch.py -q

test-ui: ## Run console UI tests
	cd control-plane-ui && npm run test -- --run

test-portal: ## Run portal tests
	cd portal && npm run test -- --run

test-gateway: ## Run gateway tests
	cd stoa-gateway && cargo test

test-cli: ## Run CLI tests
	cd cli && pytest tests/ -q

# ── Lint ─────────────────────────────────────────────────────────────────────

lint: lint-api lint-ui lint-portal lint-gateway lint-cli ## Run all linters

lint-api: ## Lint control-plane-api (ruff + black)
	cd control-plane-api && ruff check . && black --check .

lint-ui: ## Lint console UI (eslint + prettier + tsc)
	cd control-plane-ui && npm run lint && npm run format:check && npx tsc -p tsconfig.app.json --noEmit

lint-portal: ## Lint portal (eslint + prettier + tsc)
	cd portal && npm run lint && npm run format:check && npx tsc -p tsconfig.app.json --noEmit

lint-gateway: ## Lint gateway (clippy + fmt)
	cd stoa-gateway && cargo fmt --check && cargo clippy --all-targets -- -D warnings

lint-cli: ## Lint CLI (ruff)
	cd cli && ruff check .

# ── Docs Validation ──────────────────────────────────────────────────────────

check-docs: ## Validate README Quick Start commands are consistent
	@echo "==> Checking component README files..."
	@for dir in control-plane-api control-plane-ui portal stoa-gateway cli; do \
		if [ ! -f "$$dir/README.md" ]; then \
			echo "FAIL: $$dir/README.md missing"; exit 1; \
		fi; \
	done
	@echo "==> Checking .env.example files..."
	@for dir in control-plane-api control-plane-ui portal stoa-gateway; do \
		if [ ! -f "$$dir/.env.example" ]; then \
			echo "FAIL: $$dir/.env.example missing"; exit 1; \
		fi; \
	done
	@echo "==> Checking Helm chart README..."
	@test -f charts/stoa-platform/README.md || (echo "FAIL: charts/stoa-platform/README.md missing"; exit 1)
	@echo "==> Checking DEVELOPMENT.md..."
	@test -f DEVELOPMENT.md || (echo "FAIL: DEVELOPMENT.md missing"; exit 1)
	@echo "✓ All documentation files present"

# ── Demo Data ──────────────────────────────────────────────────────────────

seed-demo: ## Seed demo data (APIs, apps, metrics) — requires ANORAK_PASSWORD
	@echo "==> Seeding demo data..."
	python3 scripts/seed-demo-data.py

test-demo: ## Run E2E demo tests (@demo tag)
	@echo "==> Running demo E2E tests..."
	cd e2e && npm run test:demo

# ── Federation Demo ──────────────────────────────────────────────────────

demo-federation-setup: ## Start federation demo stack (Keycloak + LDAP + gateway + OPA)
	@./scripts/demo-federation/00-setup.sh

demo-federation-test: ## Run federation isolation test (9/9 must pass)
	@./scripts/demo-federation/04-test-isolation.sh

demo-federation-live: ## Run 2-min live presenter demo (colorful output)
	@./scripts/demo-federation/06-live-demo.sh

demo-federation-cleanup: ## Tear down federation demo stack
	@./scripts/demo-federation/99-cleanup.sh

# ── OpenSearch Demo ────────────────────────────────────────────────────

demo-opensearch-seed: ## Seed error snapshots into OpenSearch only
	@./scripts/demo/seed-all.sh --opensearch-only

demo-opensearch-test: ## Verify OpenSearch error pipeline end-to-end
	@./scripts/demo/test-opensearch.sh

demo-opensearch-live: ## Run 2-min error correlation live demo
	@./scripts/demo/opensearch-live-demo.sh

# ── Kong Migration ────────────────────────────────────────────────────────

KONG_SOURCE ?= scripts/tests/fixtures/sample-kong.yaml
STOA_OUTPUT ?= .stoa-migration

migrate-kong: ## Migrate Kong config to STOA (KONG_SOURCE=kong.yaml STOA_OUTPUT=stoa/)
	@python3 scripts/migrate-kong.py --from $(KONG_SOURCE) --to $(STOA_OUTPUT)

migrate-kong-dry-run: ## Dry-run Kong migration (KONG_SOURCE=kong.yaml)
	@python3 scripts/migrate-kong.py --from $(KONG_SOURCE) --dry-run

test-migrate-kong: ## Run Kong migration unit tests
	@echo "==> Running migrate-kong tests..."
	cd scripts && python3 -m pytest tests/test_migrate_kong.py -v

test-migrate-kong-integration: ## Run Kong migration integration tests (requires Docker)
	@echo "==> Running migrate-kong integration tests (Docker required)..."
	cd scripts && python3 -m pytest tests/test_migrate_kong_integration.py -v -m integration

# ── Help ───────────────────────────────────────────────────────────────────

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
