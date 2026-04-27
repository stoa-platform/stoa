# 02 — UAC et `compute_spec_hash` : emplacement et état

> Phase 1 audit, read-only. Réponses précises aux questions §2 du brief.

## 1. Où vit `compute_spec_hash` aujourd'hui ?

**Fonction privée**, pas exportée :
- `control-plane-api/src/services/uac_transformer.py:233-238`
  - Signature : `def _compute_spec_hash(openapi_spec: dict) -> str`
  - Le préfixe `_` indique une fonction module-private. Pas d'import dans le reste du codebase (vérifié : `grep -r "compute_spec_hash"` ne trouve que la définition elle-même + un appel local ligne 120).
- Le **nom canonique** attendu par la spec (§4.1, §6.2.1, §7) est `compute_spec_hash` (sans `_`). **Aucune fonction publique avec ce nom n'existe aujourd'hui dans le codebase.**

## 2. Comment est-elle calculée exactement ?

```python
# control-plane-api/src/services/uac_transformer.py:233-238
def _compute_spec_hash(openapi_spec: dict) -> str:
    """Compute SHA-256 hash of the spec for drift detection."""
    import json
    canonical = json.dumps(openapi_spec, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
```

Caractéristiques :
- **Entrée** : un `dict` représentant un **OpenAPI spec brut**, pas un `UACContract`. La fonction est appelée une seule fois (`uac_transformer.py:120`) avec l'OpenAPI source en entrée du transform OpenAPI → UAC.
- **Algorithme** : SHA-256 sur `json.dumps(spec, sort_keys=True, separators=(",", ":"))`.
- **Encodage** : UTF-8 implicite (`"".encode()` = UTF-8).
- **Tronquée à 16 hex chars** (`[:16]`) — pas 64.
- **Aucune exclusion** du champ `spec_hash` lui-même, parce qu'elle opère sur l'OpenAPI brut (qui ne contient pas ce champ).

Divergences avec ce que la spec §6.2.1 demande :
- La spec veut `spec_hash = sha256_hex(canonical_json(contract MINUS field "spec_hash"))` → **non implémenté**.
- La spec veut le hash sur `UACContract`, **pas sur OpenAPI** → mauvais type d'entrée.
- La spec veut 64 hex chars → la fonction tronque à 16. Confirmation in-tree : le JSON Schema dit `"first 16 hex chars"` (`control-plane-api/src/schemas/uac_contract_v1_schema.json:63`). Mais `specs/uac/demo-httpbin.uac.json:43` porte un hash de **64 chars** (`515839b4b1e23631e9699a9608e8e0f54e01f14572a513c8f514f6ee55da7e39`). Le contrat canonique et l'algorithme actuel sont déjà **incohérents entre eux**.
- Pas de gestion explicite des floats RFC 8785 — `json.dumps` Python par défaut suffit pour l'instant car aucun champ UAC n'est float, mais ça reste implicite.

## 3. Existe-t-il une parité Rust ?

**Non.** Le côté Rust ne contient pas de fonction `compute_spec_hash`.
- Recherche : `grep -rn "compute_spec_hash\|fn.*spec_hash\|sha256.*canonical" stoa-gateway/src/` → 0 résultat fonction.
- `stoa-gateway/src/uac/schema.rs:169` déclare juste `pub spec_hash: Option<String>` (champ traversé, pas calculé).
- `stoa-gateway/src/uac/binders/rest.rs:56-57, 293` lit/copie le champ tel qu'il vient du JSON.

Conséquence : la parité Python/Rust n'existe pas aujourd'hui. La Phase 4 devra créer la fonction Python canonique **et** son équivalent Rust en même temps si la spec §3 (parité enforced) doit tenir.

## 4. La fonction est-elle déjà appelée par le code de création d'API actuel ?

**Non.** L'unique appel à `_compute_spec_hash` est à `services/uac_transformer.py:120`, dans `transform_openapi_to_uac()` qui est utilisée pour migrer un OpenAPI vers un UAC (chemin import/conversion). Le handler `POST /v1/tenants/{tid}/apis` (`routers/apis.py:235`) **n'appelle ni `_compute_spec_hash`, ni `transform_openapi_to_uac`, ni aucune fonction UAC** — il écrit directement dans `api_catalog` avec un `api_metadata` JSONB ad-hoc (cf. `01-call-graph.md` §5).

Donc :
- `apis.spec_hash` (que la spec §6.6 veut introduire en colonne) n'a aujourd'hui **aucune source de vérité** côté handler.
- Aucun consommateur in-tree de `_compute_spec_hash` dans le chemin AT-1.

Note : `services/gateway_deployment_service.py:63` et `auth/sender_constrained.py:327` ont leur propre `sha256(json.dumps(..., sort_keys=True))` ad-hoc, pour usages distincts (deployment + DPoP). Ce ne sont pas des candidats à réutiliser.

## 5. `demo-httpbin.uac.json` est-il généré par cet outil ou écrit à la main ?

**Écrit à la main.** Indices convergents :
- Le hash est 64 chars (`specs/uac/demo-httpbin.uac.json:43`) ; la fonction `_compute_spec_hash` produit 16 chars. Donc le fichier n'a pas été produit par cette fonction.
- Le commentaire `specs/uac/README.md:71` annonce un futur dossier `examples/` (PR à venir) — l'écosystème de génération n'est pas en place.
- Le fichier est référencé par `architecture-rules.md:69` (`DEMO_UAC_CONTRACT=specs/uac/demo-httpbin.uac.json`) comme **une fixture exécutée par le smoke**, pas comme un artefact généré.
- Recherche d'un script générateur : aucun outil dans `control-plane-api/`, `cli/`, `stoa-go/`, `scripts/` ne produit de `*.uac.json`. `stoa-catalog/scripts/validate-uac.py` est un validateur, pas un générateur.

Conséquence : la valeur `spec_hash="515839b4b1..."` ne peut être ni vérifiée ni reproduite par le code actuel. **Non déterminé** par quel algorithme exact ce hash a été calculé — à clarifier avec Christophe avant Phase 3, sinon la première chose que `compute_spec_hash` Phase 4 fera ne matchera pas le contrat de référence.

## 6. Helper CLI existant qui produit un fichier UAC complet (Phase 4 §4.1) ?

**Aucun helper CLI in-tree ne produit un fichier `.uac.json` à la main.** Inventaire :

| Cible | Verdict | Détail |
|---|---|---|
| `python -m control_plane_api.services.uac.write_canonical_contract` | absent | le module `services/uac/` n'existe pas ; les fichiers UAC vivent à `services/uac_*.py` (sans sous-package). |
| `cli/` (Python Typer) | absent | aucune sous-commande `uac` qui écrit un fichier. |
| `stoa-go/cmd/stoactl` | absent | aucune commande `stoactl uac write` / `gen` (audité par recherche, voir `.claude/context/cli-reference.md` côté projet). |
| `stoa-catalog/scripts/validate-uac.py` | validateur uniquement | charge le JSON Schema et valide ; ne génère rien. |
| `services/uac_transformer.py:transform_openapi_to_uac` | partiel | construit un `UacContractSpec` à partir d'un OpenAPI dict (pas un payload AT-1) et calcule `spec_hash` tronqué à 16. Pas un helper CLI ; pas le chemin Phase 4 §6.13 (mapping payload→UAC). |
| `services/uac_validator.py` | validateur sémantique | charge le JSON Schema et vérifie les invariants (notamment ADR-067 destructive ⇒ approval). |
| `services/uac_tool_generator.py` | génère MCP tools, pas UAC | projection sortante, pas génération UAC entrante. |

Conséquence : Phase 4 doit créer **deux pièces neuves** :
1. Le module Python `control_plane_api/services/uac/write_canonical_contract.py` (chemin nommé dans la spec §7 ligne 716, à ce jour inexistant).
2. Un `compute_spec_hash` public, partagé par writer + worker + helper CLI, et son pendant Rust.

Le `mapping payload HTTP → UACContract` (§6.13) n'a pas non plus de helper aujourd'hui : le handler `apis.py` ne convertit jamais le payload AT-1 vers un `UacContractSpec`.

## 7. Synthèse pour Phase 3-4

- `compute_spec_hash` doit être réécrit comme fonction publique, prendre un `UacContractSpec`, exclure le champ `spec_hash`, retourner 64 chars, et avoir un test de parité Rust.
- La valeur 64-chars hardcodée dans `specs/uac/demo-httpbin.uac.json` doit être recalculée et committée par le helper Phase 4, ou validée par un test cross-check au moment où l'algorithme canonique est figé.
- Le JSON Schema `uac_contract_v1_schema.json:63` ("first 16 hex chars") est en désaccord avec la spec §6.2.1 et avec le contrat canonique. À aligner — c'est un correctif de Phase 3 ou plus tard, mais à signaler comme dette quoi qu'il arrive.
