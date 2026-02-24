"""Tests for PII Admin router — scan, mask, config endpoints.

Covers: RBAC enforcement (cpi-admin only), PII detection, masking,
and configuration retrieval.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.core.pii.config import MaskingLevel, PIIMaskingConfig
from src.core.pii.patterns import PIIType

MASKER_PATH = "src.routers.pii_admin.get_masker"


# ── Helpers ──────────────────────────────────────────────────────


def _make_masker(
    detect_result: dict | None = None,
    mask_result: str = "masked",
    config: PIIMaskingConfig | None = None,
):
    masker = MagicMock()
    masker.detect_only.return_value = detect_result or {}
    masker.mask.return_value = mask_result
    masker.config = config or PIIMaskingConfig.default_production()
    return masker


# ── POST /v1/admin/pii/scan ─────────────────────────────────────


class TestScanEndpoint:
    def test_scan_no_pii(self, client_as_cpi_admin: TestClient):
        with patch(MASKER_PATH, return_value=_make_masker()):
            resp = client_as_cpi_admin.post(
                "/v1/admin/pii/scan", json={"text": "Hello world"}
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["detections"] == []
        assert data["total_pii_count"] == 0
        assert data["text_length"] == 11

    def test_scan_with_email_pii(self, client_as_cpi_admin: TestClient):
        detect = {PIIType.EMAIL: ["user@example.com", "admin@test.com"]}
        with patch(MASKER_PATH, return_value=_make_masker(detect_result=detect)):
            resp = client_as_cpi_admin.post(
                "/v1/admin/pii/scan",
                json={"text": "Contact user@example.com or admin@test.com"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["detections"]) == 1
        assert data["detections"][0]["pii_type"] == "email"
        assert data["detections"][0]["count"] == 2
        assert data["total_pii_count"] == 2

    def test_scan_multiple_pii_types(self, client_as_cpi_admin: TestClient):
        detect = {
            PIIType.EMAIL: ["a@b.com"],
            PIIType.PHONE: ["+33612345678"],
            PIIType.IBAN: ["FR7630001007941234567890185"],
        }
        with patch(MASKER_PATH, return_value=_make_masker(detect_result=detect)):
            resp = client_as_cpi_admin.post(
                "/v1/admin/pii/scan", json={"text": "mixed PII content"}
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["detections"]) == 3
        assert data["total_pii_count"] == 3

    def test_scan_empty_text(self, client_as_cpi_admin: TestClient):
        with patch(MASKER_PATH, return_value=_make_masker()):
            resp = client_as_cpi_admin.post(
                "/v1/admin/pii/scan", json={"text": ""}
            )
        assert resp.status_code == 200
        assert resp.json()["text_length"] == 0

    def test_scan_403_tenant_admin(self, client_as_tenant_admin: TestClient):
        resp = client_as_tenant_admin.post(
            "/v1/admin/pii/scan", json={"text": "test"}
        )
        assert resp.status_code == 403

    def test_scan_422_missing_text(self, client_as_cpi_admin: TestClient):
        resp = client_as_cpi_admin.post("/v1/admin/pii/scan", json={})
        assert resp.status_code == 422


# ── POST /v1/admin/pii/mask ─────────────────────────────────────


class TestMaskEndpoint:
    def test_mask_no_pii(self, client_as_cpi_admin: TestClient):
        masker = _make_masker(mask_result="Hello world")
        with patch(MASKER_PATH, return_value=masker):
            resp = client_as_cpi_admin.post(
                "/v1/admin/pii/mask", json={"text": "Hello world"}
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["masked_text"] == "Hello world"
        assert data["detections"] == []

    def test_mask_with_pii(self, client_as_cpi_admin: TestClient):
        detect = {PIIType.EMAIL: ["user@example.com"]}
        masker = _make_masker(
            detect_result=detect,
            mask_result="Contact [EMAIL_MASKED]",
        )
        with patch(MASKER_PATH, return_value=masker):
            resp = client_as_cpi_admin.post(
                "/v1/admin/pii/mask",
                json={"text": "Contact user@example.com"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "MASKED" in data["masked_text"]
        assert data["original_length"] == len("Contact user@example.com")
        assert len(data["detections"]) == 1

    def test_mask_403_tenant_admin(self, client_as_tenant_admin: TestClient):
        resp = client_as_tenant_admin.post(
            "/v1/admin/pii/mask", json={"text": "test"}
        )
        assert resp.status_code == 403

    def test_mask_422_missing_text(self, client_as_cpi_admin: TestClient):
        resp = client_as_cpi_admin.post("/v1/admin/pii/mask", json={})
        assert resp.status_code == 422


# ── GET /v1/admin/pii/config ────────────────────────────────────


class TestConfigEndpoint:
    def test_config_returns_defaults(self, client_as_cpi_admin: TestClient):
        config = PIIMaskingConfig.default_production()
        masker = _make_masker(config=config)
        with patch(MASKER_PATH, return_value=masker):
            resp = client_as_cpi_admin.get("/v1/admin/pii/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["level"] in ("strict", "moderate", "minimal", "disabled")
        assert isinstance(data["pii_types"], list)
        assert len(data["pii_types"]) > 0
        assert isinstance(data["disabled_types"], list)
        assert isinstance(data["exempt_roles"], list)
        assert data["max_text_length"] > 0

    def test_config_disabled_masking(self, client_as_cpi_admin: TestClient):
        config = PIIMaskingConfig(enabled=False)
        masker = _make_masker(config=config)
        with patch(MASKER_PATH, return_value=masker):
            resp = client_as_cpi_admin.get("/v1/admin/pii/config")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_config_403_tenant_admin(self, client_as_tenant_admin: TestClient):
        resp = client_as_tenant_admin.get("/v1/admin/pii/config")
        assert resp.status_code == 403

    def test_config_403_viewer(self, client_as_no_tenant_user: TestClient):
        resp = client_as_no_tenant_user.get("/v1/admin/pii/config")
        assert resp.status_code == 403
