# Demo Plan B — Fallback Procedures

> Run `scripts/demo/demo-dry-run.sh` before the demo. If any segment fails, use this page.

## Fallback Table

| Component | Symptom | Fallback Action | Recovery Time |
|-----------|---------|-----------------|---------------|
| **Keycloak** | Login page timeout / 502 | Use pre-generated token stored in `.env.demo` | Immediate |
| **Keycloak** | "Invalid credentials" | Check username/password, try alternate persona | 30s |
| **Portal** | White page / 502 | Show pre-captured screenshots in slide deck | Immediate |
| **Portal** | Loads but empty catalog | Run `make seed-demo` or use screenshots | 2 min |
| **Console** | White page / 502 | Show pre-captured screenshots in slide deck | Immediate |
| **Console** | Dashboard loads but no data | Acknowledge: "demo environment being refreshed" | N/A |
| **API** | `/health/ready` returns 503 | Check pod status, restart if needed | 2 min |
| **API** | Subscribe returns 409 | "Already subscribed — that's idempotent, by design" | N/A |
| **API** | Subscribe returns 500 | Skip subscription, show existing subscriptions | Immediate |
| **MCP Gateway** | `/health` returns 503 | Skip gateway segment, explain architecture verbally | N/A |
| **MCP Gateway** | Tool call returns CB open | "Circuit breaker protecting the system — show monitoring" | 30s |
| **OpenSearch** | Dashboards inaccessible | Skip error snapshot segment, show screenshots | Immediate |
| **Network** | WiFi down | Switch to mobile hotspot | 1 min |
| **Network** | VPN blocking access | Disconnect VPN, retry | 30s |
| **All services** | Everything down | Play backup video (offline) | Immediate |

## Pre-Generated Fallback Assets

Prepare these **before** the demo:

| Asset | Location | How to Create |
|-------|----------|---------------|
| Auth token | `.env.demo` (gitignored) | Run token fetch, save `ACCESS_TOKEN=<value>` |
| Portal screenshots | `slides/backup/portal-*.png` | Capture each demo step as PNG |
| Console screenshots | `slides/backup/console-*.png` | Capture dashboard + applications page |
| OpenSearch screenshots | `slides/backup/opensearch-*.png` | Capture error correlation dashboard |
| Backup video | `slides/backup/demo-recording.mp4` | Screen-record a full successful run |
| Slide deck PDF | `slides/backup/deck.pdf` | Export as PDF in case presentation software fails |

## Segment-Specific Fallback Scripts

### If Keycloak is down — use cached token

```bash
# Pre-generated token (generate fresh tokens before demo, save in .env.demo)
source .env.demo
echo "Using cached token: ${ACCESS_TOKEN:0:20}..."

# Test with cached token
curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
  "${API_URL}/v1/portal/apis" | python3 -m json.tool | head -5
```

### If API subscription fails — show existing

```bash
# List existing subscriptions (works even if creation is broken)
curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
  "${API_URL}/v1/portal/subscriptions" | python3 -m json.tool
```

### If MCP Gateway is down — curl mock

```bash
# Demonstrate the MCP protocol format with httpbin
curl -s -X POST https://httpbin.org/anything \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"get-weather","arguments":{"city":"Paris"}},"id":1}' \
  | python3 -m json.tool
```

### If OpenSearch is down — skip segment

Say: "We also have full distributed tracing and error correlation through OpenSearch. I'll share the dashboard link after the session."

## Escalation Contacts

| Role | Responsibility | When to Contact |
|------|---------------|-----------------|
| Platform Engineer | Infrastructure, pods, deployments | Service down > 2 min |
| Backend Developer | API bugs, 500 errors | API returns unexpected errors |
| DevOps On-Call | Network, DNS, certificates | Connectivity issues |
| Demo Coordinator | Schedule, audience management | Need to delay start |

> **Note**: Keep contact details in a private channel (Slack DM or phone). Do not share in public documents.

## Decision Tree

```
Demo starts
  │
  ├── All checks pass? ──YES──▶ Run demo as planned
  │
  └── NO
      │
      ├── 1-2 segments fail? ──▶ Skip failed segments, use screenshots
      │
      ├── Auth only fails? ──▶ Use cached token, continue
      │
      ├── Network issue? ──▶ Switch to hotspot, retry in 60s
      │
      └── Multiple services down? ──▶ Play backup video
```

## Post-Incident (if fallback was used)

1. Note which segment(s) failed and what fallback was used
2. Run `scripts/demo/demo-dry-run.sh` after the demo to capture current state
3. File a ticket for any bugs discovered during the demo
4. Update this document if a new failure mode was encountered
