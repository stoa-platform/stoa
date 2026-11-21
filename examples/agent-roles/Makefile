# STOA — Agent Roles Preview Demo
.PHONY: demo prepare show test help

demo: ## Build isolated local stack, run preview scenario, verify exact decision_id correlation, clean up
	./scripts/run_demo.sh --preview

prepare: ## Pre-build local Compose images for repeated operator runs
	./scripts/run_demo.sh --prepare

show: ## Run the full parent+child scenario (requires make prepare first)
	./scripts/run_demo.sh --show

test: ## Run offline unit tests for agent-roles demo scripts
	python3 -B -m unittest discover -s scripts -p 'test_*.py'

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

.DEFAULT_GOAL := demo
