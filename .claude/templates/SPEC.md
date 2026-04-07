# Spec: <CAB-XXXX> — <Short Title>

> Spec-driven development template (CAB-2005). Council validates THIS spec before code.
> Delete this header block before committing.

## Problem

_What is broken or missing? 1-2 sentences._

## Goal

_What does success look like? Measurable outcome._

## API Contract

_If this changes an API, define the contract here._

```
METHOD /path
Request: { field: type }
Response: { field: type }
Status codes: 200, 400, 404, 409
```

## Acceptance Criteria

_Binary pass/fail. Each criterion becomes a test._

- [ ] AC1: <When X, then Y>
- [ ] AC2: <When A, then B>
- [ ] AC3: <Edge case: when Z, then W>

## Edge Cases

| Case | Input | Expected | Priority |
|------|-------|----------|----------|
| Empty input | `""` | 400 Bad Request | Must |
| Duplicate | existing name | 409 Conflict | Must |
| Max length | 500 chars | Truncate or reject | Should |

## Out of Scope

- _What this spec explicitly does NOT cover_

## Security Considerations

- [ ] Auth required? Which roles?
- [ ] PII handling?
- [ ] Rate limiting?

## Dependencies

- _Other tickets or services this depends on_

## Notes

_Implementation hints, links to ADRs, prior art._
