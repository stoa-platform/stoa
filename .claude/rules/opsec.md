---
description: Public/private repo security boundaries
globs: ".gitignore,**/*.env*,stoa-strategy/**"
---

# OpSec — Dual Repo Security

## Architecture

| Repo | Visibility | Content |
|------|-----------|---------|
| `stoa-platform/stoa` | Public | Code, tracked .claude/ rules/agents, sanitized plan.md, legal templates |
| `PotoMitan/stoa-strategy` | Private | Client data, pricing, legal drafts, demo scripts, sensitive prompts |

## Rules

### Never commit to public repo
- Real client names, contact names, company identifiers
- Pricing amounts, business model details, commission structures
- Internal execution strategy with client-specific details
- Sensitive AI Factory prompts (.claude/prompts/*.txt — blocked by .gitignore)
- Email drafts, MOU drafts, contract details

### Allowed in public repo
- Code, tests, CI/CD configuration
- .claude/rules/, .claude/agents/, .claude/skills/ (AI Factory config)
- .claude/prompts/*.md (tracked, non-sensitive ticket prompts)
- Legal templates with [PLACEHOLDER] fields
- Sanitized plan.md (execution structure only, no client details)
- memory.md (sprint status, no client names)

### Sensitive prompts
- `.claude/prompts/*.txt` = sensitive (blocked by .gitignore)
- `.claude/prompts/*.md` = tracked, safe (ticket-scoped prompts)
- New sensitive prompts go to `stoa-strategy/prompts/`

### Code names for public references
- Use "Client A", "Client B", "Partner A" in public docs
- Use "enterprise prospect", "European financial institution" generically
- Real identities only in `stoa-strategy/clients/mapping.md`

## Verification
Before any push to stoa, scan for:
```bash
git grep -i "khalil\|lvmh\|engie\|banque" -- ':!.gitignore'
git grep -P "€\d|EUR \d" -- ':!.gitignore' ':!legal/'
```
Both must return empty.
