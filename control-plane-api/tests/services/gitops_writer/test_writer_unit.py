"""Pure-unit tests for ``GitOpsWriter`` orchestration helpers.

These tests do NOT require a live PostgreSQL — they exercise the writer
modules directly to pin down edge-case behaviour that would otherwise
only be covered by the heavier integration suite (which auto-skips
without ``DATABASE_URL``). Spec §6.5 + §6.8.
"""

from __future__ import annotations

from src.services.gitops_writer.models import ApiCreatePayload
from src.services.gitops_writer.writer import (
    _ACTOR_MAX_LEN,
    _MAX_RACE_RETRIES,
    _catalog_release_branch_name,
    _catalog_release_id,
    _catalog_release_tag_name,
    _generated_openapi_spec,
    _sanitize_actor,
)


def _contains_boolean_additional_properties(value) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "additionalProperties" and isinstance(child, bool):
                return True
            if _contains_boolean_additional_properties(child):
                return True
    if isinstance(value, list):
        return any(_contains_boolean_additional_properties(child) for child in value)
    return False


class TestSanitizeActor:
    def test_passes_clean_actor_through(self) -> None:
        assert _sanitize_actor("alice@example.com") == "alice@example.com"

    def test_strips_newlines(self) -> None:
        # Newline injection in commit messages is the attack vector cited in
        # the Council review. ``_sanitize_actor`` must strip CR/LF before the
        # actor reaches ``CatalogGitClient.create_or_update``.
        assert "\n" not in _sanitize_actor("alice\nFake-Author: mallory")
        assert "\r" not in _sanitize_actor("alice\r\nFake-Author: mallory")

    def test_strips_control_chars(self) -> None:
        assert _sanitize_actor("alice\x00\x07bob") == "alicebob"

    def test_caps_length(self) -> None:
        long = "x" * (_ACTOR_MAX_LEN * 2)
        sanitized = _sanitize_actor(long)
        assert len(sanitized) == _ACTOR_MAX_LEN

    def test_empty_returns_unknown_marker(self) -> None:
        assert _sanitize_actor("") == "<unknown>"

    def test_whitespace_only_returns_unknown_marker(self) -> None:
        assert _sanitize_actor("   ") == "<unknown>"


class TestRetryConstant:
    def test_max_retries_is_three(self) -> None:
        # Spec §6.5 step 10: exactly 3 attempts before raising 503.
        assert _MAX_RACE_RETRIES == 3


class TestGeneratedOpenApiSpec:
    def test_generated_spec_is_webmethods_compatible(self) -> None:
        spec = _generated_openapi_spec(
            ApiCreatePayload(
                api_name="demo-petstore",
                display_name="Demo Petstore",
                version="1.0.0",
                backend_url="https://petstore.example.invalid",
            )
        )

        assert spec["openapi"] == "3.0.3"
        assert _contains_boolean_additional_properties(spec) is False


class TestCatalogReleaseNaming:
    def test_branch_name_is_content_hash_scoped(self) -> None:
        branch = _catalog_release_branch_name(
            tenant_id="demo-gitops",
            api_name="demo-petstore",
            version="1.2.3",
            catalog_content_hash="abcdef1234567890",
        )
        assert branch == "stoa/api/demo-gitops/demo-petstore/v1.2.3/abcdef123456"

    def test_tag_name_is_merge_commit_scoped(self) -> None:
        tag = _catalog_release_tag_name(
            tenant_id="demo-gitops",
            api_name="demo-petstore",
            version="1.2.3",
            merge_commit_sha="1234567890abcdef",
        )
        assert tag == "stoa/api/demo-gitops/demo-petstore/v1.2.3/1234567890ab"

    def test_release_id_is_stable_for_same_generation(self) -> None:
        first = _catalog_release_id(
            tenant_id="demo-gitops",
            api_name="demo-petstore",
            version="1.2.3",
            merge_commit_sha="1234567890abcdef",
        )
        second = _catalog_release_id(
            tenant_id="demo-gitops",
            api_name="demo-petstore",
            version="1.2.3",
            merge_commit_sha="1234567890abcdef",
        )
        assert first == second
        assert first.startswith("catalog-release:")
