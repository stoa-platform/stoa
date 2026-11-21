# Demo Stable 2026-04-25

## Anchor

- Tag: `demo-stable-2026-04-25`
- Commit: `402b7732ee19215985194121f30d722cbd34baae`
- Commit summary: `chore(main): release stoa-gateway 0.9.17 (#2562)`
- Proof target: `REAL_PASS — DEMO READY`

## Boot

Use this command on the local demo machine. The port overrides avoid known local
conflicts on `5432`, `8080`, and `9644`; the smoke-facing ports stay unchanged:
`8000` for cp-api, `8081` for gateway, and `9090` for mock backend.

```bash
POSTGRES_PASSWORD=stoa \
KEYCLOAK_ADMIN_PASSWORD=admin \
OPENSEARCH_ADMIN_PASSWORD=admin \
OPENSEARCH_DASHBOARDS_PASSWORD=admin \
OPENSEARCH_LOGWRITER_PASSWORD=admin \
OPENSEARCH_OIDC_CLIENT_SECRET=demo-smoke \
STOA_DISABLE_AUTH=true \
PORT_DB=15432 \
PORT_KEYCLOAK=18080 \
PORT_REDPANDA=19093 \
PORT_REDPANDA_ADMIN=19644 \
docker compose -f deploy/docker-compose/docker-compose.yml --profile demo up -d \
  postgres keycloak control-plane-api stoa-gateway mock-backend
```

## Smoke

Run the UAC-driven smoke from a checkout of the tag:

```bash
DEMO_UAC_CONTRACT=specs/uac/demo-httpbin.uac.json \
./scripts/demo-smoke-test.sh --no-observability-ui
```

Expected result:

```text
Score: 9/9
Verdict: REAL_PASS — DEMO READY
```

## Rollback

Stop and remove the local demo stack:

```bash
POSTGRES_PASSWORD=stoa \
KEYCLOAK_ADMIN_PASSWORD=admin \
OPENSEARCH_ADMIN_PASSWORD=admin \
OPENSEARCH_DASHBOARDS_PASSWORD=admin \
OPENSEARCH_LOGWRITER_PASSWORD=admin \
OPENSEARCH_OIDC_CLIENT_SECRET=demo-smoke \
STOA_DISABLE_AUTH=true \
PORT_DB=15432 \
PORT_KEYCLOAK=18080 \
PORT_REDPANDA=19093 \
PORT_REDPANDA_ADMIN=19644 \
docker compose -f deploy/docker-compose/docker-compose.yml --profile demo down -v --remove-orphans
```

## Preservation Rule

Do not merge non-essential changes into the demo path before rehearsal. If a
demo patch is unavoidable, create a new tag after a fresh UAC smoke returns
`REAL_PASS — DEMO READY`.
