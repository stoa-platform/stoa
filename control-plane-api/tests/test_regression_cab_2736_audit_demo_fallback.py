"""Regression guard for audit demo fallback fail-closed defaults."""

from src.config import Settings


def test_regression_cab_2736_audit_demo_fallback_defaults_false_in_production():
    settings = Settings(
        ENVIRONMENT="production",
        GIT_PROVIDER="gitlab",
        GITLAB_TOKEN="test-token",
        GITLAB_PROJECT_ID="1",
    )

    assert settings.audit_demo_fallback_enabled is False


def test_regression_cab_2736_audit_demo_fallback_defaults_true_in_test():
    settings = Settings(
        ENVIRONMENT="test",
        GIT_PROVIDER="gitlab",
        GITLAB_TOKEN="test-token",
        GITLAB_PROJECT_ID="1",
    )

    assert settings.audit_demo_fallback_enabled is True


def test_regression_cab_2736_audit_demo_fallback_explicit_env_wins():
    settings = Settings(
        ENVIRONMENT="test",
        STOA_AUDIT_DEMO_FALLBACK=False,
        GIT_PROVIDER="gitlab",
        GITLAB_TOKEN="test-token",
        GITLAB_PROJECT_ID="1",
    )

    assert settings.audit_demo_fallback_enabled is False
