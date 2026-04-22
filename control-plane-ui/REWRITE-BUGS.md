# UI-1 Rewrite — Backend gaps découverts

> Issues dans le contrat OpenAPI (`control-plane-api/openapi-snapshot.json`)
> trouvées pendant le rewrite des types UI. **Hors périmètre rewrite — à
> remonter à l'équipe backend (control-plane-api).**

---

## BUG-1 — `ApplicationResponse` absent du schema

**Sévérité**: HIGH (bloque migration `Application` côté UI sans contournement).

**Constat**:
Aucun schéma `ApplicationResponse` n'est exposé dans `components.schemas`. On
trouve seulement:
- `ApplicationCreate`
- `ApplicationCreateRequest`
- `ApplicationUpdateRequest`
- `ApplicationCredentials`
- `ApplicationDiffResponse`
- `ApplicationsListResponse`

Mais pas l'entité-réponse de `GET /v1/admin/applications/{id}`.

**Hypothèse**: le response model FastAPI utilise un schema inline ou un
`response_model=Application` non sérialisable, donc openapi-typescript ne
l'extrait pas comme `components.schemas` réutilisable.

**Impact UI**:
L'UI consomme ~15 fois `Application` (pages/Applications, services/api,
tests). Sans `ApplicationResponse` extrait, on doit:
1. Soit traverser `ApplicationsListResponse['items'][number]` (extraction
   indirecte fragile),
2. Soit garder `Application` UI manuellement jusqu'à correction backend.

**Action proposée backend**:
```python
# Annoter le response_model comme schema partagé
@router.get('/applications/{id}', response_model=ApplicationResponse)
```
et s'assurer que `ApplicationResponse` est `BaseModel` exporté, pas inline.

**Workaround UI Phase 2**:
```ts
type ApplicationWire = NonNullable<
  Schemas['ApplicationsListResponse']['items']
>[number];
```
À tester en Phase 2 ; fallback `src/types/index.ts` si `items` est trop pauvre.

---

## BUG-2 — `GatewayInstanceResponse` champs manquants

**Sévérité**: MEDIUM.

**Constat**: par rapport à ce que l'UI consomme aujourd'hui, le contrat omet:
- `enabled: boolean` (toggle admin)
- `source: 'argocd' | 'self_register' | 'manual'`
- `visibility: { tenant_ids: string[] } | null`
- `protected: boolean` (déjà présent côté backend mais non documenté?)
- `deleted_by: string | null`
- `target_gateway_url: string | null` (présent dans réponse, à vérifier)

Et les champs unionisés sont en `string` brut:
- `gateway_type: string` au lieu d'union (`webmethods | kong | apigee | ...`)
- `mode: string | null` au lieu d'union (`edge-mcp | sidecar | proxy | shadow | connect`)
- `status: string` au lieu d'union (`online | offline | degraded | maintenance`)

**Hypothèse**: Pydantic `extra='allow'` côté backend accepte ces champs
sans les documenter, et les enums Python ne sont pas marqués comme
`Literal[...]`.

**Workaround UI Phase 2**: pattern wire/UI séparé.
```ts
type GatewayInstanceWire = Schemas['GatewayInstanceResponse'];
type GatewayInstanceUI = Omit<
  GatewayInstanceWire,
  'gateway_type' | 'mode' | 'status'
> & {
  gateway_type: GatewayType;
  mode?: GatewayMode;
  status: GatewayInstanceStatus;
  enabled: boolean;
  source?: 'argocd' | 'self_register' | 'manual';
  visibility?: { tenant_ids: string[] } | null;
};
```

**Action proposée backend**: annoter les champs avec `Literal[...]` + déclarer
les optional fields manquants dans `GatewayInstanceResponse`.

---

## BUG-3 — `operationId` dupliqués dans le snapshot OpenAPI

**Sévérité**: HIGH (force `// @ts-nocheck` sur `generated.ts` jusqu'à fix).

**Constat**: `interface operations { ... }` produit par `openapi-typescript`
contient ≥ 11 identifiers dupliqués. tsc remonte TS2300 + TS2717 :

- `list_applications` × 2 (tenant-scoped + admin cross-tenant)
- `create_application` × 2
- `get_application` × 2
- `update_application` × 2
- `delete_application` × 2
- `regenerate_secret` × 2
- `list_bindings` × 2 (policy_id vs contract_id paths)
- `list_deployments` × 2
- `get_deployment` × 2
- `create_budget` × 2

**Cause**: deux endpoints différents (admin global vs tenant-scoped, ou
policy-bindings vs contract-bindings) partagent le même `operationId`. Or
openapi-typescript fusionne tous les `operationId` dans une seule
interface globale.

**Impact UI**: empêche tout import direct de `generated.ts` sous
`tsconfig.app.json` strict. Workaround posé en Phase 2 :
- `// @ts-nocheck` au top de `shared/api-types/generated.ts`
- Header re-injecté automatiquement par le script `generate:api-types` (cf.
  patch `shared/package.json`).

**Action proposée backend**: dédupliquer les `operationId` Pydantic/FastAPI
en préfixant par scope. Ex.:
- `list_applications` (admin) → `admin_list_applications`
- `list_applications` (tenant) → `tenant_list_applications`
- `list_bindings` (policy) → `policy_list_bindings`
- `list_bindings` (contract) → `contract_list_bindings`

Une fois fix backend, on pourra retirer `// @ts-nocheck`. Ne PAS retirer
le marqueur tant que `cd shared && npm run generate:api-types && tsc`
n'est pas vert.

---

## BUG-4 — `APIResponse` champs manquants

**Sévérité**: MEDIUM.

**Constat**: `APIResponse` omet:
- `created_at: string`
- `updated_at: string`
- `openapi_spec?: string | Record<string, unknown>` (probablement endpoint séparé)
- `audience?: 'public' | 'internal' | 'partner'` (probablement pivot depuis `tags[]` côté UI)

Et `status: string` au lieu d'union (`draft | published | deprecated`).

**Action proposée backend**:
- Ajouter `created_at`/`updated_at` au response model (cohérent avec les
  autres `*Response`).
- Documenter explicitement si `openapi_spec` doit rester sur un endpoint séparé.
- Resserrer `status` en `Literal['draft', 'published', 'deprecated']`.

**Workaround UI Phase 2**: type `APIUI` étendu (cf. `src/types/index.ts`).

---

## BUG-5 — `RolePermission` non extrait

**Sévérité**: LOW.

**Constat**: `components.schemas.RolePermission` absent — probablement inline
dans `RoleResponse.permissions: Array<{ name: string; description: string }>`.

**Action proposée backend**: extraire `RolePermission` comme schema nommé.

**Workaround UI Phase 2**: garder `RolePermission` dans `src/types/index.ts`
comme PUREMENT UI tant que le schema n'est pas extrait.

---

## Sunset — quand supprimer ce fichier

Supprimer `REWRITE-BUGS.md` quand TOUTES les conditions sont remplies :

1. BUG-1, BUG-2, BUG-3, BUG-4, BUG-5 marqués **RÉSOLU** (snapshot regénéré
   sans erreurs, types Schemas alignés sur l'usage UI).
2. `// @ts-nocheck` retiré de `shared/api-types/generated.ts` et le drift
   gate CI passe sans le wrapper `inject-tsnocheck.mjs`.
3. `control-plane-ui/scripts/migrate-types.mjs` et `strip-migrated-types.mjs`
   eux-mêmes supprimés (UI-1-Wave2 fini).
4. Les view-models DRIFT dans `src/types/index.ts` (`API`, `Application`,
   `GatewayInstance`, `Consumer`) peuvent devenir des aliases purs `Schemas[X]`
   ou être supprimés au profit d'imports directs.

Si une partie seulement est résolue, marquer les BUG individuellement
**RÉSOLU** dans leur section et garder le fichier jusqu'à clôture complète.

## Convention pour ajouts

Quand un nouveau bug backend est trouvé pendant la migration :
1. Ajouter une section `## BUG-N — <titre>` dans ce fichier.
2. Préciser : sévérité, constat, hypothèse, action backend, workaround UI.
3. Lier le bug dans le commit message UI qui pose le workaround.
4. Si `// @ts-nocheck` doit être étendu/modifié, mentionner ici.

Si un bug est résolu côté backend :
1. Régénérer `shared/api-types/generated.ts`.
2. Retirer le workaround UI correspondant.
3. Marquer le bug **RÉSOLU** ici (ne pas supprimer la section, garder pour traçabilité).
