# Impact Analysis Protocol

> MANDATORY before each MEGA-ticket and cross-component change.
> Source of truth: `docs/stoa-impact.db` (SQLite)

## Before Coding

### 1. Identify impacted components

```bash
./docs/scripts/impact-check.sh <component-id>
```

Component IDs: `control-plane`, `console`, `portal`, `stoa-gateway`, `mcp-gateway`, `keycloak`, `postgresql`, `kafka`, `prometheus`, `grafana`, `vault`, `opa`, `stoa-go`

### 2. Check specific contract impact

```bash
./docs/scripts/contract-check.sh "<endpoint or pattern>"
```

Examples:
```bash
./docs/scripts/contract-check.sh "/api/v1/subscriptions"
./docs/scripts/contract-check.sh "Keycloak Admin"
./docs/scripts/contract-check.sh "kafka"
```

### 3. For each impacted scenario, verify

- [ ] Scenario has integration/E2E test coverage
- [ ] Contract (API schema, event format) changes are backward-compatible
- [ ] All consumers of changed contracts are updated in the same PR or follow-up

### 4. Document in Linear ticket

Add to ticket description or comment:
```
**Impact Analysis**
- Components: [list from impact-check.sh]
- Scenarios: [P0/P1 scenarios affected]
- Contracts modified: [contract IDs]
- Consumer updates needed: [list]
- Tests to add/modify: [list]
```

## After Implementation

### 5. Verify impacted scenarios

For each affected scenario:
- [ ] E2E test passes (or `@wip` tagged with justification)
- [ ] No regression on adjacent scenarios
- [ ] Contract snapshots updated if schema changed

### 6. Regenerate docs if contracts changed

```bash
# Edit data in populate-db.py, then:
python3 docs/scripts/populate-db.py
```

This regenerates `DEPENDENCIES.md` and `SCENARIOS.md` automatically.

## Updating the Database

### Add a new component
Edit `COMPONENTS` list in `docs/scripts/populate-db.py`

### Add a new contract
Edit `CONTRACTS` list — use convention: `{SRC_SHORT}-{TGT_SHORT}-{NNN}`

### Add a new scenario
Edit `SCENARIOS` and `SCENARIO_STEPS` lists

### Quick SQL query (ad-hoc)
```bash
sqlite3 docs/stoa-impact.db "SELECT * FROM impact_analysis WHERE priority = 'P0'"
```

## Convention

| Entity | ID Format | Example |
|--------|-----------|---------|
| Component | `kebab-case` | `control-plane`, `stoa-gateway` |
| Contract | `{SRC}-{TGT}-{NNN}` | `CP-KC-001`, `PT-CP-003` |
| Scenario | `SCEN-{NNN}` | `SCEN-001` |

## File Inventory

| File | Purpose | Editable? |
|------|---------|-----------|
| `docs/stoa-impact.db` | SQLite database (source of truth) | Via scripts only |
| `docs/scripts/populate-db.py` | Data definitions + DB creation | Yes (edit data here) |
| `docs/scripts/regenerate-docs.py` | Markdown generator | Rarely |
| `docs/scripts/schema.sql` | DB schema | Rarely |
| `docs/scripts/impact-check.sh` | Component impact query | No |
| `docs/scripts/contract-check.sh` | Contract impact query | No |
| `docs/DEPENDENCIES.md` | Auto-generated dependency map | Never (auto-generated) |
| `docs/SCENARIOS.md` | Auto-generated scenario catalog | Never (auto-generated) |
| `docs/audit/*.md` | Component audit reports | Update when architecture changes |
