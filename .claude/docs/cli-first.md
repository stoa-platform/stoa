<!-- Chargé à la demande par skills/commands. Jamais auto-chargé. -->

---
globs:
  - "control-plane-api/**"
  - "stoa-go/**"
  - "stoa-gateway/**"
  - "charts/**"
  - "cli/**"
---
# CLI-First Context Strategy

## Rule: Read CLI Reference Before Scanning src/

When you need to understand STOA's API surface (resources, endpoints, field schemas):

1. **First** — read `.claude/context/cli-reference.md` (~16KB, complete API surface)
2. **Then** — if you need implementation details not in the reference, read specific src/ files

The CLI reference contains:
- All stoactl commands with flags
- All 10 resource kinds with spec fields (from JSON Schemas)
- Endpoint map: stoactl command → CP API route
- Enums: gateway types, auth types, MCP categories

## When to Use stoactl vs Read src/

| Need | Use | NOT |
|------|-----|-----|
| Resource structure (fields, types) | CLI reference schemas | `src/schemas/*.py` |
| Available operations | CLI reference commands | `src/routers/*.py` |
| API endpoint paths | CLI reference endpoint map | `src/main.py` routes |
| Enum values | CLI reference enums | `src/models/*.py` |
| Implementation logic (business rules) | Read src/ | CLI reference |
| Database models (relationships, indexes) | Read src/ | CLI reference |
| Test patterns | Read tests/ | CLI reference |

## Regeneration

After adding new stoactl commands or Pydantic models:
```bash
scripts/generate-cli-context.sh
```

## Context Budget Impact

Without CLI-first: ~80% context used scanning src/ to understand API surface
With CLI-first: ~16KB reference replaces reading ~50+ src/ files (~200KB+ of context)
