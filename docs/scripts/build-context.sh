#!/bin/bash
# Context Pack Builder — generates structured impact context for a ticket/component/file
# Usage:
#   ./build-context.sh --component control-plane-api --intent "ajouter endpoint audit-log"
#   ./build-context.sh --ticket "CAB-1900"
#   ./build-context.sh --file "control-plane-api/src/routers/tenants.py"
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DB="$SCRIPT_DIR/../stoa-impact.db"
FILE_MAP="$SCRIPT_DIR/../file-map.json"
OUTPUT_DIR="$SCRIPT_DIR/../context-packs"

if [ ! -f "$DB" ]; then
    echo "ERROR: Database not found at $DB"
    exit 1
fi
if [ ! -f "$FILE_MAP" ]; then
    echo "ERROR: file-map.json not found at $FILE_MAP"
    exit 1
fi

COMPONENT=""
INTENT=""
TICKET=""
FILE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --component) COMPONENT="$2"; shift 2 ;;
        --intent) INTENT="$2"; shift 2 ;;
        --ticket) TICKET="$2"; shift 2 ;;
        --file) FILE="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# --- Helper: resolve component from file path ---
resolve_component_from_file() {
    local filepath="$1"
    # Try matching against file-map paths
    local comp
    comp=$(python3 -c "
import json, sys
with open('$FILE_MAP') as f:
    fm = json.load(f)
path = '$filepath'
best_match = ''
best_comp = ''
for comp, dirs in fm.items():
    for role, dir_path in dirs.items():
        if path.startswith(dir_path) and len(dir_path) > len(best_match):
            best_match = dir_path
            best_comp = comp
if best_comp:
    print(best_comp)
else:
    # Fallback: match top-level directory to DB repo_path
    top = path.split('/')[0] + '/'
    print(top.rstrip('/'))
")
    echo "$comp"
}

# --- Resolve component ---
if [ -n "$FILE" ]; then
    COMPONENT=$(resolve_component_from_file "$FILE")
    if [ -z "$INTENT" ]; then
        INTENT="modification de $FILE"
    fi
elif [ -n "$TICKET" ]; then
    if [ -z "$COMPONENT" ]; then
        echo "INFO: --ticket mode requires --component or will use generic analysis"
        COMPONENT="control-plane-api"  # default fallback
    fi
    if [ -z "$INTENT" ]; then
        INTENT="ticket $TICKET"
    fi
fi

if [ -z "$COMPONENT" ]; then
    echo "ERROR: Could not determine component. Use --component, --file, or --ticket with --component"
    exit 1
fi

# Verify component exists in DB
COMP_EXISTS=$(sqlite3 "$DB" "SELECT COUNT(*) FROM components WHERE id = '$COMPONENT';")
if [ "$COMP_EXISTS" -eq 0 ]; then
    echo "WARNING: Component '$COMPONENT' not found in DB. Trying repo_path match..."
    COMPONENT=$(sqlite3 "$DB" "SELECT id FROM components WHERE repo_path LIKE '%${COMPONENT}%' LIMIT 1;" || true)
    if [ -z "$COMPONENT" ]; then
        echo "ERROR: No matching component found in DB"
        exit 1
    fi
fi

COMP_NAME=$(sqlite3 "$DB" "SELECT name FROM components WHERE id = '$COMPONENT';")

# --- Determine output filename ---
if [ -n "$TICKET" ]; then
    OUTPUT_ID=$(echo "$TICKET" | tr '[:upper:]' '[:lower:]')
else
    OUTPUT_ID=$(date +%Y%m%d-%H%M%S)
fi
OUTPUT_FILE="$OUTPUT_DIR/${OUTPUT_ID}.md"
mkdir -p "$OUTPUT_DIR"

NOW=$(date "+%Y-%m-%d %H:%M")

# --- Query DB ---

# 1. Outgoing contracts (this component impacts others)
CONTRACTS_OUT=$(sqlite3 -separator '|' "$DB" "
SELECT id, type, contract_ref, target_component,
    CASE typed WHEN 1 THEN 'Yes' ELSE 'No' END
FROM contracts WHERE source_component = '$COMPONENT'
ORDER BY target_component;
")

# 2. Incoming contracts (others depend on this component, exclude self-refs already in OUT)
CONTRACTS_IN=$(sqlite3 -separator '|' "$DB" "
SELECT id, type, contract_ref, source_component,
    CASE typed WHEN 1 THEN 'Yes' ELSE 'No' END
FROM contracts WHERE target_component = '$COMPONENT' AND source_component != '$COMPONENT'
ORDER BY source_component;
")

# 3. Impacted components (unique set from contracts, excluding self-references)
IMPACTED_COMPONENTS=$(sqlite3 -separator '|' "$DB" "
SELECT DISTINCT target_component, 'CONSUMER' AS relation
FROM contracts WHERE source_component = '$COMPONENT' AND target_component != '$COMPONENT'
UNION
SELECT DISTINCT source_component, 'PROVIDER' AS relation
FROM contracts WHERE target_component = '$COMPONENT' AND source_component != '$COMPONENT';
")

# 4. Scenarios traversed
SCENARIOS=$(sqlite3 -separator '|' "$DB" "
SELECT DISTINCT s.id, s.name, s.priority,
    CASE s.test_in_ci WHEN 1 THEN '✅' ELSE '❌' END,
    GROUP_CONCAT(DISTINCT 'step ' || ss.step_order)
FROM scenarios s
JOIN scenario_steps ss ON s.id = ss.scenario_id
WHERE ss.component_id = '$COMPONENT'
GROUP BY s.id
ORDER BY s.priority;
")

# 5. Open risks
RISKS=$(sqlite3 -separator '|' "$DB" "
SELECT id, severity, title
FROM risks
WHERE status = 'open' AND impacted_components LIKE '%$COMPONENT%'
ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END;
")

# 6. Untyped contracts impacted
UNTYPED=$(sqlite3 -separator '|' "$DB" "
SELECT id, contract_ref, source_component, target_component
FROM contracts
WHERE typed = 0 AND (source_component = '$COMPONENT' OR target_component = '$COMPONENT');
")

# --- Calculate impact score ---
NB_CONTRACTS=$(sqlite3 "$DB" "SELECT COUNT(*) FROM contracts WHERE source_component = '$COMPONENT' OR target_component = '$COMPONENT';")
NB_P0=$(sqlite3 "$DB" "SELECT COUNT(DISTINCT s.id) FROM scenarios s JOIN scenario_steps ss ON s.id = ss.scenario_id WHERE ss.component_id = '$COMPONENT' AND s.priority = 'P0';")
NB_P1=$(sqlite3 "$DB" "SELECT COUNT(DISTINCT s.id) FROM scenarios s JOIN scenario_steps ss ON s.id = ss.scenario_id WHERE ss.component_id = '$COMPONENT' AND s.priority = 'P1';")
NB_UNTYPED=$(sqlite3 "$DB" "SELECT COUNT(*) FROM contracts WHERE typed = 0 AND (source_component = '$COMPONENT' OR target_component = '$COMPONENT');")
NB_RISKS=$(sqlite3 "$DB" "SELECT COUNT(*) FROM risks WHERE status = 'open' AND impacted_components LIKE '%$COMPONENT%';")

IMPACT_SCORE=$(( NB_CONTRACTS * 2 + NB_P0 * 5 + NB_P1 * 2 + NB_UNTYPED * 3 + NB_RISKS * 1 ))

if [ "$IMPACT_SCORE" -ge 31 ]; then
    IMPACT_LEVEL="CRITICAL"
elif [ "$IMPACT_SCORE" -ge 16 ]; then
    IMPACT_LEVEL="HIGH"
elif [ "$IMPACT_SCORE" -ge 6 ]; then
    IMPACT_LEVEL="MEDIUM"
else
    IMPACT_LEVEL="LOW"
fi

# --- Resolve file paths from file-map ---
FILES_MODIFY=$(python3 -c "
import json
with open('$FILE_MAP') as f:
    fm = json.load(f)
comp = '$COMPONENT'
if comp in fm:
    for role, path in fm[comp].items():
        if role in ('tests', 'tests_contract', 'tests_integration', 'tests_resilience', 'tests_security', 'tests_e2e', 'test_helpers'):
            continue
        print(f'- \`{path}\` — {role}')
")

FILES_TESTS=$(python3 -c "
import json
with open('$FILE_MAP') as f:
    fm = json.load(f)
comp = '$COMPONENT'
if comp in fm:
    for role, path in fm[comp].items():
        if 'test' in role:
            print(f'- \`{path}\`')
")

FILES_PROPAGATE=$(python3 -c "
import json
with open('$FILE_MAP') as f:
    fm = json.load(f)
comp = '$COMPONENT'
# Get impacted components from contracts
import subprocess
result = subprocess.run(
    ['sqlite3', '-separator', '|', '$DB',
     \"SELECT DISTINCT target_component FROM contracts WHERE source_component = '\"+ comp +\"' UNION SELECT DISTINCT source_component FROM contracts WHERE target_component = '\" + comp + \"'\"],
    capture_output=True, text=True)
impacted = [c.strip() for c in result.stdout.strip().split('\n') if c.strip()]
for ic in impacted:
    if ic in fm:
        for role, path in fm[ic].items():
            if role in ('services', 'components', 'types', 'api_types', 'handlers', 'routers'):
                print(f'- \`{path}\` — {ic} ({role})')
")

# --- Write context pack ---
cat > "$OUTPUT_FILE" << HEADER
# Context Pack: ${TICKET:-$COMPONENT} — ${INTENT:-analysis}
> Generated: $NOW
> Primary component: $COMPONENT ($COMP_NAME)
> Intent: ${INTENT:-general analysis}
> **Impact Score: $IMPACT_SCORE ($IMPACT_LEVEL)**

HEADER

# Section 1: Impacted components
cat >> "$OUTPUT_FILE" << 'SECTION1'
## 1. Composants impactés

| Composant | Relation | Risque |
|-----------|----------|--------|
SECTION1

echo "| $COMPONENT | PRIMARY — modification directe | HIGH |" >> "$OUTPUT_FILE"
while IFS='|' read -r comp_id relation; do
    [ -z "$comp_id" ] && continue
    risk="MEDIUM"
    # Check if there are untyped contracts with this component
    has_untyped=$(sqlite3 "$DB" "SELECT COUNT(*) FROM contracts WHERE typed = 0 AND ((source_component = '$COMPONENT' AND target_component = '$comp_id') OR (source_component = '$comp_id' AND target_component = '$COMPONENT'));")
    if [ "$has_untyped" -gt 0 ]; then
        risk="HIGH"
    fi
    echo "| $comp_id | $relation | $risk |" >> "$OUTPUT_FILE"
done <<< "$IMPACTED_COMPONENTS"
echo "" >> "$OUTPUT_FILE"

# Section 2: Contracts
cat >> "$OUTPUT_FILE" << 'SECTION2'
## 2. Contrats à respecter

| Contrat ID | Type | Ref | Source → Target | Typé ? |
|------------|------|-----|-----------------|--------|
SECTION2

while IFS='|' read -r cid ctype cref ctarget ctyped; do
    [ -z "$cid" ] && continue
    echo "| $cid | $ctype | $cref | $COMPONENT → $ctarget | $ctyped |" >> "$OUTPUT_FILE"
done <<< "$CONTRACTS_OUT"

while IFS='|' read -r cid ctype cref csource ctyped; do
    [ -z "$cid" ] && continue
    echo "| $cid | $ctype | $cref | $csource → $COMPONENT | $ctyped |" >> "$OUTPUT_FILE"
done <<< "$CONTRACTS_IN"

echo "" >> "$OUTPUT_FILE"

if [ -n "$UNTYPED" ]; then
    echo "⚠️ **CONTRATS NON TYPÉS** (risque de casse silencieuse) :" >> "$OUTPUT_FILE"
    while IFS='|' read -r uid uref usrc utgt; do
        [ -z "$uid" ] && continue
        echo "- \`$uid\` — $uref ($usrc → $utgt)" >> "$OUTPUT_FILE"
    done <<< "$UNTYPED"
    echo "" >> "$OUTPUT_FILE"
fi

# Section 3: Scenarios
cat >> "$OUTPUT_FILE" << 'SECTION3'
## 3. Scénarios end-to-end traversés

| Scénario | Priorité | Test CI ? | Steps impactés |
|----------|----------|-----------|----------------|
SECTION3

while IFS='|' read -r sid sname sprio sci ssteps; do
    [ -z "$sid" ] && continue
    echo "| $sid $sname | $sprio | $sci | $ssteps |" >> "$OUTPUT_FILE"
done <<< "$SCENARIOS"
echo "" >> "$OUTPUT_FILE"

# Section 4: Files
cat >> "$OUTPUT_FILE" << SECTION4
## 4. Fichiers probablement concernés

### Modification directe (toucher)
$FILES_MODIFY

### Propagation (vérifier)
$FILES_PROPAGATE

### Tests à relancer
$FILES_TESTS

SECTION4

# Section 5: Risks
cat >> "$OUTPUT_FILE" << 'SECTION5'
## 5. Risques ouverts liés

| ID | Sévérité | Titre |
|----|----------|-------|
SECTION5

while IFS='|' read -r rid rsev rtitle; do
    [ -z "$rid" ] && continue
    echo "| $rid | $rsev | $rtitle |" >> "$OUTPUT_FILE"
done <<< "$RISKS"
echo "" >> "$OUTPUT_FILE"

# Section 6: Invariants
cat >> "$OUTPUT_FILE" << 'SECTION6'
## 6. Invariants à ne pas casser

- [ ] Les types réponse DOIVENT rester backward-compatible (ajout OK, suppression/rename NON)
- [ ] Les scénarios P0 impactés DOIVENT être validés manuellement si pas de test E2E en CI
- [ ] Si contrat non typé impacté → vérifier manuellement la compatibilité
- [ ] Si Kafka event touché → vérifier le consumer de l'autre côté
- [ ] Si schema Pydantic/TypeScript modifié → vérifier les consumers frontend

SECTION6

# Section 7: Contextual DoD
CONSUMERS=$(sqlite3 "$DB" "SELECT GROUP_CONCAT(target_component, ', ') FROM (SELECT DISTINCT target_component FROM contracts WHERE source_component = '$COMPONENT' AND target_component != '$COMPONENT');" 2>/dev/null || echo "N/A")
cat >> "$OUTPUT_FILE" << SECTION7
## 7. DoD contextualisé

- [ ] Changement implémenté + tests unitaires
- [ ] Lint + format clean
- [ ] Consumers vérifiés ($CONSUMERS)
- [ ] Scénarios P0 impactés validés ($NB_P0 scénario(s))
- [ ] Contrats non typés vérifiés manuellement ($NB_UNTYPED contrat(s))
- [ ] Impact DB mise à jour si nouveau contrat
- [ ] \`regenerate-docs.py\` exécuté si DB modifiée
SECTION7

echo ""
echo "✅ Context pack generated: $OUTPUT_FILE"
echo "   Impact Score: $IMPACT_SCORE ($IMPACT_LEVEL)"
echo "   Contracts: $NB_CONTRACTS | P0 scenarios: $NB_P0 | Untyped: $NB_UNTYPED | Risks: $NB_RISKS"
