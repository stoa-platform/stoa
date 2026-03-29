import hashlib
import hmac

from src.routers.webhooks import verify_github_signature


def test_verify_github_signature_valid():
    secret = "test-secret"
    body = b'{"ref":"refs/heads/main"}'
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_github_signature(body, sig, secret) is True


def test_verify_github_signature_invalid():
    assert verify_github_signature(b"body", "sha256=bad", "secret") is False


def test_verify_github_signature_missing():
    assert verify_github_signature(b"body", None, "secret") is False


def test_verify_github_signature_no_secret():
    assert verify_github_signature(b"body", "sha256=x", "") is False
