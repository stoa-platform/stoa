# STOA Mock Backends - Makefile
# CAB-1018: Demo Smoke Tests

.PHONY: help install test lint smoke-test smoke-test-local smoke-test-demo build run clean

# Configuration
DEMO_URL ?= https://demo.gostoa.dev
LOCAL_URL ?= http://localhost:8090
PYTHON ?= python3

help:
	@echo "STOA Mock Backends - Available targets:"
	@echo ""
	@echo "  install          Install dependencies"
	@echo "  test             Run tests with coverage"
	@echo "  lint             Run linter (ruff)"
	@echo "  smoke-test       Run smoke tests (local)"
	@echo "  smoke-test-demo  Run smoke tests (demo.gostoa.dev)"
	@echo "  build            Build Docker image"
	@echo "  run              Run locally with uvicorn"
	@echo "  clean            Clean up"

install:
	pip install -r requirements.txt
	pip install pytest pytest-cov pytest-asyncio ruff mypy httpx

test:
	pytest tests/ -v --tb=short --cov=src --cov-report=term-missing --cov-fail-under=70

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

smoke-test-local:
	@echo "=== Smoke Test ($(LOCAL_URL)) ==="
	@echo ""
	@echo "1. Health Check..."
	@curl -sf $(LOCAL_URL)/health | jq -e '.status == "healthy"' > /dev/null && \
		echo "   Health: OK" || (echo "   Health: FAILED" && exit 1)
	@echo ""
	@echo "2. Fraud Detection API..."
	@curl -sf -X POST $(LOCAL_URL)/v1/transactions/score \
		-H "Content-Type: application/json" \
		-d '{"transaction_id":"SMOKE-001","amount":1000,"currency":"EUR","sender_iban":"FR7630006000011234567890189","receiver_iban":"DE89370400440532013000"}' \
		| jq -e '.decision' > /dev/null && \
		echo "   Fraud API: OK" || (echo "   Fraud API: FAILED" && exit 1)
	@echo ""
	@echo "3. Settlement API..."
	@curl -sf -X POST $(LOCAL_URL)/v1/settlements \
		-H "Content-Type: application/json" \
		-H "Idempotency-Key: smoke-test-$$(date +%s)" \
		-d '{"settlement_id":"SMOKE-SETL-001","amount":500,"currency":"EUR","debtor_iban":"FR7630006000011234567890189","creditor_iban":"DE89370400440532013000"}' \
		| jq -e '.status' > /dev/null && \
		echo "   Settlement API: OK" || (echo "   Settlement API: FAILED" && exit 1)
	@echo ""
	@echo "4. Sanctions Screening API..."
	@curl -sf -X POST $(LOCAL_URL)/v1/screening/check \
		-H "Content-Type: application/json" \
		-d '{"entity_name":"John Doe","entity_type":"PERSON","country":"US"}' \
		| jq -e '.result' > /dev/null && \
		echo "   Sanctions API: OK" || (echo "   Sanctions API: FAILED" && exit 1)
	@echo ""
	@echo "=== All smoke tests passed! ==="

smoke-test-demo:
	@$(MAKE) smoke-test-local LOCAL_URL=$(DEMO_URL)

smoke-test: smoke-test-local

build:
	docker build -t mock-backends:local .

run:
	uvicorn src.main:app --host 0.0.0.0 --port 8090 --reload

clean:
	rm -rf __pycache__ .pytest_cache .coverage coverage.xml htmlcov .mypy_cache .ruff_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
