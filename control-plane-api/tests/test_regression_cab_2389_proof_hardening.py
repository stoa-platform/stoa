"""Regression coverage for sender-constrained proof hardening."""

import hmac
from collections.abc import Iterator
from unittest.mock import patch

import pytest

from src.auth.sender_constrained import _jti_cache, _validate_dpop_binding
from tests.test_sender_constrained import _ACCESS_TOKEN, _make_dpop_proof, _test_jkt


@pytest.fixture(autouse=True)
def clear_replay_cache() -> Iterator[None]:
    _jti_cache.clear()
    yield
    _jti_cache.clear()


URI = "https://api.example.test/v1/apis"


@pytest.mark.parametrize("binding", ["jkt", "ath"])
@pytest.mark.parametrize("matches", [True, False])
def test_regression_cab_2389_constant_time_binding(binding: str, matches: bool) -> None:
    proof = _make_dpop_proof(http_uri=URI)
    jkt = _test_jkt if binding != "jkt" or matches else "wrong-thumbprint"
    token = _ACCESS_TOKEN if binding != "ath" or matches else "wrong-token"
    with patch("src.auth.sender_constrained.hmac.compare_digest", wraps=hmac.compare_digest) as compare:
        result = _validate_dpop_binding({"jkt": jkt}, {"dpop": proof}, token, "GET", URI)
    assert result.valid is matches
    assert compare.call_count == (1 if binding == "jkt" and not matches else 2)


@pytest.mark.parametrize(
    ("proof_kwargs", "expected_error"),
    [
        ({"http_method": "PRIVATE-METHOD"}, "DPoP htm mismatch"),
        ({"http_uri": "https://proof.example.test/private-path"}, "DPoP htu mismatch"),
        ({"typ": "private-type"}, "DPoP proof has wrong typ"),
        ({"iat": 1}, "DPoP proof expired"),
    ],
)
def test_regression_cab_2389_generic_client_errors(proof_kwargs: dict, expected_error: str) -> None:
    proof = _make_dpop_proof(**({"http_uri": URI} | proof_kwargs))
    result = _validate_dpop_binding({"jkt": _test_jkt}, {"dpop": proof}, _ACCESS_TOKEN, "GET", URI)
    assert not result.valid
    assert result.error == expected_error


def test_regression_cab_2389_exception_logs_omit_untrusted_text() -> None:
    proof = _make_dpop_proof(http_uri=URI)
    with (
        patch("src.auth.sender_constrained.jwt.get_unverified_header", side_effect=ValueError("sensitive-input")),
        patch("src.auth.sender_constrained.logger") as logger,
    ):
        result = _validate_dpop_binding({"jkt": _test_jkt}, {"dpop": proof}, _ACCESS_TOKEN, "GET", URI)
    assert result.error == "DPoP validation failed"
    logger.warning.assert_called_once_with("DPoP validation error", error_type="ValueError")
