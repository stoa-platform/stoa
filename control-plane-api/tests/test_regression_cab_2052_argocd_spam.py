"""Regression test for CAB-2052 follow-up — ArgoCD reconcile spam.

When ARGOCD_TOKEN is empty (typical local dev without ArgoCD), the gateway
reconciler used to call `argocd_service.get_applications(auth_token="")` on
every cycle, which httpx would reject with `Illegal header value b"Bearer "`.
The fix short-circuits `_reconcile` early when no token is configured.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.workers.gateway_reconciler import GatewayReconciler


class TestRegression_ArgoCDReconcileSpam:
    """Guards gateway_reconciler._reconcile early-return when token is empty."""

    @pytest.mark.asyncio
    @patch("src.workers.gateway_reconciler.argocd_service")
    async def test_regression_cab_2052_reconcile_skips_when_no_token(
        self, mock_argocd, monkeypatch
    ):
        monkeypatch.setattr("src.workers.gateway_reconciler.settings.ARGOCD_TOKEN", "")
        reconciler = GatewayReconciler()
        mock_argocd.get_applications = AsyncMock(return_value=[])

        await reconciler._reconcile()

        # ArgoCD must NOT be queried when token is absent — prevents log spam.
        mock_argocd.get_applications.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.workers.gateway_reconciler.argocd_service")
    @patch("src.workers.gateway_reconciler._get_session_factory")
    async def test_regression_cab_2052_reconcile_runs_when_token_set(
        self, mock_factory, mock_argocd, monkeypatch
    ):
        monkeypatch.setattr("src.workers.gateway_reconciler.settings.ARGOCD_TOKEN", "stub-token")
        reconciler = GatewayReconciler()
        mock_argocd.get_applications = AsyncMock(return_value=[])

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = MagicMock(return_value=mock_cm)

        await reconciler._reconcile()

        # When a token is present, reconcile proceeds normally.
        mock_argocd.get_applications.assert_called_once_with(auth_token="")
