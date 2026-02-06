# STOA Memory

> Last updated: 2026-02-06 (Session 14 — CAB-1114 Phase 4 Console Integration)

## Active Sprint
- **Goal**: Revenue-ready demo by Feb 24, 2026
- **Branch**: main
- **Focus**: CAB-1114 OpenSearch Logs — Phase 4 Console integration done, all 4 phases complete

## Session State

| Status | Ticket | Description | Evidence |
|--------|--------|-------------|----------|
| DONE | CAB-1044 | API Search HTTP 500 fix | commit 2c5672d8 |
| DONE | CAB-1040 | Gateway Routes HTTP 404 fix | commit 0c33e21d |
| DONE | CAB-1042 | Vault sealed fix | commit 8bbf71b9 |
| DONE | CAB-1041 | E2E BDD auth fix | commit 248f9d29 |
| DONE | — | CLI stoa v0.1.0 (5 commands, 55 tests, 84% coverage) | Session 2 |
| DONE | — | E2E tests 24/24 pass | Session 3 |
| DONE | CAB-1061 | Demo data seed script | Session 4 |
| DONE | CAB-1060 | Docs 20 pages (Docusaurus) | Session 5 |
| DONE | CAB-1062 | Docker image + CI deploy | PR #74, Session 6 |
| DONE | ADR-030 | AI context management architecture | Session 7 |
| DONE | — | Context refactor: CLAUDE.md 11KB→3KB + 8 rules + 8 component docs + 8 skills + hooks | Session 7 |
| DONE | CAB-CD-001 | Enterprise CD Architecture deployed on EKS | Session 8, commit 46401a3b |
| DONE | CAB-1113 | Performance Phase 5: SQL filtering + DTOs légers (portal.py) | Session 9 |
| DONE | CAB-1113 | Performance Phase 6: Cache + Keycloak Boot + Web Vitals | PR #139, Session 10 |
| DONE | CAB-1114 | OpenSearch Phase 1: Deploy + Dashboards + Ingestion | commit 03665d57, e6e72a52 |
| DONE | CAB-1114 | OpenSearch Phase 2: RGPD redaction pipeline (7 PII patterns) | commit 35fa3943, Session 11 |
| DONE | CAB-1114 | OpenSearch Phase 3: Multi-Tenant OIDC Security | Session 12+13, 6/6 tests |
| DONE | CAB-1114 | OpenSearch Phase 4: Console Integration (SSO iframe) | Session 14, LogsEmbed.tsx + route + sidebar |
| NEXT | CAB-1066 | Landing gostoa.dev + Stripe | — |
| NEXT | — | Browser-based demo walkthrough | — |
| NEXT | — | Record video backup for demo | — |

## Decisions This Sprint
- 2026-02-04: Use column refs in SQLAlchemy upsert (not string keys)
- 2026-02-04: E2E auth requires dual OIDC client tokens (portal + console)
- 2026-02-05: ADRs live in stoa-docs, not stoa (ADR-030)
- 2026-02-05: Retire .stoa-ai/ — migrate to native Claude Code features (skills, rules, hooks)
- 2026-02-05: CLAUDE.md hierarchy: root (compact) + .claude/rules/ (modular) + component CLAUDE.md (lazy)
- 2026-02-06: Kyverno policies in Audit mode first, switch to Enforce after validation
- 2026-02-06: ArgoCD ApplicationSet uses goTemplate mode for multi-env deployments
- 2026-02-06: OpenSearch 2.11.0 doesn't support `_meta` on ingest pipelines (only on index templates)
- 2026-02-06: Painless regex requires `script.painless.regex.enabled=true` in OpenSearch env for reliable `.matcher().replaceAll()`
- 2026-02-06: `default_pipeline` on index template applies to all `_bulk` writes — pipeline must exist before seeding data
- 2026-02-06: OpenSearch OIDC requires `extra_hosts: localhost:host-gateway` for Docker containers to reach nginx (OIDC discovery URL)
- 2026-02-06: Fallback OIDC discovery URL: `http://nginx/auth/realms/stoa/.well-known/openid-configuration` if host-gateway fails
- 2026-02-06: OpenSearch security plugin requires demo certs (`allow_unsafe_democertificates: true`) for single-node dev
- 2026-02-06: `securityadmin.sh` needs kirk.pem admin cert to push security config — run from opensearch image container
- 2026-02-06: Tenant alignment: `tenant-alpha/beta` renamed to `oasis-gunters/ioi-sixers` to match Keycloak users
- 2026-02-06: Demo certs must be extracted from OpenSearch image and mounted — `DISABLE_INSTALL_DEMO_CONFIG=true` required
- 2026-02-06: `securityadmin.sh` requires ALL 8 config files (incl. `nodes_dn.yml`, `whitelist.yml`)
- 2026-02-06: Dashboards OIDC `connect_url` must use `http://keycloak:8080` (not nginx) to avoid circular dependency
- 2026-02-06: OpenSearch `roles_key` does NOT support nested paths — use flat `roles` claim, not `realm_access.roles`
- 2026-02-06: nginx alpine healthcheck: use `127.0.0.1` not `localhost` (IPv6 `::1` issue)

## CD Infrastructure (Session 8 — 2026-02-06)
- **Argo Rollouts**: Installed for progressive delivery (canary deployments)
- **Kyverno v1.17.0**: 9 pods, 5 policies in Audit mode
  - `verify-image-signatures`: Cosign keyless with GitHub OIDC
  - `require-labels`: app.kubernetes.io/part-of required
  - `require-probes`: Liveness/readiness required for deployments
  - `require-external-secrets`: Block raw secrets, force ESO
  - `restrict-privileged`: Block privileged containers (Enforce mode)
- **ArgoCD ApplicationSet**: 15 apps (5 components × 3 envs) with sync waves
- **PrometheusRule**: DORA metrics (success rate, lead time, failure rate)
- **TODO**: Switch Kyverno policies to Enforce mode after validation period

## Known Issues
- **CI/CD pipelines broken** since PR #76 — startup_failure on workflow files. Pods won't auto-update until fixed.
- Loki behind oauth2-proxy — requires Grafana for direct queries
- Portal has 2 APIs in catalog; Console has 0 per tenant until seed

## E2E Validation (Session 3 — 2026-02-04)
- **24/24 tests passed** (22.6s)
- Auth: 7/7 personas, Portal: 5/5, Console: 5/5, Gateway: 6/6, TTFTC: 1/1 (12.7s)
- Zero HTTP 500 errors across all endpoints
- All 4 bug fixes verified live

## Notes
- Demo: mardi 24 fevrier 2026
- Presentation "ESB is Dead" same day
- 2 design partners to close
- Stack = Python (not Node)
- Console tenants: "oasis", "oasis-gunters"
- Portal OIDC client: stoa-portal; Console OIDC client: control-plane-ui
- Demo seed: `make seed-demo` or `ANORAK_PASSWORD=xxx python3 scripts/seed-demo-data.py`
- Docs site: stoa-docs/ (Docusaurus 3.9), 20 pages
