#!/bin/bash
# Usage: ./risk-report.sh [severity]
# Returns: open risks, optionally filtered by severity
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DB="$SCRIPT_DIR/../stoa-impact.db"
SEVERITY=${1:-""}

if [ ! -f "$DB" ]; then
    echo "ERROR: Database not found at $DB"
    echo "Run: python3 docs/scripts/populate-db.py"
    exit 1
fi

echo "=== STOA Risk Report ==="
echo ""

if [ -n "$SEVERITY" ]; then
    sqlite3 -column -header "$DB" \
        "SELECT id, severity, title, impacted_components, status, COALESCE(ticket_ref, '—') AS ticket FROM risks WHERE severity = '$SEVERITY' AND status = 'open';"
else
    sqlite3 -column -header "$DB" \
        "SELECT id, severity, title, impacted_components, status, COALESCE(ticket_ref, '—') AS ticket FROM risks WHERE status = 'open' ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END;"
fi

echo ""
echo "--- Risk Distribution ---"
sqlite3 -column -header "$DB" \
    "SELECT severity, COUNT(*) AS count FROM risks WHERE status = 'open' GROUP BY severity ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END;"
