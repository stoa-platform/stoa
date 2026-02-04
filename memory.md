# STOA Memory

> Dernière MAJ: 2026-02-04 (Session 1)

## DONE
- CAB-1044: API Search HTTP 500 — Fixed (escape LIKE wildcards in portal search) — commit 2c5672d8
- CAB-1040: Gateway Routes HTTP 404 — Fixed (disable redirect_slashes to prevent 307 on /mcp) — commit 0c33e21d
- CAB-1042: Vault sealed — Fixed (VaultSealedException + _ensure_unsealed() in both vault clients) — commit 8bbf71b9
- CAB-1041: E2E BDD auth — Fixed (capture/restore sessionStorage for OIDC tokens) — commit 248f9d29

## IN PROGRESS
CAB-1052: Fix 4 bugs critiques (4/4 DONE)
- [x] CAB-1044: API Search — HTTP 500 (FIXED)
- [x] CAB-1040: Gateway Routes — HTTP 404 (FIXED)
- [x] CAB-1042: Vault sealed — credentials fail (FIXED)
- [x] CAB-1041: E2E BDD auth — tests fail (FIXED)

## NEXT
- CLI stoa complète (login, get apis, apply)
- E2E tests 100% pass (needs live environment)
- CAB-1060: Docs 20 pages (docs.gostoa.dev)
- CAB-1061: Demo script 5 min
- CAB-1062: Final polish + dry-runs
- CAB-1066: Landing gostoa.dev + Stripe

## BLOCKED
(rien)

## NOTES
- Demo: mardi 24 février 2026
- Présentation "ESB is Dead" même jour
- 2 design partners à closer
- Stack = Python (pas Node)
- Existing CLAUDE.md preserved (more comprehensive than bootstrap version)
- Branch: feat/claude-sprint-feb24
- CAB-1041 root cause: react-oidc-context uses sessionStorage, Playwright storageState() misses it
- CAB-1042 root cause: no sealed check before Vault operations, obscure hvac errors
- Pre-existing TS errors in e2e/steps/console.steps.ts (RegExp type mismatch) — not in scope
