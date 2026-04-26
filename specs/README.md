# `specs/` — Index technique

Ce dossier contient les **spécifications structurantes** du projet STOA :
contrats produit (UAC), périmètre démo, règles d'architecture, garde-fous
de rewrite, et contrats inter-composants.

> Audience : développeurs internes STOA.
> Pour la vitrine produit (pitch, quickstart, architecture publique),
> voir le [`README.md`](../README.md) à la racine du repo.
> Pour la documentation utilisateur, voir [docs.gostoa.dev](https://docs.gostoa.dev).

## Inventaire

| Fichier | Rôle | Statut |
|---|---|---|
| [`uac/`](./uac/) | Contrat produit canonique (UAC v1) — schémas, doctrine, exemples | Référence |
| [`demo-scope.md`](./demo-scope.md) | Périmètre minimal exécutable de la démo (5 étapes non négociables) | Figé |
| [`client-prospect-demo-scope.md`](./client-prospect-demo-scope.md) | Parcours commercial client/prospect | Figé |
| [`demo-acceptance-tests.md`](./demo-acceptance-tests.md) | Tests d'acceptation de la démo | Figé |
| [`demo-readiness-report.md`](./demo-readiness-report.md) | Rapport de readiness démo | Suivi |
| [`api-runtime-reconciliation-contract.md`](./api-runtime-reconciliation-contract.md) | Contrat de réconciliation runtime (Console `/api-deployments`) | Référence |
| [`gateway-topology-normalization.md`](./gateway-topology-normalization.md) | Normalisation de la topologie gateway | Référence |
| [`gateway-sidecar-contract.md`](./gateway-sidecar-contract.md) | Contrat sidecar gateway | Référence |
| [`architecture-rules.md`](./architecture-rules.md) | Règles d'architecture transverses | Référence |
| [`rewrite-guardrails.md`](./rewrite-guardrails.md) | Garde-fous applicables pendant le rewrite | Actif |
| [`validation-commands.md`](./validation-commands.md) | Commandes de validation locales/CI | Référence |

## Conventions

- **Une spec = un sujet**. Pas de spec "fourre-tout".
- **Statuts** : *Figé* (ne change pas sans décision écrite), *Actif* (vivant, suivi en cycle), *Référence* (mis à jour à la demande), *Suivi* (rapport périodique).
- **Toute spec démo renvoie à `demo-scope.md`** comme source de vérité.
- **Les ADR vivent dans `stoa-docs`** (pas ici). Cf. [stoa-docs/docs/architecture/adr/](https://github.com/stoa-platform/stoa-docs/tree/main/docs/architecture/adr).
