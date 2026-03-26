#!/bin/bash
# Post-Change Learning — compares actual changes with predicted impact
# Usage: ./post-change-learn.sh --commit HEAD --ticket CAB-1900
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DB="$SCRIPT_DIR/../stoa-impact.db"
FILE_MAP="$SCRIPT_DIR/../file-map.json"
CONTEXT_PACKS_DIR="$SCRIPT_DIR/../context-packs"
LEARNING_DIR="$SCRIPT_DIR/../learning"

if [ ! -f "$DB" ]; then
    echo "ERROR: Database not found at $DB"
    exit 1
fi

COMMIT=""
TICKET=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --commit) COMMIT="$2"; shift 2 ;;
        --ticket) TICKET="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [ -z "$COMMIT" ]; then
    echo "ERROR: --commit is required"
    echo "Usage: $0 --commit HEAD --ticket CAB-1900"
    exit 1
fi

COMMIT_HASH=$(git rev-parse "$COMMIT")
COMMIT_SHORT=$(git rev-parse --short "$COMMIT")

mkdir -p "$LEARNING_DIR"

# --- Get actual files changed ---
ACTUAL_FILES=$(git diff --name-only "${COMMIT}~1" "$COMMIT" 2>/dev/null || git diff --name-only --root "$COMMIT")

# --- Map files to components ---
map_files_to_components() {
    local files="$1"
    python3 -c "
import json, sys

with open('$FILE_MAP') as f:
    fm = json.load(f)

files = '''$files'''.strip().split('\n')
components = set()

for filepath in files:
    filepath = filepath.strip()
    if not filepath:
        continue
    best_match = ''
    best_comp = ''
    for comp, dirs in fm.items():
        for role, dir_path in dirs.items():
            if filepath.startswith(dir_path) and len(dir_path) > len(best_match):
                best_match = dir_path
                best_comp = comp
    if best_comp:
        components.add(best_comp)
    else:
        # Fallback: check top-level dir against DB repo_path
        top = filepath.split('/')[0]
        if top in ('control-plane-api', 'control-plane-ui', 'portal', 'stoa-gateway',
                    'stoa-go', 'keycloak', 'e2e', 'charts', 'deploy', 'shared',
                    'stoa-operator', 'cli'):
            components.add(top)

for c in sorted(components):
    print(c)
"
}

ACTUAL_COMPONENTS=$(map_files_to_components "$ACTUAL_FILES")

# --- Load predicted components from context pack (if exists) ---
PREDICTED_COMPONENTS=""
PREDICTED_FILES=""
CONTEXT_PACK=""

if [ -n "$TICKET" ]; then
    TICKET_LOWER=$(echo "$TICKET" | tr '[:upper:]' '[:lower:]')
    CONTEXT_PACK="$CONTEXT_PACKS_DIR/${TICKET_LOWER}.md"
fi

if [ -n "$CONTEXT_PACK" ] && [ -f "$CONTEXT_PACK" ]; then
    # Extract predicted components from the context pack table
    PREDICTED_COMPONENTS=$(grep -E '^\|' "$CONTEXT_PACK" | grep -v '^\|[-]' | grep -v '^\| Composant' | grep -v '^\| Contrat' | grep -v '^\| Scénario' | grep -v '^\| ID' | head -20 | awk -F'|' '{gsub(/^[ \t]+|[ \t]+$/, "", $2); if ($2 != "" && $2 != "Composant") print $2}' | sort -u || true)

    PREDICTED_FILES=$(grep '`' "$CONTEXT_PACK" | grep -E '^\-' | sed 's/.*`\([^`]*\)`.*/\1/' | sort -u || true)
    HAS_PREDICTION=1
else
    HAS_PREDICTION=0
fi

# --- Calculate precision/recall ---
NOW=$(date "+%Y-%m-%d %H:%M")

if [ "$HAS_PREDICTION" -eq 1 ] && [ -n "$PREDICTED_COMPONENTS" ]; then
    METRICS=$(python3 -c "
import json

predicted = set('''$PREDICTED_COMPONENTS'''.strip().split('\n'))
predicted = {p.strip() for p in predicted if p.strip()}
actual = set('''$ACTUAL_COMPONENTS'''.strip().split('\n'))
actual = {a.strip() for a in actual if a.strip()}

tp = predicted & actual
fp = predicted - actual
fn = actual - predicted

precision = len(tp) / len(predicted) if predicted else 0
recall = len(tp) / len(actual) if actual else 0
f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

result = {
    'tp': sorted(tp),
    'fp': sorted(fp),
    'fn': sorted(fn),
    'precision': round(precision, 3),
    'recall': round(recall, 3),
    'f1': round(f1, 3),
    'predicted': sorted(predicted),
    'actual': sorted(actual)
}
print(json.dumps(result))
")

    PRECISION=$(echo "$METRICS" | python3 -c "import json,sys; print(json.load(sys.stdin)['precision'])")
    RECALL=$(echo "$METRICS" | python3 -c "import json,sys; print(json.load(sys.stdin)['recall'])")
    F1=$(echo "$METRICS" | python3 -c "import json,sys; print(json.load(sys.stdin)['f1'])")
    TP=$(echo "$METRICS" | python3 -c "import json,sys; print(', '.join(json.load(sys.stdin)['tp']) or 'none')")
    FP=$(echo "$METRICS" | python3 -c "import json,sys; print(', '.join(json.load(sys.stdin)['fp']) or 'none')")
    FN=$(echo "$METRICS" | python3 -c "import json,sys; print(', '.join(json.load(sys.stdin)['fn']) or 'none')")
else
    PRECISION="N/A"
    RECALL="N/A"
    F1="N/A"
    TP="N/A"
    FP="N/A"
    FN="N/A"
fi

# --- Generate report ---
REPORT_FILE="$LEARNING_DIR/${TICKET:-$COMMIT_SHORT}.md"

cat > "$REPORT_FILE" << EOF
# Post-Change Report: ${TICKET:-$COMMIT_SHORT}
> Commit: $COMMIT_SHORT ($COMMIT_HASH)
> Date: $NOW
> Context pack: $([ "$HAS_PREDICTION" -eq 1 ] && echo "found ($CONTEXT_PACK)" || echo "not found")

## Composants réellement modifiés

$(echo "$ACTUAL_COMPONENTS" | while read -r comp; do [ -n "$comp" ] && echo "- $comp"; done)

## Fichiers modifiés

$(echo "$ACTUAL_FILES" | while read -r f; do [ -n "$f" ] && echo "- \`$f\`"; done)
EOF

if [ "$HAS_PREDICTION" -eq 1 ] && [ -n "$PREDICTED_COMPONENTS" ]; then
    cat >> "$REPORT_FILE" << EOF

## Prédiction vs Réalité

| Composant | Prédit ? | Touché ? | Verdict |
|-----------|----------|----------|---------|
EOF

    # Generate comparison table
    python3 -c "
import json

metrics = json.loads('''$METRICS''')
all_comps = sorted(set(metrics['predicted']) | set(metrics['actual']))

for comp in all_comps:
    predicted = '✅' if comp in metrics['predicted'] else '❌'
    actual = '✅' if comp in metrics['actual'] else '❌'
    if comp in metrics['tp']:
        verdict = 'TP (True Positive)'
    elif comp in metrics['fp']:
        verdict = 'FP (False Positive — prédit mais pas touché)'
    elif comp in metrics['fn']:
        verdict = 'FN (False Negative — pas prédit, touché !)'
    else:
        verdict = '?'
    print(f'| {comp} | {predicted} | {actual} | {verdict} |')
" >> "$REPORT_FILE"

    cat >> "$REPORT_FILE" << EOF

## Métriques
- Précision : $(echo "$PRECISION * 100" | bc -l 2>/dev/null || echo "$PRECISION")%
- Rappel : $(echo "$RECALL * 100" | bc -l 2>/dev/null || echo "$RECALL")%
- F1-Score : $F1
EOF

    if [ "$FN" != "none" ] && [ "$FN" != "N/A" ]; then
        cat >> "$REPORT_FILE" << EOF

## False Negatives (CRITIQUE — la DB a raté ces impacts)

$(echo "$FN" | tr ',' '\n' | while read -r comp; do
    comp=$(echo "$comp" | xargs)
    [ -n "$comp" ] && echo "- **$comp** touché mais non prédit → VÉRIFIER si un contrat manque dans la DB"
done)

## Contrats manquants suggérés

\`\`\`sql
$(echo "$FN" | tr ',' '\n' | while read -r comp; do
    comp=$(echo "$comp" | xargs)
    [ -n "$comp" ] && echo "-- Auto-detected missing contract on $NOW"
    [ -n "$comp" ] && echo "-- INSERT INTO contracts VALUES ('REVIEW-ME', '???', '$comp', 'rest-api', 'UNKNOWN', 'none', NULL, 0, 'Auto-detected by post-change learning');"
done)
\`\`\`
EOF
    fi

    # Store in DB
    PRED_JSON=$(echo "$METRICS" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin)['predicted']))")
    ACT_JSON=$(echo "$METRICS" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin)['actual']))")
    FN_JSON=$(echo "$METRICS" | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin)['fn']))")
    ACTUAL_FILES_JSON=$(echo "$ACTUAL_FILES" | python3 -c "import json,sys; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))")

    sqlite3 "$DB" "INSERT INTO change_log (ticket_ref, commit_hash, components_predicted, components_actual, files_actual, precision, recall, f1_score, false_negatives)
    VALUES ('${TICKET:-}', '$COMMIT_HASH', '$PRED_JSON', '$ACT_JSON', '$ACTUAL_FILES_JSON', $PRECISION, $RECALL, $F1, '$FN_JSON');"
else
    cat >> "$REPORT_FILE" << EOF

## Note
Pas de context pack trouvé pour ce ticket — pas de comparaison prédiction/réalité possible.
Composants touchés enregistrés pour enrichir le co-change discovery.
EOF

    # Still store actual data
    ACTUAL_FILES_JSON=$(echo "$ACTUAL_FILES" | python3 -c "import json,sys; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))")
    ACT_JSON=$(echo "$ACTUAL_COMPONENTS" | python3 -c "import json,sys; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))")

    sqlite3 "$DB" "INSERT INTO change_log (ticket_ref, commit_hash, components_actual, files_actual)
    VALUES ('${TICKET:-}', '$COMMIT_HASH', '$ACT_JSON', '$ACTUAL_FILES_JSON');"
fi

echo ""
echo "✅ Post-change report: $REPORT_FILE"
if [ "$HAS_PREDICTION" -eq 1 ] && [ -n "$PREDICTED_COMPONENTS" ]; then
    echo "   Precision: $PRECISION | Recall: $RECALL | F1: $F1"
    [ "$FN" != "none" ] && [ "$FN" != "N/A" ] && echo "   ⚠️  False Negatives: $FN"
fi
echo "   Logged to change_log table in DB"
