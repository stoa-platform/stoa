# STOA Demo — Catalog Release & Versioning Contract

> **Statut**: v0.1 — 2026-05-01. Contrat transverse pour versionner les
> desired states GitOps du `stoa-catalog`.
> **ADRs sources**: ADR-040 (Born GitOps multi-environment), ADR-059
> (Promotion Deploy Chain), ADR-067 (`UAC describes. MCP projects. Smoke
> proves.`).

## 1. Pourquoi ce contrat

Un commit Git seul n'est pas un objet de release exploitable par la Console, les
gateways ou un opérateur. Il donne une preuve technique, mais pas de lifecycle:
pas de PR source, pas de statut de review/CI, pas de tag stable, pas de version
rollbackable, et pas de lien clair entre un desired state Git et les
`GatewayDeployment` qui l'appliquent.

Ce contrat ajoute donc un niveau:

```text
UAC/API contract
→ Catalog PR
→ Catalog merge commit
→ Catalog release tag
→ CP materialized desired state
→ GatewayDeployment target generation
→ gateway ack
```

## 2. Sources de vérité

| Objet | Rôle | Source de vérité |
|-------|------|------------------|
| UAC/API contract | intention déclarative versionnée | fichier Git catalog |
| Pull request | gouvernance, review, CI | Git provider |
| Merge commit | état Git accepté | Git provider |
| Release tag | version stable rollbackable | Git provider |
| `api_catalog` | read model CP | projection du merge commit/tag |
| `GatewayDeployment` | vérité runtime | ack gateway pour une release donnée |

Invariants:
- `api_catalog.git_commit_sha` référence le merge commit ou le dernier commit
  catalog déjà accepté pour ce fichier.
- `api_catalog.catalog_release_tag` référence le tag Git qui versionne cette
  génération.
- `deployment_status=synced` ne prouve jamais la fraîcheur Git sans
  `desired_commit_sha` et `catalog_release_tag`.
- En production, un desired state sans PR/merge/tag est un raccourci non
  conforme ADR-040.

## 3. Modes de write catalog

| Mode | Usage | Comportement |
|------|-------|--------------|
| `direct` | compatibilité dev/demo legacy | commit direct sur la branche par défaut, sans release tag obligatoire |
| `pull_request` | mode canonique STOA | branche dédiée, commit, PR, merge, tag release, puis projection CP |

`direct` reste un mode de compatibilité. Tout environnement qui prétend être
GitOps complet doit utiliser `pull_request`.

Précondition opérationnelle: si la branche catalog cible impose checks/reviews,
le mode `pull_request` ne doit être activé en synchrone que si l'identité STOA a
un bypass explicite ou si le provider peut merger après checks/review sans
interaction humaine. Sinon, le chemin conforme est asynchrone: STOA crée la PR,
le webhook de merge déclenche la réconciliation, puis seulement la projection CP.

## 4. Format des branches et tags

Branches catalog:

```text
stoa/api/{tenant_id}/{api_id}/v{api_version}/{content_hash_12}
```

Tags catalog:

```text
stoa/api/{tenant_id}/{api_id}/v{api_version}/{merge_sha_12}
```

Le tag est annoté avec au minimum:

```text
tenant_id
api_id
api_version
git_path
catalog_content_hash
pull_request_url
merge_commit_sha
```

## 5. Contrat API/DB

`api_catalog` expose la release matérialisée:

| Champ | Description |
|-------|-------------|
| `catalog_release_id` | identifiant stable de génération |
| `catalog_release_tag` | tag Git release |
| `catalog_pr_url` | PR source |
| `catalog_pr_number` | numéro PR/MR provider |
| `catalog_source_branch` | branche temporaire source |
| `catalog_merge_commit_sha` | commit accepté/taggé |

La réponse Console/API doit pouvoir afficher ces champs en lecture seule.

## 6. Acceptance Criteria

| ID | Critère |
|----|---------|
| CRV-1 | En mode `pull_request`, une création API écrit sur une branche dédiée et ouvre une PR. |
| CRV-2 | Une création API `pull_request` ne projette `api_catalog` qu'après merge et tag release. |
| CRV-3 | `api_catalog` stocke `catalog_release_tag`, `catalog_pr_url`, `catalog_pr_number`, `catalog_source_branch`, `catalog_merge_commit_sha`. |
| CRV-4 | Un replay idempotent du même contenu ne crée pas une nouvelle release incompatible. |
| CRV-5 | La réponse API expose les métadonnées de release en lecture seule. |
| CRV-6 | Le mode `direct` reste compatible avec l'ancien comportement tant que l'env n'a pas basculé. |

## 7. Hors scope de cette tranche

- Attente asynchrone des checks CI catalog dans la requête HTTP.
- UI complète de rollback de release.
- Migration des updates/deletes API vers le même pipeline.
- Application rétroactive de tags à tout l'historique catalog.
