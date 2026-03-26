#!/bin/bash
# Quick health dashboard of the impact analysis system
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DB="$SCRIPT_DIR/../stoa-impact.db"

if [ ! -f "$DB" ]; then
    echo "ERROR: Database not found at $DB"
    echo "Run: python3 docs/scripts/populate-db.py"
    exit 1
fi

echo "=== STOA Impact Analysis Dashboard ==="
echo ""
echo "Components:        $(sqlite3 "$DB" 'SELECT COUNT(*) FROM components WHERE status = "active"') active ($(sqlite3 "$DB" 'SELECT COUNT(*) FROM components') total)"
echo "Contracts:         $(sqlite3 "$DB" 'SELECT COUNT(*) FROM contracts') total ($(sqlite3 "$DB" 'SELECT COUNT(*) FROM contracts WHERE typed = 1') typed, $(sqlite3 "$DB" 'SELECT COUNT(*) FROM contracts WHERE typed = 0') untyped)"
echo "Scenarios:         $(sqlite3 "$DB" 'SELECT COUNT(*) FROM scenarios') total ($(sqlite3 "$DB" 'SELECT COUNT(*) FROM scenarios WHERE test_in_ci = 1') in CI)"
echo "Scenario Steps:    $(sqlite3 "$DB" 'SELECT COUNT(*) FROM scenario_steps')"
echo "Open Risks:        $(sqlite3 "$DB" 'SELECT COUNT(*) FROM risks WHERE status = "open"')"
echo "  CRITICAL:        $(sqlite3 "$DB" 'SELECT COUNT(*) FROM risks WHERE severity = "CRITICAL" AND status = "open"')"
echo "  HIGH:            $(sqlite3 "$DB" 'SELECT COUNT(*) FROM risks WHERE severity = "HIGH" AND status = "open"')"
echo "  MEDIUM:          $(sqlite3 "$DB" 'SELECT COUNT(*) FROM risks WHERE severity = "MEDIUM" AND status = "open"')"
echo ""

echo "--- Top Risk Components ---"
sqlite3 -column -header "$DB" "SELECT * FROM component_risk_score LIMIT 5;"
echo ""

echo "--- Untested P0 Scenarios ---"
sqlite3 -column -header "$DB" "SELECT id, name, test_level FROM untested_scenarios WHERE priority = 'P0';"
echo ""

echo "--- Untyped Cross-Language Contracts (Kafka) ---"
sqlite3 -column -header "$DB" "SELECT id, contract_ref, source_component, target_component FROM untyped_contracts WHERE type = 'kafka-event';"
echo ""

echo "--- Open CRITICAL/HIGH Risks ---"
sqlite3 -column -header "$DB" "SELECT id, severity, title FROM risks WHERE status = 'open' AND severity IN ('CRITICAL', 'HIGH') ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 ELSE 2 END;"
echo ""

# Context Compiler accuracy (if change_log table exists)
HAS_CHANGELOG=$(sqlite3 "$DB" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='change_log';")
if [ "$HAS_CHANGELOG" -eq 1 ]; then
    CHANGELOG_COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM change_log WHERE precision IS NOT NULL;")
    if [ "$CHANGELOG_COUNT" -gt 0 ]; then
        echo "--- Context Compiler Accuracy (last 20 changes) ---"
        sqlite3 -column -header "$DB" "SELECT
            ROUND(AVG(precision)*100,1) AS avg_precision_pct,
            ROUND(AVG(recall)*100,1) AS avg_recall_pct,
            ROUND(AVG(f1_score)*100,1) AS avg_f1_pct,
            COUNT(*) AS total_changes
        FROM (SELECT * FROM change_log WHERE precision IS NOT NULL ORDER BY date DESC LIMIT 20);"
        echo ""
    fi

    COCHANGE_COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='cochange_pairs';")
    if [ "$COCHANGE_COUNT" -eq 1 ]; then
        MISSING=$(sqlite3 "$DB" "SELECT COUNT(*) FROM cochange_pairs WHERE has_contract = 0 AND cochange_count >= 3;")
        if [ "$MISSING" -gt 0 ]; then
            echo "--- Co-Change Gaps (frequent pairs without contracts) ---"
            sqlite3 -column -header "$DB" "SELECT component_a, component_b, cochange_count FROM cochange_pairs WHERE has_contract = 0 AND cochange_count >= 3 ORDER BY cochange_count DESC LIMIT 10;"
            echo ""
        fi
    fi
fi
