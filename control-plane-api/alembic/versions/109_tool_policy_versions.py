"""Add per-tenant monotonic tool policy versions."""

import sqlalchemy as sa
from alembic import op

revision = "109_tool_policy_versions"
down_revision = "108_audit_emit_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    schema = bind.scalar(sa.text("SELECT current_schema()"))
    namespace = bind.dialect.identifier_preparer.quote_schema(schema)
    counter = f"{namespace}.tool_policy_versions"
    permission = f"{namespace}.tenant_tool_permissions"
    schema_literal = sa.literal(schema).compile(dialect=bind.dialect, compile_kwargs={"literal_binds": True})
    counter_table = op.create_table(
        "tool_policy_versions",
        sa.Column("tenant_id", sa.String(255), primary_key=True),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.CheckConstraint("version >= 1", name="ck_tool_policy_version_positive"),
        schema=schema,
    )
    permissions = sa.table("tenant_tool_permissions", sa.column("tenant_id"), schema=schema)
    op.execute(
        counter_table.insert().from_select(
            ["tenant_id", "version"], sa.select(permissions.c.tenant_id, sa.literal(1)).distinct()
        )
    )
    # Keep the statement exact: its complete call frame identifies the trusted writer.
    increment = f"""INSERT INTO {counter} AS counter (tenant_id, version)
            VALUES (CASE WHEN TG_OP = 'DELETE' THEN OLD.tenant_id ELSE NEW.tenant_id END, 2)
            ON CONFLICT (tenant_id) DO UPDATE SET version = counter.version + 1"""  # noqa: S608 - Quoted schema.
    caller = f'SQL statement "{increment}"\nPL/pgSQL function {namespace}.bump_tool_policy_version() line '
    caller = str(sa.literal(caller).compile(dialect=bind.dialect, compile_kwargs={"literal_binds": True}))
    op.execute(f"""
        CREATE FUNCTION {namespace}.bump_tool_policy_version() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
        BEGIN
            IF TG_TABLE_SCHEMA <> {schema_literal} OR TG_TABLE_NAME <> 'tenant_tool_permissions' THEN
                RAISE EXCEPTION 'policy version requires the permission relation';
            END IF;
            IF TG_OP = 'UPDATE' AND NEW.tenant_id IS DISTINCT FROM OLD.tenant_id THEN
                RAISE EXCEPTION 'permission tenant cannot change';
            END IF;
            {increment};
            RETURN NULL;
        END;
        $$
    """)
    op.execute(f"""
        CREATE TRIGGER tool_permission_version AFTER INSERT OR UPDATE OR DELETE ON {permission}
        FOR EACH ROW EXECUTE FUNCTION {namespace}.bump_tool_policy_version()
    """)
    op.execute(f"""
        CREATE FUNCTION {namespace}.guard_tool_policy_version() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, pg_temp AS $$
        DECLARE call_stack text;
        BEGIN
            IF TG_OP NOT IN ('INSERT', 'UPDATE') THEN
                RAISE EXCEPTION 'policy version cannot be removed';
            END IF;
            GET DIAGNOSTICS call_stack = PG_CONTEXT;
            IF NOT starts_with(substr(call_stack, strpos(call_stack, E'\\n') + 1), {caller}) THEN
                RAISE EXCEPTION 'policy version requires a permission mutation';
            END IF;
            IF (TG_OP = 'INSERT' AND NEW.version <> 2) OR (TG_OP = 'UPDATE'
                AND (NEW.tenant_id IS DISTINCT FROM OLD.tenant_id OR NEW.version <> OLD.version + 1)) THEN
                RAISE EXCEPTION 'policy version must advance once for the same tenant';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    for name, event, table, level in [
        ("tool_policy_version_guard", "INSERT OR UPDATE OR DELETE", "tool_policy_versions", "ROW"),
        ("tool_policy_version_no_truncate", "TRUNCATE", "tool_policy_versions", "STATEMENT"),
        ("tool_permission_no_truncate", "TRUNCATE", "tenant_tool_permissions", "STATEMENT"),
    ]:
        op.execute(
            f"CREATE TRIGGER {name} BEFORE {event} ON {namespace}.{table} "
            f"FOR EACH {level} EXECUTE FUNCTION {namespace}.guard_tool_policy_version()"
        )


def downgrade() -> None:
    namespace = op.get_bind().dialect.identifier_preparer.quote_schema(
        op.get_bind().scalar(sa.text("SELECT current_schema()"))
    )
    op.execute(f"DROP TRIGGER tool_permission_no_truncate ON {namespace}.tenant_tool_permissions")
    op.execute(f"DROP TRIGGER tool_permission_version ON {namespace}.tenant_tool_permissions")
    op.execute(f"DROP FUNCTION {namespace}.bump_tool_policy_version()")
    op.drop_table("tool_policy_versions", schema=op.get_bind().scalar(sa.text("SELECT current_schema()")))
    op.execute(f"DROP FUNCTION {namespace}.guard_tool_policy_version()")
