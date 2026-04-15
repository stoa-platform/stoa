<!-- Chargé à la demande par skills/commands. Jamais auto-chargé. -->

---
globs: "blog/**,docs/**"
---

# Content Compliance

## P0 — Forbidden (never acceptable)

- Competitor pricing ("Kong costs $X", "$50K/year")
- Client names without written authorization
- Certification claims ("STOA is DORA-compliant", "certified ISO 27001")
- Defamatory statements about competitors
- Competitor UI screenshots or internal docs
- Financial health statements about competitors

## P1 — Fix Before Publishing

- Feature comparisons without source + date (`last verified: YYYY-MM`)
- Negative category characterizations ("legacy gateways")
- Missing disclaimer on comparison pages
- `last verified` date > 6 months old
- Regulatory claims without nuance (use "supports", not "enables/guarantees")

## Allowed with Conditions

- **Comparisons**: public source + `last verified: YYYY-MM` + disclaimer. No "better/superior/best"
- **Regulatory**: "supports compliance with" (not "is compliant"). Add "not legal advice" disclaimer
- **Migration**: "migrate from [product]" (not "escape from", "replace your expensive")
- **Positioning**: "alternative to" (not "replacement for", "better than")

## Quick Checklist

1. Competitor by name? → source + date + disclaimer
2. Client name? → remove unless written authorization
3. Price? → remove (even if public)
4. "Compliant/certified"? → "supports compliance"
5. "Legacy/outdated/expensive"? → neutral wording
6. Disclaimer present? → add template

## Reference

Full details (disclaimer templates, competitor list, last-verified policy):
→ `docs/ai-ops/content-compliance-reference.md`
