"""Add per-tenant monotonic tool policy versions."""

import sqlalchemy as sa
from alembic import op

revision = "109_tool_policy_versions"
down_revision = "108_audit_emit_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tool_policy_versions",
        sa.Column("tenant_id", sa.String(255), primary_key=True),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.CheckConstraint("version >= 1", name="ck_tool_policy_version_positive"),
    )
    # Controlled migration backfill runs before the counter write guards are installed.
    op.execute("""
        INSERT INTO tool_policy_versions (tenant_id, version)
        SELECT DISTINCT tenant_id, 1 FROM tenant_tool_permissions
    """)
    # Missing rows have baseline version 1; the first mutation must advance it.
    op.execute("""
        CREATE FUNCTION bump_tool_policy_version() RETURNS trigger AS $$
        DECLARE
            previous_context text := current_setting('stoa.tool_policy_mutation', true);
        BEGIN
            IF TG_OP = 'UPDATE' AND NEW.tenant_id IS DISTINCT FROM OLD.tenant_id THEN
                RAISE EXCEPTION 'permission tenant cannot change';
            END IF;
            PERFORM set_config('stoa.tool_policy_mutation', 'on', true);
            INSERT INTO tool_policy_versions (tenant_id, version)
            VALUES (CASE WHEN TG_OP = 'DELETE' THEN OLD.tenant_id ELSE NEW.tenant_id END, 2)
            ON CONFLICT (tenant_id) DO UPDATE
                SET version = tool_policy_versions.version + 1;
            PERFORM set_config('stoa.tool_policy_mutation', COALESCE(previous_context, ''), true);
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER tool_permission_version
        AFTER INSERT OR UPDATE OR DELETE ON tenant_tool_permissions
        FOR EACH ROW EXECUTE FUNCTION bump_tool_policy_version()
    """)
    op.execute("""
        CREATE FUNCTION guard_tool_policy_version() RETURNS trigger AS $$
        BEGIN
            IF TG_OP NOT IN ('INSERT', 'UPDATE') THEN
                RAISE EXCEPTION 'policy version cannot be removed';
            END IF;
            IF pg_trigger_depth() < 2
               OR current_setting('stoa.tool_policy_mutation', true) IS DISTINCT FROM 'on' THEN
                RAISE EXCEPTION 'policy version requires a permission mutation';
            END IF;
            IF TG_OP = 'UPDATE'
               AND (NEW.tenant_id IS DISTINCT FROM OLD.tenant_id OR NEW.version <= OLD.version) THEN
                RAISE EXCEPTION 'policy version must increase for the same tenant';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER tool_policy_version_guard BEFORE INSERT OR UPDATE OR DELETE ON tool_policy_versions
        FOR EACH ROW EXECUTE FUNCTION guard_tool_policy_version()
    """)
    op.execute("""
        CREATE TRIGGER tool_policy_version_no_truncate BEFORE TRUNCATE ON tool_policy_versions
        FOR EACH STATEMENT EXECUTE FUNCTION guard_tool_policy_version()
    """)
    op.execute("""
        CREATE TRIGGER tool_permission_no_truncate BEFORE TRUNCATE ON tenant_tool_permissions
        FOR EACH STATEMENT EXECUTE FUNCTION guard_tool_policy_version()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER tool_permission_no_truncate ON tenant_tool_permissions")
    op.execute("DROP TRIGGER tool_permission_version ON tenant_tool_permissions")
    op.execute("DROP FUNCTION bump_tool_policy_version()")
    op.drop_table("tool_policy_versions")
    op.execute("DROP FUNCTION guard_tool_policy_version()")
