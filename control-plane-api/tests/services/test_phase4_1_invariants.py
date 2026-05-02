"""Phase 4-1 invariants — primitives must stay orchestration-free.

Spec §6.5, §6.9, §6.13 + garde-fous §9. These tests enforce that the helpers
introduced in Phase 4-1 cannot drift into a mini-writer, and that the
existing ``POST /v1/tenants/{tenant_id}/apis`` handler stays untouched. Phase
4-2 will lift the handler invariant when wiring lands.
"""

from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path

NEW_MODULES_ROOT = Path(__file__).parent.parent.parent / "src/services"
HELPER_FILE = NEW_MODULES_ROOT / "catalog/write_api_yaml.py"
PROJECTION_FILE = NEW_MODULES_ROOT / "catalog_reconciler/projection.py"
APIS_ROUTER = Path(__file__).parent.parent.parent / "src/routers/apis.py"


def _code_only(source: str) -> str:
    """Strip comments and string literals so grep targets executable code."""
    out: list[str] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for tok in tokens:
            if tok.type in (tokenize.COMMENT, tokenize.STRING, tokenize.NL, tokenize.NEWLINE):
                continue
            out.append(tok.string)
            out.append(" ")
    except tokenize.TokenizeError:
        return source
    return "".join(out)


def test_helper_does_not_import_db() -> None:
    """``write_api_yaml`` must not touch the database.

    The helper is a pure generator (spec §7). Importing SQLAlchemy or a
    db_session would broaden its responsibility into a mini-writer.
    """
    assert HELPER_FILE.exists(), f"helper missing: {HELPER_FILE}"
    code = _code_only(HELPER_FILE.read_text())
    forbidden = ["sqlalchemy", "asyncpg", "AsyncSession", "db_session"]
    for fb in forbidden:
        assert fb not in code, (
            f"Helper write_api_yaml imports forbidden module/symbol: {fb}. Helper must be pure (no DB)."
        )


def test_helper_does_not_import_git_client_or_github() -> None:
    """``write_api_yaml`` must not call Git.

    Importing the catalog Git client or PyGithub would broaden its
    responsibility into a mini-writer.
    """
    assert HELPER_FILE.exists(), f"helper missing: {HELPER_FILE}"
    raw = HELPER_FILE.read_text()
    code = _code_only(raw)
    forbidden = ["catalog_git_client", "github_service", "PyGithub"]
    for fb in forbidden:
        assert fb not in code, (
            f"Helper write_api_yaml imports forbidden module/symbol: {fb}. Helper must be pure (no Git)."
        )
    # PyGithub commonly imports as ``from github import ...``; check raw too
    # but tolerate ``Github`` substrings inside docstrings (which _code_only
    # already strips). The bare-import check below is the strict guard.
    bare_github_import = re.compile(r"^\s*(from\s+github\b|import\s+github\b)", re.MULTILINE)
    assert not bare_github_import.search(raw), (
        "Helper write_api_yaml imports the github package. Forbidden — pure helper."
    )


def test_projection_module_does_not_assign_target_gateways() -> None:
    """``project_to_api_catalog`` must never write deployment-owned targets.

    Spec §6.9: ``target_gateways`` is owned by deployment. A static assignment
    in the projection would re-introduce GitOps authority over a field it must
    preserve. ``openapi_spec`` is intentionally not part of this guard anymore:
    it is a runtime cache derived from the sibling Git OpenAPI/Swagger file.
    """
    assert PROJECTION_FILE.exists(), f"projection missing: {PROJECTION_FILE}"
    code = _code_only(PROJECTION_FILE.read_text())
    forbidden = [
        "target_gateways=",
        "target_gateways =",
    ]
    for fb in forbidden:
        assert fb not in code, f"Active code mutates {fb!r} in projection module. Forbidden by §6.9."


# Phase 4-1 explicitly forbade the apis router from importing the new
# GitOps modules so the stubs could not be exercised before Phase 4-2.
# That guard was lifted when Phase 4-2 wired the handler. The Phase 4-2
# invariants in ``test_phase4_2_invariants.py`` enforce that the wiring is
# flag-gated and never reaches the writer when the flag is OFF — see
# ``test_handler_post_apis_imports_gated_by_flag``.


def test_main_catalog_reconciler_stays_flag_gated() -> None:
    """``main.py`` may wire the reconciler scaffold but it must stay flag-gated.

    Phase 3 already wires a conditional ``asyncio.create_task(reconciler.start())``
    behind ``settings.GITOPS_CREATE_API_ENABLED``. Phase 4-1 must keep that
    gate in place so production (flag=False) never reaches the worker's
    ``NotImplementedError``. Phase 4-2 will keep the gate AND fill the loop.
    """
    main_py = Path(__file__).parent.parent.parent / "src/main.py"
    assert main_py.exists(), f"main.py missing: {main_py}"
    raw = main_py.read_text()
    if "catalog_reconciler" not in raw:
        # Wiring not yet present (Phase 3 may have been refactored). Nothing
        # to assert — Phase 4-1 must not introduce wiring beyond Phase 3.
        return
    # The flag check must appear in the same module before the create_task.
    flag_match = re.search(r"settings\.GITOPS_CREATE_API_ENABLED", raw)
    create_task_match = re.search(
        r"asyncio\.create_task\s*\(\s*[\w_.]*catalog_reconciler[\w_.()]*\.start\s*\(",
        raw,
    )
    assert flag_match is not None, "main.py references catalog_reconciler but no GITOPS_CREATE_API_ENABLED gate found."
    if create_task_match is not None:
        assert flag_match.start() < create_task_match.start(), (
            "GITOPS_CREATE_API_ENABLED flag must be checked before the reconciler is spawned."
        )


# ``test_writer_create_api_still_raises_in_phase_4_1`` removed in Phase 4-2.
# The writer is now implemented; behavioural tests live in
# ``tests/services/gitops_writer/test_writer_integration.py``.


def test_helper_writes_no_files_outside_argument() -> None:
    """``render_api_yaml`` returns a string and never opens a file by itself.

    The CLI ``main()`` writes to ``--output``; the function under test must
    not perform any filesystem side-effect.
    """
    code = _code_only(HELPER_FILE.read_text())
    # Look for filesystem writes inside the render function. A grep on the
    # module is enough for Phase 4-1; the function is small.
    forbidden = ["open(", ".write_text(", ".write_bytes("]
    # The CLI ``main()`` legitimately uses ``Path.write_text``; we count
    # occurrences and require at most one per pattern (the CLI use).
    for fb in forbidden:
        count = code.count(fb)
        assert count <= 1, (
            f"Helper has {count} occurrences of {fb!r}. "
            "render_api_yaml must be pure; only main() may touch the filesystem."
        )
