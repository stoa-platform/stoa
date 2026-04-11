#!/usr/bin/env bats
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 STOA Platform
#
# council-review.bats — unit tests for scripts/council-review.sh
#
# CAB-2047 Step 4: covers the pure helpers extracted in Step 3c —
#   - aggregate_scores <tmpdir> <failed_count> <expected_count>
#   - sum_usage_tokens <tmpdir>
#   - compute_cost_eur <input_tokens> <output_tokens>
#
# Tests source council-review.sh directly. The script guards `main "$@"`
# behind `BASH_SOURCE[0] == $0`, so sourcing loads functions without
# executing main.
#
# Run: bats tests/bats/council-review.bats

SCRIPT_PATH="${BATS_TEST_DIRNAME}/../../scripts/council-review.sh"

setup() {
    # shellcheck source=/dev/null
    source "$SCRIPT_PATH"

    TEST_TMPDIR=$(mktemp -d)
}

teardown() {
    if [ -n "${TEST_TMPDIR:-}" ] && [ -d "$TEST_TMPDIR" ]; then
        rm -rf "$TEST_TMPDIR"
    fi
}

# -----------------------------------------------------------------------------
# Fixture helpers
# -----------------------------------------------------------------------------

# Write a valid axis result JSON with the given score.
write_axis_result() {
    local axis="$1"
    local score="$2"
    cat > "${TEST_TMPDIR}/${axis}.json" <<EOF
{
  "score": ${score},
  "blockers": [],
  "warnings": [],
  "summary": "fixture axis ${axis} score ${score}"
}
EOF
}

# Write an invalid/empty axis result (simulates an errored axis).
write_empty_axis_result() {
    local axis="$1"
    : > "${TEST_TMPDIR}/${axis}.json"
}

# Write a usage raw (Anthropic response shape) for token sum tests.
write_usage_raw() {
    local axis="$1"
    local input="$2"
    local output="$3"
    cat > "${TEST_TMPDIR}/${axis}.raw" <<EOF
{
  "content": [{"type": "text", "text": "stub"}],
  "usage": {"input_tokens": ${input}, "output_tokens": ${output}}
}
EOF
}

# =============================================================================
# aggregate_scores — 5 canonical DoD scenarios (CAB-2047 Adj #9)
# =============================================================================

@test "aggregate_scores: 4 axes all ok, avg >= 8.0 → APPROVED exit 0" {
    write_axis_result conformance 9
    write_axis_result debt 8
    write_axis_result attack_surface 9
    write_axis_result contract_impact 8

    run aggregate_scores "$TEST_TMPDIR" 0 4

    [ "$status" -eq 0 ]
    [[ "$output" == *'"status":"APPROVED"'* ]]
    [[ "$output" == *'"count":4'* ]]
    [[ "$output" == *'"errors":0'* ]]
    # Average is (9+8+9+8)/4 = 8.50
    [[ "$output" == *'"score":8.5'* ]]
}

@test "aggregate_scores: 4 axes all ok, avg < 8.0 → REWORK exit 1" {
    write_axis_result conformance 7
    write_axis_result debt 7
    write_axis_result attack_surface 8
    write_axis_result contract_impact 7

    run aggregate_scores "$TEST_TMPDIR" 0 4

    [ "$status" -eq 1 ]
    [[ "$output" == *'"status":"REWORK"'* ]]
    [[ "$output" == *'"count":4'* ]]
    [[ "$output" == *'"errors":0'* ]]
    # Average is (7+7+8+7)/4 = 7.25
    [[ "$output" == *'"score":7.25'* ]]
}

@test "aggregate_scores: 3 axes ok + 1 errored → averaged over 3, count=3 errors=1" {
    write_axis_result conformance 9
    write_axis_result debt 9
    write_axis_result attack_surface 9
    write_empty_axis_result contract_impact

    run aggregate_scores "$TEST_TMPDIR" 0 4

    # 1 error is below the >=2 threshold — verdict still computed over 3 axes.
    [ "$status" -eq 0 ]
    [[ "$output" == *'"status":"APPROVED"'* ]]
    [[ "$output" == *'"count":3'* ]]
    [[ "$output" == *'"errors":1'* ]]
    [[ "$output" == *'"score":9'* ]]
}

@test "aggregate_scores: 2 axes errored → exit 2 technical failure" {
    write_axis_result conformance 9
    write_axis_result debt 9
    write_empty_axis_result attack_surface
    write_empty_axis_result contract_impact

    run aggregate_scores "$TEST_TMPDIR" 2 4

    [ "$status" -eq 2 ]
    [[ "$output" == *'"status":"error"'* ]]
    [[ "$output" == *'"errors":2'* ]]
    [[ "$output" == *'"count":2'* ]]
    [[ "$output" == *'"failed":2'* ]]
}

@test "aggregate_scores: contract_impact skipped (expected_count=3) → avg over 3" {
    write_axis_result conformance 8
    write_axis_result debt 8
    write_axis_result attack_surface 9
    # contract_impact intentionally absent — DB stale, so expected_count=3.

    run aggregate_scores "$TEST_TMPDIR" 0 3

    [ "$status" -eq 0 ]
    [[ "$output" == *'"status":"APPROVED"'* ]]
    [[ "$output" == *'"count":3'* ]]
    [[ "$output" == *'"errors":0'* ]]
    # Average is (8+8+9)/3 ≈ 8.33
    [[ "$output" == *'"score":8.33'* ]]
}

# =============================================================================
# Additional edge cases — defensive coverage
# =============================================================================

@test "aggregate_scores: all 4 axes errored → exit 2, count=0" {
    write_empty_axis_result conformance
    write_empty_axis_result debt
    write_empty_axis_result attack_surface
    write_empty_axis_result contract_impact

    run aggregate_scores "$TEST_TMPDIR" 4 4

    [ "$status" -eq 2 ]
    [[ "$output" == *'"status":"error"'* ]]
    [[ "$output" == *'"errors":4'* ]]
    [[ "$output" == *'"count":0'* ]]
}

@test "aggregate_scores: score exactly 8.0 → APPROVED" {
    write_axis_result conformance 8
    write_axis_result debt 8
    write_axis_result attack_surface 8
    write_axis_result contract_impact 8

    run aggregate_scores "$TEST_TMPDIR" 0 4

    [ "$status" -eq 0 ]
    [[ "$output" == *'"status":"APPROVED"'* ]]
    [[ "$output" == *'"score":8'* ]]
}

@test "aggregate_scores: missing conformance (expected) counts as error, not silent skip" {
    # conformance is in the expected_axes list, so its absence should be
    # counted — not silently skipped.
    write_axis_result debt 9
    write_axis_result attack_surface 9
    write_axis_result contract_impact 9

    run aggregate_scores "$TEST_TMPDIR" 0 4

    [ "$status" -eq 0 ]
    [[ "$output" == *'"errors":1'* ]]
    [[ "$output" == *'"count":3'* ]]
}

# =============================================================================
# sum_usage_tokens — token aggregation across axis .raw files
# =============================================================================

@test "sum_usage_tokens: sums input and output across all .raw files" {
    write_usage_raw conformance 1000 500
    write_usage_raw debt 800 400
    write_usage_raw attack_surface 1200 600
    write_usage_raw contract_impact 900 450

    run sum_usage_tokens "$TEST_TMPDIR"

    [ "$status" -eq 0 ]
    # Expected: 1000+800+1200+900 = 3900 input ; 500+400+600+450 = 1950 output
    [ "$output" = "3900 1950" ]
}

@test "sum_usage_tokens: no .raw files → 0 0" {
    run sum_usage_tokens "$TEST_TMPDIR"

    [ "$status" -eq 0 ]
    [ "$output" = "0 0" ]
}

@test "sum_usage_tokens: malformed .raw file → treated as 0" {
    echo "not json" > "${TEST_TMPDIR}/conformance.raw"
    write_usage_raw debt 100 50

    run sum_usage_tokens "$TEST_TMPDIR"

    [ "$status" -eq 0 ]
    [ "$output" = "100 50" ]
}

# =============================================================================
# compute_cost_eur — Sonnet 4.5 pricing (€2.76/MTok in, €13.80/MTok out)
# =============================================================================

@test "compute_cost_eur: 1M input / 0 output → 2.760000 EUR" {
    run compute_cost_eur 1000000 0
    [ "$status" -eq 0 ]
    [ "$output" = "2.760000" ]
}

@test "compute_cost_eur: 0 input / 1M output → 13.800000 EUR" {
    run compute_cost_eur 0 1000000
    [ "$status" -eq 0 ]
    [ "$output" = "13.800000" ]
}

@test "compute_cost_eur: realistic 4-axis call (12k in, 2k out) → under 0.10 EUR" {
    run compute_cost_eur 12000 2000
    [ "$status" -eq 0 ]
    # Expected: 12000*2.76/1e6 + 2000*13.80/1e6 = 0.03312 + 0.02760 = 0.060720
    [ "$output" = "0.060720" ]
}

@test "compute_cost_eur: zero tokens → 0.000000" {
    run compute_cost_eur 0 0
    [ "$status" -eq 0 ]
    [ "$output" = "0.000000" ]
}

# =============================================================================
# resolve_api_key — regression tests for CAB-2046 Infisical fallback
# =============================================================================
#
# These tests cover the no-op branches of resolve_api_key() without hitting
# the real Infisical API. The happy-path (actual Infisical fetch) is covered
# empirically by the self-review pre-push hook in this PR — see
# council-history.jsonl for the APPROVED 8.00/10 run on commit e74b1dfa.

@test "resolve_api_key: regression CAB-2046 — env already set is no-op, value preserved" {
    export ANTHROPIC_API_KEY="sk-ant-sentinel-value-do-not-touch"
    resolve_api_key
    [ "$ANTHROPIC_API_KEY" = "sk-ant-sentinel-value-do-not-touch" ]
}

@test "resolve_api_key: regression CAB-2046 — MOCK_API=1 skips fallback, env left empty" {
    unset ANTHROPIC_API_KEY
    export MOCK_API=1
    resolve_api_key
    [ -z "${ANTHROPIC_API_KEY:-}" ]
}

@test "resolve_api_key: regression CAB-2046 — COUNCIL_NO_INFISICAL=1 kill-switch skips fallback" {
    unset ANTHROPIC_API_KEY
    unset MOCK_API
    export COUNCIL_NO_INFISICAL=1
    resolve_api_key
    [ -z "${ANTHROPIC_API_KEY:-}" ]
}

@test "resolve_api_key: regression CAB-2046 — infisical CLI missing → silent no-op" {
    unset ANTHROPIC_API_KEY
    unset MOCK_API
    unset COUNCIL_NO_INFISICAL
    # Empty PATH guarantees `command -v infisical` fails
    local saved_path="$PATH"
    PATH=""
    resolve_api_key
    PATH="$saved_path"
    [ -z "${ANTHROPIC_API_KEY:-}" ]
}

@test "resolve_api_key: regression CAB-2046 — infisical-token helper missing → silent no-op" {
    unset ANTHROPIC_API_KEY
    unset MOCK_API
    unset COUNCIL_NO_INFISICAL
    # Sandbox PATH so `infisical` resolves but `infisical-token` does not.
    local sandbox
    sandbox=$(mktemp -d)
    : > "$sandbox/infisical"
    chmod +x "$sandbox/infisical"
    local saved_path="$PATH"
    PATH="$sandbox"
    resolve_api_key
    PATH="$saved_path"
    [ -z "${ANTHROPIC_API_KEY:-}" ]
    rm -rf "$sandbox"
}
