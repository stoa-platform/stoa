---
globs:
  - "docs/**"
  - "blog/**"
---

# Documentation URL Convention

## 3 Zones

| Zone | Pattern | Example | When |
|------|---------|---------|------|
| **Marketing/CTA** | Real URL | `console.gostoa.dev/signup` | Landing pages, blog CTAs, "Try STOA" links |
| **Code blocks** (bash, curl, Python, TS) | Shell variable `${STOA_*_URL}` | `${STOA_API_URL}/v1/portal/apis` | Any executable example |
| **YAML/Helm config** | Angle bracket `<YOUR_DOMAIN>` | `api.<YOUR_DOMAIN>` | Config files, env var defaults, Helm values |

## Standard Variables

```
STOA_API_URL     = https://api.<YOUR_DOMAIN>     # Control Plane API
STOA_AUTH_URL    = https://auth.<YOUR_DOMAIN>     # Keycloak
STOA_GATEWAY_URL = https://mcp.<YOUR_DOMAIN>     # MCP Gateway
STOA_PORTAL_URL  = https://portal.<YOUR_DOMAIN>  # Developer Portal
STOA_CONSOLE_URL = https://console.<YOUR_DOMAIN> # Console UI
```

## What to KEEP (real URLs)

- Marketing CTAs in blog posts (`console.gostoa.dev` "Try STOA" links)
- `docs.gostoa.dev` cross-links in blog posts
- CRD API groups (`gostoa.dev/v1alpha1` — not URLs)
- Canonical/SEO metadata (docusaurus.config.ts, robots.txt, llms.txt, JSON-LD)
- Blog `authors.yml` author URL
- Quick Start hosted service paths (MCP server URL, Portal link)
- QuickStartCode CTA button ("Try STOA Free")

## What to REPLACE

- Any `*.gostoa.dev` URL inside a code block (```bash, ```python, ```typescript, ```yaml)
- Curl commands with production endpoints
- Helm values with hardcoded domains
- Environment variable examples with production values
- Config file examples with production URLs

## Env Setup Admonition

Pages with curl examples should import the reusable admonition:

```mdx
import EnvSetup from '@site/docs/_partials/_env-setup.mdx';

<EnvSetup />
```

Or inline the tip block for pages that need custom variables.

## Verification

After editing docs, run:
```bash
cd stoa-docs && npm run build 2>&1 | grep -E "broken|error"
```

Grep check (should only find marketing/CTA URLs):
```bash
grep -rn 'api\.gostoa\.dev\|auth\.gostoa\.dev\|mcp\.gostoa\.dev' docs/ src/ --include='*.md' --include='*.mdx' --include='*.tsx'
```
