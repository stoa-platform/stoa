# 01 — Read-only

**Cas d'usage** : un agent doit lire l'état d'une ressource connue. GET idempotent, sans mutation.

## Choix structurants

- `side_effects: "read"` — *parce que* l'opération lit un état existant. `none` est réservé aux endpoints qui ne touchent pas l'API métier (ex: health, version) ; `read` documente une lecture métier observable.
- `safe_for_agents: true` — *parce que* l'opération est idempotente et ne consomme pas de quota destructif. Un agent peut la rejouer sans risque.
- `requires_human_approval: false` — *parce que* lire un catalogue ne porte aucun risque irréversible. Demander une approbation humaine sur une lecture est un anti-pattern (friction sans bénéfice).

## Pourquoi ces `examples[]`

- **`{ item_id: "sku-1234" }`** — happy path, avec `expected_output_contains` qui ancre la forme minimale de la réponse.
- **`{ item_id: "missing" }`** — cas limite (ressource absente). Pas d'`expected_output_contains` : on documente que l'agent doit gérer une 404 sans inférer le payload.

## Anti-patterns évités

- Ne pas mettre `safe_for_agents: false` "par prudence" sur un GET pur — ça signale à tort un danger et empêche l'usage légitime.
- Ne pas mettre `requires_human_approval: true` sur une lecture — ce flag existe pour les opérations destructives, pas pour gérer la confidentialité (qui se traite via classification + RBAC).
- Ne pas omettre `output_schema` : sans lui, l'agent ne peut pas valider la réponse et `examples[].expected_output_contains` perd son ancrage.
