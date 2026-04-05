# MEGA CAB-1969 — Gateway Audit Results

**Date**: 2026-04-04
**Environment**: Docker Compose local stack (15 services, 7h+ uptime)
**Auditor**: Claude Opus 4.6 (automated) + Playwright MCP (manual verification)

## Final Score: 36/37 pass (1 skip) — 97.3%

| Phase | Ticket | PR | Tests | Result | Duration |
|-------|--------|----|-------|--------|----------|
| P1 Infrastructure + MCP | CAB-1970 | #2176 (merged) | 8+9=17 | 17/17 pass | 6.8s |
| P2 Security + Observability | CAB-1971 | #2183 (merged) | 12+8=20 | 19/20 (1 skip) | 15.2s |
| P3 Guardrails + Deploy | CAB-1972 | #2185 (merged) | 7+7=14 | 14/14 pass | 36.1s |
| P4 Console Screens | CAB-1973 | #2189 (open) | 2054 vitest | 2054/2054 pass | 14.3s |
| **Full suite** | — | — | **51** | **50/51** | **60s** |

## Screenshots Archive

| File | Phase | What it proves |
|------|-------|----------------|
| `1.3-console-login.png` | P1 | Console login as parzival works |
| `2.7-gateway-registry.png` | P1 | Gateway Registry shows 3 online gateways |
| `2.8-gateway-modes.png` | P1 | Gateway Modes dashboard (Edge MCP, Sidecar, Connect) |
| `4.7-observability.png` | P2 | Console observability page loads |
| `4.8-call-flow.png` | P2 | Console call flow page loads |
| `6.4-deployments.png` | P3 | Deployments page with status cards |
| `6.5-gateway-overview.png` | P3 | Gateway overview page |
| `6.6-config-sync.png` | P3 | Config sync (drift detection) page |
| `P4-gateway-security-devserver.png` | P4 | NEW Security Dashboard (4 cards + table) |
| `P4-gateway-guardrails-devserver.png` | P4 | NEW Guardrails Dashboard (5 cards + config) |

## Skip: 4.5 — Gateway logs structured JSON
**Reason**: Promtail not configured to scrape stoa-gateway container in docker-compose.
**Mitigation**: Gateway produces JSON logs (verified via `docker logs stoa-gateway`). Loki integration works in K8s prod.

## Deliverables

### Code (merged to main)
- `e2e/fixtures/audit-auth.ts` — shared login helper (KC DOM IDs)
- `e2e/playwright.audit.config.ts` — dedicated audit runner
- `e2e/tests/audit-phase1-infra.spec.ts` — 8 infra assertions
- `e2e/tests/audit-phase2-mcp.spec.ts` — 9 MCP assertions
- `e2e/tests/audit-phase3-security.spec.ts` — 12 security assertions
- `e2e/tests/audit-phase4-observability.spec.ts` — 8 observability assertions
- `e2e/tests/audit-phase5-guardrails.spec.ts` — 7 guardrails assertions
- `e2e/tests/audit-phase6-deploy.spec.ts` — 7 deploy assertions
- `e2e/scripts/generate-evidence-pack.sh` — HTML evidence generator
- `deploy/docker-compose/.env.audit` — all feature flags enabled
- `scripts/demo/seed-audit.sh` — idempotent seed script
- `docs/audit/mtls-dpop-unit-evidence.md` — 36 Rust unit tests reference

### Code (PR #2189 — pending merge)
- `control-plane-ui/src/pages/GatewaySecurity/` — Security Dashboard (289 LOC)
- `control-plane-ui/src/pages/GatewayGuardrails/` — Guardrails Dashboard (180 LOC)
- Routes in App.tsx + nav in Layout.tsx

### Evidence (this directory)
- 19 screenshots (.png)
- 1 HTML report (Playwright)
- 1 JSON results file
- 1 Evidence Pack (EVIDENCE-PACK.html)

## How to reproduce

```bash
cd deploy/docker-compose && cp .env.audit .env && docker compose up -d
./scripts/demo/seed-audit.sh
cd e2e && npx playwright test --config playwright.audit.config.ts
```

## Council Score
8.50/10 — Go (unanime, 4 personas)
Impact: 68 (CRITICAL, mitigated to -0.5 via phase decomposition)
