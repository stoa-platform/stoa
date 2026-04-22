#!/usr/bin/env bash
# CAB-1889 CP-2 C.5 — grep gate: prevent regressions onto the legacy flat
# Git provider env attributes (settings.GIT_PROVIDER / GITHUB_* / GITLAB_*).
#
# Consumers must read settings.git.* (hydrated by config.py). The flat
# fields still exist on Settings for ingress compatibility but are
# declared with exclude=True and must not be read anywhere else.
#
# Usage:
#   scripts/check_git_config_access.sh [src-dir]
# Exit codes:
#   0  clean (no leaks)
#   1  one or more legacy accesses found
set -euo pipefail

SRC_DIR="${1:-src}"
ALLOWED_FILE="src/config.py"

leaks=$(grep -rn 'settings\.\(GIT_PROVIDER\|GITHUB_\|GITLAB_\)' "$SRC_DIR" --include="*.py" \
    | grep -v "$ALLOWED_FILE" || true)

if [[ -n "$leaks" ]]; then
    echo "::error::Direct access to legacy Git provider env attrs detected."
    echo "Use settings.git.provider / settings.git.github.* / settings.git.gitlab.* instead."
    echo ""
    echo "$leaks"
    exit 1
fi

echo "OK: no direct access to settings.GIT_PROVIDER / GITHUB_* / GITLAB_* outside $ALLOWED_FILE"
