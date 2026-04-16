# STOA PR Guardian — Policy Pack

This is the **rubric** the Guardian applies. The skill enforces the shape
(verdict, confidence, comment format). This file defines the content (what
counts as a flag, how flags combine into a verdict). Edit this file to tune
the rubric — no workflow change, no skill change required.

- **Advisory only.** Guardian never blocks merge.
- **Binary verdict** + confidence.
- **Fail-visible, never silent.**

Related:
- ADR-065 — decision record in stoa-docs.
- `.claude/skills/pr-guardian/SKILL.md` — the skill source.
- `docs/ai/pr-guardian-runbook.md` — operational surface.

---

## The three axes

Every flag carries a prefix. Inline comments lead with the prefix; the
summary comment aggregates counts per prefix.

### Axis 1 — ADR compliance → `[ADR-XXX]`

Load context: ADR-012 (RBAC), ADR-041 (Community / Enterprise), and — if the
PR touches Portal or Console — ADR-055 (Portal/Console governance). Add any
ADR referenced in the PR title, body, or commit messages (regex `ADR-\d+`),
capped at 6 loaded ADRs total.

For each changed file:

| Check | Fires when |
|---|---|
| **ADR-012 bypass** | A new HTTP route or FastAPI endpoint lacks `Depends(require_scope(...))`, or a Rust axum handler lacks the equivalent middleware/guard, or a React route is not wrapped in the scoped guard component. |
| **ADR-041 boundary leak** | Community code imports a module or crate tagged `enterprise-only`, or vice-versa. File-level `// @community` / `// @enterprise` markers or directory conventions (`src/enterprise/`) are authoritative. |
| **ADR-055 Portal/Console leak** | Portal code (`portal/`) imports from Console-only modules, or renders a Provider-scoped feature (API creation, subscription approval, gateway mgmt, webhooks, credentials, contracts). |
| **Dynamic ADR ref** | The PR cites `ADR-XXX` and the diff reads inconsistent with the decision described in that ADR. |

Flag shape:

```
[ADR-055] Portal importing Console-only module

Why this matters: breaks Portal=Consumer/Console=Provider split; confuses RBAC.
Suggested fix: move this hook to `control-plane-ui/` or route via the public API.
```

### Axis 2 — Security regression → `[SEC]`

Any `[SEC]` flag promotes the verdict to `NO-GO`. Be conservative: if in
doubt, the reviewer can overrule. False negatives are worse than false
positives on this axis.

| Check | Fires when |
|---|---|
| **Hardcoded secret** | Literal API key, JWT, Bearer token, private key, or credential in source, tests, fixtures, or migrations. Patterns: entropy > 3.5 on 20+ char strings, `AKIA...`, `sk_live_`, PEM headers, `eyJ...`. Exclude documented examples in `*.example.*`, `README`, and `docs/`. |
| **Auth bypass — Python** | New FastAPI route (`@router.get/post/...`) without `Depends(require_scope(...))` or equivalent. Applies to `control-plane-api/` and `mcp-gateway/` (legacy). |
| **Auth bypass — Rust** | New axum handler added without a middleware layer that enforces scope. Remember: `.layer()` only applies to routes registered BEFORE it. |
| **Auth bypass — React** | New Portal/Console route registered without a scoped guard (e.g. `<Protected scopes={...}>`). |
| **Unsafe deserialization** | Eval-like parsing (`eval`, `pickle.loads`, `yaml.load` without `SafeLoader`, `serde_json::from_value` on untrusted single-item arrays, JSONPath matches that silently return a single element when a list is expected — see webMethods JSONPath bug). |
| **SQL / NoSQL injection** | String concatenation or f-string interpolation into a query instead of parameterized binding. Applies to raw SQL, SQLAlchemy text(), MongoDB filter dicts built from user input. |
| **CORS / CSP loosening** | `Access-Control-Allow-Origin: *` added, CSP `unsafe-inline`/`unsafe-eval` added, without a justification comment tied to a ticket. |
| **Secret in log / response** | Log statement or HTTP response body containing a token, password, api key, or session cookie. Includes structured logging fields named `token`, `secret`, `authorization`, `password`. |

Flag shape:

```
[SEC] Route bypasses RBAC — missing scope guard

Why this matters: exposes the endpoint to any authenticated user.
Suggested fix: add `Depends(require_scope("stoa:write"))` to the signature.
```

### Axis 3 — AI-generated code smell → `[SMELL]`

~85% of STOA code is AI co-authored. Look for failure modes typical of LLM
generation. This is the axis that decays fastest — tune aggressively.

| Check | Fires when |
|---|---|
| **Dead code** | Unused import, unused variable, unused function, unreachable branch. Trust the linter — fire only when the linter is not covering this file. |
| **Over-abstraction** | Single-call wrapper adds no value (rename, parameter reorder, same signature). One-file helper imported once. Premature interface with a single implementer. |
| **Duplicated logic** | Same function logic reimplemented in a sibling file with minor variation. Heuristic: two functions with identical signatures and 80%+ overlapping bodies. |
| **Inconsistent naming** | New symbol deviates from the codebase convention (snake_case vs camelCase, `get_*` vs `fetch_*`, `Client` vs `Service`). Cross-reference 3+ existing symbols in the same module before flagging. |
| **Tests that test mocks** | Assertions verify what the mock was called with but no assertion on the real output or side effect under test. Common with `AsyncMock`, `httpx.MockTransport` used against the code under test instead of a boundary. |
| **WHAT-not-WHY comments** | Comment restates what the line does (`# increment counter`) instead of explaining a non-obvious constraint, invariant, or reason. |
| **Leftover markers** | `TODO`, `FIXME`, `XXX`, `HACK` in the diff (not in files outside the diff). |
| **Swallowed exceptions** | `except: pass`, `except Exception: pass` without logging, `.unwrap()` on fallible Rust Result/Option in non-test code, empty `catch {}` in TS, `|_|` ignored errors in Rust without a reason. |

Flag shape:

```
[SMELL] Swallowed exception hides storage failure

Why this matters: `except: pass` turns a DB timeout into silent data loss.
Suggested fix: log at WARN and re-raise, or catch the specific exception class.
```

---

## Verdict computation

Apply in order. First match wins.

1. **Any `[SEC]` flag → `NO-GO`.**
2. **`[ADR-XXX]` + `[SMELL]` combined count ≥ 3 → `NO-GO`.**
3. Otherwise → `GO`.

Count rule: a single file with three independent SMELLs counts as three. A
single SMELL referenced across five files counts as one (it is the same
issue). Use human judgment — the Guardian is advisory.

---

## Confidence computation

| Level | Fires when |
|---|---|
| `high` | Full diff analyzed (≤ 500 lines), all requested ADRs loaded, stack is unambiguous (single-stack PR). |
| `medium` | ONE of: diff in 500-1000 range, mixed-stack PR, one or more ADR requests partially loaded, unusual file layout. |
| `low` | TWO or more medium triggers, ADR loader returned the `ADR_LOADER_FETCH_FAILED` sentinel for any requested ADR, or diff is within 100 lines of the 1000-line cap. |

State the confidence and its primary reason in the summary. Example:
`Confidence: medium (mixed-stack PR)`.

---

## What the Guardian does NOT do

The following are explicitly out of scope. They belong to other tools or
to human reviewers:

- **Style/format nits** — ruff, black, prettier, clippy, eslint already cover these. The Guardian does not duplicate.
- **Test coverage thresholds** — coverage gates live in the per-stack CI workflows (ADR-031).
- **Build/test failures** — CI tells you. Guardian does not re-check.
- **Performance regressions** — out of scope; dedicated benchmarks handle this.
- **Prescription of fix** — Guardian suggests, humans decide. A `[SMELL]` with two possible fixes offers both; does not pick one.
- **Issue creation, Linear sync, task tracking** — Guardian is read-only beyond the PR comment surface.

---

## Policy evolution

Edits to this file land on `main` via PR. The Guardian picks up the new
rubric on its **next run** — no workflow restart, no skill redeploy. Expect
two sprints of advisory data before promoting any rule from "tune" to
"enforce" (see ADR-065 rollout plan).

When adding a rule: include a one-line "Fires when" cell in the relevant
axis table, a concrete flag example, and — if the rule has a historical
incident behind it — a reference (ticket ID, commit SHA).
