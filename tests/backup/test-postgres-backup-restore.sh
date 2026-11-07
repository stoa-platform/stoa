#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 STOA Platform
#
# Backup/restore cycle test for scripts/backup/backup-postgres.sh.
#
# Runs one real backup -> damage -> restore cycle against a DISPOSABLE
# PostgreSQL server and asserts the data comes back byte-for-byte, plus the
# failure paths (truncated, corrupt and invalid backups must fail and must not
# destroy the live database). No kubectl cluster, no S3: the script runs in
# `direct` connection mode with a local backup destination, and its default
# `kubectl` mode is exercised through a local kubectl stand-in that executes
# the client command on this host.
#
# The test creates its own uniquely named database and drops it on exit; it
# never touches any other database on the server.
#
# Requirements:
#   - psql / pg_dump on PATH (major version >= server major version)
#   - libpq env pointing at a disposable server: PGHOST, PGPORT, PGUSER
#     (+ PGPASSWORD if needed). PGUSER must be allowed to CREATE DATABASE.
#   - BACKUP_RESTORE_TEST_DISPOSABLE=1 to confirm the server is disposable.
#
# Run:
#   BACKUP_RESTORE_TEST_DISPOSABLE=1 PGHOST=localhost PGPORT=5432 \
#     PGUSER=postgres PGPASSWORD=postgres tests/backup/test-postgres-backup-restore.sh

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKUP_SCRIPT="${REPO_ROOT}/scripts/backup/backup-postgres.sh"

if [[ "${BACKUP_RESTORE_TEST_DISPOSABLE:-}" != "1" ]]; then
    echo "Refusing to run: set BACKUP_RESTORE_TEST_DISPOSABLE=1 to confirm the PostgreSQL server is disposable." >&2
    exit 2
fi

: "${PGUSER:?PGUSER must be set}"
export PGUSER

# Keep notifications fully offline whatever the caller environment holds
unset SLACK_WEBHOOK_URL SLACK_BOT_TOKEN SLACK_CHANNEL_ID \
    STOA_PROXY_URL STOA_PROXY_TOKEN STOA_PROXY_CLIENT_ID STOA_PROXY_CLIENT_SEC

TEST_DB="stoa_backup_restore_test_$$_${RANDOM}"
WORK_DIR="$(mktemp -d -t stoa-backup-restore-test-XXXXXXXX)"
BACKUP_DIR="${WORK_DIR}/backups"
SHIM_DIR="${WORK_DIR}/shim"
HOLDER_PID=""

PASSED=0
FAILED=0

pass() { PASSED=$((PASSED + 1)); echo "  PASS: $*"; }
fail() { FAILED=$((FAILED + 1)); echo "  FAIL: $*"; }

# Fixture-side SQL; never goes through the script under test
sql() {
    local database=$1
    shift
    psql --no-psqlrc -v ON_ERROR_STOP=1 -q -At -d "$database" "$@"
}

cleanup() {
    if [[ -n "$HOLDER_PID" ]]; then
        kill "$HOLDER_PID" 2>/dev/null || true
        wait "$HOLDER_PID" 2>/dev/null || true
    fi
    sql postgres -v db="$TEST_DB" <<'SQL' >/dev/null 2>&1 || true
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :'db' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS :"db";
SQL
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT

# Run the script under test; stdout/stderr captured.
# Usage: run_script OUT ERR [VAR=value...] [-- script args...]
run_script() {
    local out_file=$1
    local err_file=$2
    shift 2
    local env_vars=()
    while [[ $# -gt 0 && "$1" != "--" ]]; do
        env_vars+=("$1")
        shift
    done
    [[ $# -gt 0 ]] && shift
    env LOG_LEVEL=INFO PG_DATABASE="$TEST_DB" PG_USER="$PGUSER" "${env_vars[@]}" \
        bash "$BACKUP_SCRIPT" "$@" >"$out_file" 2>"$err_file"
}

# Stable digest of every row, the view and the sequence state
fingerprint() {
    sql "$TEST_DB" <<'SQL'
SELECT md5(
    coalesce((SELECT string_agg(t::text, '|' ORDER BY id) FROM tenants t), '') || '#' ||
    coalesce((SELECT string_agg(a::text, '|' ORDER BY id) FROM apis a), '') || '#' ||
    coalesce((SELECT string_agg(v::text, '|' ORDER BY name) FROM published_apis v), '') || '#' ||
    (SELECT last_value::text FROM apis_id_seq)
);
SQL
}

count_public_tables() {
    sql "$TEST_DB" -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';"
}

# -----------------------------------------------------------------------------
echo "== Preflight"
# -----------------------------------------------------------------------------
for bin in psql pg_dump gzip gunzip; do
    if ! command -v "$bin" >/dev/null; then
        echo "Missing required binary: $bin" >&2
        exit 2
    fi
done

server_major=$(sql postgres -c "SHOW server_version_num;") || { echo "Cannot reach PostgreSQL server" >&2; exit 2; }
server_major=$((server_major / 10000))
client_major=$(pg_dump --version | grep -oE '[0-9]+' | head -1)
if (( client_major < server_major )); then
    echo "pg_dump ${client_major} cannot dump a PostgreSQL ${server_major} server" >&2
    exit 2
fi
echo "  server PostgreSQL ${server_major}, client tools ${client_major}, test database ${TEST_DB}"

if [[ -n "$(sql postgres -v db="$TEST_DB" <<<"SELECT 1 FROM pg_database WHERE datname = :'db';" 2>/dev/null)" ]]; then
    echo "Test database ${TEST_DB} already exists; refusing to reuse it" >&2
    exit 2
fi

# -----------------------------------------------------------------------------
echo "== Seed disposable database"
# -----------------------------------------------------------------------------
sql postgres -v db="$TEST_DB" -v owner="$PGUSER" <<'SQL' || { echo "Cannot create test database" >&2; exit 1; }
CREATE DATABASE :"db" OWNER :"owner";
SQL

sql "$TEST_DB" <<'SQL' || { echo "Cannot seed test database" >&2; exit 1; }
CREATE TYPE api_status AS ENUM ('draft', 'published', 'deprecated');
CREATE TABLE tenants (
    id serial PRIMARY KEY,
    name text NOT NULL UNIQUE,
    settings jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE apis (
    id bigserial PRIMARY KEY,
    tenant_id integer NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name text NOT NULL,
    status api_status NOT NULL,
    created_at timestamptz NOT NULL DEFAULT '2026-01-01T00:00:00Z'
);
CREATE INDEX apis_tenant_idx ON apis (tenant_id);
CREATE VIEW published_apis AS
    SELECT a.name, t.name AS tenant
    FROM apis a JOIN tenants t ON t.id = a.tenant_id
    WHERE a.status = 'published';

INSERT INTO tenants (name, settings) VALUES
    ('acme', '{"tier": "gold"}'),
    ('zürich-ünïcode', '{"note": "multi\nline", "quote": "it''s"}'),
    ('tab	and;semicolon', '{}');
INSERT INTO apis (tenant_id, name, status)
    SELECT 1 + (g % 3), 'api-' || g, (ARRAY['draft', 'published', 'deprecated']::api_status[])[1 + g % 3]
    FROM generate_series(1, 500) AS g;
SQL

before_fp=$(fingerprint)
before_tables=$(count_public_tables)
echo "  seeded: ${before_tables} tables, fingerprint ${before_fp}"

# -----------------------------------------------------------------------------
echo "== Backup (direct mode, local destination)"
# -----------------------------------------------------------------------------
if run_script "$WORK_DIR/backup.out" "$WORK_DIR/backup.err" \
    PG_CONNECTION_MODE=direct BACKUP_DESTINATION=local BACKUP_LOCAL_DIR="$BACKUP_DIR"; then
    pass "backup exits 0"
else
    fail "backup exits non-zero"; cat "$WORK_DIR/backup.err"
fi

# stdout must carry only the backup location (logs go to stderr)
backup_file=""
if [[ "$(wc -l <"$WORK_DIR/backup.out")" -eq 1 ]]; then
    backup_file=$(cat "$WORK_DIR/backup.out")
    pass "backup stdout is a single line"
else
    fail "backup stdout is not a single line:"; cat "$WORK_DIR/backup.out"
fi

if [[ -n "$backup_file" && -s "$backup_file" && "$backup_file" == "$BACKUP_DIR"/*/stoa_backup_*.sql.gz ]]; then
    pass "backup written to ${backup_file#"$WORK_DIR"/}"
else
    fail "backup file missing or misplaced: '${backup_file}'"
    echo "Cannot continue without a backup file" >&2
    exit 1
fi

if gunzip -t "$backup_file" && [[ "$(gunzip -c "$backup_file" | grep -c "PostgreSQL database dump complete")" -ge 1 ]]; then
    pass "backup is valid gzip with a complete dump"
else
    fail "backup is not a complete gzip dump"
fi

# -----------------------------------------------------------------------------
echo "== Damage the database, keep a session open, then restore"
# -----------------------------------------------------------------------------
sql "$TEST_DB" <<'SQL'
DELETE FROM apis WHERE id % 2 = 0;
UPDATE tenants SET settings = '{"tampered": true}'::jsonb;
CREATE TABLE stray_after_backup (id int);
SQL
if [[ "$(fingerprint)" != "$before_fp" ]]; then
    pass "database differs from backup before restore"
else
    fail "damage step did not change the database"
fi

# An open connection makes a plain DROP DATABASE fail; restore must handle it
psql --no-psqlrc -q -d "$TEST_DB" -c "SELECT pg_sleep(300);" >/dev/null 2>&1 &
HOLDER_PID=$!
for _ in $(seq 1 50); do
    [[ "$(sql postgres -v db="$TEST_DB" <<<"SELECT count(*) FROM pg_stat_activity WHERE datname = :'db' AND query LIKE '%pg_sleep%' AND pid <> pg_backend_pid();")" -ge 1 ]] && break
    sleep 0.1
done

if run_script "$WORK_DIR/restore.out" "$WORK_DIR/restore.err" \
    PG_CONNECTION_MODE=direct -- --restore "$backup_file" --force; then
    pass "restore exits 0 with an open session on the database"
else
    fail "restore exits non-zero"; cat "$WORK_DIR/restore.err"
fi
# The restore terminates the holder session; stop it anyway if it survived
kill "$HOLDER_PID" 2>/dev/null
wait "$HOLDER_PID" 2>/dev/null
HOLDER_PID=""

after_fp=$(fingerprint 2>/dev/null || echo "unavailable")
if [[ "$after_fp" == "$before_fp" ]]; then
    pass "restored data matches the backup (fingerprint ${after_fp})"
else
    fail "restored fingerprint ${after_fp} != ${before_fp}"
fi

if [[ "$(count_public_tables)" == "$before_tables" ]] \
    && [[ -z "$(sql "$TEST_DB" -c "SELECT to_regclass('public.stray_after_backup');")" ]]; then
    pass "objects created after the backup are gone"
else
    fail "table count after restore is $(count_public_tables), expected ${before_tables}"
fi

next_id=$(sql "$TEST_DB" -c "INSERT INTO apis (tenant_id, name, status) VALUES (1, 'post-restore', 'draft') RETURNING id;")
if [[ "$next_id" == "501" ]]; then
    pass "sequences restored (next id 501)"
else
    fail "unexpected next id after restore: ${next_id}"
fi
sql "$TEST_DB" -c "DELETE FROM apis WHERE id = 501; SELECT setval('apis_id_seq', 500);" >/dev/null
current_fp=$(fingerprint)

# -----------------------------------------------------------------------------
echo "== Invalid backups are rejected before the live database is touched"
# -----------------------------------------------------------------------------
truncated="${WORK_DIR}/truncated.sql.gz"
gunzip -c "$backup_file" | head -n -20 | gzip >"$truncated"
if run_script "$WORK_DIR/trunc.out" "$WORK_DIR/trunc.err" PG_CONNECTION_MODE=direct -- --restore "$truncated" --force; then
    fail "restore of a truncated backup exits 0"
else
    pass "restore of a truncated backup fails"
fi
[[ "$(fingerprint)" == "$current_fp" ]] && pass "database intact after truncated backup" || fail "database changed by truncated backup"

corrupt="${WORK_DIR}/corrupt.sql.gz"
head -c 4096 /dev/urandom >"$corrupt"
if run_script "$WORK_DIR/corrupt.out" "$WORK_DIR/corrupt.err" PG_CONNECTION_MODE=direct -- --restore "$corrupt" --force; then
    fail "restore of a corrupt backup exits 0"
else
    pass "restore of a corrupt backup fails"
fi
[[ "$(fingerprint)" == "$current_fp" ]] && pass "database intact after corrupt backup" || fail "database changed by corrupt backup"

if run_script "$WORK_DIR/missing.out" "$WORK_DIR/missing.err" PG_CONNECTION_MODE=direct -- --restore "${WORK_DIR}/does-not-exist.sql.gz" --force; then
    fail "restore of a missing file exits 0"
else
    pass "restore of a missing file fails"
fi
[[ "$(fingerprint)" == "$current_fp" ]] && pass "database intact after missing backup" || fail "database changed by missing backup"

# A complete-looking dump with a failing statement must fail, not half-restore
bad_sql="${WORK_DIR}/bad-sql.sql.gz"
{
    gunzip -c "$backup_file" | head -n -5
    echo "INSERT INTO table_that_does_not_exist VALUES (1);"
    gunzip -c "$backup_file" | tail -n 5
} | gzip >"$bad_sql"
if run_script "$WORK_DIR/badsql.out" "$WORK_DIR/badsql.err" PG_CONNECTION_MODE=direct -- --restore "$bad_sql" --force; then
    fail "restore of a dump with a SQL error exits 0"
else
    pass "restore of a dump with a SQL error fails"
fi
if [[ "$(count_public_tables 2>/dev/null)" == "0" ]]; then
    pass "failed restore is rolled back as one transaction (no partial schema)"
else
    fail "failed restore left a partial schema behind"
fi

# -----------------------------------------------------------------------------
echo "== Default kubectl mode (local kubectl stand-in, same disposable server)"
# -----------------------------------------------------------------------------
mkdir -p "$SHIM_DIR"
cat >"${SHIM_DIR}/kubectl" <<'SHIM'
#!/bin/bash
# Test stand-in for kubectl: records the call, runs `exec` targets locally.
echo "kubectl $*" >>"${KUBECTL_SHIM_LOG}"
case "$1" in
    cluster-info) exit 0 ;;
    config) echo "disposable-test"; exit 0 ;;
    get) echo "Running"; exit 0 ;;
    exec)
        shift
        while [[ $# -gt 0 && "$1" != "--" ]]; do shift; done
        shift
        exec "$@"
        ;;
esac
echo "unexpected kubectl call: $*" >&2
exit 1
SHIM
chmod +x "${SHIM_DIR}/kubectl"
shim_log="${WORK_DIR}/kubectl.log"
: >"$shim_log"

if run_script "$WORK_DIR/kbackup.out" "$WORK_DIR/kbackup.err" \
    PATH="${SHIM_DIR}:${PATH}" KUBECTL_SHIM_LOG="$shim_log" \
    BACKUP_DESTINATION=local BACKUP_LOCAL_DIR="${WORK_DIR}/kbackups" \
    PG_NAMESPACE=stoa-system PG_POD_NAME=control-plane-db-0 -- --restore "$backup_file" --force; then
    pass "kubectl-mode restore of the good backup exits 0"
else
    fail "kubectl-mode restore exits non-zero"; cat "$WORK_DIR/kbackup.err"
fi
[[ "$(fingerprint 2>/dev/null)" == "$before_fp" ]] && pass "kubectl-mode restore brings data back" || fail "kubectl-mode restore data mismatch"

if run_script "$WORK_DIR/kbackup2.out" "$WORK_DIR/kbackup2.err" \
    PATH="${SHIM_DIR}:${PATH}" KUBECTL_SHIM_LOG="$shim_log" \
    BACKUP_DESTINATION=local BACKUP_LOCAL_DIR="${WORK_DIR}/kbackups" \
    PG_NAMESPACE=stoa-system PG_POD_NAME=control-plane-db-0; then
    pass "kubectl-mode backup exits 0"
else
    fail "kubectl-mode backup exits non-zero"; cat "$WORK_DIR/kbackup2.err"
fi
kbackup_file=$(cat "$WORK_DIR/kbackup2.out" 2>/dev/null)
if [[ -s "$kbackup_file" ]] && [[ "$(gunzip -c "$kbackup_file" | grep -c "PostgreSQL database dump complete")" -ge 1 ]]; then
    pass "kubectl-mode backup is a complete dump"
else
    fail "kubectl-mode backup missing or incomplete: '${kbackup_file}'"
fi
if grep -q -- "exec -i -n stoa-system control-plane-db-0 -- pg_dump" "$shim_log" \
    && grep -q -- "exec -i -n stoa-system control-plane-db-0 -- psql" "$shim_log"; then
    pass "kubectl mode targets the configured namespace/pod with stdin attached"
else
    fail "unexpected kubectl invocations:"; cat "$shim_log"
fi

# -----------------------------------------------------------------------------
echo
echo "Result: ${PASSED} passed, ${FAILED} failed"
[[ "$FAILED" -eq 0 ]]
