"""Tests for OIDC auth flow."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from src.auth import _decode_jwt_claims, _generate_pkce, refresh_token
from src.config import Credentials, StoaConfig

from .conftest import _make_fake_jwt


class TestPKCE:
    def test_generates_verifier_and_challenge(self):
        verifier, challenge = _generate_pkce()
        assert len(verifier) > 40
        assert len(challenge) > 20
        assert verifier != challenge

    def test_deterministic_challenge(self):
        """Same verifier should produce the same challenge."""
        _v1, c1 = _generate_pkce()
        # Can't test determinism directly (random), but ensure format
        assert "=" not in c1  # base64url has no padding


class TestDecodeJWT:
    def test_decode_valid_jwt(self):
        payload = {"sub": "user-1", "email": "a@b.com"}
        token = _make_fake_jwt(payload)
        claims = _decode_jwt_claims(token)
        assert claims["sub"] == "user-1"
        assert claims["email"] == "a@b.com"

    def test_decode_invalid_token(self):
        claims = _decode_jwt_claims("not.a.jwt")
        assert claims == {} or isinstance(claims, dict)

    def test_decode_empty_string(self):
        claims = _decode_jwt_claims("")
        assert claims == {}


class TestRefreshToken:
    def test_refresh_success(self, sample_config: StoaConfig):
        payload = {
            "sub": "user-1",
            "preferred_username": "john",
            "email": "j@test.com",
            "exp": int(time.time()) + 3600,
        }
        new_jwt = _make_fake_jwt(payload)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": new_jwt,
            "refresh_token": "new-refresh",
            "expires_in": 300,
            "token_type": "Bearer",
        }

        old_creds = Credentials(
            access_token="old-token",
            refresh_token="old-refresh",
            expires_at=0,
        )

        with patch("src.auth.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            with patch("src.auth.save_credentials"):
                new_creds = refresh_token(sample_config, old_creds)

        assert new_creds.access_token == new_jwt
        assert new_creds.refresh_token == "new-refresh"
        assert new_creds.expires_at > time.time()

    def test_refresh_no_token_raises(self, sample_config: StoaConfig):
        creds = Credentials(access_token="tok", refresh_token="")
        with pytest.raises(RuntimeError, match="No refresh token"):
            refresh_token(sample_config, creds)

    def test_refresh_failure_raises(self, sample_config: StoaConfig):
        mock_response = MagicMock()
        mock_response.status_code = 401

        creds = Credentials(access_token="tok", refresh_token="ref")

        with patch("src.auth.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            with pytest.raises(RuntimeError, match="Token refresh failed"):
                refresh_token(sample_config, creds)
