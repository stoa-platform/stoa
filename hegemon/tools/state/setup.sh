#!/bin/bash
# HEGEMON State Store — Setup
# Creates ~/.hegemon/state.db and symlinks heg-state CLI
#
# Usage: bash hegemon/tools/state/setup.sh
# Idempotent: safe to run multiple times.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HEGEMON_DIR="${HOME}/.hegemon"
DB_PATH="${HEGEMON_DIR}/state.db"
SCHEMA_PATH="${SCRIPT_DIR}/schema.sql"
CLI_SOURCE="${SCRIPT_DIR}/heg_state.py"
CLI_TARGET="${HOME}/.local/bin/heg-state"

echo "HEGEMON State Store Setup"
echo "========================="

# 1. Create ~/.hegemon/
mkdir -p "$HEGEMON_DIR"
echo "[1/4] Directory: $HEGEMON_DIR"

# 2. Initialize SQLite database
if [ ! -f "$DB_PATH" ]; then
  sqlite3 "$DB_PATH" < "$SCHEMA_PATH"
  echo "[2/4] Database created: $DB_PATH"
else
  # Apply schema (CREATE IF NOT EXISTS = safe)
  sqlite3 "$DB_PATH" < "$SCHEMA_PATH"
  echo "[2/4] Database updated: $DB_PATH"
fi

# 3. Verify WAL mode
WAL_MODE=$(sqlite3 "$DB_PATH" "PRAGMA journal_mode;" 2>/dev/null)
if [ "$WAL_MODE" = "wal" ]; then
  echo "[3/4] WAL mode: active"
else
  echo "[3/4] WAL mode: $WAL_MODE (expected: wal)"
fi

# 4. Symlink CLI
mkdir -p "$(dirname "$CLI_TARGET")"
chmod +x "$CLI_SOURCE"
ln -sf "$CLI_SOURCE" "$CLI_TARGET"
echo "[4/4] CLI symlinked: $CLI_TARGET -> $CLI_SOURCE"

echo ""
echo "Done. Test with: heg-state ls"
echo ""
echo "Note: ensure ~/.local/bin is on your PATH:"
echo '  export PATH="$HOME/.local/bin:$PATH"'
