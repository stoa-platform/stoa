#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 STOA Platform
#
# council-review.sh — Automated 4-axis code review gate (Stage 3)
#
# Evaluates a git diff via 4 independent Anthropic API calls (conformance,
# debt, attack_surface, contract_impact), aggregates scores, and returns a
# binary verdict.
#
# Data handling:
#   - Sends diff content to Anthropic API (no training on API traffic per ToS).
#   - Gitleaks pre-flight blocks execution if secrets are detected in the diff.
#   - Linear API token (read-only issues) from Vault: stoa/shared/linear_token.
#
# Exit codes:
#   0 — APPROVED (score >= 8.0, or empty diff — nothing to review)
#   1 — REWORK (score < 8.0)
#   2 — Technical error (missing deps, gitleaks block, >=2 axes failed, etc.)
#
# See .claude/rules/council-s3.md for full documentation.
# CAB-2047 Step 1: skeleton + args parsing + Étape 0 pre-checks.

set -euo pipefail

# =============================================================================
# Script metadata
# =============================================================================

VERSION="0.2.0-step2a-cost-guardrails"
SCRIPT_NAME="council-review.sh"
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)

# =============================================================================
# Defaults
# =============================================================================

DIFF_RANGE="origin/main..HEAD"
TICKET=""
TRIVY_REPORT=""
MAX_DIFF_LINES=10000
DB_PATH="${REPO_ROOT}/docs/stoa-impact.db"
DB_STALE_DAYS=7
DIFF_TRUNCATED=false
COUNCIL_TMPDIR=""
TIMEOUT_CMD=""

# Cost-safety guardrails
COUNCIL_HISTORY_FILE="${COUNCIL_HISTORY_FILE:-${REPO_ROOT}/council-history.jsonl}"
DIFF_SHA=""

# =============================================================================
# Logging
# =============================================================================

log_info()  { echo "info  $*" >&2; }
log_warn()  { echo "warn  $*" >&2; }
log_error() { echo "error $*" >&2; }
log_ok()    { echo "ok    $*" >&2; }

# =============================================================================
# Help
# =============================================================================

usage() {
    cat <<'EOF'
Usage: council-review.sh [OPTIONS]

Council Stage 3 — Automated 4-axis code review.
Evaluates a git diff on conformance, debt, attack_surface, contract_impact.

OPTIONS:
  --diff RANGE          Git diff range (default: origin/main..HEAD)
  --ticket CAB-XXXX     Linear ticket ID (optional — fetches ticket context)
  --trivy-report FILE   Path to Trivy JSON report (optional — enriches attack_surface)
  --version             Print version and exit
  --help                Print this help and exit

ENVIRONMENT:
  ANTHROPIC_API_KEY     Required for API calls (set in GitHub secrets or .env)
  LINEAR_API_KEY        Optional — enables --ticket context fetching
  MOCK_API              If set to "1", uses fixture responses instead of real API calls
  TMPDIR                Override the temp directory (default: /tmp)

COST SAFETY (HARD GUARDRAILS — enforced before any API call):
  COUNCIL_DISABLE=1     Kill-switch — exit 0 immediately, no review
  COUNCIL_DAILY_CAP_EUR Daily spend cap in EUR (default: 5). Script reads
                        council-history.jsonl, sums today's cost_eur, exits 0
                        if >= cap. Override via: COUNCIL_DAILY_CAP_EUR=50
  COUNCIL_FORCE_DEDUP   Set to "0" to disable SHA dedup and re-evaluate
                        identical diffs (default: 1, dedup enabled)

EXIT CODES:
  0   APPROVED (score >= 8.0, or empty diff — nothing to review)
  1   REWORK  (score < 8.0 — see feedback for required changes)
  2   Technical error — missing deps, gitleaks detected secrets,
      >=2 axes failed, or invalid args

EXAMPLES:
  # Review staged changes against main
  council-review.sh --diff origin/main..HEAD --ticket CAB-2047

  # Review last 5 commits with Trivy context
  council-review.sh --diff HEAD~5..HEAD --trivy-report /tmp/trivy.json

  # Dry-run mode (no real API calls, reads fixtures)
  MOCK_API=1 council-review.sh --diff HEAD~1..HEAD

SEE ALSO:
  .claude/rules/council-s3.md — Full documentation and FAQ
  .claude/skills/council/SKILL.md — Council Stage 1 / Stage 2 skill
EOF
}

# =============================================================================
# Argument parsing
# =============================================================================

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --diff)
                [[ $# -ge 2 ]] || { log_error "--diff requires an argument"; exit 2; }
                DIFF_RANGE="$2"
                shift 2
                ;;
            --ticket)
                [[ $# -ge 2 ]] || { log_error "--ticket requires an argument"; exit 2; }
                TICKET="$2"
                shift 2
                ;;
            --trivy-report)
                [[ $# -ge 2 ]] || { log_error "--trivy-report requires an argument"; exit 2; }
                TRIVY_REPORT="$2"
                shift 2
                ;;
            --version)
                echo "${SCRIPT_NAME} ${VERSION}"
                exit 0
                ;;
            --help|-h)
                usage
                exit 0
                ;;
            *)
                log_error "Unknown argument: $1"
                usage >&2
                exit 2
                ;;
        esac
    done
}

# =============================================================================
# Pre-check 1: Dependencies (Adj #3, #7)
# Exit 2 if any required tool is missing. Resolves timeout vs gtimeout (macOS).
# =============================================================================

check_dependencies() {
    local missing=()
    local cmd
    for cmd in jq curl git awk sed gitleaks; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            missing+=("$cmd")
        fi
    done

    if command -v timeout >/dev/null 2>&1; then
        TIMEOUT_CMD=timeout
    elif command -v gtimeout >/dev/null 2>&1; then
        TIMEOUT_CMD=gtimeout
    else
        missing+=("timeout (or gtimeout via 'brew install coreutils' on macOS)")
    fi

    if [ ${#missing[@]} -gt 0 ]; then
        log_error "Missing required commands: ${missing[*]}"
        log_error "Install them and retry."
        exit 2
    fi
}

# =============================================================================
# Cost guardrail 1: COUNCIL_DISABLE kill-switch (Step 2a)
# Fast-path exit before anything else runs. Redundant with CAB-2048's
# DISABLE_COUNCIL_GATE=1 from the pre-push hook, but also covers CI and
# manual invocation scenarios.
# =============================================================================

check_disable_flag() {
    if [ "${COUNCIL_DISABLE:-0}" = "1" ]; then
        log_warn "COUNCIL_DISABLE=1 — Council S3 skipped (kill-switch)"
        exit 0
    fi
}

# =============================================================================
# Cost guardrail 2: Daily spend cap (Step 2a)
# Reads council-history.jsonl, sums today's cost_eur across all entries,
# exits 0 (not 2) if the total is at or above COUNCIL_DAILY_CAP_EUR.
# Rationale: the cap is a soft guardrail, not a review verdict — we don't
# want to fail the developer's PR, we just don't review it until tomorrow.
# =============================================================================

check_daily_cap() {
    local cap="${COUNCIL_DAILY_CAP_EUR:-5}"
    local today
    today=$(date -u +%Y-%m-%d)

    if [ ! -f "$COUNCIL_HISTORY_FILE" ]; then
        log_info "Daily cap: €0.00 / €${cap} (no history yet)"
        return 0
    fi

    local today_spend
    today_spend=$(jq -r --arg d "$today" \
        'select(.timestamp | startswith($d)) | .cost_eur // 0' \
        "$COUNCIL_HISTORY_FILE" 2>/dev/null \
        | awk '{sum += $1} END {printf "%.4f", sum + 0}')

    if [ -z "$today_spend" ]; then
        today_spend="0"
    fi

    # awk handles float comparison (bash cannot)
    if awk -v spent="$today_spend" -v cap="$cap" \
        'BEGIN {exit !(spent + 0 >= cap + 0)}'; then
        log_warn "Daily cap €${cap} reached (spent €${today_spend} today) — SKIP review"
        log_warn "Bypass: COUNCIL_DAILY_CAP_EUR=50 ${SCRIPT_NAME} ..."
        exit 0
    fi

    log_info "Daily cap: €${today_spend} / €${cap}"
}

# =============================================================================
# Cost guardrail 3: Diff SHA dedup (Step 2a)
# Computes SHA1 of the full diff content. If an entry with the same SHA
# exists in today's council-history.jsonl, skip the review — this happens
# on CI reruns, successive pushes with no new changes, or identical
# cherry-picks. Saves one full 4-axis round-trip (~€0.036).
# Sets DIFF_SHA global for later use by the JSONL writer (Step 4).
# =============================================================================

check_sha_dedup() {
    local sha_tool=""
    if command -v sha1sum >/dev/null 2>&1; then
        sha_tool=sha1sum
    elif command -v shasum >/dev/null 2>&1; then
        sha_tool=shasum
    else
        log_warn "No sha1sum/shasum available — SHA dedup disabled"
        DIFF_SHA="unknown"
        return 0
    fi

    DIFF_SHA=$(git diff "$DIFF_RANGE" 2>/dev/null | "$sha_tool" | awk '{print $1}')

    if [ -z "$DIFF_SHA" ]; then
        log_warn "Failed to compute diff SHA — dedup disabled"
        DIFF_SHA="unknown"
        return 0
    fi

    if [ ! -f "$COUNCIL_HISTORY_FILE" ]; then
        log_info "Diff SHA ${DIFF_SHA:0:8} — first evaluation (no history)"
        return 0
    fi

    local today
    today=$(date -u +%Y-%m-%d)

    local hit
    hit=$(jq -r --arg sha "$DIFF_SHA" --arg d "$today" \
        'select(.timestamp | startswith($d)) | select(.diff_sha == $sha) | .timestamp' \
        "$COUNCIL_HISTORY_FILE" 2>/dev/null | head -1)

    if [ -n "$hit" ]; then
        if [ "${COUNCIL_FORCE_DEDUP:-1}" = "0" ]; then
            log_warn "Diff SHA ${DIFF_SHA:0:8} already evaluated at ${hit} — COUNCIL_FORCE_DEDUP=0, re-evaluating"
            return 0
        fi
        log_info "Diff SHA ${DIFF_SHA:0:8} already evaluated today at ${hit} — SKIP"
        log_info "Bypass: COUNCIL_FORCE_DEDUP=0 ${SCRIPT_NAME} ..."
        exit 0
    fi

    log_info "Diff SHA ${DIFF_SHA:0:8} — first evaluation today"
}

# =============================================================================
# Pre-check 2: Diff lines count (Adj #5)
# Use --numstat for insertions + deletions; --stat $4 only gives insertions.
# =============================================================================

compute_diff_lines() {
    git diff --numstat "$DIFF_RANGE" 2>/dev/null \
        | awk '{sum += $1 + $2} END {print sum + 0}'
}

# =============================================================================
# Pre-check 3: Gitleaks pre-flight BLOCKING (Adj #6)
# Writes the diff to a temp file and scans it with --no-git. Any leak → exit 2
# BEFORE any API call is made. This is the cheapest possible guard against
# accidentally exfiltrating secrets to Anthropic.
# =============================================================================

gitleaks_preflight() {
    local diff_tmp="${COUNCIL_TMPDIR}/diff-preflight.patch"
    git diff "$DIFF_RANGE" > "$diff_tmp"

    local rc=0
    gitleaks detect \
        --no-git \
        --source "$diff_tmp" \
        --redact \
        --no-banner \
        --exit-code 1 \
        >/dev/null 2>&1 || rc=$?

    if [ "$rc" -eq 1 ]; then
        log_error "Gitleaks pre-flight BLOCKED: secrets detected in diff"
        log_error "Aborting before any API call. Fix the leaks and retry."
        log_error "Inspect via: gitleaks detect --no-git --source '${diff_tmp}' --redact"
        exit 2
    elif [ "$rc" -ne 0 ]; then
        log_warn "Gitleaks returned unexpected exit code ${rc} — treating as PASS (review recommended)"
    fi
}

# =============================================================================
# Pre-check 4: DB freshness via portable stat (Adj #2)
# GNU (Linux/CI) uses stat -c %Y; BSD/macOS uses stat -f %m.
# Returns age in days, or -1 if the file is missing/unreadable.
# =============================================================================

compute_db_age_days() {
    local db=$1
    local mtime
    mtime=$(stat -c %Y "$db" 2>/dev/null || stat -f %m "$db" 2>/dev/null || echo 0)
    if [ "$mtime" -eq 0 ]; then
        echo "-1"
    else
        local now
        now=$(date +%s)
        echo $(( (now - mtime) / 86400 ))
    fi
}

# =============================================================================
# Pre-check 5: Diff content extraction with truncation (Adj #5)
# Large diffs are truncated to MAX_DIFF_LINES to cap API input tokens.
# Sets DIFF_TRUNCATED=true when truncation occurred.
# =============================================================================

extract_diff_content() {
    local diff_lines=$1
    if [ "$diff_lines" -gt "$MAX_DIFF_LINES" ]; then
        log_warn "Diff truncated from ${diff_lines} to ${MAX_DIFF_LINES} lines"
        DIFF_TRUNCATED=true
        git diff "$DIFF_RANGE" | head -n "$MAX_DIFF_LINES"
    else
        DIFF_TRUNCATED=false
        git diff "$DIFF_RANGE"
    fi
}

# =============================================================================
# Main
# =============================================================================

main() {
    parse_args "$@"

    log_info "${SCRIPT_NAME} ${VERSION}"
    log_info "Diff range: ${DIFF_RANGE}"
    [ -n "$TICKET" ] && log_info "Ticket: ${TICKET}"

    # --- 0. Kill-switch (fastest possible exit) -----------------------------
    check_disable_flag

    # --- 1. Dependencies ----------------------------------------------------
    check_dependencies
    log_ok "Dependencies: jq curl git awk sed gitleaks ${TIMEOUT_CMD}"

    # --- 2. Diff lines + empty diff fast-path -------------------------------
    local diff_lines
    diff_lines=$(compute_diff_lines)
    if [ "$diff_lines" -eq 0 ]; then
        log_ok "No changes in diff range — nothing to review"
        exit 0
    fi
    log_info "Diff lines: ${diff_lines} (insertions + deletions)"

    # --- 2b. Cost guardrails (BEFORE any expensive op, esp. API calls) ----
    check_daily_cap
    check_sha_dedup

    # --- 3. Tempdir setup (needed by gitleaks preflight and future axes) ---
    COUNCIL_TMPDIR=$(mktemp -d "${TMPDIR:-/tmp}/council.XXXXXX")
    trap 'rm -rf "${COUNCIL_TMPDIR}"' EXIT
    log_info "Tempdir: ${COUNCIL_TMPDIR}"

    # --- 4. Gitleaks pre-flight (BLOCKING before any API call) --------------
    gitleaks_preflight
    log_ok "Gitleaks pre-flight: no secrets detected"

    # --- 5. DB freshness → AXES_COUNT ---------------------------------------
    local db_age
    db_age=$(compute_db_age_days "$DB_PATH")
    local axes_count=4
    local skip_axis=""
    if [ "$db_age" -eq -1 ]; then
        log_warn "stoa-impact.db not found at ${DB_PATH} — contract_impact SKIPPED"
        axes_count=3
        skip_axis="contract_impact"
    elif [ "$db_age" -gt "$DB_STALE_DAYS" ]; then
        log_warn "stoa-impact.db stale (${db_age}d > ${DB_STALE_DAYS}d) — contract_impact SKIPPED"
        axes_count=3
        skip_axis="contract_impact"
    else
        log_ok "stoa-impact.db fresh (${db_age}d)"
    fi

    # --- 6. Diff content extraction (with truncation) ----------------------
    local diff_content
    diff_content=$(extract_diff_content "$diff_lines")
    local diff_bytes=${#diff_content}
    if [ "$DIFF_TRUNCATED" = "true" ]; then
        log_warn "diff_truncated=true (max ${MAX_DIFF_LINES} lines, ${diff_bytes} bytes)"
    fi

    # --- 7. Trivy report (optional, best-effort) ---------------------------
    local trivy_loaded=no
    if [ -n "$TRIVY_REPORT" ] && [ -f "$TRIVY_REPORT" ]; then
        trivy_loaded=yes
        log_ok "Trivy report loaded: ${TRIVY_REPORT}"
    elif [ -n "$TRIVY_REPORT" ]; then
        log_warn "Trivy report not found at ${TRIVY_REPORT} — attack_surface runs without Trivy context"
    fi

    # --- Step 2a complete — stub for Step 2b+ ------------------------------
    log_info "------------------------------------------------------------"
    log_info "[STEP 2a SKELETON] All pre-checks + cost guardrails passed."
    log_info "[STEP 2a SKELETON] API evaluation (evaluate_axis × ${axes_count}) not yet implemented."
    log_info "[STEP 2a SKELETON] See CAB-2047 for Step 2b (anthropic_call + single-axis test)."
    log_info "------------------------------------------------------------"
    log_info "Summary:"
    log_info "  diff_lines=${diff_lines}"
    log_info "  diff_truncated=${DIFF_TRUNCATED}"
    log_info "  diff_bytes=${diff_bytes}"
    log_info "  diff_sha=${DIFF_SHA:0:12}"
    log_info "  axes_count=${axes_count}"
    log_info "  skip_axis=${skip_axis:-none}"
    log_info "  db_age_days=${db_age}"
    log_info "  trivy_loaded=${trivy_loaded}"
    log_info "  daily_cap=€${COUNCIL_DAILY_CAP_EUR:-5}"

    exit 0
}

main "$@"
