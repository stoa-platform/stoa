#!/usr/bin/env bash
# adr-loader.sh — fetch ADRs from stoa-platform/stoa-docs for the PR Guardian.
#
# Usage: adr-loader.sh <number> [<number> ...]
#        Emits concatenated markdown on stdout. One `## ADR-XXX` header per ADR.
#
# Fallback contract: on any fetch failure, echoes a sentinel line that the
# skill greps for ("ADR_LOADER_FETCH_FAILED"). Never exits non-zero when called
# with valid arguments — the skill decides how to degrade confidence.

set -u
# Note: deliberately no `-e` so partial failures still emit the sentinel and
# continue to the next ADR.

REPO_OWNER="${ADR_REPO_OWNER:-stoa-platform}"
REPO_NAME="${ADR_REPO_NAME:-stoa-docs}"
BRANCH="${ADR_BRANCH:-main}"
ADR_DIR="docs/architecture/adr"

# Prefer raw.githubusercontent.com; fall back to gh api if available.
fetch_adr() {
  local n="$1"
  local padded
  padded=$(printf "%03d" "$n" 2>/dev/null || echo "$n")
  local slug_pattern="adr-${padded}-"

  # Ask stoa-docs for the filename matching adr-XXX-*.md via GitHub API.
  # This lets us fetch the ADR without hardcoding its slug.
  local filename=""
  if command -v gh >/dev/null 2>&1; then
    filename=$(gh api "repos/${REPO_OWNER}/${REPO_NAME}/contents/${ADR_DIR}?ref=${BRANCH}" \
      --jq ".[] | select(.name | startswith(\"${slug_pattern}\")) | .name" 2>/dev/null | head -1)
  fi

  if [ -z "$filename" ]; then
    # Fallback: try plain-curl directory listing via the REST API.
    filename=$(curl -sS -H "Accept: application/vnd.github+json" \
      "https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/contents/${ADR_DIR}?ref=${BRANCH}" 2>/dev/null \
      | jq -r ".[] | select(.name | startswith(\"${slug_pattern}\")) | .name" 2>/dev/null | head -1)
  fi

  if [ -z "$filename" ]; then
    echo "<!-- ADR_LOADER_FETCH_FAILED: could not resolve filename for ADR-${padded} -->"
    return
  fi

  local url="https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/${BRANCH}/${ADR_DIR}/${filename}"
  local body
  body=$(curl -sSfL --max-time 10 "$url" 2>/dev/null || echo "")

  if [ -z "$body" ]; then
    echo "<!-- ADR_LOADER_FETCH_FAILED: fetch error on ${url} -->"
    return
  fi

  echo ""
  echo "## ADR-${padded} (source: ${filename})"
  echo ""
  echo "$body"
  echo ""
  echo "---"
}

if [ $# -eq 0 ]; then
  echo "Usage: $0 <number> [<number> ...]" >&2
  exit 2
fi

for arg in "$@"; do
  # Accept both "12" and "012"; normalize to integer.
  n=$(echo "$arg" | sed 's/^0*//')
  [ -z "$n" ] && n=0
  fetch_adr "$n"
done
