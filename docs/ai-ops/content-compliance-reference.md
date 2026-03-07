# Content Compliance — Full Reference

> Extracted from `.claude/rules/content-compliance.md` (rules diet). Essential rules remain in the rule file.

## Disclaimer Templates

### Feature Comparison
```
> Feature comparisons are based on publicly available documentation as of
> [YYYY-MM]. Product capabilities change frequently. We encourage readers
> to verify current features directly with each vendor. All trademarks
> belong to their respective owners. See [trademarks](/legal/trademarks).
```

### Regulation
```
> STOA Platform provides technical capabilities that support regulatory
> compliance efforts. This does not constitute legal advice or a guarantee
> of compliance. Organizations should consult qualified legal counsel for
> compliance requirements.
```

### Migration Guide
```
> This guide describes technical migration steps and does not imply any
> deficiency in the source platform. Migration decisions depend on
> specific organizational requirements. All trademarks belong to their
> respective owners.
```

### Landing Page
```
> Product names and logos are trademarks of their respective owners. STOA
> Platform is not affiliated with or endorsed by any mentioned vendor.
> See [trademarks](/legal/trademarks) for details.
```

## "Last Verified" Policy

| Age | Status | Action |
|-----|--------|--------|
| < 6 months | OK | None |
| 6-12 months | P1 | Re-verify and update date |
| > 12 months | P0 | Remove or re-verify immediately |

Format: `<!-- last verified: YYYY-MM -->` in source, or inline `(last verified: YYYY-MM)`.

## Known Competitors

| Category | Products |
|----------|----------|
| API Gateway OSS | Kong, Tyk, Gravitee, Apache APISIX, KrakenD |
| API Gateway Enterprise | Apigee (Google), MuleSoft (Salesforce), webMethods (Software AG), IBM API Connect |
| API Gateway Cloud | AWS API Gateway, Azure APIM, GCP Apigee, Cloudflare API Shield |
| Integration/iPaaS | MuleSoft Anypoint, Boomi, Workato, Celigo |
| Legacy / On-Prem | Oracle API Gateway, Oracle OAM, IBM DataPower, Axway |
| MCP / AI Gateway | Anthropic MCP, OpenAI Plugins, LangChain, Portkey |

Any mention of these names in public content triggers the `content-reviewer` scan.

## P2 — Suggestions (non-blocking)

| Type | Examples | Risk |
|------|----------|------|
| Missing trademark attribution | "Kong" without (TM) | Trademark dilution |
| Missing trademarks.md link | Page without trademark reference | Best practice |
| Improvable wording | "better than" vs "alternative to" | Aggressive tone |
