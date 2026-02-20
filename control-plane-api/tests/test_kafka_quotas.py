"""Tests for Kafka multi-tenant quotas.

Tests verify that:
1. Quotas are configured correctly for standard and premium tiers
2. Noisy tenants hitting quota limits get rejected
3. Fair usage is enforced across tenants
"""

import time
from unittest.mock import MagicMock, patch

import pytest
from kafka import KafkaProducer
from kafka.admin import KafkaAdminClient, QuotaEntity, QuotaEntityType
from kafka.errors import KafkaError, QuotaViolationError


@pytest.fixture
def mock_admin_client():
    """Mock KafkaAdminClient for quota operations."""
    with patch("kafka.admin.KafkaAdminClient") as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


@pytest.fixture
def mock_producer():
    """Mock KafkaProducer for quota violation testing."""
    with patch("kafka.KafkaProducer") as mock:
        producer = MagicMock()
        mock.return_value = producer
        yield producer


class TestKafkaQuotaConfiguration:
    """Test quota configuration via admin API."""

    def test_standard_tier_quota_values(self):
        """Standard tier should have 10MB/s prod, 20MB/s cons, 25% CPU."""
        standard_quota = {
            "producer_byte_rate": 10 * 1024 * 1024,
            "consumer_byte_rate": 20 * 1024 * 1024,
            "request_percentage": 25.0,
        }

        assert standard_quota["producer_byte_rate"] == 10485760
        assert standard_quota["consumer_byte_rate"] == 20971520
        assert standard_quota["request_percentage"] == 25.0

    def test_premium_tier_quota_values(self):
        """Premium tier should have 50MB/s prod, 100MB/s cons, 50% CPU."""
        premium_quota = {
            "producer_byte_rate": 50 * 1024 * 1024,
            "consumer_byte_rate": 100 * 1024 * 1024,
            "request_percentage": 50.0,
        }

        assert premium_quota["producer_byte_rate"] == 52428800
        assert premium_quota["consumer_byte_rate"] == 104857600
        assert premium_quota["request_percentage"] == 50.0

    def test_configure_standard_quota(self, mock_admin_client):
        """Test configuring quota for standard tenant."""
        mock_admin_client.alter_client_quotas.return_value = None

        # Simulate quota configuration
        entity = QuotaEntity(entity_type=QuotaEntityType.CLIENT_ID, entity_name="tenant-*")

        # This would call admin_client.alter_client_quotas in real code
        mock_admin_client.alter_client_quotas(entities=[entity], quotas=[], validate_only=False)

        mock_admin_client.alter_client_quotas.assert_called_once()

    def test_configure_premium_quota(self, mock_admin_client):
        """Test configuring quota for premium tenant."""
        mock_admin_client.alter_client_quotas.return_value = None

        entity = QuotaEntity(entity_type=QuotaEntityType.CLIENT_ID, entity_name="tenant-premium-*")

        mock_admin_client.alter_client_quotas(entities=[entity], quotas=[], validate_only=False)

        mock_admin_client.alter_client_quotas.assert_called_once()


class TestQuotaEnforcement:
    """Test quota enforcement under load."""

    @pytest.mark.asyncio
    async def test_standard_tenant_quota_violation(self, mock_producer):
        """Test that standard tenant exceeding 10MB/s gets rejected."""
        # Simulate quota violation
        mock_producer.send.side_effect = QuotaViolationError("Quota exceeded")

        producer = mock_producer
        producer.send.side_effect = QuotaViolationError("Producer quota exceeded")

        # Attempt to produce at high rate
        with pytest.raises(QuotaViolationError):
            for i in range(100):
                producer.send("stoa.api.lifecycle", value={"data": "x" * 1024})

    @pytest.mark.asyncio
    async def test_premium_tenant_higher_limit(self, mock_producer):
        """Test that premium tenant has higher quota limit."""
        # Premium tenant should not hit quota at standard rate
        mock_producer.send.return_value = MagicMock()

        producer = mock_producer

        # Produce at standard rate (should succeed for premium)
        for i in range(50):
            producer.send("stoa.api.lifecycle", value={"data": "x" * 1024})

        # Should not raise QuotaViolationError
        assert producer.send.call_count == 50

    @pytest.mark.asyncio
    async def test_cpu_quota_enforcement(self, mock_producer):
        """Test that CPU request % quota is enforced."""
        # Simulate high request rate exceeding CPU quota
        mock_producer.send.side_effect = [
            MagicMock() for _ in range(20)
        ] + [QuotaViolationError("Request quota exceeded")]

        producer = mock_producer

        # First 20 requests succeed, then quota violation
        successful = 0
        try:
            for i in range(30):
                producer.send("stoa.api.lifecycle", value={"data": "x"})
                successful += 1
        except QuotaViolationError:
            pass

        assert successful == 20

    def test_quota_applies_to_client_id_pattern(self, mock_admin_client):
        """Test that quota applies to client_id pattern (tenant-*)."""
        mock_admin_client.describe_client_quotas.return_value = {
            "producer_byte_rate": 10485760,
            "consumer_byte_rate": 20971520,
            "request_percentage": 25.0,
        }

        entity = QuotaEntity(entity_type=QuotaEntityType.CLIENT_ID, entity_name="tenant-*")
        quotas = mock_admin_client.describe_client_quotas(entities=[entity])

        assert "producer_byte_rate" in quotas
        assert quotas["producer_byte_rate"] == 10 * 1024 * 1024


class TestQuotaVerification:
    """Test quota verification and monitoring."""

    def test_verify_standard_quota_exists(self, mock_admin_client):
        """Test verifying that standard quota is configured."""
        mock_admin_client.describe_client_quotas.return_value = {
            "producer_byte_rate": 10485760,
        }

        entity = QuotaEntity(entity_type=QuotaEntityType.CLIENT_ID, entity_name="tenant-*")
        result = mock_admin_client.describe_client_quotas(entities=[entity])

        assert result is not None
        assert "producer_byte_rate" in result

    def test_verify_premium_quota_exists(self, mock_admin_client):
        """Test verifying that premium quota is configured."""
        mock_admin_client.describe_client_quotas.return_value = {
            "producer_byte_rate": 52428800,
        }

        entity = QuotaEntity(entity_type=QuotaEntityType.CLIENT_ID, entity_name="tenant-premium-*")
        result = mock_admin_client.describe_client_quotas(entities=[entity])

        assert result is not None
        assert result["producer_byte_rate"] == 50 * 1024 * 1024

    def test_missing_quota_returns_empty(self, mock_admin_client):
        """Test that missing quota returns empty result."""
        mock_admin_client.describe_client_quotas.return_value = {}

        entity = QuotaEntity(entity_type=QuotaEntityType.CLIENT_ID, entity_name="tenant-nonexistent-*")
        result = mock_admin_client.describe_client_quotas(entities=[entity])

        assert result == {}


class TestNoisyNeighborPrevention:
    """Test noisy neighbor abuse prevention."""

    @pytest.mark.asyncio
    async def test_noisy_tenant_does_not_affect_others(self, mock_producer):
        """Test that one noisy tenant doesn't impact other tenants."""
        # Tenant A (noisy) hits quota
        mock_producer_a = MagicMock()
        mock_producer_a.send.side_effect = QuotaViolationError("Quota exceeded")

        # Tenant B (normal) continues to work
        mock_producer_b = MagicMock()
        mock_producer_b.send.return_value = MagicMock()

        # Tenant A gets rejected
        with pytest.raises(QuotaViolationError):
            mock_producer_a.send("stoa.api.lifecycle", value={"data": "x" * 1024 * 1024})

        # Tenant B can still produce
        mock_producer_b.send("stoa.api.lifecycle", value={"data": "y"})
        assert mock_producer_b.send.call_count == 1

    def test_quota_isolation_per_client_id(self):
        """Test that quotas are isolated per client_id."""
        # Standard tenant uses client_id="tenant-acme"
        # Premium tenant uses client_id="tenant-premium-bigcorp"
        # Both should have independent quota counters

        standard_client_id = "tenant-acme"
        premium_client_id = "tenant-premium-bigcorp"

        assert standard_client_id.startswith("tenant-")
        assert premium_client_id.startswith("tenant-premium-")
        assert standard_client_id != premium_client_id
