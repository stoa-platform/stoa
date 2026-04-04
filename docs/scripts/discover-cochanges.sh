#!/bin/bash
# Co-Change Discovery — finds components that change together but lack contracts in the DB
# Usage: ./discover-cochanges.sh --commits 100
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DB="$SCRIPT_DIR/../stoa-impact.db"
FILE_MAP="$SCRIPT_DIR/../file-map.json"
LEARNING_DIR="$SCRIPT_DIR/../learning"

if [ ! -f "$DB" ]; then
    echo "ERROR: Database not found at $DB"
    exit 1
fi

COMMIT_COUNT=100

while [[ $# -gt 0 ]]; do
    case $1 in
        --commits) COMMIT_COUNT="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

mkdir -p "$LEARNING_DIR"

echo "Analyzing last $COMMIT_COUNT commits for co-change patterns..."

python3 - "$DB" "$FILE_MAP" "$COMMIT_COUNT" "$LEARNING_DIR" << 'PYEOF'
import json
import subprocess
import sys
import sqlite3
from collections import defaultdict
from itertools import combinations
from datetime import datetime

db_path = sys.argv[1]
file_map_path = sys.argv[2]
commit_count = sys.argv[3]
learning_dir = sys.argv[4]

with open(file_map_path) as f:
    file_map = json.load(f)

def file_to_component(filepath):
    best_match = ""
    best_comp = ""
    for comp, dirs in file_map.items():
        for role, dir_path in dirs.items():
            if filepath.startswith(dir_path) and len(dir_path) > len(best_match):
                best_match = dir_path
                best_comp = comp
    return best_comp if best_comp else None

# Get commit hashes
result = subprocess.run(
    ["git", "log", "--oneline", f"-{commit_count}", "--format=%H"],
    capture_output=True, text=True, check=True
)
commits = [c.strip() for c in result.stdout.strip().split("\n") if c.strip()]

# For each commit, get changed files and map to components
cochange_counts = defaultdict(int)
total_commits = 0

for commit in commits:
    result = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "-r", "--name-only", commit],
        capture_output=True, text=True
    )
    files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    components = set()
    for f in files:
        comp = file_to_component(f)
        if comp:
            components.add(comp)

    if len(components) >= 2:
        total_commits += 1
        for pair in combinations(sorted(components), 2):
            cochange_counts[pair] += 1

# Load existing contracts from DB
db = sqlite3.connect(db_path)
cursor = db.cursor()

existing_contracts = set()
cursor.execute("SELECT DISTINCT source_component, target_component FROM contracts")
for row in cursor.fetchall():
    pair = tuple(sorted([row[0], row[1]]))
    existing_contracts.add(pair)

sorted_pairs = sorted(cochange_counts.items(), key=lambda x: -x[1])

# Update DB
for (comp_a, comp_b), count in sorted_pairs:
    has_contract = 1 if (comp_a, comp_b) in existing_contracts or (comp_b, comp_a) in existing_contracts else 0
    cursor.execute("""
        INSERT INTO cochange_pairs (component_a, component_b, cochange_count, has_contract, last_updated)
        VALUES (?, ?, ?, ?, datetime('now'))
        ON CONFLICT(component_a, component_b) DO UPDATE SET
            cochange_count = excluded.cochange_count,
            has_contract = excluded.has_contract,
            last_updated = datetime('now')
    """, (comp_a, comp_b, count, has_contract))

db.commit()
db.close()

# Generate report
now = datetime.now().strftime("%Y-%m-%d %H:%M")
lines = []
lines.append("# Co-Change Discovery Report")
lines.append(f"> Based on last {len(commits)} commits ({total_commits} multi-component)")
lines.append(f"> Generated: {now}")
lines.append("")
lines.append("## Paires de composants fréquemment co-modifiées")
lines.append("")
lines.append("| Comp A | Comp B | Co-changes | Contrat existe ? | Action |")
lines.append("|--------|--------|-----------|-----------------|--------|")

missing = []
for (comp_a, comp_b), count in sorted_pairs:
    if count < 2:
        continue
    has = (comp_a, comp_b) in existing_contracts or (comp_b, comp_a) in existing_contracts
    action = "✅ OK" if has else "⚠️ Contrat manquant"
    lines.append(f"| {comp_a} | {comp_b} | {count} | {'Oui' if has else 'Non'} | {action} |")
    if not has and count >= 3:
        missing.append((comp_a, comp_b, count))

lines.append("")

if missing:
    lines.append("## Contrats manquants suggérés")
    lines.append("")
    for ca, cb, cnt in missing:
        lines.append(f"- **{ca}** ↔ **{cb}** ({cnt} co-changes) — investiguer le type de couplage")
    lines.append("")
    lines.append("```sql")
    lines.append("-- Suggested contracts to investigate")
    for ca, cb, cnt in missing:
        lines.append(f"-- {ca} ↔ {cb} ({cnt} co-changes)")
        lines.append(f"-- INSERT INTO contracts VALUES ('REVIEW-{ca}-{cb}', '{ca}', '{cb}', 'rest-api', 'INVESTIGATE', 'none', NULL, 0, 'Co-change detected ({cnt}x)');")
    lines.append("```")
else:
    lines.append("## Résultat")
    lines.append("")
    lines.append("Toutes les paires fréquentes (>= 3 co-changes) ont un contrat existant. ✅")

report = "\n".join(lines)
report_path = f"{learning_dir}/cochange-report.md"
with open(report_path, "w") as f:
    f.write(report)
print(report)
print()
print(f"✅ Report written to {report_path}")
print(f"   DB updated: cochange_pairs table")
PYEOF
