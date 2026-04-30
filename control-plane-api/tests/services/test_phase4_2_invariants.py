"""Phase 4-2 invariants — orchestration must stay flag-gated.

Spec §6.5 / §6.6 / §6.13 / §6.14 + garde-fous §9. These tests grep the
shipped orchestration code so the Phase 4-2 wiring (writer, reconciler,
handler branch) cannot drift into the legacy path nor reintroduce a
banned behaviour (Kafka emit on the GitOps path, DELETE in reconciler,
hardcoded ON, etc.).
"""

from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path

NEW_MODULES_ROOT = Path(__file__).parent.parent.parent / "src/services"
APIS_ROUTER = Path(__file__).parent.parent.parent / "src/routers/apis.py"
MAIN_PY = Path(__file__).parent.parent.parent / "src/main.py"
WRITER_FILE = NEW_MODULES_ROOT / "gitops_writer/writer.py"
RECONCILER_DIR = NEW_MODULES_ROOT / "catalog_reconciler"
GITOPS_MODULE_DIRS = (
    NEW_MODULES_ROOT / "gitops_writer",
    NEW_MODULES_ROOT / "catalog_reconciler",
    NEW_MODULES_ROOT / "catalog_git_client",
    NEW_MODULES_ROOT / "catalog",
)


def _code_only(source: str) -> str:
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


def test_handler_post_apis_imports_gated_by_flag() -> None:
    """The POST handler imports GitOpsWriter but only invokes it under the flag.

    The flag check must dominate the call site so legacy callers never reach
    the GitOps path inadvertently (spec §6.13 + §11 audit-informed).
    """
    raw = APIS_ROUTER.read_text()

    flag_match = re.search(r"settings\.GITOPS_CREATE_API_ENABLED", raw)
    assert flag_match is not None, "apis router must guard the GitOps path on settings.GITOPS_CREATE_API_ENABLED"

    eligible_match = re.search(r"settings\.GITOPS_ELIGIBLE_TENANTS", raw)
    assert (
        eligible_match is not None
    ), "apis router must check tenant_id ∈ GITOPS_ELIGIBLE_TENANTS before routing to GitOps writer"

    # Locate the wrapper handler and constrain the search window to its body
    # so we do not accidentally pick up the function definition of
    # ``_create_api_gitops`` (declared after the wrapper).
    wrapper_start = raw.find("async def create_api(")
    assert wrapper_start != -1, "apis router must define the wrapper async create_api"
    next_def = re.search(r"\nasync def \w|\ndef \w", raw[wrapper_start + 1 :])
    wrapper_end = wrapper_start + 1 + next_def.start() if next_def else len(raw)
    wrapper_body = raw[wrapper_start:wrapper_end]

    invocation = re.search(r"_create_api_gitops\s*\(", wrapper_body)
    assert invocation is not None, "apis router wrapper must invoke _create_api_gitops"

    flag_in_wrapper = re.search(r"settings\.GITOPS_CREATE_API_ENABLED", wrapper_body)
    assert flag_in_wrapper is not None, "wrapper handler must check the flag before delegating"
    assert (
        flag_in_wrapper.start() < invocation.start()
    ), "GITOPS_CREATE_API_ENABLED check must dominate the _create_api_gitops invocation"


def test_main_py_reconciler_gated_by_flag() -> None:
    """``main.py`` only spawns the reconciler when the flag is True.

    The flag literal must appear before the ``asyncio.create_task`` that
    starts the reconciler loop.
    """
    raw = MAIN_PY.read_text()
    flag_match = re.search(r"settings\.GITOPS_CREATE_API_ENABLED", raw)
    assert flag_match is not None, "main.py must reference settings.GITOPS_CREATE_API_ENABLED"
    create_task = re.search(
        r"asyncio\.create_task\s*\(\s*[\w_.]*catalog_reconciler[\w_.()]*\.start\s*\(",
        raw,
    )
    assert create_task is not None, "main.py must spawn the catalog reconciler loop"
    assert (
        flag_match.start() < create_task.start()
    ), "GITOPS_CREATE_API_ENABLED must be checked before the reconciler is spawned"


def test_gitops_writer_does_not_emit_kafka_lifecycle_event() -> None:
    """Spec §6.13: the GitOps path NEVER emits ``stoa.api.lifecycle``.

    Phase 3 already grepped this against the gitops_writer module; Phase 4-2
    repeats the assertion against the now-orchestrating writer to keep the
    invariant load-bearing post-implementation.
    """
    pattern = re.compile(r"stoa\.api\.lifecycle")
    offenders: list[str] = []
    for f in (NEW_MODULES_ROOT / "gitops_writer").rglob("*.py"):
        if pattern.search(_code_only(f.read_text())):
            offenders.append(str(f))
    assert (
        not offenders
    ), f"Kafka event 'stoa.api.lifecycle' referenced in {offenders}. Forbidden on the GitOps path (§6.13)."


def test_handler_gitops_branch_does_not_emit_kafka_lifecycle() -> None:
    """The new ``_create_api_gitops`` helper must not emit Kafka events.

    Spec §6.13 + test Phase 5 covers this at runtime; the static check
    pins it at the call-site so a refactor cannot accidentally re-add an
    ``emit_api_created`` line.
    """
    raw = APIS_ROUTER.read_text()
    helper_start = raw.find("async def _create_api_gitops")
    assert helper_start != -1, "apis router must define _create_api_gitops"
    next_top = re.search(r"\n(?:async def |def |@router\.)", raw[helper_start + 1 :])
    helper_end = helper_start + 1 + next_top.start() if next_top else len(raw)
    helper_body = raw[helper_start:helper_end]
    helper_code = _code_only(helper_body)
    # Strip stripped-token whitespace artefacts so dotted attribute accesses
    # (``kafka_service . emit_api_created``) match the bare symbol checks.
    helper_code = helper_code.replace(" . ", ".")
    forbidden = ["emit_api_created", "emit_audit_event", "stoa.api.lifecycle"]
    for fb in forbidden:
        assert (
            fb not in helper_code
        ), f"_create_api_gitops references forbidden symbol {fb!r}. GitOps path must not emit Kafka (§6.13)."


def test_reconciler_does_not_delete_rows() -> None:
    """Spec §6.14 + garde-fou §9.13/§9.15: reconciler never deletes ``api_catalog`` rows.

    The classifier categories B / C / D are *detection only*. A DELETE or a
    ``deleted_at`` write would imply silent migration of legacy rows.
    """
    forbidden_patterns = [
        re.compile(r"\bDELETE\s+FROM\s+api_catalog\b", re.IGNORECASE),
        re.compile(r"\.delete\(\)\.where\("),
        re.compile(r"deleted_at\s*=\s*"),
    ]
    offenders: list[str] = []
    for f in RECONCILER_DIR.rglob("*.py"):
        code = _code_only(f.read_text())
        for pat in forbidden_patterns:
            if pat.search(code):
                offenders.append(f"{f}: {pat.pattern}")
    assert not offenders, f"Reconciler mutates deletion semantics: {offenders}. Spec §6.14 forbids auto-delete."


def test_writer_uses_advisory_lock_and_no_native_hash() -> None:
    """Spec §6.8: writer acquires/releases ``pg_advisory_lock``.

    SQL identifiers live inside string literals; the raw source is the
    authoritative surface (``_code_only`` strips strings on purpose). The
    bare-``hash()`` guard separately uses ``_code_only`` to ignore docstring
    references.
    """
    raw = WRITER_FILE.read_text()
    assert "pg_advisory_lock" in raw, "Writer must acquire pg_advisory_lock (spec §6.8)"
    assert "pg_advisory_unlock" in raw, "Writer must release pg_advisory_unlock (spec §6.8)"
    code = _code_only(raw)
    bare_hash = re.compile(r"(?<![\w.])hash\s*\(")
    assert not bare_hash.search(code), "Bare hash() forbidden in writer (spec §6.8)."


def test_reconciler_uses_try_advisory_xact_lock() -> None:
    """Spec §6.8 reconciler side: non-blocking transaction-scoped lock."""
    raw = (RECONCILER_DIR / "worker.py").read_text()
    assert "pg_try_advisory_xact_lock" in raw, "Reconciler must use pg_try_advisory_xact_lock (non-blocking, spec §6.8)"


def test_writer_does_not_write_target_gateways_or_openapi_spec() -> None:
    """Spec §6.5 step 14 + §6.9: writer never writes preserved columns.

    Same invariant as Phase 3 but expanded to cover the now-orchestrating
    writer which actually issues SQL via ``project_to_api_catalog``.
    """
    forbidden = re.compile(r"(target_gateways|openapi_spec)\s*=")
    offenders: list[str] = []
    for f in (NEW_MODULES_ROOT / "gitops_writer").rglob("*.py"):
        if forbidden.search(_code_only(f.read_text())):
            offenders.append(str(f))
    assert not offenders, f"Writer mutates target_gateways/openapi_spec: {offenders}. Spec §6.9."


def test_writer_max_retries_is_three() -> None:
    """Spec §6.5 step 10: max 3 retries before raising 503."""
    raw = WRITER_FILE.read_text()
    assert "_MAX_RACE_RETRIES" in raw, "Writer must define an explicit retry constant"
    assert re.search(r"_MAX_RACE_RETRIES\s*=\s*3", raw), "Spec §6.5 step 10: cap is 3 retries."


def test_eligible_tenants_default_empty() -> None:
    """Spec §6.13: even with the flag on, no tenant is auto-routed by default.

    Phase 6 strangler explicitly populates this list. Setting it non-empty
    here would silently activate GitOps for production tenants.
    """
    from src.config import Settings

    fresh = Settings()
    assert fresh.GITOPS_CREATE_API_ENABLED is False, "Flag must default to False (spec §6.13)."
    assert fresh.GITOPS_ELIGIBLE_TENANTS == [], "Default list must be empty (spec §11 audit-informed)."


def test_writer_imports_classify_legacy() -> None:
    """Spec §6.5 step 7: anti-collision uses :func:`classify_legacy`.

    A grep test, not a behavioural test, so a refactor that bypasses the
    classifier (and therefore the cat B/C/D protections) trips this guard.
    """
    code = _code_only(WRITER_FILE.read_text())
    assert "classify_legacy" in code, "Writer must call classify_legacy at step 7."


def test_reconciler_no_kafka_lifecycle_emit() -> None:
    """The reconciler also never emits ``stoa.api.lifecycle``.

    Although §6.13 only mandates this for the writer path, allowing the
    reconciler to emit would re-create the double-write race during the
    strangler.
    """
    pattern = re.compile(r"stoa\.api\.lifecycle")
    offenders: list[str] = []
    for f in RECONCILER_DIR.rglob("*.py"):
        if pattern.search(_code_only(f.read_text())):
            offenders.append(str(f))
    assert not offenders, f"Reconciler emits Kafka lifecycle event: {offenders}. Forbidden during strangler."


def test_main_py_passes_session_factory_to_reconciler() -> None:
    """The reconciler is constructed with a real DB session factory in Phase 4-2.

    Phase 3 wired ``db=None``; Phase 4-2 must pass ``db_session_factory=...``
    so each tick opens a fresh session.
    """
    raw = MAIN_PY.read_text()
    assert (
        "db_session_factory" in raw
    ), "main.py must pass db_session_factory to CatalogReconcilerWorker (Phase 4-2 wiring)"
    # Phase 3 used ``db=None`` — that line must not survive Phase 4-2.
    assert "db=None" not in raw, "Phase 3 stub ``db=None`` must be replaced by db_session_factory in Phase 4-2."


def test_gitops_modules_use_structlog_only() -> None:
    """CAB-2208: GitOps modules must wire on structlog via the central wrapper.

    Phase 4-1/4-2 introduced ``services/gitops_writer``, ``services/catalog_reconciler``,
    ``services/catalog_git_client`` and the ``services/catalog`` helper. These
    modules emit ``catalog_sync_status`` and must use ``get_logger`` from
    ``src.logging_config`` so ``extra=`` fields survive in production. stdlib
    ``logging.getLogger`` was used during the Phase 4-1/4-2 scaffold and
    silently drops kwargs, leaving only the bare event name in the JSON log
    stream — masking ``status`` transitions from §7bis and Phase 7-9 smokes.
    """
    forbidden_patterns = [
        (re.compile(r"\bimport\s+logging\b"), "import logging"),
        (re.compile(r"\bfrom\s+logging\s+import\b"), "from logging import"),
        (re.compile(r"\blogging\s*\.\s*getLogger\b"), "logging.getLogger"),
    ]
    offenders: list[str] = []
    for d in GITOPS_MODULE_DIRS:
        for f in d.rglob("*.py"):
            code = _code_only(f.read_text())
            for pat, label in forbidden_patterns:
                if pat.search(code):
                    offenders.append(f"{f}: {label}")
    assert not offenders, (
        f"GitOps modules use stdlib logging: {offenders}. "
        "Use ``from src.logging_config import get_logger`` instead "
        "(structlog wrapper, CAB-2208)."
    )


def test_catalog_sync_status_counter_wired_in_log_helpers() -> None:
    """CAB-2208: ``_log_sync_status`` increments the Prometheus counter.

    The structured log is the narrative surface but loses fields when the
    structlog pipeline isn't bound; the ``catalog_sync_status_total`` counter
    is the durable observability surface §7bis and Phase 7-9 smokes assert
    against. The helper in writer.py and worker.py must call
    ``CATALOG_SYNC_STATUS_TOTAL.labels(...).inc()`` before the log line so the
    metric is incremented even if structured logging fails.
    """
    pattern = re.compile(r"CATALOG_SYNC_STATUS_TOTAL\s*\.\s*labels\s*\(")
    helpers = (
        WRITER_FILE,
        RECONCILER_DIR / "worker.py",
    )
    for f in helpers:
        code = _code_only(f.read_text())
        assert pattern.search(code), (
            f"{f} must call ``CATALOG_SYNC_STATUS_TOTAL.labels(...)`` inside " "``_log_sync_status`` (CAB-2208)."
        )
