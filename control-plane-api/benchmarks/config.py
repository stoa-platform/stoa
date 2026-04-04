# Copyright 2026 CAB Ingénierie — Apache 2.0
"""Benchmark configuration — environment-driven settings."""

from __future__ import annotations

import os

# Target API
API_BASE_URL = os.getenv("BENCH_API_URL", "http://localhost:8000")

# Auth — OIDC token for authenticated endpoints
AUTH_TOKEN = os.getenv("BENCH_AUTH_TOKEN", "")

# Tenant used for scoped requests
TENANT_ID = os.getenv("BENCH_TENANT_ID", "oasis")

# Concurrency profiles (users, spawn_rate, duration)
PROFILES = {
    "smoke": {"users": 5, "spawn_rate": 5, "run_time": "30s"},
    "load": {"users": 50, "spawn_rate": 10, "run_time": "120s"},
    "stress": {"users": 200, "spawn_rate": 20, "run_time": "180s"},
    "soak": {"users": 30, "spawn_rate": 5, "run_time": "600s"},
}

DEFAULT_PROFILE = os.getenv("BENCH_PROFILE", "smoke")

# Thresholds (p95 latency in ms)
THRESHOLDS = {
    "health": 50,
    "tenants_list": 300,
    "apis_list": 500,
    "portal_search": 500,
    "subscriptions_list": 400,
}
