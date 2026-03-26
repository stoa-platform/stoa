#!/bin/bash
# Usage: ./impact-check.sh <component_id>
# Returns: all scenarios and contracts impacted by a change to this component
set -euo pipefail

COMPONENT=${1:?Usage: $0 <component_id>}
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DB="$SCRIPT_DIR/../stoa-impact.db"

if [ ! -f "$DB" ]; then
    echo "ERROR: Database not found at $DB"
    echo "Run: python3 docs/scripts/populate-db.py"
    exit 1
fi

echo "=== Impact Analysis: $COMPONENT ==="
echo ""

echo "--- Outgoing Contracts ---"
sqlite3 -column -header "$DB" \
    "SELECT id, contract_ref, target_component AS target, type, CASE typed WHEN 1 THEN 'typed' ELSE 'UNTYPED' END AS schema FROM contracts WHERE source_component = '$COMPONENT' ORDER BY target_component;"
echo ""

echo "--- Incoming Contracts ---"
sqlite3 -column -header "$DB" \
    "SELECT id, contract_ref, source_component AS source, type, CASE typed WHEN 1 THEN 'typed' ELSE 'UNTYPED' END AS schema FROM contracts WHERE target_component = '$COMPONENT' ORDER BY source_component;"
echo ""

echo "--- Impacted Scenarios ---"
sqlite3 -column -header "$DB" \
    "SELECT DISTINCT s.priority, s.id, s.name, s.test_level, CASE s.test_in_ci WHEN 1 THEN 'CI' ELSE 'NO CI' END AS ci FROM scenarios s JOIN scenario_steps ss ON s.id = ss.scenario_id WHERE ss.component_id = '$COMPONENT' ORDER BY s.priority;"
echo ""

echo "--- Open Risks ---"
sqlite3 -column -header "$DB" \
    "SELECT id, severity, title FROM risks WHERE status = 'open' AND impacted_components LIKE '%$COMPONENT%' ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END;"
echo ""

echo "--- Risk Score ---"
sqlite3 -column -header "$DB" \
    "SELECT * FROM component_risk_score WHERE id = '$COMPONENT';"
