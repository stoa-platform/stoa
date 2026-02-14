"""Tests for certificate utility functions (CAB-872)."""

from datetime import UTC, datetime, timedelta

from src.services.certificate_utils import certificate_health_score, days_until_expiry


class TestDaysUntilExpiry:
    """Tests for days_until_expiry."""

    def test_future_cert(self):
        """Certificate expiring in 90 days returns ~90."""
        not_after = datetime.now(UTC) + timedelta(days=90)
        result = days_until_expiry(not_after)
        assert 89 <= result <= 90

    def test_expired_cert(self):
        """Expired certificate returns negative days."""
        not_after = datetime.now(UTC) - timedelta(days=10)
        result = days_until_expiry(not_after)
        assert result <= -10

    def test_expiring_today(self):
        """Certificate expiring today returns 0."""
        not_after = datetime.now(UTC) + timedelta(hours=12)
        result = days_until_expiry(not_after)
        assert result == 0


class TestCertificateHealthScore:
    """Tests for certificate_health_score."""

    def test_healthy_active_cert(self):
        """Active cert with >90 days returns high score."""
        not_after = datetime.now(UTC) + timedelta(days=365)
        score = certificate_health_score(not_after, "active", rotation_count=1)
        # base=70 + status=30 + rotation=5 → capped at 100
        assert score == 100

    def test_expiring_soon_cert(self):
        """Active cert with 15 days returns moderate score."""
        not_after = datetime.now(UTC) + timedelta(days=15)
        score = certificate_health_score(not_after, "active", rotation_count=0)
        # base=30 + status=30 + rotation=0 = 60
        assert score == 60

    def test_critical_cert(self):
        """Active cert with 3 days returns low score."""
        not_after = datetime.now(UTC) + timedelta(days=3)
        score = certificate_health_score(not_after, "active", rotation_count=0)
        # base=10 + status=30 + rotation=0 = 40
        assert score == 40

    def test_expired_cert(self):
        """Expired cert returns 0."""
        not_after = datetime.now(UTC) - timedelta(days=5)
        score = certificate_health_score(not_after, "expired", rotation_count=0)
        # base=0 + status=0 + rotation=0 = 0
        assert score == 0

    def test_revoked_cert(self):
        """Revoked cert returns 0 status bonus."""
        not_after = datetime.now(UTC) + timedelta(days=365)
        score = certificate_health_score(not_after, "revoked", rotation_count=0)
        # base=70 + status=0 + rotation=0 = 70
        assert score == 70

    def test_rotating_cert(self):
        """Rotating cert gets 20 status bonus."""
        not_after = datetime.now(UTC) + timedelta(days=60)
        score = certificate_health_score(not_after, "rotating", rotation_count=1)
        # base=50 + status=20 + rotation=5 = 75
        assert score == 75

    def test_none_rotation_count(self):
        """None rotation_count is treated as 0."""
        not_after = datetime.now(UTC) + timedelta(days=365)
        score = certificate_health_score(not_after, "active", rotation_count=None)
        # base=70 + status=30 + rotation=0 = 100
        assert score == 100
