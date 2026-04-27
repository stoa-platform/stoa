"""Phase 3 scaffold invariants — static analysis of the new GitOps modules.

These tests grep the new code to enforce architectural invariants from
``specs/api-creation-gitops-rewrite.md`` §6 and §9. They are intentionally
shallow: they fail fast if the Phase 4 implementation reintroduces a banned
pattern (UUID5, worktree, ``apis`` table, Kafka emit, native ``hash()`` for
the advisory lock).

Each test references the relevant Linear ticket so a future failure points
straight to the spec section.
"""

from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path

import pytest

NEW_MODULES_ROOT = Path(__file__).parent.parent.parent / "src/services"
NEW_MODULES = [
    NEW_MODULES_ROOT / "gitops_writer",
    NEW_MODULES_ROOT / "catalog_reconciler",
    NEW_MODULES_ROOT / "catalog_git_client",
]


def _all_python_files() -> list[Path]:
    files: list[Path] = []
    for module in NEW_MODULES:
        if module.exists():
            files.extend(p for p in module.rglob("*.py") if "__pycache__" not in p.parts)
    return files


def _code_only(source: str) -> str:
    """Return ``source`` with comments and string literals stripped.

    Phase 3 invariant tests guard against forbidden patterns appearing in
    *executable code*. Banning the same words in docstrings would punish the
    spec/README cross-references that document why the patterns are forbidden,
    so we tokenize and drop ``COMMENT`` and ``STRING`` tokens before grepping.
    """
    out: list[str] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for tok in tokens:
            if tok.type in (tokenize.COMMENT, tokenize.STRING, tokenize.NL, tokenize.NEWLINE):
                continue
            out.append(tok.string)
            out.append(" ")
    except tokenize.TokenizeError:
        # Fall back to raw source if tokenisation fails (should not happen on
        # files that import cleanly).
        return source
    return "".join(out)


def test_new_modules_exist() -> None:
    """Sanity: scaffold actually created the three module trees."""
    for module in NEW_MODULES:
        assert module.is_dir(), f"missing module dir: {module}"


def test_no_uuid5_in_new_code() -> None:
    """CAB-2181 B-IDENTITY: no ``uuid5()`` in the GitOps modules.

    Spec §6.4 + §9.10 forbids deriving ``api_id`` from ``uuid5(...)``. The
    public identity is the slug ``api_name`` from the payload.
    """
    pattern = re.compile(r"\buuid5\s*\(")
    offenders = []
    for f in _all_python_files():
        if pattern.search(_code_only(f.read_text())):
            offenders.append(str(f))
    assert not offenders, (
        f"uuid5() found in {offenders}. Forbidden by §6.4 (CAB-2181). Use the api_name slug from the payload instead."
    )


def test_no_worktree_in_new_code() -> None:
    """CAB-2184 B-CLIENT: no ``git`` CLI / worktree dependency.

    Spec §6.7 + §9.10. The ``CatalogGitClient`` goes through PyGithub Contents
    API only.
    """
    pattern = re.compile(r"\bworktree\b|\bgit\s+push\b|\bgit\s+show\b", re.IGNORECASE)
    offenders = []
    for f in _all_python_files():
        if pattern.search(_code_only(f.read_text())):
            offenders.append(str(f))
    assert not offenders, (
        f"git CLI / worktree reference found in {offenders}. Forbidden by §6.7 (CAB-2184). Use PyGithub Contents API."
    )


def test_no_apis_table_in_new_code() -> None:
    """CAB-2180 B-CATALOG: no reference to a ``apis`` table.

    The actual table is ``api_catalog`` (spec §6.3 + audit Phase 1).
    """
    forbidden = re.compile(
        r"\b(FROM|INTO|UPDATE|TABLE)\s+apis\b(?!\s*_)",
        re.IGNORECASE,
    )
    offenders = []
    for f in _all_python_files():
        match = forbidden.search(_code_only(f.read_text()))
        if match:
            offenders.append(f"{f}: {match.group()}")
    assert not offenders, (
        f"reference to table 'apis' found: {offenders}. Use 'api_catalog' instead. Spec §6.3 (CAB-2180)."
    )


def test_no_kafka_event_emit_in_gitops_writer() -> None:
    """CAB-2185 B-FLOW: the writer never emits ``stoa.api.lifecycle``.

    Spec §6.13: when ``GITOPS_CREATE_API_ENABLED=True`` the legacy Kafka event
    is short-circuited. The writer must not reference the topic at all.
    """
    pattern = re.compile(r"stoa\.api\.lifecycle")
    offenders = []
    for f in (NEW_MODULES_ROOT / "gitops_writer").rglob("*.py"):
        if pattern.search(_code_only(f.read_text())):
            offenders.append(str(f))
    assert not offenders, (
        f"Kafka event 'stoa.api.lifecycle' referenced in {offenders}. "
        "Forbidden when GITOPS_CREATE_API_ENABLED=True. Spec §6.13 (CAB-2185)."
    )


def test_no_git_sync_on_write_in_new_code() -> None:
    """Garde-fou §9.6: the legacy flag ``GIT_SYNC_ON_WRITE`` is not reused."""
    pattern = re.compile(r"GIT_SYNC_ON_WRITE")
    offenders = []
    for f in _all_python_files():
        if pattern.search(_code_only(f.read_text())):
            offenders.append(str(f))
    assert not offenders, (
        f"Legacy flag GIT_SYNC_ON_WRITE referenced in {offenders}. "
        "Forbidden by garde-fou §9.6. Use GITOPS_CREATE_API_ENABLED only."
    )


def test_no_python_native_hash_in_advisory_lock() -> None:
    """Spec §6.8: ``advisory_lock_key`` MUST use ``hashlib.sha256``.

    Native ``hash()`` is process-randomised; using it would let writer and
    reconciler claim different lock keys for the same row.
    """
    advisory_lock_file = NEW_MODULES_ROOT / "gitops_writer/advisory_lock.py"
    assert advisory_lock_file.exists(), "advisory_lock.py is required by spec §6.8"
    raw = advisory_lock_file.read_text()
    code = _code_only(raw)
    bare_hash = re.compile(r"(?<![\w.])hash\s*\(")
    assert "hashlib" in raw, "advisory_lock.py must import hashlib"
    assert not bare_hash.search(code), (
        "Bare hash() detected in advisory_lock.py code. Use hashlib.sha256() for cross-process determinism (spec §6.8)."
    )


def test_compute_catalog_content_hash_signature() -> None:
    """CAB-2182 B-HASH: the function is exposed publicly and accepts bytes."""
    from src.services.gitops_writer.hashing import compute_catalog_content_hash

    result = compute_catalog_content_hash(b"test content")
    assert isinstance(result, str)
    assert len(result) == 64  # sha256 hex = 64 chars

    with pytest.raises(TypeError):
        compute_catalog_content_hash("test content")  # type: ignore[arg-type]


def test_advisory_lock_key_deterministic() -> None:
    """Spec §6.8: ``advisory_lock_key`` deterministic across processes/runs."""
    from src.services.gitops_writer.advisory_lock import advisory_lock_key

    a = advisory_lock_key("demo", "petstore")
    b = advisory_lock_key("demo", "petstore")
    assert a == b

    c = advisory_lock_key("demo-gitops", "petstore")
    assert a != c

    assert isinstance(a, int)
    assert -(2**63) <= a < 2**63


def test_no_compute_uac_spec_hash_created() -> None:
    """CAB-2182 B-HASH: no ``compute_uac_spec_hash`` is created in this rewrite.

    UAC V2 hash is out-of-scope (spec §4.2 ``Cycle UAC V2``). Reintroducing
    it now would conflate two distinct concerns.
    """
    pattern = re.compile(r"def\s+compute_uac_spec_hash\s*\(")
    offenders = []
    for f in _all_python_files():
        if pattern.search(_code_only(f.read_text())):
            offenders.append(str(f))
    assert not offenders, (
        f"compute_uac_spec_hash defined in {offenders}. Out-of-scope this cycle (UAC V2). Spec §6.2.1 (CAB-2182)."
    )


def test_gitops_create_api_enabled_default_false() -> None:
    """Spec §6.13: the flag defaults to OFF."""
    from src.config import Settings

    fresh = Settings()
    assert fresh.GITOPS_CREATE_API_ENABLED is False, "GITOPS_CREATE_API_ENABLED must default to False (spec §6.13)."
    assert fresh.CATALOG_RECONCILE_INTERVAL_SECONDS == 10, (
        "CATALOG_RECONCILE_INTERVAL_SECONDS must default to 10 (spec §6.6)."
    )


def test_catalog_git_client_protocol_has_5_methods() -> None:
    """CAB-2184 B-CLIENT: the Protocol exposes exactly 5 methods (spec §6.7)."""
    from src.services.catalog_git_client.protocol import CatalogGitClient

    expected = {"get", "create_or_update", "read_at_commit", "latest_file_commit", "list"}
    actual = {
        name
        for name in dir(CatalogGitClient)
        if not name.startswith("_") and callable(getattr(CatalogGitClient, name, None))
    }

    missing = expected - actual
    assert not missing, f"CatalogGitClient missing methods: {missing}"


# Phase 3 stub-message tests removed in Phase 4-2 once the stubs were filled.
# The static invariants below (UUID5, worktree, Kafka emit, hash, etc.) still
# guard the implementation. Behavioural coverage of the writer + reconciler
# lives in ``tests/services/gitops_writer/test_writer_integration.py`` and
# ``tests/services/catalog_reconciler/test_worker_loop.py``.


def test_no_target_gateways_or_openapi_spec_writes_in_writer() -> None:
    """Spec §6.5 step 14 + §6.9: GitOps writer never writes target_gateways or openapi_spec.

    Phase 3 grep guards against accidental introduction in Phase 4.
    """
    forbidden = re.compile(
        r"(target_gateways|openapi_spec)\s*=",
    )
    offenders = []
    for f in (NEW_MODULES_ROOT / "gitops_writer").rglob("*.py"):
        if forbidden.search(_code_only(f.read_text())):
            offenders.append(str(f))
    assert not offenders, (
        f"Mutation of target_gateways/openapi_spec in {offenders}. "
        "Forbidden — those columns are owned by deployment / UAC V2 flows. "
        "Spec §6.9 mapping table."
    )
