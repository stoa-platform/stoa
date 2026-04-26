# 03 — Destructive

**Cas d'usage** : un agent doit supprimer une ressource. Opération irréversible, soumise à approbation humaine obligatoire.

## Choix structurants

- `side_effects: "destructive"` — *parce que* la suppression est définitive et ne peut pas être annulée par une opération inverse de l'API. Le validator UAC enforce la règle dure : `destructive` ⇒ `requires_human_approval: true`.
- `safe_for_agents: false` — *parce que* même avec approbation humaine, le flag signale au runtime MCP que l'agent ne doit pas chaîner cet appel dans une boucle autonome. L'approbation reste une étape explicite pilotée par un humain.
- `requires_human_approval: true` — *forcé par le validator*. Toute tentative de mettre `false` ici déclenche une erreur de validation, pas un warning.
- `classification: "VH"` — *parce que* la sensibilité d'une suppression justifie `mtls` + `audit-logging` en plus de `rate-limit` + `auth-jwt`. La classification doit suivre la criticité métier, pas seulement le verbe HTTP.

## Pourquoi ces `examples[]`

- **Un seul exemple, avec sortie booléenne explicite** — sur un `destructive`, on veut documenter le contrat de retour minimal (`deleted: true`) pour que l'agent puisse vérifier que l'opération a bien abouti avant de notifier l'utilisateur.

## Anti-patterns évités

- Ne pas tenter de contourner la règle dure en passant `requires_human_approval: false` sur un `destructive`. Le validator rejette le contrat à la publication.
- Ne pas requalifier en `write` ce qui est réellement `destructive` pour éviter l'approbation humaine — c'est une violation de doctrine et le code en aval (UI, audit) compte sur la sémantique correcte.
- Ne pas baisser la classification (`H` au lieu de `VH`) pour réduire la liste de policies. La classification reflète le risque ICT, pas l'effort opérationnel.
