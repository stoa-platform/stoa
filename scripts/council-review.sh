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
# CAB-2047 Step 2a: cost guardrails (disable + daily cap + SHA dedup).
# CAB-2047 Step 2b: anthropic_call + evaluate_axis(conformance) + MOCK_API.
# CAB-2047 Step 3a: externalize prompts to scripts/council-prompts/*.md.
# CAB-2047 Step 3b: fetch_linear_ticket + fetch_db_context + evaluate_axis context injection.
# CAB-2047 Step 3c: parallel 4-axis orchestration + aggregate_scores + council-history.jsonl.

set -euo pipefail

# =============================================================================
# Script metadata
# =============================================================================

VERSION="0.6.0-step3c-parallel"
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

# Step 2b: API configuration
ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-claude-sonnet-4-5}"
ANTHROPIC_MAX_TOKENS="${ANTHROPIC_MAX_TOKENS:-1024}"
ANTHROPIC_TIMEOUT_S="${ANTHROPIC_TIMEOUT_S:-30}"

# Cost-safety guardrails
COUNCIL_HISTORY_FILE="${COUNCIL_HISTORY_FILE:-${REPO_ROOT}/council-history.jsonl}"
DIFF_SHA=""

# Step 3b: context fetchers (populated by fetch_linear_ticket / fetch_db_context)
TICKET_CONTEXT=""
DB_CONTEXT=""
LINEAR_API_URL="${LINEAR_API_URL:-https://api.linear.app/graphql}"
LINEAR_TIMEOUT_S="${LINEAR_TIMEOUT_S:-10}"
DB_CONTEXT_MAX_COMPONENTS=20
DB_CONTEXT_MAX_CONTRACTS_PER_COMP=5

# =============================================================================
# Logging
# =============================================================================

log_info()  { echo "info  $*" >&2; }
log_warn()  { echo "warn  $*" >&2; }
log_error() { echo "error $*" >&2; }
log_ok()    { echo "ok    $*" >&2; }

# Portable monotonic-ish millisecond timestamp. GNU date supports %3N for ms,
# but BSD date (macOS) treats the format literally and returns the seconds
# epoch with a trailing "N". Fall back to seconds*1000 in that case.
now_ms() {
    local ms
    ms=$(date +%s%3N 2>/dev/null)
    if [[ "$ms" =~ ^[0-9]+$ ]]; then
        echo "$ms"
    else
        echo $(($(date +%s) * 1000))
    fi
}

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
  LINEAR_API_KEY        Optional — enables --ticket context fetching (read-only
                        token from Vault: stoa/shared/linear_token)
  LINEAR_TIMEOUT_S      Linear API timeout in seconds (default: 10)
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
# Step 2b: anthropic_call (Adj #4 — typed retry, 429/5xx only)
# Sends a tool_use request to Anthropic API and extracts the tool input into
# the output file. Returns:
#   0 — success (output_file contains JSON matching record_review schema)
#   1 — failure (network, permanent HTTP error, or malformed response)
#
# Retry policy:
#   - 200 → success, stop
#   - 429 | 5xx → retry with backoff (up to max_attempts)
#   - anything else (401, 400, 000, etc.) → permanent failure, NO retry
#
# Arguments:
#   $1 — system prompt (string)
#   $2 — user content (string, typically the diff)
#   $3 — output file path (absolute)
# =============================================================================

anthropic_call() {
    local system_prompt="$1"
    local user_content="$2"
    local out="$3"
    local attempt=1
    local max_attempts=2
    local http_status=""

    if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
        log_error "ANTHROPIC_API_KEY not set — cannot call Anthropic API"
        return 1
    fi

    local payload
    payload=$(jq -n \
        --arg model "$ANTHROPIC_MODEL" \
        --argjson max_tokens "$ANTHROPIC_MAX_TOKENS" \
        --arg sys "$system_prompt" \
        --arg usr "$user_content" \
        '{
            model: $model,
            max_tokens: $max_tokens,
            system: $sys,
            messages: [{role: "user", content: $usr}],
            tools: [{
                name: "record_review",
                description: "Record the review verdict for one axis",
                input_schema: {
                    type: "object",
                    properties: {
                        score: {
                            type: "integer",
                            minimum: 1,
                            maximum: 10,
                            description: "Quality score, 1-10. >=8 means APPROVED for this axis."
                        },
                        feedback: {
                            type: "string",
                            maxLength: 500,
                            description: "Actionable feedback, max 500 chars"
                        },
                        blockers: {
                            type: "array",
                            items: {type: "string"},
                            description: "Array of blocker descriptions (empty if none)"
                        }
                    },
                    required: ["score", "feedback", "blockers"]
                }
            }],
            tool_choice: {type: "tool", name: "record_review"}
        }')

    local raw="${out}.raw"

    while [ "$attempt" -le "$max_attempts" ]; do
        http_status=$("$TIMEOUT_CMD" "$ANTHROPIC_TIMEOUT_S" curl -sS \
            -o "$raw" \
            -w "%{http_code}" \
            -H "x-api-key: ${ANTHROPIC_API_KEY}" \
            -H "anthropic-version: 2023-06-01" \
            -H "content-type: application/json" \
            -X POST https://api.anthropic.com/v1/messages \
            --data-binary "$payload" 2>/dev/null) || http_status="000"

        case "$http_status" in
            200)
                # Extract the tool_use input block as the axis result JSON.
                if jq -e '.content[] | select(.type=="tool_use") | .input' "$raw" \
                    > "$out" 2>/dev/null; then
                    if [ -s "$out" ]; then
                        return 0
                    fi
                fi
                log_error "anthropic_call: 200 OK but tool_use extraction failed"
                log_error "Raw response saved to: ${raw}"
                return 1
                ;;
            429|5*)
                if [ "$attempt" -lt "$max_attempts" ]; then
                    local backoff=$((attempt * 2))
                    log_warn "anthropic_call: transient status=${http_status}, retrying in ${backoff}s (attempt ${attempt}/${max_attempts})"
                    sleep "$backoff"
                    attempt=$((attempt + 1))
                    continue
                fi
                log_error "anthropic_call: transient status=${http_status}, max attempts reached"
                return 1
                ;;
            *)
                log_error "anthropic_call: permanent failure status=${http_status} — NO retry"
                if [ -s "$raw" ]; then
                    log_error "Response body: $(head -c 200 "$raw")"
                fi
                return 1
                ;;
        esac
    done

    return 1
}

# =============================================================================
# Step 3a: prompt loader — loads axis system prompts from scripts/council-prompts/
# One file per axis: conformance.md, debt.md, attack_surface.md, contract_impact.md.
# Keeping prompts as standalone markdown makes them reviewable and independently
# calibratable without touching bash logic (Council S2 Adjustment #2).
#
# Arguments:
#   $1 — axis name (conformance | debt | attack_surface | contract_impact)
# Prints the prompt content on stdout. Exits 2 if the file is missing.
# =============================================================================

load_prompt() {
    local axis="$1"
    local prompt_file="${REPO_ROOT}/scripts/council-prompts/${axis}.md"
    if [ ! -f "$prompt_file" ]; then
        log_error "load_prompt: missing prompt file for axis='${axis}' at ${prompt_file}"
        return 2
    fi
    cat "$prompt_file"
}

# =============================================================================
# Step 3b: fetch_linear_ticket — populates TICKET_CONTEXT from Linear GraphQL.
#
# Reads the ticket identifier passed via --ticket, resolves it via issueSearch
# (same pattern as scripts/ai-ops/ai-factory-notify.sh), and injects title +
# description into the conformance axis user message.
#
# Graceful degradation: any failure (no --ticket, no LINEAR_API_KEY, malformed
# ID, network error, 4xx, ticket not found) logs a warning and returns 0 so
# the review proceeds on the diff alone. Linear context is "nice to have",
# not a gate.
#
# Security: LINEAR_API_KEY expected to be scoped read-only. Token is never
# logged, only used as Authorization header. Timeout capped at LINEAR_TIMEOUT_S.
# =============================================================================

fetch_linear_ticket() {
    if [ -z "$TICKET" ]; then
        return 0
    fi

    if [ -z "${LINEAR_API_KEY:-}" ]; then
        log_warn "fetch_linear_ticket: LINEAR_API_KEY not set — ticket context unavailable"
        return 0
    fi

    if [[ ! "$TICKET" =~ ^[A-Z]+-[0-9]+$ ]]; then
        log_warn "fetch_linear_ticket: invalid ticket format '${TICKET}' (expected e.g. CAB-2047)"
        return 0
    fi

    # jq-built payload ensures proper JSON escaping of the identifier.
    local query
    query=$(jq -n --arg id "$TICKET" '{
        query: "query($id: String!) { issueSearch(filter: {identifier: {eq: $id}}) { nodes { identifier title description priority estimate state { name } } } }",
        variables: {id: $id}
    }')

    local resp="${COUNCIL_TMPDIR}/linear.json"
    local http_status
    http_status=$("$TIMEOUT_CMD" "$LINEAR_TIMEOUT_S" curl -sS \
        -o "$resp" \
        -w "%{http_code}" \
        -X POST "$LINEAR_API_URL" \
        -H "Authorization: ${LINEAR_API_KEY}" \
        -H "Content-Type: application/json" \
        --data-binary "$query" 2>/dev/null) || http_status="000"

    if [ "$http_status" != "200" ]; then
        log_warn "fetch_linear_ticket: HTTP ${http_status} from Linear — ticket context unavailable"
        return 0
    fi

    local title description priority estimate state
    title=$(jq -r '.data.issueSearch.nodes[0].title // empty' "$resp" 2>/dev/null)
    description=$(jq -r '.data.issueSearch.nodes[0].description // empty' "$resp" 2>/dev/null)
    priority=$(jq -r '.data.issueSearch.nodes[0].priority // empty' "$resp" 2>/dev/null)
    estimate=$(jq -r '.data.issueSearch.nodes[0].estimate // empty' "$resp" 2>/dev/null)
    state=$(jq -r '.data.issueSearch.nodes[0].state.name // empty' "$resp" 2>/dev/null)

    if [ -z "$title" ]; then
        log_warn "fetch_linear_ticket: ticket ${TICKET} not found (or no access via token)"
        return 0
    fi

    # Truncate description to ~2k chars to keep prompt small.
    local desc_truncated="$description"
    if [ "${#description}" -gt 2000 ]; then
        desc_truncated="${description:0:2000}

[... truncated, full description is ${#description} chars ...]"
    fi

    TICKET_CONTEXT="Ticket: ${TICKET}
Title: ${title}
State: ${state:-unknown}  Priority: ${priority:-none}  Estimate: ${estimate:-none}

Description:
${desc_truncated}"

    log_ok "fetch_linear_ticket: ${TICKET} loaded (title=${#title}ch description=${#description}ch)"
}

# =============================================================================
# Step 3b: fetch_db_context — populates DB_CONTEXT from stoa-impact.db.
#
# Matches changed-file paths against components.repo_path, then lists contracts
# that touch the affected components (inbound + outbound). Used by the
# contract_impact axis (wired in Step 3c — current Step 3b only gates on
# conformance, so DB_CONTEXT is computed but not yet passed to the axis).
#
# Caller guarantees:
#   - DB_PATH already validated by compute_db_age_days (we skip if file missing
#     or db_age indicates "stale", which is communicated via the db_age arg).
#   - COUNCIL_TMPDIR exists.
#
# Security: all comp_ids that flow into interpolated SQL are validated against
# ^[a-zA-Z0-9_-]+$ before the query. sqlite3 is invoked with -readonly so
# even a malicious component row cannot mutate the DB.
#
# Graceful degradation: missing sqlite3, empty diff, no matches, or any SQL
# error → log a warning and return 0. DB_CONTEXT stays empty, contract_impact
# axis will still run on the raw diff.
#
# Arguments:
#   $1 — db_age_days (from compute_db_age_days; -1 means file missing,
#        >DB_STALE_DAYS means stale and already skipped by caller)
# =============================================================================

fetch_db_context() {
    local db_age="$1"

    if [ "$db_age" -eq -1 ] || [ "$db_age" -gt "$DB_STALE_DAYS" ]; then
        return 0
    fi

    if ! command -v sqlite3 >/dev/null 2>&1; then
        log_warn "fetch_db_context: sqlite3 not installed — contract_impact context unavailable"
        return 0
    fi

    local changed_files
    changed_files=$(git diff --name-only "$DIFF_RANGE" 2>/dev/null)
    if [ -z "$changed_files" ]; then
        return 0
    fi

    # Load all components with a non-empty repo_path into a TSV.
    local components_tsv
    components_tsv=$(sqlite3 -readonly -separator $'\t' "$DB_PATH" \
        "SELECT id, COALESCE(repo_path, '') FROM components WHERE repo_path IS NOT NULL AND repo_path != '';" \
        2>/dev/null) || {
        log_warn "fetch_db_context: sqlite3 query failed — contract_impact context unavailable"
        return 0
    }

    if [ -z "$components_tsv" ]; then
        log_info "fetch_db_context: no components with repo_path in DB"
        return 0
    fi

    # Match changed files against each component's repo_path prefix. grep -F
    # avoids regex interpretation of the path.
    local affected_file="${COUNCIL_TMPDIR}/affected-components.txt"
    : > "$affected_file"

    while IFS=$'\t' read -r comp_id comp_path; do
        [ -z "$comp_path" ] && continue
        if echo "$changed_files" | grep -qF -- "$comp_path"; then
            # Only keep if at least one changed file starts with the path.
            if echo "$changed_files" | awk -v p="$comp_path" 'index($0, p) == 1 {found=1; exit} END {exit !found}'; then
                echo "$comp_id" >> "$affected_file"
            fi
        fi
    done <<< "$components_tsv"

    # awk NF>0 instead of grep -v '^$' — grep returns 1 on empty input, which
    # would kill this function under `set -o pipefail`.
    local affected_count
    affected_count=$(sort -u "$affected_file" | awk 'NF>0' | wc -l | awk '{print $1}')

    if [ "$affected_count" -eq 0 ]; then
        log_info "fetch_db_context: no components matched changed files"
        return 0
    fi

    # Cap the component list to avoid prompt bloat.
    local affected_list
    affected_list=$(sort -u "$affected_file" | awk 'NF>0' | head -n "$DB_CONTEXT_MAX_COMPONENTS")

    local header="Affected components (${affected_count}):"
    local comp_line
    comp_line=$(echo "$affected_list" | tr '\n' ',' | sed 's/,$//; s/,/, /g')

    DB_CONTEXT="${header}
${comp_line}

Cross-component contracts:"

    # Query contracts per affected component. comp_id is DB-sourced AND
    # re-validated here to keep interpolation strictly alphanumeric.
    local line
    while IFS= read -r comp_id; do
        [ -z "$comp_id" ] && continue
        if [[ ! "$comp_id" =~ ^[a-zA-Z0-9_-]+$ ]]; then
            log_warn "fetch_db_context: skipping non-alphanumeric component id '${comp_id}'"
            continue
        fi

        local rows
        rows=$(sqlite3 -readonly -separator ' | ' "$DB_PATH" \
            "SELECT type, contract_ref, source_component || ' -> ' || target_component
             FROM contracts
             WHERE source_component = '${comp_id}' OR target_component = '${comp_id}'
             LIMIT ${DB_CONTEXT_MAX_CONTRACTS_PER_COMP};" 2>/dev/null) || continue

        if [ -n "$rows" ]; then
            DB_CONTEXT="${DB_CONTEXT}
[${comp_id}]"
            while IFS= read -r line; do
                [ -z "$line" ] && continue
                DB_CONTEXT="${DB_CONTEXT}
  - ${line}"
            done <<< "$rows"
        fi
    done <<< "$affected_list"

    log_ok "fetch_db_context: ${affected_count} components matched (context=${#DB_CONTEXT}ch)"
}

# =============================================================================
# Step 3a: evaluate_axis now loads prompts from disk via load_prompt().
# Step 3b: accepts optional extra_context (Linear ticket, stoa-impact.db extract)
# that gets wrapped alongside the diff in tagged blocks inside the user message.
# Step 2b still gates on conformance in main() — the other axes won't actually
# be invoked until Step 3c (parallel orchestration), but the loader supports
# them today so Step 3c is a pure bash-logic change, not a prompt rewrite.
#
# Respects MOCK_API=1 for deterministic testing without real API calls (Adj #10).
#
# Arguments:
#   $1 — axis name (conformance | debt | attack_surface | contract_impact)
#   $2 — output file path
#   $3 — diff content (the user message body)
#   $4 — extra_context (optional — Linear ticket for conformance, DB context
#        for contract_impact, Trivy report for attack_surface). Wrapped in
#        <context>…</context> before the <diff>…</diff> block.
# =============================================================================

evaluate_axis() {
    local axis="$1"
    local out="$2"
    local diff_content="$3"
    local extra_context="${4:-}"

    case "$axis" in
        conformance|debt|attack_surface|contract_impact) ;;
        *)
            log_error "evaluate_axis: unsupported axis='${axis}'"
            return 1
            ;;
    esac

    # MOCK_API path — deterministic tests, zero API cost.
    if [ "${MOCK_API:-0}" = "1" ]; then
        local fixture="${REPO_ROOT}/tests/fixtures/council/${axis}.json"
        if [ -n "${MOCK_API_FIXTURE:-}" ]; then
            fixture="$MOCK_API_FIXTURE"
        fi
        if [ ! -f "$fixture" ]; then
            log_error "MOCK_API: fixture not found at ${fixture}"
            return 1
        fi
        cp "$fixture" "$out"
        if [ -n "$extra_context" ]; then
            log_info "MOCK_API: axis=${axis} fixture=${fixture} (context=${#extra_context}ch — ignored in mock mode)"
        else
            log_info "MOCK_API: loaded fixture for axis=${axis} from ${fixture}"
        fi
        return 0
    fi

    # Real API path — load prompt from scripts/council-prompts/${axis}.md.
    local system_prompt
    if ! system_prompt=$(load_prompt "$axis"); then
        return 1
    fi

    # Wrap diff (and optional context) in tagged blocks so the model can
    # unambiguously distinguish context from the diff under review.
    local user_content
    if [ -n "$extra_context" ]; then
        user_content="<context>
${extra_context}
</context>

<diff>
${diff_content}
</diff>"
    else
        user_content="<diff>
${diff_content}
</diff>"
    fi

    anthropic_call "$system_prompt" "$user_content" "$out"
}

# =============================================================================
# Step 3c: aggregate_scores — pure function over the tempdir.
#
# Reads $tmpdir/{conformance,debt,attack_surface,contract_impact}.json, parses
# `.score`, and emits a single JSON verdict on stdout:
#
#   {"status":"APPROVED|REWORK|error","score":<avg>,"count":<n>,"errors":<e>}
#
# Return codes:
#   0 — APPROVED (avg >= 8.0 over the valid axes)
#   1 — REWORK   (avg < 8.0)
#   2 — error    (>= 2 axes failed OR 0 valid axes)
#
# Skipped axes (missing file, e.g. contract_impact when DB is stale) are
# silently ignored — the average is taken only over the ready axes.
#
# Designed to be testable in isolation: no globals, no side effects beyond
# stdout.
#
# Arguments:
#   $1 — tmpdir (absolute path)
#   $2 — failed_count from the parallel wait (diagnostic)
#   $3 — expected_count (3 when contract_impact is skipped, 4 otherwise)
# =============================================================================

aggregate_scores() {
    local tmpdir="$1"
    local failed_count="${2:-0}"
    local expected_count="${3:-4}"
    local total=0 count=0 errors=0 score
    local axis file

    # Canonical order + contract_impact appended only when expected.
    local expected_axes=("conformance" "debt" "attack_surface")
    if [ "$expected_count" -ge 4 ]; then
        expected_axes+=("contract_impact")
    fi

    for axis in "${expected_axes[@]}"; do
        file="${tmpdir}/${axis}.json"
        # A missing or empty file for an EXPECTED axis is an error — not a
        # silent skip. Silent skip is reserved for contract_impact when the
        # DB is stale (expected_count=3, so the loop never visits it).
        if [ ! -f "$file" ] || [ ! -s "$file" ]; then
            errors=$((errors + 1))
            continue
        fi
        score=$(jq -r '.score // empty' "$file" 2>/dev/null)
        if [ -z "$score" ] || ! [[ "$score" =~ ^[0-9]+$ ]]; then
            errors=$((errors + 1))
            continue
        fi
        total=$((total + score))
        count=$((count + 1))
    done

    # Technical failure: >=2 errored axes, or no valid axis at all.
    if [ "$errors" -ge 2 ] || [ "$count" -eq 0 ]; then
        jq -n -c \
            --arg reason ">=2 axes failed or no valid result" \
            --argjson errors "$errors" \
            --argjson count "$count" \
            --argjson failed "$failed_count" \
            '{status:"error", reason:$reason, errors:$errors, count:$count, failed:$failed}'
        return 2
    fi

    local avg
    avg=$(awk -v t="$total" -v c="$count" 'BEGIN {printf "%.2f", t/c}')

    if awk -v a="$avg" 'BEGIN {exit !(a >= 8.0)}'; then
        jq -n -c \
            --argjson score "$avg" \
            --argjson count "$count" \
            --argjson errors "$errors" \
            '{status:"APPROVED", score:$score, count:$count, errors:$errors}'
        return 0
    else
        jq -n -c \
            --argjson score "$avg" \
            --argjson count "$count" \
            --argjson errors "$errors" \
            '{status:"REWORK", score:$score, count:$count, errors:$errors}'
        return 1
    fi
}

# =============================================================================
# Step 3c: sum_usage_tokens — total input/output tokens across all axis raws.
# Anthropic responses are cached by anthropic_call() at ${out}.raw, so we just
# glob $tmpdir/*.raw and sum the .usage fields. Missing raws (MOCK_API mode)
# yield 0 tokens.
#
# Prints: "<input_tokens> <output_tokens>" on stdout.
# =============================================================================

sum_usage_tokens() {
    local tmpdir="$1"
    local in=0 out=0 raw i o
    for raw in "$tmpdir"/*.raw; do
        [ -f "$raw" ] || continue
        i=$(jq -r '.usage.input_tokens // 0' "$raw" 2>/dev/null || echo 0)
        o=$(jq -r '.usage.output_tokens // 0' "$raw" 2>/dev/null || echo 0)
        [[ "$i" =~ ^[0-9]+$ ]] || i=0
        [[ "$o" =~ ^[0-9]+$ ]] || o=0
        in=$((in + i))
        out=$((out + o))
    done
    echo "${in} ${out}"
}

# =============================================================================
# Step 3c: compute_cost_eur — Sonnet 4.5 API pricing converted to EUR.
#   input:  $3 /MTok → €2.76/MTok  (assuming 1 USD ≈ €0.92)
#   output: $15/MTok → €13.80/MTok
# Printed with 6 decimals (micro-euro granularity for daily-cap aggregation).
# =============================================================================

compute_cost_eur() {
    local input_tokens="$1"
    local output_tokens="$2"
    awk -v i="$input_tokens" -v o="$output_tokens" \
        'BEGIN {printf "%.6f", (i * 2.76 / 1e6) + (o * 13.80 / 1e6)}'
}

# =============================================================================
# Step 3c: write_history — append one JSONL entry to council-history.jsonl.
# Fields match the spec in CAB-2047 description. All numeric fields are real
# JSON numbers (via --argjson), booleans are real JSON booleans, strings are
# real JSON strings. Never fails the script — a history write error just logs
# a warning, since the review verdict has already been computed.
#
# Arguments (positional, all required):
#   $1  status           APPROVED | REWORK | error | BYPASSED
#   $2  global_score     float (0 if status=error)
#   $3  axes_evaluated   integer (0-4)
#   $4  db_fresh         true | false
#   $5  input_tokens     integer
#   $6  output_tokens    integer
#   $7  cost_eur         decimal string
#   $8  diff_lines       integer
#   $9  duration_ms      integer
# =============================================================================

write_history() {
    local status="$1"
    local global_score="$2"
    local axes_evaluated="$3"
    local db_fresh="$4"
    local input_tokens="$5"
    local output_tokens="$6"
    local cost_eur="$7"
    local diff_lines="$8"
    local duration_ms="$9"

    local timestamp
    timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    local total_tokens=$((input_tokens + output_tokens))

    # jq builds the entry, guaranteeing valid JSON regardless of shell quoting.
    local entry
    entry=$(jq -n -c \
        --arg ts "$timestamp" \
        --arg ticket "${TICKET:-}" \
        --arg status "$status" \
        --argjson score "${global_score:-0}" \
        --argjson axes "$axes_evaluated" \
        --argjson db_fresh "$db_fresh" \
        --arg model "$ANTHROPIC_MODEL" \
        --argjson tokens "$total_tokens" \
        --argjson input_tokens "$input_tokens" \
        --argjson output_tokens "$output_tokens" \
        --argjson cost_eur "${cost_eur:-0}" \
        --argjson diff_lines "$diff_lines" \
        --argjson diff_truncated "$DIFF_TRUNCATED" \
        --argjson duration_ms "$duration_ms" \
        --arg diff_sha "${DIFF_SHA:-unknown}" \
        '{
            timestamp: $ts,
            ticket: $ticket,
            status: $status,
            global_score: $score,
            axes_evaluated: $axes,
            db_fresh: $db_fresh,
            model: $model,
            tokens: $tokens,
            input_tokens: $input_tokens,
            output_tokens: $output_tokens,
            cost_eur: $cost_eur,
            diff_lines: $diff_lines,
            diff_truncated: $diff_truncated,
            duration_ms: $duration_ms,
            diff_sha: $diff_sha
        }' 2>/dev/null) || {
        log_warn "write_history: jq failed to build entry — skipping"
        return 0
    }

    if ! echo "$entry" >> "$COUNCIL_HISTORY_FILE" 2>/dev/null; then
        log_warn "write_history: cannot write to ${COUNCIL_HISTORY_FILE} — skipping"
        return 0
    fi

    log_info "History appended: ${COUNCIL_HISTORY_FILE} (status=${status} score=${global_score} tokens=${total_tokens} cost=€${cost_eur})"
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

    # --- 7b. Step 3b: context fetchers (Linear ticket + stoa-impact.db) ----
    # Both are best-effort: any failure logs a warning and leaves the context
    # variable empty. The axes still run on the raw diff.
    fetch_linear_ticket
    fetch_db_context "$db_age"

    # --- 8. Step 2b: conformance axis evaluation ---------------------------
    log_info "------------------------------------------------------------"
    log_info "Pre-check summary:"
    log_info "  diff_lines=${diff_lines}"
    log_info "  diff_truncated=${DIFF_TRUNCATED}"
    log_info "  diff_bytes=${diff_bytes}"
    log_info "  diff_sha=${DIFF_SHA:0:12}"
    log_info "  axes_count=${axes_count}"
    log_info "  skip_axis=${skip_axis:-none}"
    log_info "  db_age_days=${db_age}"
    log_info "  trivy_loaded=${trivy_loaded}"
    log_info "  ticket_context_bytes=${#TICKET_CONTEXT}"
    log_info "  db_context_bytes=${#DB_CONTEXT}"
    log_info "  daily_cap=€${COUNCIL_DAILY_CAP_EUR:-5}"
    log_info "  mock_api=${MOCK_API:-0}"
    log_info "------------------------------------------------------------"

    # --- 8. Step 3c: parallel orchestration of all axes -------------------
    log_info "Evaluating ${axes_count} axes in parallel (Step 3c)"

    local conformance_out="${COUNCIL_TMPDIR}/conformance.json"
    local debt_out="${COUNCIL_TMPDIR}/debt.json"
    local attack_out="${COUNCIL_TMPDIR}/attack_surface.json"
    local contract_out="${COUNCIL_TMPDIR}/contract_impact.json"

    # Best-effort Trivy context for attack_surface (cap at 8KB to avoid
    # inflating the prompt beyond what the axis actually uses).
    local trivy_context=""
    if [ "$trivy_loaded" = "yes" ]; then
        trivy_context=$(head -c 8192 "$TRIVY_REPORT")
    fi

    # Start wall-clock timer (ms resolution where supported; fallback to s*1000).
    local start_ts end_ts duration_ms
    start_ts=$(now_ms)

    # Launch each axis as an independent subshell writing to its own output file.
    # PIDs are captured INCREMENTALLY (Adj #1 — $! only returns the most recent
    # background PID, so we must grab it right after each &).
    evaluate_axis conformance "$conformance_out" "$diff_content" "$TICKET_CONTEXT" \
        > "${COUNCIL_TMPDIR}/conformance.stdout" \
        2> "${COUNCIL_TMPDIR}/conformance.stderr" &
    local pid_conformance=$!

    evaluate_axis debt "$debt_out" "$diff_content" "" \
        > "${COUNCIL_TMPDIR}/debt.stdout" \
        2> "${COUNCIL_TMPDIR}/debt.stderr" &
    local pid_debt=$!

    evaluate_axis attack_surface "$attack_out" "$diff_content" "$trivy_context" \
        > "${COUNCIL_TMPDIR}/attack_surface.stdout" \
        2> "${COUNCIL_TMPDIR}/attack_surface.stderr" &
    local pid_attack=$!

    local axis_pids="$pid_conformance $pid_debt $pid_attack"

    if [ "$axes_count" -eq 4 ]; then
        evaluate_axis contract_impact "$contract_out" "$diff_content" "$DB_CONTEXT" \
            > "${COUNCIL_TMPDIR}/contract_impact.stdout" \
            2> "${COUNCIL_TMPDIR}/contract_impact.stderr" &
        local pid_contract=$!
        axis_pids="${axis_pids} ${pid_contract}"
    fi

    # Wait for every axis. `wait <pid>` is not disabled by `set -e` in bash 4+,
    # but we guard with `|| true` to keep counting failures across all PIDs.
    local failed=0 pid
    for pid in $axis_pids; do
        if ! wait "$pid"; then
            failed=$((failed + 1))
        fi
    done

    end_ts=$(now_ms)
    duration_ms=$((end_ts - start_ts))

    log_info "Parallel run complete: failed=${failed}/${axes_count} duration=${duration_ms}ms"

    # --- 9. Per-axis summary (best-effort, before aggregation) ------------
    local axis f axis_score axis_blockers
    for axis in conformance debt attack_surface contract_impact; do
        f="${COUNCIL_TMPDIR}/${axis}.json"
        if [ -f "$f" ] && [ -s "$f" ]; then
            axis_score=$(jq -r '.score // "?"' "$f" 2>/dev/null || echo "?")
            axis_blockers=$(jq -r '.blockers | length' "$f" 2>/dev/null || echo 0)
            log_ok "  ${axis}: score=${axis_score}/10 blockers=${axis_blockers}"
        elif [ "$axis" = "contract_impact" ] && [ "$axes_count" -eq 3 ]; then
            log_info "  ${axis}: SKIPPED (db stale/missing)"
        else
            log_warn "  ${axis}: NO RESULT (see ${axis}.stderr)"
            if [ -f "${COUNCIL_TMPDIR}/${axis}.stderr" ] && [ -s "${COUNCIL_TMPDIR}/${axis}.stderr" ]; then
                sed 's/^/    /' "${COUNCIL_TMPDIR}/${axis}.stderr" >&2 || true
            fi
        fi
    done

    # --- 10. Aggregate scores → verdict ------------------------------------
    # aggregate_scores return code mirrors the verdict (0/1/2) but we parse
    # the JSON `status` field to decide the exit — it carries strictly more
    # information (score, count, errors) and is easier to log. `|| true`
    # prevents set -e from killing us on REWORK (rc=1) or error (rc=2).
    local verdict
    verdict=$(aggregate_scores "$COUNCIL_TMPDIR" "$failed" "$axes_count" || true)

    local status global_score axes_used
    status=$(echo "$verdict" | jq -r '.status')
    global_score=$(echo "$verdict" | jq -r '.score // 0')
    axes_used=$(echo "$verdict" | jq -r '.count // 0')

    # --- 11. Usage + cost accounting (zero under MOCK_API) ----------------
    local tokens_line input_tokens output_tokens cost_eur
    tokens_line=$(sum_usage_tokens "$COUNCIL_TMPDIR")
    input_tokens=${tokens_line% *}
    output_tokens=${tokens_line#* }
    cost_eur=$(compute_cost_eur "$input_tokens" "$output_tokens")

    local db_fresh=true
    if [ "$axes_count" -ne 4 ]; then
        db_fresh=false
    fi

    # --- 12. Append history entry (never fails the script) ----------------
    write_history \
        "$status" \
        "$global_score" \
        "$axes_used" \
        "$db_fresh" \
        "$input_tokens" \
        "$output_tokens" \
        "$cost_eur" \
        "$diff_lines" \
        "$duration_ms"

    # --- 13. Final verdict + blockers dump --------------------------------
    case "$status" in
        APPROVED)
            log_ok "VERDICT: APPROVED (score=${global_score}/10 over ${axes_used} axes)"
            exit 0
            ;;
        REWORK)
            log_warn "VERDICT: REWORK (score=${global_score}/10 over ${axes_used} axes)"
            for axis in conformance debt attack_surface contract_impact; do
                f="${COUNCIL_TMPDIR}/${axis}.json"
                [ -f "$f" ] && [ -s "$f" ] || continue
                axis_blockers=$(jq -r '.blockers | length' "$f" 2>/dev/null || echo 0)
                if [ "$axis_blockers" -gt 0 ]; then
                    log_warn "  ${axis} blockers:"
                    jq -r '.blockers[]' "$f" 2>/dev/null | while IFS= read -r b; do
                        log_warn "    - ${b}"
                    done
                fi
            done
            exit 1
            ;;
        error|*)
            log_error "VERDICT: technical failure — verdict=${verdict}"
            exit 2
            ;;
    esac
}

main "$@"
