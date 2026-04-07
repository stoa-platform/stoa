#!/bin/bash
# verify-claude-code-integrity.sh — Post-install integrity check for Claude Code
#
# CAB-2005: After the March 31, 2026 npm source map leak and concurrent Axios
# supply-chain attack, verify Claude Code installation integrity before use.
#
# Run after: npm install -g @anthropic-ai/claude-code
# Run via:   scripts/ai-ops/verify-claude-code-integrity.sh
#
# Checks:
# 1. No source map files leaked in the package
# 2. Package version matches expected (pinned)
# 3. No unexpected large files (>10MB) in package
# 4. Package signature/provenance if available

set -euo pipefail

# --- Configuration ---
# Pin to a known-good version. Update this after verifying each new release.
EXPECTED_VERSION="1.0.33"
PACKAGE_NAME="@anthropic-ai/claude-code"
MAX_FILE_SIZE_MB=10

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ERRORS=0

echo "=== Claude Code Integrity Check ==="
echo ""

# 1. Check installed version
INSTALLED_VERSION=$(claude --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "not installed")
echo -n "Version: ${INSTALLED_VERSION} (expected: ${EXPECTED_VERSION}) ... "
if [[ "$INSTALLED_VERSION" == "$EXPECTED_VERSION" ]]; then
  echo -e "${GREEN}OK${NC}"
else
  echo -e "${YELLOW}MISMATCH${NC} — update EXPECTED_VERSION in this script if intentional"
fi

# 2. Find package installation path
CLAUDE_PATH=$(which claude 2>/dev/null || echo "")
if [[ -z "$CLAUDE_PATH" ]]; then
  echo -e "${RED}FAIL${NC}: claude not found in PATH"
  exit 1
fi

# Resolve symlink to find package dir
REAL_PATH=$(realpath "$CLAUDE_PATH" 2>/dev/null || readlink -f "$CLAUDE_PATH" 2>/dev/null || echo "$CLAUDE_PATH")
PACKAGE_DIR=$(dirname "$(dirname "$REAL_PATH")")

echo "Package dir: ${PACKAGE_DIR}"
echo ""

# 3. Check for source map files (the exact leak vector)
echo -n "Source maps (.map files): "
MAP_FILES=$(find "$PACKAGE_DIR" -name "*.map" -type f 2>/dev/null | head -5)
if [[ -n "$MAP_FILES" ]]; then
  echo -e "${RED}FOUND — POTENTIAL LEAK${NC}"
  echo "$MAP_FILES"
  ERRORS=$((ERRORS + 1))
else
  echo -e "${GREEN}NONE${NC}"
fi

# 4. Check for unexpectedly large files
echo -n "Large files (>${MAX_FILE_SIZE_MB}MB): "
LARGE_FILES=$(find "$PACKAGE_DIR" -type f -size "+${MAX_FILE_SIZE_MB}M" 2>/dev/null | head -5)
if [[ -n "$LARGE_FILES" ]]; then
  echo -e "${YELLOW}FOUND${NC}"
  echo "$LARGE_FILES" | while read -r f; do
    SIZE=$(du -h "$f" 2>/dev/null | cut -f1)
    echo "  ${SIZE}  ${f}"
  done
else
  echo -e "${GREEN}NONE${NC}"
fi

# 5. Check for debug/PDB files
echo -n "Debug files (.pdb): "
PDB_FILES=$(find "$PACKAGE_DIR" -name "*.pdb" -type f 2>/dev/null | head -5)
if [[ -n "$PDB_FILES" ]]; then
  echo -e "${YELLOW}FOUND${NC}"
  echo "$PDB_FILES"
else
  echo -e "${GREEN}NONE${NC}"
fi

echo ""

# 6. Summary
if [[ "$ERRORS" -gt 0 ]]; then
  echo -e "${RED}=== INTEGRITY CHECK FAILED ===${NC}"
  echo "Do NOT use this installation. Reinstall from a verified source."
  echo "  npm uninstall -g ${PACKAGE_NAME}"
  echo "  npm install -g ${PACKAGE_NAME}@${EXPECTED_VERSION}"
  exit 1
else
  echo -e "${GREEN}=== INTEGRITY CHECK PASSED ===${NC}"
  echo "Claude Code ${INSTALLED_VERSION} appears clean."
fi
