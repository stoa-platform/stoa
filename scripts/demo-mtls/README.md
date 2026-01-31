# mTLS Demo Runbook — Feb 26, 2026

## Prerequisites

1. **Database** running with tables created (alembic migrations applied)
2. **100 clients seeded**:
   ```bash
   cd control-plane-api
   python3 -m scripts.seed_demo_clients
   ```
3. **Services running**:
   - Control Plane API (`http://localhost:8000`)
   - MCP Gateway (`http://localhost:8080`)
   - PostgreSQL (`localhost:5432`)
4. **Dashboard open**: `http://localhost:3000/clients`

## Quick Start

```bash
# Full demo (seed + traffic + rotation + burst)
./scripts/demo-mtls/run_demo.sh full

# Traffic only (10 TPS, 2 minutes)
./scripts/demo-mtls/run_demo.sh traffic-only 10 120

# Rotate a random expiring client
./scripts/demo-mtls/run_demo.sh rotation
```

## Demo Scenarios

### Scenario 1: Traffic Overview (2 min)

Show the dashboard with 100 clients, then generate traffic.

```bash
./scripts/demo-mtls/run_demo.sh traffic-only 10 120
```

**Talk track**:
> "Nous avons 100 clients API, chacun avec son propre certificat mTLS.
> Vert = sain, Jaune = expire bientot, Rouge = critique.
> Le dashboard montre le statut en temps reel de tous les certificats."

### Scenario 2: Certificate Rotation (3 min)

Pick an "expiring soon" client and rotate live.

1. Open client detail page in dashboard
2. Click "Rotate Certificate"
3. Show grace period (blue banner)
4. Show both fingerprints active during grace period

```bash
./scripts/demo-mtls/run_demo.sh rotation
```

**Talk track**:
> "Quand on fait la rotation, l'ancien ET le nouveau certificat fonctionnent
> pendant la periode de grace. Zero downtime. L'ancien certificat expire
> automatiquement apres 24 heures."

### Scenario 3: Security — Certificate Binding (2 min)

Show what happens with wrong certificate. Watch the metrics.

```bash
# Terminal 1: Watch cert binding metrics
watch -n 2 'curl -s http://localhost:8080/metrics | grep cert_binding'

# Terminal 2: Generate mixed traffic (20% will fail)
./scripts/demo-mtls/run_demo.sh traffic-only 5 60
```

**Talk track**:
> "Si quelqu'un essaie d'utiliser un JWT destine a un autre certificat,
> le gateway le rejette immediatement. Le certificate binding empeche
> les attaques de vol de token — meme si le JWT est valide, il ne marche
> qu'avec le bon certificat client."

Metrics to highlight:
- `stoa_mcp_gateway_cert_binding_validations_total{status="success"}` — successful bindings
- `stoa_mcp_gateway_cert_binding_failures_total{reason="mismatch"}` — rejected mismatches

### Scenario 4: Full Flow (5 min)

Run the complete demo sequence:

```bash
./scripts/demo-mtls/run_demo.sh full
```

Steps: seed 100 clients → warm-up (5 TPS, 30s) → live rotation → burst (20 TPS, 60s)

## Traffic Mix

The traffic generator sends:
- **80%** valid requests (matching JWT `cnf` + certificate header)
- **10%** header mismatch (correct JWT, wrong `X-SSL-Client-Cert-SHA256`)
- **10%** JWT mismatch (wrong `cnf.x5t#S256` in token, correct header)

This demonstrates RFC 8705 certificate binding validation from both directions.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GATEWAY_URL` | `http://localhost:8080` | MCP Gateway URL |
| `API_URL` | `http://localhost:8000` | Control Plane API URL |
| `DB_URL` | `postgresql+asyncpg://stoa:stoa@localhost:5432/stoa` | Database URL |
| `ENDPOINT` | `/health` | Target endpoint for traffic |

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No clients in dashboard | Run `python3 -m scripts.seed_demo_clients` |
| DB connection error | Check PostgreSQL is running on port 5432 |
| All requests fail (connection refused) | Check MCP Gateway is running on port 8080 |
| 401 on all requests | Expected for 20% of traffic (mismatch demo) |
| Metrics not updating | Check `CERT_BINDING_ENABLED=true` in gateway env |

## Files

| File | Purpose |
|------|---------|
| `mock_jwt.py` | Generate JWTs with `cnf.x5t#S256` claims |
| `generate_traffic.py` | Async traffic generator (httpx) |
| `run_demo.sh` | Demo orchestrator (3 scenarios) |
| `README.md` | This runbook |
