# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Pytest configuration and shared fixtures."""

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.config import clear_settings_cache


@pytest.fixture(autouse=True)
def reset_settings():
    """Reset settings cache before each test."""
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture
def client() -> TestClient:
    """Create test client for the FastAPI app."""
    return TestClient(app)
