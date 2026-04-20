# Baseline live prod — 2026-04-20

T0: 2026-04-20T09:01:42Z
T-baseline-end: see timestamp-baseline-end.txt

## API endpoints (curl)

| Endpoint | Status | Note |
|----------|--------|------|
| `https://mcp.gostoa.dev/health` | 200 | OK |
| `https://api.gostoa.dev/health` | 200 | OK |
| `https://console.gostoa.dev` | 200 (redirect /login) | OK |
| `https://portal.gostoa.dev` | 200 (redirect KC SSO) | OK |
| `https://auth.gostoa.dev/realms/stoa/.well-known/openid-configuration` | 200 | OK |
| `https://grafana.gostoa.dev/api/health` | DNS NXDOMAIN | **SCRIPT BUG** — pas un fail prod, scripts pointent mauvais host |
| `https://opensearch.gostoa.dev` | 503 | **CAB-2119 ouvert, prod réel** |
| `https://mcp.gostoa.dev/mcp/v1/tools` (anon REST) | 401 | **CAB-2121 effect** — gate fermé, intentionnel post-PR #2433 |
| `https://mcp.gostoa.dev/mcp/tools/list` (anon JSON-RPC) | 401 | Idem |
| `POST /mcp/sse initialize` (anon) | 200 (Server: STOA Gateway 0.9.10) | OK — handshake claude.ai possible |
| `POST /mcp/sse tools/list` (anon) | 401 | CAB-2121 effect |

## UI checks (Playwright)

| URL | Verdict |
|-----|---------|
| https://console.gostoa.dev | ✅ login page render, "Login with Keycloak" button visible |
| https://portal.gostoa.dev | ✅ redirect KC SSO (PKCE flow, client_id=stoa-portal) |
| https://console.gostoa.dev/grafana | ✅ Grafana dashboards page render, 0 console errors, OIDC SSO transparent |

## Diagnostic

**Prod = sain pour démo via OAuth flow (claude.ai connector).**

3 problèmes différents :
1. **DNS Grafana** : `grafana.gostoa.dev` n'existe pas. Vrai Grafana = `console.gostoa.dev/grafana`. Scripts hardcoded sur mauvais host → faux WARN/FAIL.
2. **Discovery anon 401** : CAB-2121 (PR #2433, mergé hier ~05:33 UTC) a fermé `tools/list` du `public_methods`. **Régression intentionnelle**. Pour la démo claude.ai connector → OAuth → tools/list authentifié → fonctionne. Pour les scripts qui testent anon → faux FAIL.
3. **OpenSearch 503** : CAB-2119 réel, vrai prod issue. Acte 5 démo concerné.
