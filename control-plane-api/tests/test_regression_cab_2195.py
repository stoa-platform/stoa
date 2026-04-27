"""Regression tests for CAB-2195 (KeycloakService realm-mutation token refresh bug)."""

from unittest.mock import patch

from src.config import settings
from src.services.keycloak_service import KeycloakService


class TestRegressionCab2195:
    async def test_regression_cab_2195_connect_uses_user_realm_name(self):
        # Authenticate against master (where the admin user lives) and operate
        # on the configured realm. Mutating connection.realm_name post-init
        # breaks token refresh because python-keycloak hits the token endpoint
        # of the mutated realm — where `admin` does not exist — yielding 401
        # invalid_grant on every refresh.
        svc = KeycloakService()
        with (
            patch("src.services.keycloak_service.KeycloakOpenIDConnection") as mock_conn,
            patch("src.services.keycloak_service.KeycloakAdmin"),
        ):
            await svc.connect()
            kwargs = mock_conn.call_args.kwargs
            assert kwargs["realm_name"] == settings.KEYCLOAK_REALM
            assert kwargs["user_realm_name"] == "master"
