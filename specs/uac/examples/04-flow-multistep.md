# 04 — Flow multi-step

**Cas d'usage** : un agent enchaîne plusieurs opérations cohérentes (ici : créer un brouillon → vérifier le statut → confirmer). Le flow est cadré par un seul contrat UAC qui en porte les trois endpoints.

## Choix structurants

- **Trois endpoints dans un même contrat** — *parce que* leur cycle de vie est lié (un draft expire, un draft confirmé devient billable). Splitter en trois contrats casse la traçabilité du flow et duplique `tenant_id` / `classification`.
- `intent` qui se référence l'autre — chaque `intent` cite explicitement le `tool_name` de l'étape suivante ou précédente. C'est ce qui transforme une liste d'endpoints en *flow* lisible pour un agent.
- `side_effects` mixtes (`write` / `read` / `write`) — *parce que* la sémantique de chaque étape est indépendante. Un agent qui n'a accès qu'à `read` peut quand même observer le statut sans pouvoir confirmer.
- Tous `safe_for_agents: true`, aucun `requires_human_approval` — *parce que* la confirmation est elle-même la décision explicite (l'agent doit la déclencher après vérification). L'approbation humaine est gérée par le métier au-dessus du contrat, pas par chaque endpoint.

## Pourquoi ces `examples[]`

- **Un exemple par endpoint, alignés sur le même `order_id` fictif (`ord-abc`)** — un agent qui lit le contrat reconstitue mentalement l'enchaînement. Si chaque exemple utilisait un id différent, le flow deviendrait illisible.
- `expected_output_contains.status` enforce la transition d'état attendue à chaque étape (`draft` → observable → `confirmed`).

## Anti-patterns évités

- Ne pas exposer un `tool_name` qui décrit l'objet (`order`) plutôt que l'action (`create_draft`, `get_status`, `confirm`). Les agents raisonnent en verbes.
- Ne pas mettre une logique de timeout (`expire after 15 minutes`) uniquement dans `intent` — c'est un rappel utile pour le LLM, mais la garantie technique vit dans le backend, pas dans le contrat.
- Ne pas chaîner trois contrats séparés "pour la propreté". Un flow cohérent = un contrat. Trois contrats = trois cycles de vie indépendants à orchestrer en aval.
