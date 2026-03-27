# Runbook: Realdata Traffic Test Suite

> **Severity**: Medium
> **Last updated**: 2026-03-27
> **Owner**: Platform Team
> **Linear Issue**: CAB-1861

---

## 1. Overview

The realdata-traffic test suite validates two Alembic seed migrations that populate the `demo` tenant's API catalog with realistic data for the Call Flow Dashboard and gateway traffic simulation.

| Migration | File | APIs | Purpose |
|-----------|------|------|---------|
| `074_seed_realdata_apis` | `alembic/versions/074_seed_realdata_apis.py` | 6 | Public APIs (ExchangeRate, CoinGecko, OpenWeatherMap, NewsAPI, AlphaVantage, Echo) |
| `075_seed_traffic_seeder_apis` | `alembic/versions/075_seed_traffic_seeder_apis.py` | 6 | EU/FAPI APIs (ECB, Eurostat, OAuth2 echo, Bearer echo, FAPI accounts, FAPI transfers) |

**Total**: 12 APIs across all auth types (`none`, `api_key_query`, `api_key_header`, `oauth2_cc`, `bearer`, `fapi_baseline`, `fapi_advanced`) and deployment modes (`edge-mcp`, `sidecar`, `connect`).

---

## 2. Running the Test Suite

### Full suite (recommended)

```bash
cd control-plane-api
pytest tests/test_seed_realdata_apis.py tests/test_seed_traffic_seeder_apis.py -v
```

### With coverage

```bash
pytest tests/test_seed_realdata_apis.py tests/test_seed_traffic_seeder_apis.py \
  --cov=src --cov-report=term-missing -v
```

### Single migration

```bash
# Migration 074 only
pytest tests/test_seed_realdata_apis.py -v

# Migration 075 only
pytest tests/test_seed_traffic_seeder_apis.py -v
```

### In CI (component-level)

Tests run as part of the standard `control-plane-api` CI pipeline:

```bash
pytest tests/ --cov=src --cov-fail-under=70 --ignore=tests/test_opensearch.py -q
```

No special flags or environment variables are required — these tests are pure unit tests that load migration modules directly from the filesystem. **No database or running service is needed.**

---

## 3. Test Structure

### Migration 074 (`test_seed_realdata_apis.py`)

| Test Class | What it validates |
|------------|------------------|
| `TestSeedRealdataAPIsData` | Seed data integrity (6 APIs, required fields, backend URLs, auth types, tags) |
| `TestInternalCatalogRealdataAPIs` | FastAPI `/v1/internal/catalog/apis` endpoint contract (mocked DB) |

Key assertions:
- Exactly 6 APIs defined for tenant `demo`
- All have `realdata` tag and `portal_published=True`
- `echo-fallback` has `category=internal` and `auth_type=none`
- `api_key_query` APIs have `auth_param`; `api_key_header` APIs have `auth_header`
- Backend URLs are reachable public endpoints (not validated live)

### Migration 075 (`test_seed_traffic_seeder_apis.py`)

| Test Class | What it validates |
|------------|------------------|
| `TestSeedTrafficSeederAPIsData` | Extended seed data (6 APIs, UUIDs v4, deployment modes, auth types, FAPI banking category) |

Key assertions:
- No UUID or `api_id` overlap with migration 074
- `down_revision` chain: `075` → `074`
- FAPI APIs have `category=banking` and `fapi` tag
- EU APIs (`ecb-financial-data`, `eurostat`) have `eu-public` tag
- Valid `deployment_mode` values: `edge-mcp`, `sidecar`, `connect`

---

## 4. Interpreting Results

### Green (all pass)

```
tests/test_seed_realdata_apis.py ..........  [10/10]
tests/test_seed_traffic_seeder_apis.py ...............  [15/15]
25 passed in 2.1s
```

Both migrations are structurally valid. The demo tenant catalog is correctly configured.

### Common failure patterns

| Failure | Cause | Fix |
|---------|-------|-----|
| `assert len(APIS) == 6` | API added/removed from migration | Update migration file to restore count |
| `{api_id} missing fields` | Required field dropped from seed dict | Add missing field to migration |
| `UUID … is not v4` | Wrong UUID format used | Use `uuid.uuid4()` in migration |
| `ID overlap with 074` | Duplicate UUID across migrations | Generate a new UUID for the 075 API |
| `down_revision` assertion fails | Migration chain broken | Restore `down_revision = "074_seed_realdata_apis"` |
| `ImportError` | Migration file missing or syntax error | Check file exists and parses correctly |
| `auth_type not in valid_auth` | New auth type added without updating test | Add to `valid_auth` set in test, document in this runbook |
| `deployment_mode not in valid_modes` | New mode added | Add to `valid_modes` set, update schema |

### Locating the failure

```bash
# Run with short traceback to pinpoint the assertion
pytest tests/test_seed_realdata_apis.py -v --tb=short

# Run a single parametrized test case
pytest tests/test_seed_realdata_apis.py::TestSeedRealdataAPIsData::test_backend_urls[exchange-rate-https://api.exchangerate-api.com] -v
```

---

## 5. Troubleshooting

### Migration file not found

```
ModuleNotFoundError: No module named 'migration_074'
```

The tests load migration modules by absolute path. Verify the file exists:

```bash
ls control-plane-api/alembic/versions/074_seed_realdata_apis.py
ls control-plane-api/alembic/versions/075_seed_traffic_seeder_apis.py
```

If missing, check git history:

```bash
git log --oneline --diff-filter=D -- control-plane-api/alembic/versions/074_seed_realdata_apis.py
```

### FastAPI app import fails (test class `TestInternalCatalogRealdataAPIs`)

The internal endpoint tests import `src.main:app`. Common causes:

```bash
# Check that all dependencies are installed
pip install -r control-plane-api/requirements.txt

# Verify the app starts (dry run)
cd control-plane-api && python -c "from src.main import app; print('OK')"
```

If env vars are missing, set minimal config:

```bash
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost/db"
export KEYCLOAK_URL="http://localhost:8080"
# Then re-run the tests
```

### Stale migration chain (after rebase/squash)

If the `down_revision` assertion fails after a branch rebase:

```bash
# Check current revision chain
cd control-plane-api && alembic history --verbose | head -20
```

Restore the correct `down_revision` in `075_seed_traffic_seeder_apis.py`:

```python
revision = "075_seed_traffic_seeder_apis"
down_revision = "074_seed_realdata_apis"
```

---

## 6. Uptime Kuma Monitor Definitions

The following monitors cover the MCP and portal endpoints that the realdata APIs back. Configure in Uptime Kuma at `https://status.gostoa.dev`.

### MCP Gateway — Tool Discovery

| Field | Value |
|-------|-------|
| **Monitor type** | HTTP(s) |
| **Name** | MCP Gateway — Tool Discovery |
| **URL** | `https://mcp.gostoa.dev/mcp/tools/list` |
| **Method** | GET |
| **Expected status** | 200 |
| **Check interval** | 60 s |
| **Timeout** | 15 s |
| **Tags** | `mcp`, `gateway`, `critical` |
| **Alert threshold** | 2 consecutive failures |

### MCP Gateway — Health

| Field | Value |
|-------|-------|
| **Monitor type** | HTTP(s) |
| **Name** | MCP Gateway — Health |
| **URL** | `https://mcp.gostoa.dev/health` |
| **Method** | GET |
| **Expected status** | 200 |
| **Check interval** | 30 s |
| **Timeout** | 10 s |
| **Tags** | `mcp`, `gateway`, `health` |
| **Alert threshold** | 1 consecutive failure |

### Control Plane API — Internal Catalog (realdata)

| Field | Value |
|-------|-------|
| **Monitor type** | HTTP(s) |
| **Name** | CP API — Internal Catalog |
| **URL** | `https://api.gostoa.dev/v1/internal/catalog/apis` |
| **Method** | GET |
| **Expected status** | 200 |
| **Check interval** | 120 s |
| **Timeout** | 10 s |
| **Tags** | `api`, `catalog`, `realdata` |
| **Notes** | Returns 12 seeded demo APIs when migrations 074+075 applied |
| **Alert threshold** | 2 consecutive failures |

### Portal API Discovery

| Field | Value |
|-------|-------|
| **Monitor type** | HTTP(s) |
| **Name** | Portal — API Discovery |
| **URL** | `https://portal.gostoa.dev/api/v1/catalog/apis?published=true` |
| **Method** | GET |
| **Expected status** | 200 |
| **Check interval** | 120 s |
| **Timeout** | 10 s |
| **Tags** | `portal`, `catalog` |
| **Alert threshold** | 2 consecutive failures |

### Echo Fallback (internal backend)

| Field | Value |
|-------|-------|
| **Monitor type** | HTTP(s) |
| **Name** | Echo Backend — Fallback |
| **URL** | `http://echo-backend:8888` |
| **Method** | GET |
| **Expected status** | 200 |
| **Check interval** | 60 s |
| **Timeout** | 5 s |
| **Tags** | `internal`, `echo`, `realdata` |
| **Notes** | Only accessible from within the cluster; monitor via internal probe |
| **Alert threshold** | 3 consecutive failures |

### Import via Uptime Kuma API (optional)

Uptime Kuma does not have a native import format, but monitors can be bulk-created via the REST API or directly through the UI. Use the table above as the canonical definition.

---

## 7. Cost Audit — Token and Compute Costs

### Local development

| Item | Estimate | Notes |
|------|----------|-------|
| `pytest` run (25 tests) | **< 1 s CPU** | Pure unit tests, no I/O, no network |
| Memory peak | **~80 MB RSS** | FastAPI app import + pytest fixtures |
| Anthropic tokens (CI assist) | **0** | No AI involved in test execution |

These tests are among the cheapest in the suite — no database, no network, no docker.

### CI (GitHub Actions, `ubuntu-latest`)

| Item | Estimate | Notes |
|------|----------|-------|
| Runner minutes | **~2 min** | Shared with full `control-plane-api` test suite |
| Runner cost | **~$0.004 / run** | `ubuntu-latest` = $0.008/min, 50% of full suite time |
| Monthly (assuming 50 PRs) | **~$0.20/month** | Negligible |

The full `control-plane-api` CI suite takes ~4 min on `ubuntu-latest`. Seed migration tests add < 5 s.

### AI Factory sessions (when modifying migrations)

Modifying migration 074 or 075 typically falls in the **"Show" category** (isolated data change, no logic).

| Session type | Model | Estimated cost |
|---|---|---|
| Understanding migration structure | Haiku (Explore subagent) | ~$0.05 |
| Writing/fixing a seed migration | Sonnet | ~$0.30–$0.80 |
| Full Council review (if requested) | Sonnet × 4 personas | ~$0.50–$1.00 |

Reference pricing (API-equivalent, 2026-03):

| Model | Input/MTok | Output/MTok |
|-------|-----------|-------------|
| Opus 4.6 | $15 | $75 |
| Sonnet 4.6 | $3 | $15 |
| Haiku 4.5 | $0.80 | $4 |

### Gateway traffic simulation (Call Flow Dashboard)

When the seeded APIs are used by a traffic seeder script to generate realistic call patterns:

| Scenario | Estimate | Notes |
|----------|----------|-------|
| 1 req/s to 6 APIs × 1h | ~21,600 gateway calls | Gateway overhead: ~2 ms/req |
| External API rate limits | Free tier: 1,000–10,000 calls/day | ExchangeRate: 1,500/day free; CoinGecko: 100/min |
| Cost of external API calls | $0 (free tier) | AlphaVantage: 25 req/day free |
| Echo fallback calls | $0 | Internal, no rate limit |

**Recommendation**: Point traffic seeder at `echo-fallback` or `echo-oauth2`/`echo-bearer` for sustained load tests to avoid exhausting external API quotas.

---

## 8. Post-Resolution Verification

After a test failure is fixed:

```bash
# Re-run suite
cd control-plane-api
pytest tests/test_seed_realdata_apis.py tests/test_seed_traffic_seeder_apis.py -v

# Confirm migrations apply cleanly in a dev DB
alembic upgrade 074_seed_realdata_apis
alembic upgrade 075_seed_traffic_seeder_apis

# Confirm internal catalog returns 12 APIs (requires running stack)
curl -s https://api.gostoa.dev/v1/internal/catalog/apis | jq '.total'
# Expected: 12
```

---

## 9. References

- [Migration 074](../../control-plane-api/alembic/versions/074_seed_realdata_apis.py) — realdata APIs seed
- [Migration 075](../../control-plane-api/alembic/versions/075_seed_traffic_seeder_apis.py) — traffic seeder APIs seed
- [Test 074](../../control-plane-api/tests/test_seed_realdata_apis.py) — unit tests
- [Test 075](../../control-plane-api/tests/test_seed_traffic_seeder_apis.py) — unit tests
- [Call Flow Dashboard](https://grafana.gostoa.dev/d/call-flow) — Grafana dashboard fed by seeded traffic
- [Uptime Kuma](https://status.gostoa.dev) — monitor status page
- Linear: CAB-1856 (realdata APIs), CAB-1869 (traffic seeder APIs), CAB-1861 (this runbook)

---

## Modification History

| Date | Author | Modification |
|------|--------|--------------|
| 2026-03-27 | @platform-team | Initial creation (CAB-1861) |
