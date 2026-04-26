# UAC — Universal API Contract

> **Audience** : développeurs STOA écrivant ou modifiant un contrat UAC.
> Pour le corpus pédagogique destiné aux agents/LLMs, voir [`examples/`](./examples/).

## Doctrine

Règle canonique (ADR-067) :

```
UAC describes.
MCP projects.
Smoke proves.
```

- **UAC est le contrat produit primaire.** Toute opération exposée à un agent
  doit être attachée à un contrat UAC ou à un flow contract.
- **Les MCP tools sont des projections** d'opérations UAC. Elles ne se déclarent
  pas indépendamment.
- **La metadata LLM est endpoint-level**, pas contract-level. Chaque endpoint
  exposé à un agent porte son propre bloc `endpoint.llm`.
- **Règle dure** : `side_effects = "destructive"` ⇒ `requires_human_approval = true`.
  Le validator rejette l'inverse.

## Schéma

| Source | Chemin |
|---|---|
| JSON Schema canonique | [`../../control-plane-api/src/schemas/uac_contract_v1_schema.json`](../../control-plane-api/src/schemas/uac_contract_v1_schema.json) |
| Pydantic (cp-api) | [`../../control-plane-api/src/schemas/uac.py`](../../control-plane-api/src/schemas/uac.py) |
| Rust (gateway, parité) | [`../../stoa-gateway/src/uac/schema.rs`](../../stoa-gateway/src/uac/schema.rs) |
| Validator sémantique | [`../../control-plane-api/src/services/uac_validator.py`](../../control-plane-api/src/services/uac_validator.py) |

La parité cross-langage est enforced par le JSON Schema. Toute évolution doit
toucher les trois représentations dans la même PR.

## Bloc `endpoint.llm` (V1)

Champs requis lorsque le bloc est présent :

| Champ | Type | Description |
|---|---|---|
| `summary` | string | Résumé court orienté humain. |
| `intent` | string | Quand un agent doit utiliser cet endpoint. |
| `tool_name` | string | Nom MCP stable, unique dans le contrat. |
| `side_effects` | enum | `none` \| `read` \| `write` \| `destructive`. |
| `safe_for_agents` | bool | Un agent autonome peut-il l'appeler ? |
| `requires_human_approval` | bool | Approbation humaine requise avant invocation. |
| `examples[]` | list (≥1) | Exemples `{ input, expected_output_contains? }`. |

### Statut V1 vs V2

- **V1 (actuel)** : metadata absente = *warning*. Metadata malformée = *erreur*.
- **V2 (cible)** : tout nouvel endpoint MCP-exposé doit être LLM-ready avant merge.
  Champs additionnels prévus (non normatifs aujourd'hui) : `do_not_use_when`,
  `permissions`, `rate_limit_policy`, `approval_policy`, `test_generation_hints`.

## Écrire un contrat

1. Partir d'un endpoint réel (path, méthode, backend).
2. Écrire `input_schema` / `output_schema` (JSON Schema strict, `additionalProperties: false` par défaut).
3. Si l'endpoint est destiné à un agent, ajouter le bloc `endpoint.llm` complet.
4. Choisir la classification (`H` / `VH` / `VVH`) en fonction du risque ICT (DORA).
5. Valider localement : le contrat doit charger sans erreur via le validator cp-api.

## Exemple minimal de référence

[`demo-httpbin.uac.json`](./demo-httpbin.uac.json) — contrat consommé par le
smoke démo (`scripts/demo-smoke-test.sh`).

> **Note** : ce contrat n'expose pas encore de bloc `endpoint.llm`. Il sert à
> prouver le chemin REST minimal. Les exemples LLM-ready vivront dans
> [`examples/`](./examples/) (PR suivante).

## Voir aussi

- [`specs/demo-scope.md`](../demo-scope.md) — où ce contrat est consommé.
- `.claude/docs/uac-llm-ready.md` — checklist détaillée et notes V2.
