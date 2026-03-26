#!/bin/bash
# Usage: ./contract-check.sh "<endpoint_pattern>"
# Returns: contracts and scenarios that traverse this contract
set -euo pipefail

PATTERN=${1:?Usage: $0 "<endpoint_pattern>"}
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DB="$SCRIPT_DIR/../stoa-impact.db"

if [ ! -f "$DB" ]; then
    echo "ERROR: Database not found at $DB"
    echo "Run: python3 docs/scripts/populate-db.py"
    exit 1
fi

echo "=== Contracts matching: $PATTERN ==="
echo ""

sqlite3 -column -header "$DB" <<EOF
SELECT c.id, c.contract_ref, c.source_component AS source, c.target_component AS target,
       c.type, CASE c.typed WHEN 1 THEN 'typed' ELSE 'UNTYPED' END AS schema,
       COALESCE(s.priority, '—') AS prio, COALESCE(s.name, '(no scenario)') AS scenario
FROM contracts c
LEFT JOIN scenario_steps ss ON ss.contract_id = c.id
LEFT JOIN scenarios s ON s.id = ss.scenario_id
WHERE c.contract_ref LIKE '%$PATTERN%' OR c.id LIKE '%$PATTERN%'
ORDER BY s.priority, c.id;
EOF
