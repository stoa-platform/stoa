# UAC LLM-ready metadata

Use this note when touching UAC schemas, UAC examples, MCP tool generation,
MCP smoke tests, or API operations exposed to agents.

Canonical rule from ADR-067:

```text
UAC describes.
MCP projects.
Smoke proves.
```

## Doctrine

- UAC is the primary product contract.
- MCP tools are projections of UAC operations.
- Smoke tests prove that the projection exists and behaves safely at runtime.
- LLM metadata is endpoint-level because intent, side effects, approval, and
  examples differ per operation.
- V1 is progressive: missing metadata is a warning/review note, not a blanket
  blocker for existing contracts.
- Malformed metadata is an error when present.
- V2 target: new MCP-exposed endpoints must be LLM-ready before merge.

## V1 endpoint metadata

When `endpoint.llm` is present, it should contain:

```yaml
llm:
  summary: "Retrieve one customer by id."
  intent: "Use when an agent needs customer details before answering or preparing a follow-up action."
  tool_name: "customer_get_customer"
  side_effects: "read" # none | read | write | destructive
  safe_for_agents: true
  requires_human_approval: false
  examples:
    - input:
        id: "cust_123"
      expected_output_contains:
        id: "cust_123"
```

Keep `summary` and `intent` short. Do not turn them into policy prose or a
prompt. Prefer one synthetic example, two only when it removes real ambiguity.

## Hard rule

```text
side_effects=destructive -> requires_human_approval=true
```

Examples of destructive operations: delete, revoke, overwrite, rotate, external
business commitment, payment movement, irreversible workflow trigger, or any
operation with high blast radius.

## Deferred to v2

Do not add these fields in v1 unless a later ADR updates the contract:

- `sensitive_data`
- `do_not_use_when`
- `permissions`
- `rate_limit_policy`
- `approval_policy`
- `test_generation_hints`

## Review checklist

For an API or MCP-exposed change:

- Is the changed behavior attached to a UAC operation or flow contract?
- If it is MCP-exposed, does `endpoint.llm` exist or is its absence explicitly
  accepted as a v1 warning?
- If `endpoint.llm` exists, are all v1 fields present?
- Is `tool_name` stable and unique for the tenant/API namespace?
- Do `side_effects` and MCP annotations agree?
- If destructive, is `requires_human_approval=true`?
- Is there smoke proof that the UAC projection is discoverable?
- Are examples synthetic and free of secrets/customer data?

## Smoke expectation

The smoke test should prove at least:

- the tool appears in `tools/list`;
- the expected name is discoverable;
- the description reflects `summary`/`intent` when metadata is present;
- annotations match `side_effects`;
- example input validates against `input_schema`;
- read-only safe examples can run in deterministic smoke;
- write/destructive examples are not blindly executed and expose gating instead.
