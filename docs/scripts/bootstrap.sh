#!/bin/bash
set -euo pipefail

# ══════════════════════════════════════════════════
# STOA Impact Analysis — Bootstrap
# Usage: ./docs/scripts/bootstrap.sh [key_path]
# ══════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOCS_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$DOCS_DIR")"
DB_PATH="$DOCS_DIR/stoa-impact.db"

echo "=== STOA Impact Analysis Bootstrap ==="
echo ""

# 1. Check git-crypt
if ! command -v git-crypt &>/dev/null; then
    echo "❌ git-crypt not installed."
    echo "   macOS:  brew install git-crypt"
    echo "   Ubuntu: apt-get install git-crypt"
    exit 1
fi

# 2. Check if already unlocked
if git-crypt status &>/dev/null 2>&1; then
    LOCKED_COUNT=$(git-crypt status 2>/dev/null | grep -c "encrypted:" || true)
    if [ "$LOCKED_COUNT" -gt 0 ]; then
        echo "🔒 Repository is locked ($LOCKED_COUNT encrypted files)."

        KEY_PATH="${1:-$HOME/.stoa/keys/stoa-git-crypt.key}"

        if [ -f "$KEY_PATH" ]; then
            echo "   Unlocking with $KEY_PATH..."
            cd "$REPO_ROOT"
            git-crypt unlock "$KEY_PATH"
            echo "✅ Unlocked."
        else
            echo "❌ Key not found at $KEY_PATH"
            echo "   Options:"
            echo "   1. Copy key from another device: scp user@desktop:~/.stoa/keys/stoa-git-crypt.key ~/.stoa/keys/"
            echo "   2. Pull from Vault: vault kv get -field=key stoa/secrets/git-crypt > ~/.stoa/keys/stoa-git-crypt.key"
            echo "   3. Specify path: ./bootstrap.sh /path/to/key"
            exit 1
        fi
    else
        echo "✅ Repository already unlocked."
    fi
fi

# 3. Check sqlite3
if ! command -v sqlite3 &>/dev/null; then
    echo "❌ sqlite3 not installed."
    exit 1
fi

# 4. Verify DB exists and is readable
if [ ! -f "$DB_PATH" ]; then
    echo "⚠️  DB not found. Rebuilding from seed..."
    sqlite3 "$DB_PATH" < "$SCRIPT_DIR/schema.sql"
    sqlite3 "$DB_PATH" < "$SCRIPT_DIR/seed.sql"
    echo "✅ DB rebuilt from seed."
elif ! sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM components;" &>/dev/null 2>&1; then
    echo "⚠️  DB exists but unreadable (still encrypted?). Rebuilding from seed..."
    rm -f "$DB_PATH"
    sqlite3 "$DB_PATH" < "$SCRIPT_DIR/schema.sql"
    sqlite3 "$DB_PATH" < "$SCRIPT_DIR/seed.sql"
    echo "✅ DB rebuilt from seed."
else
    COMP_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM components WHERE status = 'active';")
    CONTRACT_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM contracts;")
    SCENARIO_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM scenarios;")
    echo "✅ DB OK — $COMP_COUNT components, $CONTRACT_COUNT contracts, $SCENARIO_COUNT scenarios"
fi

# 5. Verify scripts are executable
chmod +x "$SCRIPT_DIR"/*.sh 2>/dev/null || true
echo "✅ Scripts ready."

# 6. Quick dashboard
echo ""
"$SCRIPT_DIR/dashboard.sh"
