"""Audit immutability + pseudonymization auxiliary table (ADR-068 + ADR-069 DRAFT).

Revision ID: 107_audit_immutability_pseudonymization
Revises: 106_drop_api_catalog_full_unique
Create Date: 2026-05-13

============================================================================
DRAFT MIGRATION — DO NOT APPLY TO PRODUCTION UNTIL SIGN-OFF.
============================================================================

See `107_README.md` in this directory for the full sign-off pre-requisites
(Linear ticket CAB-2226: ADR-068 + ADR-069 joint sign-off).

What this migration does (per ADR-068 + ADR-069 drafts):

1. Adds a PostgreSQL trigger to refuse UPDATE / DELETE on `audit_events`.
   The current `erase_user_pii()` code path WILL break the moment this
   trigger is in force — a code-side rewrite (separate PR, also blocked
   on sign-off) is required for production deployment.
2. Adds `audit_chain_heads` table for per-tenant hash-chain ordering.
   Schema only. Insertion logic lives in a follow-up code PR.
3. Adds a nullable `row_hash` column on `audit_events`. Existing rows
   keep NULL until a backfill migration runs under break-glass procedure.
4. Adds `pseudonymized_audit_erasures` auxiliary table — the GDPR Art.17
   path that satisfies erasure requests WITHOUT mutating the source row.
5. Adds `audit_events_redacted` view — the default read surface for SOC,
   support, tenant admins. Applies redaction at read time per the
   `redaction_map` in `pseudonymized_audit_erasures`.

What this migration does NOT do:

- Does NOT rewrite `audit_service.erase_user_pii()`. Without that rewrite,
  applying this migration to a live system breaks the GDPR erasure path.
- Does NOT backfill `row_hash` for existing rows. The trigger only blocks
  UPDATE/DELETE — existing NULL row_hash values are tolerated.
- Does NOT enable hash-chain validation in audit_service.py inserts.
- Does NOT add SQLAlchemy models for `audit_chain_heads` /
  `pseudonymized_audit_erasures`. Those come with the code PR.

Why DRAFT: regulatory + DPO + Legal sign-off required (CAB-2226).
Reviewers see the concrete SQL artefact before approving the abstract
ADR. This file IS the reviewable artefact.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "107_audit_immutability_pseudonymization"
down_revision: str | tuple[str, ...] | None = "106_drop_api_catalog_full_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply ADR-068 + ADR-069 schema changes.

    Idempotent where possible (IF NOT EXISTS / OR REPLACE) so re-runs
    against a partially-applied DB do not panic. Triggers are not
    idempotent in the standard sense; they are explicitly DROPped-then-
    recreated to guarantee a known state.
    """

    # ----- 1. Extensions (pgcrypto for sha256/digest in the redacted view).
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # ----- 2. row_hash column on audit_events.
    # Nullable. Existing rows keep NULL. Insertion code (separate PR)
    # populates new rows. Backfill of existing rows is a separate
    # break-glass operation under DPO/Compliance sign-off.
    op.execute("ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS row_hash BYTEA")
    op.execute(
        "COMMENT ON COLUMN audit_events.row_hash IS "
        "'Per-tenant hash chain (ADR-068 §4.5). sha256(prev_hash || event_id || "
        "created_at || tenant_id || actor_id || action || resource_type:resource_id "
        "|| outcome). NULL on rows created before the chain was enabled.'"
    )

    # ----- 3. audit_chain_heads — per-tenant chain head.
    # ADR-068 §4.5 concurrency invariant. Insertion path locks the
    # row with `SELECT ... FOR UPDATE` (or pg_advisory_xact_lock) before
    # computing the next row_hash.
    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_chain_heads (
            tenant_id     VARCHAR(255) PRIMARY KEY,
            last_row_hash BYTEA NOT NULL,
            last_event_id VARCHAR(36) NOT NULL,
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """)
    op.execute(
        "COMMENT ON TABLE audit_chain_heads IS "
        "'ADR-068 §4.5: serializes per-tenant audit hash chain inserts. "
        "Concurrency: SELECT ... FOR UPDATE or pg_advisory_xact_lock(hashtext(tenant_id)::bigint).'"
    )

    # ----- 4. Immutability trigger function + 2 triggers.
    # Refuses UPDATE and DELETE on audit_events. GDPR erasure path
    # uses the auxiliary pseudonymization table instead (see §6 view).
    # Three documented exceptions (ADR-069 §4.6): retention purge,
    # schema migration, disaster-recovery restore. Each is a break-glass
    # procedure that temporarily drops the relevant trigger inside a
    # transaction and re-creates it before commit, with the operation
    # itself audited.
    op.execute("""
        CREATE OR REPLACE FUNCTION audit_events_immutable() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'audit_events is append-only (ADR-068). '
                'Use the pseudonymization auxiliary table for GDPR Art.17 erasure.'
                USING ERRCODE = 'P0001';
        END;
        $$ LANGUAGE plpgsql
        """)
    # DROP-then-CREATE for idempotency on re-runs against a partial state.
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_update ON audit_events")
    op.execute("""
        CREATE TRIGGER audit_events_no_update
            BEFORE UPDATE ON audit_events
            FOR EACH ROW EXECUTE FUNCTION audit_events_immutable()
        """)
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_delete ON audit_events")
    op.execute("""
        CREATE TRIGGER audit_events_no_delete
            BEFORE DELETE ON audit_events
            FOR EACH ROW EXECUTE FUNCTION audit_events_immutable()
        """)

    # ----- 5. pseudonymized_audit_erasures — GDPR Art.17 auxiliary table.
    # ADR-069 §4.2. DPO-controlled inserts. The pseudonymization_key is
    # encrypted at the application layer before insertion; pgcrypto here
    # is only used for the view's `digest()` call, not for key handling.
    op.execute("""
        CREATE TABLE IF NOT EXISTS pseudonymized_audit_erasures (
            erasure_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            request_received_at   TIMESTAMPTZ NOT NULL,
            legal_basis           TEXT NOT NULL,
            dpo_approver_id       VARCHAR(255) NOT NULL,
            dpo_approved_at       TIMESTAMPTZ NOT NULL,
            subject_external_ref  TEXT,
            pseudonymization_key  BYTEA NOT NULL,
            scope_actor_ids       VARCHAR(255)[] NOT NULL DEFAULT '{}',
            scope_event_ids       VARCHAR(36)[] NOT NULL DEFAULT '{}',
            redaction_map         JSONB NOT NULL,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """)
    op.execute(
        "COMMENT ON TABLE pseudonymized_audit_erasures IS "
        "'ADR-069 §4.2: GDPR Art.17 erasures recorded without mutating audit_events. "
        "DPO-approved inserts only. Pseudonymization_key encrypted at app layer.'"
    )
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_pseudo_erasures_actor_ids
            ON pseudonymized_audit_erasures USING GIN (scope_actor_ids)
        """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_pseudo_erasures_event_ids
            ON pseudonymized_audit_erasures USING GIN (scope_event_ids)
        """)

    # ----- 6. _audit_is_redacted() helper (stable SQL function).
    # The redacted view consults it for each row; STABLE means the
    # planner can cache it within a single query.
    op.execute("""
        CREATE OR REPLACE FUNCTION _audit_is_redacted(
            p_event_id VARCHAR,
            p_actor_id VARCHAR
        ) RETURNS BOOLEAN AS $$
            SELECT EXISTS (
                SELECT 1 FROM pseudonymized_audit_erasures p
                WHERE
                    (p_actor_id IS NOT NULL AND p.scope_actor_ids @> ARRAY[p_actor_id]::VARCHAR[])
                    OR p.scope_event_ids @> ARRAY[p_event_id]::VARCHAR[]
            );
        $$ LANGUAGE SQL STABLE
        """)

    # ----- 7. audit_events_redacted view — default read surface.
    # ADR-069 §4.2. Regulatory fields are preserved as-is. Identifying
    # fields are pseudonymized or NULLed when an erasure entry references
    # the row's actor or event id.
    op.execute("""
        CREATE OR REPLACE VIEW audit_events_redacted AS
        SELECT
            e.id,
            e.tenant_id,
            CASE
                WHEN _audit_is_redacted(e.id, e.actor_id)
                THEN 'pseudo:' || encode(digest(coalesce(e.actor_id, e.id), 'sha256'), 'hex')
                ELSE e.actor_id
            END AS actor_id,
            CASE
                WHEN _audit_is_redacted(e.id, e.actor_id) THEN NULL
                ELSE e.actor_email
            END AS actor_email,
            e.actor_type,
            e.action,
            e.method,
            e.path,
            e.resource_type,
            e.resource_id,
            e.resource_name,
            e.outcome,
            e.status_code,
            CASE
                WHEN _audit_is_redacted(e.id, e.actor_id) THEN NULL
                ELSE e.client_ip
            END AS client_ip,
            CASE
                WHEN _audit_is_redacted(e.id, e.actor_id) THEN NULL
                ELSE e.user_agent
            END AS user_agent,
            e.correlation_id,
            e.details,
            e.diff,
            e.duration_ms,
            e.created_at,
            e.row_hash
        FROM audit_events e
        """)
    op.execute(
        "COMMENT ON VIEW audit_events_redacted IS "
        "'ADR-069 §4.2: default read surface for SOC/support/tenant-admin. "
        "Regulatory fields preserved; identifying fields redacted per pseudonymized_audit_erasures.'"
    )


def downgrade() -> None:
    """Break-glass downgrade — drops triggers, view, helper, and aux tables.

    The `row_hash` column on `audit_events` is INTENTIONALLY preserved
    so that any computed chain data survives. Operator must explicitly
    drop the column under a separate procedure if truly needed.
    """
    op.execute("DROP VIEW IF EXISTS audit_events_redacted")
    op.execute("DROP FUNCTION IF EXISTS _audit_is_redacted(VARCHAR, VARCHAR)")
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_delete ON audit_events")
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_update ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS audit_events_immutable()")
    op.execute("DROP INDEX IF EXISTS idx_pseudo_erasures_event_ids")
    op.execute("DROP INDEX IF EXISTS idx_pseudo_erasures_actor_ids")
    op.execute("DROP TABLE IF EXISTS pseudonymized_audit_erasures")
    op.execute("DROP TABLE IF EXISTS audit_chain_heads")
    # NOTE: row_hash column on audit_events is intentionally preserved.
