"""Regression coverage for webMethods URL isolation by environment."""

from unittest.mock import AsyncMock, patch

from src.models.gateway_instance import GatewayType
from tests.test_gateway_internal import (
    GW_KEY_HEADER,
    REGISTER_URL,
    VALID_KEY,
    _make_gateway_instance,
    _registration_payload,
)


def test_regression_cab_1953_nonprod_webmethods_registration_clears_prod_ui_url(client):
    """Non-prod webMethods registrations must not keep stale prod UI links."""
    existing = _make_gateway_instance(
        name="stoa-link-wm-dev-sidecar-dev",
        gateway_type=GatewayType.STOA_SIDECAR,
        environment="dev",
        mode="sidecar",
        deployment_mode="connect",
        target_gateway_type="webmethods",
        topology="remote-agent",
        public_url="https://dev-wm-k3s.gostoa.dev",
        target_gateway_url="https://webmethods.gostoa.dev",
        ui_url="https://vps-wm-ui.gostoa.dev",
        endpoints={
            "public_url": "https://dev-wm-k3s.gostoa.dev",
            "target_gateway_url": "https://webmethods.gostoa.dev",
            "ui_url": "https://vps-wm-ui.gostoa.dev",
        },
    )

    with (
        patch("src.routers.gateway_internal.settings") as mock_settings,
        patch("src.routers.gateway_internal.GatewayInstanceRepository") as MockRepo,
    ):
        mock_settings.gateway_api_keys_list = [VALID_KEY]

        mock_repo = MockRepo.return_value
        mock_repo.get_by_name = AsyncMock(return_value=existing)
        mock_repo.update = AsyncMock(return_value=existing)

        resp = client.post(
            REGISTER_URL,
            json=_registration_payload(
                hostname="stoa-link-wm-dev",
                mode="sidecar",
                environment="dev",
                target_gateway_type="webmethods",
                target_gateway_url="https://dev-wm.gostoa.dev",
                public_url="https://dev-wm-k3s.gostoa.dev",
            ),
            headers={GW_KEY_HEADER: VALID_KEY},
        )

        assert resp.status_code == 201
        assert existing.ui_url is None
        assert existing.target_gateway_url == "https://dev-wm.gostoa.dev"
        assert existing.endpoints["target_gateway_url"] == "https://dev-wm.gostoa.dev"
        assert "ui_url" not in existing.endpoints
        mock_repo.update.assert_awaited_once()
