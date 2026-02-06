# STOA Platform - Ready Player One Demo

> "Ready Player One" themed demo showcasing STOA's enterprise capabilities.

## Demo Tenants

| Tenant | Theme | Use Case | Key Features |
|--------|-------|----------|--------------|
| **high-five** | Fintech Startup | Crypto + Payments | Semantic caching, Rate limiting |
| **ioi** | Enterprise Legacy | Shadow Mode | API discovery, PII masking, Compliance |
| **oasis** | AI-First Company | AI/ML + DevOps | HuggingFace, GitHub, Token tracking |

## Quick Start

```bash
# Deploy all demo resources
kubectl apply -k deploy/demo-rpo/

# Verify deployment
kubectl get tools -A -l stoa.io/demo=true

# Check namespaces
kubectl get ns | grep tenant-
```

## Demo Scenarios

### Scenario 1: Legacy-to-MCP Bridge (5 min)
**Tenant**: IOI

1. Show STOA in **shadow mode** observing legacy ERP traffic
2. View captured traffic in dashboard
3. Generate **UAC draft** automatically
4. Promote to **edge-mcp** mode
5. Claude invokes the tool via MCP

### Scenario 2: Fintech Agent (7 min)
**Tenant**: HIGH-FIVE

Tools:
- `high-five:crypto-prices` → CoinGecko API
- `high-five:payment-charge` → Stripe Test
- `high-five:send-alert` → Webhooks

Demo flow:
1. Agent queries BTC/ETH prices (cache MISS)
2. Same query again (cache HIT - **semantic caching**)
3. Agent creates payment charge (audit trail)
4. Agent sends alert notification

### Scenario 3: Multi-Tenant Isolation (3 min)
**Tenants**: HIGH-FIVE vs IOI

1. Split-screen: 2 portals
2. Same API call → different rate limits
3. IOI hits rate limit → visible in real-time
4. Cross-tenant query fails (isolation proof)

### Scenario 4: DevOps Workflow (5 min)
**Tenant**: OASIS

Tools:
- `oasis:github-list-issues`
- `oasis:github-create-issue`
- `oasis:github-create-pr`
- `oasis:slack-notify`

Demo flow:
1. Claude lists issues from repo
2. Claude creates fix issue
3. Claude creates PR
4. Slack notification sent
5. Full audit trail visible

### Scenario 5: AI Pipeline Bridge (5 min)
**Tenant**: OASIS

Tools:
- `oasis:sentiment-analysis` → HuggingFace
- `oasis:text-classification`
- `oasis:summarize-text`

Demo flow:
1. Analyze sentiment of customer reviews
2. Classify support tickets
3. Summarize long document
4. Token budget tracking visible

### Scenario 6: Compliance & Audit (5 min)
**Tenant**: IOI

1. Show **PII masking** in CRM queries (email → `***@***.com`)
2. Export **audit trail** CSV
3. Demonstrate **tenant isolation**
4. Show **policy enforcement** (OPA)
5. Security events dashboard

## APIs Used

### Zero Auth (Quick Demo)
- **Open-Meteo**: Weather forecasts
- **CoinGecko**: Crypto prices
- **JSONPlaceholder**: CRUD testing
- **dummyjson.com**: User data (with PII - email, phone, password)

### API Key Required
- **GitHub REST API**: DevOps automation
- **HuggingFace Inference**: AI/ML models
- **Stripe Test Mode**: Payments

### Mock Endpoints
- **httpbin.org**: Generic request/response testing

## Configuration

### Environment Variables

```bash
# Optional: For real API calls
export GITHUB_TOKEN="ghp_..."
export HUGGINGFACE_API_KEY="hf_..."
export STRIPE_TEST_KEY="sk_test_..."
```

### UAC Files

The corresponding UAC configuration files are located at:

```
stoa-catalog/tenants/
├── high-five/uac.yaml
├── ioi/uac.yaml
└── oasis/uac.yaml
```

## Demo Checklist

- [ ] All tenants visible in Console
- [ ] APIs accessible (no rate limit exceeded)
- [ ] Semantic cache warm (10+ entries)
- [ ] Grafana dashboards showing data
- [ ] Claude can invoke MCP tools
- [ ] Reset script tested

## Troubleshooting

### Tools not appearing
```bash
kubectl get tools -n tenant-high-five
kubectl describe tool crypto-prices -n tenant-high-five
```

### Rate limiting issues
```bash
# Check CoinGecko limits (30 req/min free tier)
curl -s https://api.coingecko.com/api/v3/ping
```

### MCP Gateway not responding
```bash
kubectl logs -n stoa-system deploy/mcp-gateway -f
```

## Reset Demo

```bash
# Delete all demo resources
kubectl delete -k deploy/demo-rpo/

# Re-deploy fresh
kubectl apply -k deploy/demo-rpo/

# Seed demo data
python scripts/demo/seed-rpo-demo.py
```
