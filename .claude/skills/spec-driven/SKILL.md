---
name: spec-driven
description: Create a SPEC.md for a feature, validate via Council, then generate failing tests from acceptance criteria before implementation.
user_invocable: true
---

# Spec-Driven Development

CAB-2005: Formalize the spec-first pattern. Council validates the spec BEFORE code.
Acceptance criteria become test cases. Tests are written BEFORE implementation.

## Usage

```
/spec-driven CAB-XXXX
/spec-driven "feature description"
```

## Step 1: Create Spec

1. If a CAB-XXXX ID is given, fetch the ticket from Linear: `linear.get_issue("CAB-XXXX")`
2. Copy template from `.claude/templates/SPEC.md`
3. Fill in: Problem, Goal, API Contract, Acceptance Criteria, Edge Cases
4. Write to branch root as `SPEC.md`

## Step 2: Council on Spec (Stage 1 variant)

Run the 4-persona Council but evaluate the **spec quality**, not the feature itself:

- **Chucky**: Are edge cases covered? Missing failure modes?
- **OSS Killer**: Is the goal measurable? Will this deliver user value?
- **Archi**: Is the API contract consistent with existing patterns? Breaking changes?
- **Better Call Saul**: Security considerations complete? PII/GDPR noted?

Threshold: >= 7.0 to proceed. Below 7.0: revise spec first.

## Step 3: Generate Failing Tests

From each acceptance criterion, generate a test:

- **Python (api)**: `test_spec_ac1_<description>()` in `tests/test_spec_<ticket>.py`
- **TypeScript (ui/portal)**: `describe('spec/CAB-XXXX', () => { it('AC1: ...') })` in `src/__tests__/spec/`
- **Rust (gateway)**: `fn spec_ac1_description()` in inline `#[cfg(test)] mod tests`

All tests MUST fail (red) at this stage. If any passes, the criterion is already met or the test is wrong.

## Step 4: Implement

Write code to make all tests pass. Standard Pattern 3 workflow.

## Step 5: Verify

- All spec tests green
- No other tests broken
- `SPEC.md` stays in the branch (committed with the PR) as documentation

## Rules

- Spec lives in branch root, committed in the same PR as the implementation
- Council scores the spec, not the implementation plan
- Every acceptance criterion = exactly one test
- Edge cases table = additional tests (tagged `@edge-case`)
- If spec changes during implementation, re-run Council
- `.spec.md` = technical only. Business data → stoa-strategy (private repo)
