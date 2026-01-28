# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Tests for Sanctions Screening API.

CAB-1018: Mock APIs for Central Bank Demo
"""

import pytest
from fastapi.testclient import TestClient

from src.services.semantic_cache import normalize


class TestSanctionsScreening:
    """Tests for sanctions screening functionality."""

    def test_screening_hit_ivan_petrov(self, client: TestClient, sanctioned_entity):
        """Known sanctioned entity should return HIT."""
        response = client.post(
            "/v1/screening/check",
            json=sanctioned_entity,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["result"] == "HIT"
        assert data["confidence"] >= 90
        assert len(data["matches"]) > 0
        assert data["matches"][0]["list_name"] == "OFAC"
        assert data["cached"] is False

    def test_screening_no_hit_clean_entity(self, client: TestClient, clean_entity):
        """Clean entity should return NO_HIT."""
        response = client.post(
            "/v1/screening/check",
            json=clean_entity,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["result"] == "NO_HIT"
        assert data["confidence"] < 60
        assert len(data["matches"]) == 0

    def test_screening_partial_match(self, client: TestClient):
        """Partial name match should return PARTIAL_MATCH."""
        response = client.post(
            "/v1/screening/check",
            json={
                "entity_name": "Petrov",
                "entity_type": "PERSON",
                "country": "RU",
            },
        )

        assert response.status_code == 200
        data = response.json()
        # Partial match: "Petrov" in "Ivan Petrov"
        assert data["result"] in ["PARTIAL_MATCH", "HIT"]
        assert data["confidence"] >= 60

    def test_screening_organization(self, client: TestClient):
        """Organization screening should work."""
        response = client.post(
            "/v1/screening/check",
            json={
                "entity_name": "Omega Trading Corp",
                "entity_type": "ORGANIZATION",
                "country": "IR",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["result"] == "HIT"
        assert data["entity_type"] == "ORGANIZATION"


class TestSemanticCache:
    """Tests for semantic cache functionality."""

    def test_cache_hit_second_request(self, client: TestClient, sanctioned_entity):
        """Second request should be cache hit."""
        # First request - cache miss
        response1 = client.post(
            "/v1/screening/check",
            json=sanctioned_entity,
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["cached"] is False

        # Second request - cache hit
        response2 = client.post(
            "/v1/screening/check",
            json=sanctioned_entity,
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["cached"] is True
        assert data2["result"] == data1["result"]

    def test_normalize_case_insensitive(self, client: TestClient):
        """Normalized names should produce cache hit."""
        # First request - lowercase
        response1 = client.post(
            "/v1/screening/check",
            json={
                "entity_name": "ivan petrov",
                "entity_type": "PERSON",
                "country": "RU",
            },
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["cached"] is False

        # Second request - uppercase (should be cache hit)
        response2 = client.post(
            "/v1/screening/check",
            json={
                "entity_name": "IVAN PETROV",
                "entity_type": "PERSON",
                "country": "RU",
            },
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["cached"] is True

    def test_normalize_hyphen_handling(self, client: TestClient):
        """Hyphens should be normalized to spaces."""
        # First request with spaces
        response1 = client.post(
            "/v1/screening/check",
            json={
                "entity_name": "Kim Jong sik",
                "entity_type": "PERSON",
                "country": "KP",
            },
        )
        assert response1.status_code == 200
        data1 = response1.json()

        # Second request with hyphen (should be cache hit)
        response2 = client.post(
            "/v1/screening/check",
            json={
                "entity_name": "Kim Jong-sik",
                "entity_type": "PERSON",
                "country": "KP",
            },
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["cached"] is True

    def test_cache_clear(self, client: TestClient, sanctioned_entity):
        """Cache clear should reset cache."""
        # Create cache entry
        response1 = client.post(
            "/v1/screening/check",
            json=sanctioned_entity,
        )
        assert response1.json()["cached"] is False

        # Clear cache
        clear_response = client.post("/demo/trigger/cache-clear")
        assert clear_response.status_code == 200

        # Should be cache miss again
        response2 = client.post(
            "/v1/screening/check",
            json=sanctioned_entity,
        )
        assert response2.json()["cached"] is False


class TestNormalizeFunction:
    """Tests for the normalize function."""

    def test_normalize_lowercase(self):
        """Should convert to lowercase."""
        assert normalize("IVAN PETROV") == "ivan petrov"

    def test_normalize_strip_whitespace(self):
        """Should strip leading/trailing whitespace."""
        assert normalize("  Ivan Petrov  ") == "ivan petrov"

    def test_normalize_replace_hyphens(self):
        """Should replace hyphens with spaces."""
        assert normalize("Kim Jong-sik") == "kim jong sik"

    def test_normalize_collapse_spaces(self):
        """Should collapse multiple spaces."""
        assert normalize("Ivan    Petrov") == "ivan petrov"


class TestListVersions:
    """Tests for list versions endpoint."""

    def test_get_list_versions(self, client: TestClient):
        """Should return all list versions."""
        response = client.get("/v1/screening/lists/version")

        assert response.status_code == 200
        data = response.json()
        assert "lists" in data
        assert len(data["lists"]) == 3

        list_names = [lst["name"] for lst in data["lists"]]
        assert "OFAC" in list_names
        assert "EU_SANCTIONS" in list_names
        assert "UN_CONSOLIDATED" in list_names

        # Check structure
        for lst in data["lists"]:
            assert "name" in lst
            assert "version" in lst
            assert "last_updated" in lst
            assert "entry_count" in lst
            assert lst["entry_count"] > 0


class TestResponseHeaders:
    """Tests for response headers."""

    def test_screening_has_demo_headers(self, client: TestClient, sanctioned_entity):
        """Screening response should have demo headers."""
        response = client.post(
            "/v1/screening/check",
            json=sanctioned_entity,
        )

        assert response.status_code == 200
        assert response.headers.get("X-Demo-Mode") == "true"
        assert response.headers.get("X-Data-Classification") == "SYNTHETIC"
        assert "X-Trace-Id" in response.headers
