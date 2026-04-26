# 02 — Write (non-destructive mutation)

**Cas d'usage** : un agent crée une ressource. L'opération mute l'état mais reste réversible (la ressource peut être supprimée a posteriori).

## Choix structurants

- `side_effects: "write"` — *parce que* l'opération crée un nouvel état persistant. À distinguer de `destructive` : un `write` peut être annulé par l'opération inverse, un `destructive` non.
- `safe_for_agents: true` — *parce que* la création de ressource ne porte pas de risque irréversible si elle est rate-limitée et auditée (ce que la classification `H` impose via `required_policies`).
- `requires_human_approval: false` — *parce que* l'opération est réversible et que demander une approbation humaine sur chaque création briserait l'autonomie utile de l'agent. L'approbation se traite au niveau de la classification (`VH`/`VVH`) si la ressource créée porte un risque métier.

## Pourquoi ces `examples[]`

- **Un seul exemple complet, avec `expected_output_contains`** — pour les `write`, un exemple précis est plus utile qu'un volume d'exemples partiels. L'agent voit le shape exact de l'input attendu et peut l'imiter.

## Anti-patterns évités

- Ne pas marquer un `write` réversible comme `destructive` — ça déclenche `requires_human_approval=true` (règle dure) et casse l'autonomie d'un agent qui pourrait gérer le cas seul.
- Ne pas omettre `additionalProperties: false` sur l'`input_schema` d'un write — sinon l'agent peut envoyer des champs hors-contrat qui passeront silencieusement.
- Ne pas confondre `safe_for_agents` avec "l'opération est sûre dans l'absolu". Le flag dit : *un agent autonome peut l'invoquer sans superviseur humain*. Une création de ressource sensible (paiement, contrat) devrait être `safe_for_agents: false` même si techniquement réversible.
