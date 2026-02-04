# STOA Platform — Developer Makefile
# Usage: make <target>

.PHONY: seed-demo test-demo migrate-kong migrate-kong-dry-run test-migrate-kong test-migrate-kong-integration help

# ── Demo Data ──────────────────────────────────────────────────────────────

seed-demo: ## Seed demo data (APIs, apps, metrics) — requires ANORAK_PASSWORD
	@echo "==> Seeding demo data..."
	python3 scripts/seed-demo-data.py

test-demo: ## Run E2E demo tests (@demo tag)
	@echo "==> Running demo E2E tests..."
	cd e2e && npm run test:demo

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
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
