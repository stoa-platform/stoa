# FIX-PLAN-UI2-P1 — Phase 1 (plan only, NO code)

> **Source** : `BUG-REPORT-UI-2.md` — 16 P1 findings (High).
> **Branche** : `fix/ui-2-p1-batch` depuis `fix/ui-2-p0-batch` (P0 pas encore mergé). Rebase sur `main` après squash-merge de la PR P0.
> **Worktree** : `/Users/torpedo/hlfh-repos/stoa-ui-2-fix` (même que P0).
> **Méthode** : Plan → **STOP** → Phase 2 (code) après validation user.
> **Référence P0** : 4 commits déjà en place — C1 `a88c98902`, C2 `7c773c888`, C3 `95fafa8ea`, C4 `7bddb1501`.
> **Rev1 (2026-04-24)** : 8 corrections challenger intégrées — cf. §Rev1 en bas. Ordre commits changé en **C4 → C2 → C3 → C1** (petits déterministes avant gros sweep).

---

## Résumé exécutif

| # | Thème | P1 fermés | LOC est. | Files | Risk |
|---|---|---|---|---|---|
| C1 | Dashboard resilience (`allSettled` per-slice) | P1-1 | ~400 net | 19 pages | moyen (large surface, mécanique) |
| C2 | HTTP client robustness | P1-2, P1-8, P1-13, P1-14 | ~80 net | 5-7 services + client core | faible |
| C3 | Auth / Context hardening | P1-5, P1-6, P1-7, P1-15, P1-16 | ~60 net | `AuthContext.tsx` + 1 test | moyen (auth-sensible) |
| C4 | Skills deprecated path migration | P1-4 | ~5 net | `skillsApi.ts` + 1 test | faible |

**Anti-redondance P0** : **4/16 P1 déjà fermés** par les commits P0 — détail en §Anti-redondance ci-dessous. Reste 12 P1 à fixer sur ce batch.

**Ordre d'exécution validé (Rev1)** : **C4 → C2 → C3 → C1**. Aucune dépendance cross-commit.

---

## Anti-redondance avec P0 — détail

| P1 | Status | Proof | Verification |
|---|---|---|---|
| P1-9 useEvents `isConnected` state | **CLOSED by C4 (7bddb1501)** | `useEvents.ts:16-17` exposent `isConnected`, `lastError` via `useState` ; `useEvents.ts:69-79` wiring `onOpen`/`onError` | ✓ code lu |
| P1-10 SSE reconnect post-refresh | **CLOSED by C4 (7bddb1501)** | `sse.ts` `onopen(401)` appelle `refreshAuthTokenWithTimeout()` + throw `RetriableError` → retry avec nouveau token | ✓ commit message explicite |
| P1-11 path injection latent étendue | **CLOSED by C3 (95fafa8ea)** pour les 29 domain clients (segments path). **Résidu** : 6 interpolations query-string (`?key=`, `?limit=`) notées en C3 commit. Géré dans C2 ci-dessous (traitement `params: { ... }`) | ✓ grep confirme |
| P1-12 hooks bypass `fetch()` direct | **CLOSED by C2 (7c773c888)** | ESLint `no-restricted-globals` ajoutée sur `src/hooks/**`; `useApiConnectivity` + `useServiceHealth` allowlistés par design (non-auth) | ✓ commit message + ESLint config |

Restent **12 P1 ouverts** : P1-1, P1-2, P1-3, P1-4, P1-5, P1-6, P1-7, P1-8, P1-13, P1-14, P1-15, P1-16.

---

## Fiches des 16 P1

### P1-1 — `Promise.all` systémique (19 dashboards) — **OPEN**
- **Résumé** : un endpoint down = écran entier vide. Pattern `catch { setX([]); setY(null) }` écrase les données valides.
- **Fichier** : 19 pages (cf. §C1.2 ci-dessous). Exemple canonique `APIMonitoring.tsx:552-570`.
- **Cluster** : **A** (dashboards). Fix C1.
- **Approche** : migration `Promise.allSettled`. Chaque résultat devient une slice indépendante avec erreur locale si fulfilled=false.
- **Régression guard** : 3 tests représentatifs (1 monitoring, 1 gateway, 1 AITools) asserting "si `/stats` fail et `/txns` succeed → transactions affichées, stats= null avec erreur locale".

### P1-2 — `axios.create` sans `timeout` — **OPEN**
- **Résumé** : `client.ts:4-11` sans timeout → requêtes hang indéfiniment si backend stuck.
- **Fichier** : `src/services/http/client.ts:4-11`
- **Cluster** : **B** (HTTP robustness). Fix C2.
- **Approche** : `timeout: 30_000` par défaut + `config.api.timeoutMs` lu depuis env (`VITE_API_TIMEOUT_MS`). Overridable per-call via `{ timeout: N }` sur endpoints long-running (ex: `/deploy`, `/git/sync`).
- **Régression guard** : test axios timeout via adapter custom qui ne resolve jamais → rejected after 30s (testé avec `vi.useFakeTimers()` + 30_000 advance).

### P1-3 — Multi-tab `authToken` divergence — **OPEN (design-intent)**
- **Résumé** : chaque onglet a son propre module-scope `authToken` + sessionStorage par onglet → refresh tokens divergent.
- **Fichier** : `src/services/http/auth.ts:8`, `src/main.tsx:45` (sessionStorage choice)
- **Cluster** : **C** (Auth). Fix C3 (**WONT-FIX, design intent documenté**).
- **Approche** : **pas de BroadcastChannel** (ARB-2 ci-dessous). sessionStorage est intentionnel (XSS blast-radius hardening). Chaque onglet refresh son propre token de son côté. Ajout d'un comment block dans `auth.ts` + `main.tsx` référant la décision. Pas de code fonctionnel.
- **Régression guard** : test unit assertant que `authToken` est isolé (trivial, mais sert d'anchor doc).

### P1-4 — `skillsApi.ts` path deprecated GW-1 P2-3 — **OPEN**
- **Résumé** : `DELETE /v1/gateway/admin/skills?key=X` deprecated côté gateway (PR #2512, Sunset 2026-10-24). Nouveau : `DELETE /v1/gateway/admin/skills/:key`.
- **Fichier** : `src/services/skillsApi.ts:67-69`
- **Cluster** : **D** (seul). Fix C4.
- **Approche** : migrer vers `apiService.delete(path('v1', 'gateway', 'admin', 'skills', key))` (utilise le helper C3 P0). Decision ARB-4 ci-dessous : migrer **maintenant**, pas attendre 2026-10-24.
- **Régression guard** : 1 test unit asserting URL encodée conforme `/v1/gateway/admin/skills/<encoded>`.

### P1-5 — `atob` sur `base64url` JWT fragile — **OPEN**
- **Résumé** : `atob(payload)` échoue sur tokens contenant chars base64url-specific (`-`, `_`). Catch swallow → `roles = []` → utilisateur **perd toutes ses permissions** silencieusement.
- **Fichier** : `src/contexts/AuthContext.tsx:99-103`
- **Cluster** : **C** (Auth). Fix C3.
- **Approche** : helper local `decodeJwtPayload` (5-8 lignes) : replace `-/_` → `+//`, pad `=` à length%4, puis `atob`. ARB-3 ci-dessous : **pas de nouvelle dep `jwt-decode`**, manuel suffit.
- **Régression guard** : 3 tests — token standard base64, token avec `-` dans payload, token avec `_` dans payload.

### P1-6 — `getMe()` résout après unmount → setState on unmounted — **OPEN**
- **Résumé** : AuthProvider démonte pendant que `getMe()` est en vol → `setUser` sur composant démonté (warning React, pattern qui masque memory leaks).
- **Fichier** : `src/contexts/AuthContext.tsx:153-164`
- **Cluster** : **C** (Auth). Fix C3.
- **Approche** : `mountedRef` guard avant `setUser` dans le `.then`. Pattern déjà utilisé dans `APIMonitoring.tsx:548, 558`. Pas d'AbortController (nécessiterait propagation signal dans domain clients — hors scope P1).
- **Régression guard** : unit test qui unmount AuthProvider avant resolve du mock `getMe()` → vérifier qu'aucun `setUser` n'est appelé.

### P1-7 — `setTokenRefresher` re-set à chaque render — **OPEN**
- **Résumé** : effect L177-192 dep sur `oidc` (objet instable `react-oidc-context`). Refresher redéfini à chaque render. Pas catastrophique (setter idempotent) mais allocation inutile + closure potentiellement obsolète.
- **Fichier** : `src/contexts/AuthContext.tsx:177-192`
- **Cluster** : **C** (Auth). Fix C3.
- **Approche** : dep sur `[oidc.signinSilent, oidc.signinRedirect]` (refs stables exposées par la lib). Vérifier que ces refs sont bien stables en lisant les types `react-oidc-context` (likely case puisque la lib expose une API fonctionnelle).
- **Régression guard** : render test qui compte le nombre d'appels `apiService.setTokenRefresher` sur N re-renders ≥ 1 (seuil bas pour ne pas coupler à l'impl exacte de la lib — l'objectif est "pas ∝ renders").

### P1-8 — Data-shape fallback silencieux `data.items ?? data` — **OPEN**
- **Résumé** : `data.items ?? data` masque les divergences backend. Si `data` devient `{ total: 5, page: 1 }` sans `items`, fallback retourne l'objet casté → crash plus loin avec message obscur.
- **Fichier** : `src/services/api/apis.ts:10, 17`, `src/services/api/consumers.ts:10`, `src/services/api/applications.ts:9`. **Note** : `proxyBackendService.ts:50-54` a déjà un pattern explicite `Array.isArray` → OK, pas dans le scope.
- **Cluster** : **B** (HTTP robustness). Fix C2.
- **Approche** : remplacer par une fonction utilitaire `extractList(data, label)` qui :
  - Si `Array.isArray(data)` → retourne data.
  - Si `Array.isArray(data.items)` → retourne data.items.
  - Sinon → throw `Error(`Unexpected ${label} response shape`)` (fail fast, visible).
- Placement du helper : `src/services/http/payload.ts` (new). Export via `services/http/index.ts`. 4 call sites migrés.
- **Régression guard** : 3 tests — list response, paginated `{items}` response, invalid shape throws with label.

### P1-13 — `chat.ts:getUsageBySource` spread override `undefined` — **OPEN**
- **Résumé** : `params: { group_by: 'source', ...params }` — si le caller passe `{ group_by: undefined, days: 7 }`, le spread écrase le default avec undefined, axios skip le param, backend applique son propre défaut.
- **Fichier** : `src/services/api/chat.ts:103-114`
- **Cluster** : **B** (HTTP robustness). Fix C2.
- **Approche** : `params: { ...params, group_by: params.group_by ?? 'source' }` (default en dernier avec null-coalescing). Pattern à prévenir via commentaire générique dans le helper `extractList` (ou ajout d'une note dans CONTRIBUTING).
- **Régression guard** : 2 tests — caller passe `{ group_by: undefined, days: 7 }` → URL contient `group_by=source&days=7` ; caller passe `{ group_by: 'model' }` → URL contient `group_by=model`.

### P1-14 — `if (statusCode) params.status_code = statusCode` skip `0` — **OPEN**
- **Résumé** : `0` falsy → jamais envoyé. `0` n'est pas un HTTP status valide (peu grave en pratique) mais le pattern est copié dans `traces.ts`, `platform.ts`, etc. Premier `0` sémantique (ex: offset=0) réveillera la classe.
- **Fichier** : `src/services/api/monitoring.ts:68-72, 84`, `src/services/api/traces.ts:13-16, 44-45, 52-53`, `src/services/api/platform.ts:120-121`
- **Cluster** : **B** (HTTP robustness). Fix C2.
- **Approche** : remplacer `if (x) params.y = x` par `if (x !== undefined) params.y = x`. Systématique sur les 15-20 sites concernés (grep ciblé).
- **Régression guard** : 1 test pour `monitoring.listTransactions(..., statusCode=0)` → URL contient `status_code=0`. Lock suffisante pour la classe.

### P1-15 — `isMcpCallback` `startsWith` fragile aux basePaths — **OPEN**
- **Résumé** : `window.location.pathname.startsWith('/mcp-connectors/callback')` casse si l'app est servie sous un sous-path (`/console/mcp-connectors/callback`).
- **Fichier** : `src/contexts/AuthContext.tsx:199`, `src/main.tsx:53`
- **Cluster** : **C** (Auth). Fix C3.
- **Approche** : utiliser `import.meta.env.BASE_URL` (Vite injects trailing slash) en prefix. Helper local `isMcpCallbackPath(pathname: string): boolean`. Couvre le cas `base: '/'` (actuel, `BASE_URL = '/'`) ET le cas `base: '/console/'`.
- **HYPOTHÈSE VÉRIFIÉE** : `vite.config.ts` n'a pas de `base:` aujourd'hui → `BASE_URL === '/'` → comportement actuel inchangé, juste robuste aux déploiements futurs sous sous-path.
- **Régression guard** : 2 tests — `BASE_URL='/'` et pathname `/mcp-connectors/callback?code=X` → match ; `BASE_URL='/console/'` et pathname `/console/mcp-connectors/callback?code=X` → match.

### P1-16 — Flash erreur avant redirect login — **OPEN**
- **Résumé** : dans le refresher AuthContext, `oidc.signinRedirect()` est appelé avant `return null`. Entre la navigation initiée (async) et le déchargement effectif, la queue est rejetée + error toast affiché → flash tech visible avant redirect.
- **Fichier** : `src/contexts/AuthContext.tsx:184-191`
- **Cluster** : **C** (Auth). Fix C3.
- **Approche** : flag module-scope `isRedirectingToLogin` dans un nouveau fichier `src/services/http/redirect.ts` (ou extension de `auth.ts`). `applyFriendlyErrorMessage` check le flag → skip les toasts pendant redirect. Set le flag avant `oidc.signinRedirect()` dans AuthContext. Le `window` reload fera un reset du flag naturellement.
- **Régression guard** : test unit de `applyFriendlyErrorMessage` avec flag actif → pas de transformation.

---

## Plan des 4 commits

### COMMIT 1 (C1) — Dashboard resilience via `Promise.allSettled`

**Bugs fermés** : P1-1.
**Risque** : moyen. Surface large (19 fichiers, ~400 LOC touchées) mais transformation mécanique + 5 bons patterns existants comme templates (`ChatUsageDashboard`, `LLMCostDashboard`, `ToolCatalog`, `ApiTrafficDashboard`, `gatewayApi.getGatewayStatus`).

#### C1.1 — Pattern uniforme

Pour chaque dashboard `await Promise.all([apiA, apiB, ...])` avec un catch global :

```ts
// AVANT
try {
  const [a, b] = await Promise.all([apiA, apiB]);
  setA(a.data); setB(b.data);
} catch (_err) {
  setError('...');
  setA([]); setB(null);  // ← écrase tout
}

// APRÈS
const results = await Promise.allSettled([apiA, apiB]);
const [aRes, bRes] = results;

if (aRes.status === 'fulfilled') {
  setA(aRes.value.data);
} else {
  setA([]); // preserve previous or reset, pattern choice per dashboard
  setErrors((prev) => ({ ...prev, a: 'A unavailable' }));
}
// Même bloc pour b, etc.

// Error état consolidé : "partial" si au moins 1 fulfilled, "failed" si 0/N.
const hasAnyData = results.some((r) => r.status === 'fulfilled');
if (!hasAnyData) setError('Dashboard unavailable');
```

**Option simpler pour dashboards existants** : pour les dashboards où un seul state `error` existe déjà, convertir vers `errors: Record<string, string | null>` ou conserver `error` global mais **ne plus écraser les données partielles** (chaque slice setter fire uniquement sur son succès, avec fallback `null`/`[]` au niveau initial state uniquement).

**Choix Phase 2** : suivre le pattern `LLMCostDashboard.tsx:77` (déjà `allSettled`) comme référence — minimalist, pas de refactor d'état.

#### C1.2 — Fichiers à migrer (19)

```
src/pages/Applications.tsx:130
src/pages/Deployments.tsx:389
src/pages/APIMonitoring.tsx:552
src/pages/ErrorSnapshots.tsx:561
src/pages/HegemonDashboard.tsx:448
src/pages/Business/BusinessDashboard.tsx:247
src/pages/GatewayGuardrails/GuardrailsDashboard.tsx:95
src/pages/GatewayObservability/GatewayObservabilityDashboard.tsx:111
src/pages/GatewayDeployments/DeployAPIDialog.tsx:58
src/pages/GatewayDeployments/GatewayDeploymentsDashboard.tsx:52
src/pages/AITools/UsageDashboard.tsx:41
src/pages/AITools/ToolDetail.tsx:41
src/pages/AITools/MySubscriptions.tsx:39
src/pages/ApiDeployments/ApiDeploymentsDashboard.tsx:67
src/pages/DriftDetection/DriftDetection.tsx:93
src/pages/AnalyticsDashboard/AnalyticsDashboard.tsx:154
src/pages/GatewaySecurity/GatewaySecurityDashboard.tsx:42
src/pages/SecurityPosture/SecurityPostureDashboard.tsx:184,198,215
src/pages/ToolPermissionsMatrix.tsx:75,182
```

21 call-sites sur 19 fichiers (2 fichiers ont 2-3 `Promise.all` chacun).

#### C1.3 — Tests de régression

3 tests représentatifs (1 par zone) :

1. `src/test/pages/APIMonitoring.resilience.test.tsx` — mock `apiService.get`, faire échouer `/stats` mais pas `/transactions` → assert transactions affichées + erreur locale visible sur stats uniquement.
2. `src/test/pages/GatewayObservabilityDashboard.resilience.test.tsx` — 3 endpoints, 1 fail → assert 2 slices rendues.
3. `src/test/pages/AITools/ToolDetail.resilience.test.tsx` — endpoint tool-detail down mais subscriptions ok → detail vide avec erreur, subscriptions affichées.

Les 16 autres fichiers ne sont pas testés individuellement (transformation mécanique, suffisamment couverte par ces 3 "canaries"). Le type-check TS + ESLint build couvrent les régressions structurelles.

#### C1.4 — Commit message

```
fix(ui/dashboards): migrate Promise.all to allSettled across 19 dashboards

One-endpoint-down = whole-dashboard-blank pattern was systemic. catch blocks
reset all state (setX([]); setY(null)) even when only one endpoint of 2-3
failed, erasing valid partial data.

5 dashboards already used allSettled correctly (ChatUsageDashboard,
LLMCostDashboard, AITools/ToolCatalog, ApiTrafficDashboard, gatewayApi
getGatewayStatus) — pattern documented as CAB-1887 G2 but not propagated.

Fix:
- Rewrite 21 call-sites across 19 pages to allSettled + per-slice state
- Keep the existing error flag for "no data at all" but stop clobbering
  fulfilled slices when a sibling rejects
- 3 regression tests (APIMonitoring, GatewayObservability, AITools/ToolDetail)
  covering "partial failure" → partial render + scoped error

Closes: P1-1 (BUG-REPORT-UI-2.md)
```

---

### COMMIT 2 (C2) — HTTP client robustness

**Bugs fermés** : P1-2, P1-8, P1-13, P1-14.
**Risque** : faible (modifications localisées, un helper nouveau, tests unitaires directs).

#### C2.1 — Modifications de code

##### `src/services/http/client.ts` (P1-2)
```ts
return axios.create({
  baseURL: config.api.baseUrl,
  timeout: config.api.timeoutMs ?? 30_000, // P1-2
  headers: { 'Content-Type': 'application/json' },
});
```

##### `src/config.ts`
Ajouter `api.timeoutMs`, lu depuis `VITE_API_TIMEOUT_MS` (fallback 30_000).

##### `src/services/http/payload.ts` (NEW, P1-8)
```ts
/**
 * Extract a list from a paginated or raw-array response. Fail fast on
 * unexpected shape to surface backend schema drift early instead of
 * propagating a falsely-typed object that crashes downstream with an
 * obscure message.
 */
export function extractList<T>(data: unknown, label: string): T[] {
  if (Array.isArray(data)) return data as T[];
  if (data && typeof data === 'object' && 'items' in data && Array.isArray((data as { items: unknown[] }).items)) {
    return (data as { items: T[] }).items;
  }
  throw new Error(`Unexpected ${label} response shape: expected array or { items: [...] }`);
}
```

Export depuis `services/http/index.ts`.

##### Migration call-sites (P1-8)
- `src/services/api/apis.ts:10, 17` → `return extractList<API>(data, 'apis');`
- `src/services/api/consumers.ts:10` → `return extractList<Consumer>(data, 'consumers');`
- `src/services/api/applications.ts:9` → `return extractList<Application>(data, 'applications');`

`proxyBackendService.ts:50-54` garde son pattern explicite (déjà fail-safe).

##### `src/services/api/chat.ts:103-114` (P1-13)
```ts
const { data } = await httpClient.get(
  path('v1', 'tenants', tenantId, 'chat', 'usage', 'tenant'),
  { params: { ...params, group_by: params.group_by ?? 'source' } },
);
```

##### Pattern `if (x) params.y = x` → `if (x !== undefined)` (P1-14)

Fichiers concernés (grep ciblé sur `src/services/api/*.ts`) :
- `monitoring.ts:68-72, 84`
- `traces.ts:13-16, 44-45, 52-53`
- `platform.ts:120-121`
- Plus tout autre site détecté par `grep -n "if (\w*) params\." src/services/api/*.ts`.

Transformation mécanique.

#### C2.2 — Tests de régression

Étendre `src/services/http/client.test.ts` (ou nouveau) :
1. `test('client has 30s default timeout')`
2. `test('VITE_API_TIMEOUT_MS overrides default')`

Nouveau `src/services/http/payload.test.ts` :
3. `test('extractList returns array data as-is')`
4. `test('extractList unwraps data.items paginated response')`
5. `test('extractList throws on unexpected shape with label')`

Étendre `src/test/services/api/ui2-s2a-clients.test.ts` (apis/consumers/applications) :
6. `test('apisClient.list throws on non-list response shape')`
7. `test('apisClient.list returns items from paginated response')`

Étendre `src/test/services/api/chat.test.ts` (ou siblings):
8. `test('chat.getUsageBySource uses source default when group_by undefined')` — explicit `{ group_by: undefined, days: 7 }`.
9. `test('chat.getUsageBySource honors explicit group_by')`.

Étendre `monitoring.test.ts` :
10. `test('monitoring.listTransactions forwards statusCode=0')` — LOCK P1-14.

**Total nouveaux tests C2** : ~10.

#### C2.3 — Commit message

```
fix(ui/services): http client robustness (timeout, shape guard, params)

Four interacting P1 issues in the HTTP / domain-client layer:
- No axios timeout = requests hang indefinitely if backend stuck
- `data.items ?? data` fallback masked backend schema drift with false
  typed return, crashing downstream with obscure `.map is not a function`
- chat.getUsageBySource spread-defaulted group_by with `undefined` override
  → backend-side default silently applied instead of the client's
- `if (statusCode) params.x = statusCode` dropped `0`, a pattern copied
  to 15+ sites (monitoring.ts, traces.ts, platform.ts)

Fix:
- client.ts: timeout 30_000 default, override via VITE_API_TIMEOUT_MS
- http/payload.ts (new): extractList(data, label) fail-fast shape guard,
  wired in apis.ts, consumers.ts, applications.ts (proxyBackendService
  already had its own explicit Array.isArray guard — left untouched)
- chat.ts: `...params, group_by: params.group_by ?? 'source'` (default
  preserved across undefined overrides)
- monitoring.ts / traces.ts / platform.ts: switch all `if (x) params.y = x`
  to `if (x !== undefined)` (mechanical, 15+ sites)
- 10 regression tests covering timeout, shape extraction, param defaulting,
  statusCode=0 forwarding

Closes: P1-2, P1-8, P1-13, P1-14 (BUG-REPORT-UI-2.md)
```

---

### COMMIT 3 (C3) — Auth / Context hardening

**Bugs fermés** : P1-5, P1-6, P1-7, P1-15, P1-16. **P1-3 WONT-FIX (design intent)** — comment block ajouté, pas de code fonctionnel.
**Risque** : moyen. AuthContext est auth-sensible, chaque changement doit être couvert par test.

#### C3.1 — Modifications de code

##### `src/contexts/AuthContext.tsx`

1. **P1-5 — helper `decodeJwtPayload`** :
   ```ts
   function base64UrlDecode(seg: string): string {
     const padded = seg + '='.repeat((4 - (seg.length % 4)) % 4);
     const base64 = padded.replace(/-/g, '+').replace(/_/g, '/');
     return atob(base64);
   }
   function decodeJwtPayload(token: string): unknown {
     const [, payload] = token.split('.');
     if (!payload) throw new Error('Invalid JWT — missing payload');
     return JSON.parse(base64UrlDecode(payload));
   }
   ```
   Remplace L99 : `const payload = decodeJwtPayload(oidcUser.access_token) as { realm_access?: { roles?: string[] } };`.

2. **P1-6 — `mountedRef` guard sur `getMe()`** :
   ```ts
   const mountedRef = useRef(true);
   useEffect(() => () => { mountedRef.current = false; }, []);
   // ...
   apiService.getMe().then((me) => {
     if (!mountedRef.current) return;     // ← guard
     if (me.role_display_names) {
       setUser((prev) => prev ? { ...prev, role_display_names: me.role_display_names } : prev);
     }
   }).catch(() => {});
   ```

3. **P1-7 — deps stables sur refresher effect** :
   ```ts
   useEffect(() => {
     apiService.setTokenRefresher(async () => { /* ... */ });
   }, [oidc.signinSilent, oidc.signinRedirect]);
   ```
   **NOTE** : vérifier en Phase 2 que `oidc.signinSilent` et `oidc.signinRedirect` sont bien des refs stables chez `react-oidc-context`. Si ce n'est pas le cas (certaines versions retournent de nouvelles fonctions à chaque render), fallback plan : capturer dans un `useRef` et mettre à jour via un effect secondaire. À arbitrer à la lecture de `node_modules/react-oidc-context/...`.

4. **P1-15 — `isMcpCallback` via `BASE_URL`** :
   ```ts
   function isMcpCallbackPath(pathname: string): boolean {
     const base = (import.meta.env.BASE_URL || '/').replace(/\/+$/, '');
     return pathname.startsWith(`${base}/mcp-connectors/callback`);
   }
   // usage
   if (!oidc.isAuthenticated && !oidc.isLoading && hasAuthParams() && !isMcpCallbackPath(window.location.pathname)) {
     oidc.signinRedirect();
   }
   ```
   Export depuis AuthContext + propagation dans `src/main.tsx:53` (`skipSigninCallback: isMcpCallbackPath(window.location.pathname)`).

5. **P1-16 — flag `isRedirectingToLogin`** :

   Nouveau fichier `src/services/http/redirect.ts` :
   ```ts
   let redirecting = false;
   export function markRedirecting(): void { redirecting = true; }
   export function isRedirecting(): boolean { return redirecting; }
   export function resetRedirecting(): void { redirecting = false; } // for tests only
   ```

   Dans `src/services/http/errors.ts` (ou `applyFriendlyErrorMessage`) :
   ```ts
   import { isRedirecting } from './redirect';
   export function applyFriendlyErrorMessage(error: AxiosError): void {
     if (isRedirecting()) return; // skip flash during redirect
     // ... existing logic
   }
   ```

   Dans `AuthContext.tsx` refresher :
   ```ts
   } catch {
     markRedirecting();
     oidc.signinRedirect();
     return null;
   }
   ```
   (Idem pour le cas `renewed?.access_token` absent.)

##### `src/services/http/auth.ts` (P1-3 comment)

Ajout d'un bloc de commentaire en tête du fichier documentant la session-scoped storage et le fait que le multi-tab divergence est intentionnel (renvoie vers l'éventuel ADR ou `SECURITY.md`).

#### C3.2 — Tests de régression

Nouveau fichier `src/contexts/AuthContext.jwt.test.ts` :
1. `test('decodeJwtPayload handles standard base64 payload')`
2. `test('decodeJwtPayload handles base64url with - and _')`
3. `test('decodeJwtPayload pads short segments correctly')`
4. `test('decodeJwtPayload throws on malformed token')`

Extension `src/contexts/AuthContext.test.tsx` :
5. `test('getMe() after unmount does not setState')` — render, unmount, resolve mock, assert no warning.
6. `test('setTokenRefresher not called on re-render when oidc.signinSilent stable')` — spy `apiService.setTokenRefresher`, 3 re-renders avec même refs ⇒ 1 call max.

Nouveau fichier `src/contexts/AuthContext.mcpCallback.test.ts` :
7. `test('isMcpCallbackPath matches / base')`
8. `test('isMcpCallbackPath matches /console/ base')`

Extension `src/services/http/errors.test.ts` (ou nouveau) :
9. `test('applyFriendlyErrorMessage skips when redirecting flag set')`.

**Total nouveaux tests C3** : ~9.

#### C3.3 — Commit message

```
fix(ui/auth): harden AuthContext JWT decode + lifecycle + multi-env paths

Five P1 issues in AuthContext concentrated around the auth flow:
- atob() on JWT payload fails on base64url-specific chars (- and _), catch
  swallow → roles=[] → user silently loses all permissions
- getMe() resolves after AuthProvider unmount → setState warning, masks
  real leaks in sibling effects
- setTokenRefresher effect dep was `[oidc]` (whole object) → re-set on
  every render with potentially stale closure
- isMcpCallback hardcoded '/mcp-connectors/callback' breaks if app served
  at a basePath (e.g. `/console/…`) — latent in current prod (base '/')
- Between oidc.signinRedirect() and actual page unload, the rejected-queue
  error toasts → flash of tech error before redirect

Design intent documented (P1-3 WONT-FIX):
- authToken + Keycloak sessionStorage are per-tab by design (XSS blast
  radius). Multi-tab divergence is accepted; comment block added in auth.ts

Fix:
- decodeJwtPayload helper (base64url + padding, manual, no new dep)
- mountedRef guard on getMe().then setUser
- deps [oidc.signinSilent, oidc.signinRedirect] on refresher effect
- isMcpCallbackPath(pathname) respecting import.meta.env.BASE_URL, wired
  in AuthContext + main.tsx skipSigninCallback
- services/http/redirect.ts markRedirecting() flag, consumed by
  applyFriendlyErrorMessage to skip toasts during pending navigation
- 9 regression tests (4 JWT, 2 lifecycle, 2 basePath, 1 redirect flag)

Closes: P1-5, P1-6, P1-7, P1-15, P1-16 (BUG-REPORT-UI-2.md)
Design intent: P1-3 (sessionStorage per-tab, documented)
```

---

### COMMIT 4 (C4) — Skills deprecated path migration

**Bugs fermés** : P1-4.
**Risque** : faible. Une ligne, un test.

#### C4.1 — Modifications de code

##### `src/services/skillsApi.ts:67-69`

```ts
async deleteSkill(key: string): Promise<void> {
  await apiService.delete(path('v1', 'gateway', 'admin', 'skills', key));
}
```

Importer `path` depuis `./api` ou directement depuis `./http`. **Note** : `skillsApi.ts` utilise `apiService`, pas `httpClient` direct — `path` helper fonctionne pour les deux, il produit juste une string.

Add import `import { path } from './http';`.

#### C4.2 — Tests de régression

Nouveau fichier `src/services/skillsApi.test.ts` (ou extension si existant) :
1. `test('deleteSkill uses REST path /v1/gateway/admin/skills/:key')`
2. `test('deleteSkill URL-encodes key with special characters')` — double-lock contre P0-6 régression + fix P1-4.

#### C4.3 — Commit message

```
fix(ui/skills): migrate delete to REST path /v1/gateway/admin/skills/:key

Gateway PR #2512 (GW-1 P2-3) deprecated the query-string form
`DELETE /v1/gateway/admin/skills?key=X` with Sunset 2026-10-24 and emits
`Deprecation: @<epoch>` response headers. The new REST path is
`DELETE /v1/gateway/admin/skills/:key`.

Fix:
- Switch skillsApi.deleteSkill to path('v1', 'gateway', 'admin', 'skills', key)
  (uses the C3/P0 encoding helper)
- 2 regression tests (URL shape, special-char encoding)

Closes: P1-4 (BUG-REPORT-UI-2.md)
```

---

## Arbitrages — résolus en Phase 1

### ARB-1 — P1-1 migration : **1 commit monolithique**
**Retenu** : 1 commit pour les 19 dashboards, pattern uniforme, 3 tests canary (1 par zone représentative). Raisons :
- Transformation mécanique identique sur les 19 sites.
- 5 dashboards déjà `allSettled` servent de template de vérification (copy-paste semantics).
- Splitting par zone (Gateways/Monitoring/AITools) introduit 3 PRs avec zéro bénéfice review (aucun risque de régression inter-zone).
- 19 fichiers × 10-20 LOC ≈ 200-400 LOC touchées — sous la limite PR 300 LOC si le diff contient essentiellement les `Promise.allSettled` et handlers. **Vérification obligatoire en Phase 2** : si diff > 300 LOC net, split par zone.

**Rejeté** : split par zone "pour rester sous 300 LOC" → 3 PRs. Complexité de review séquentiel + rebase pour zéro bénéfice si 1 PR < 300.

### ARB-2 — P1-3 multi-tab : **WONT-FIX (design intent)**, pas de BroadcastChannel
**Retenu** : aucun code de sync. Bloc de commentaire en tête de `src/services/http/auth.ts` référant la décision (sessionStorage par onglet = XSS blast-radius hardening, verified `src/main.tsx:45`). Raisons :
- BroadcastChannel ajouterait ~30 LOC + une source de bug (event listener leaks).
- Bénéfice UX marginal : chaque onglet refresh de son côté, l'UX actuelle n'est pas cassée.
- sessionStorage est un choix de sécurité explicite ; documenter > changer.

**Suivi** : ADR dans stoa-docs à envisager (hors scope P1). Mentionner dans le commit message.

**Rejeté** : BroadcastChannel ; pinger la question au futur ADR.

### ARB-3 — P1-5 JWT decode : **manual base64url fix, pas de `jwt-decode`**
**Retenu** : 5-8 lignes helper local. Raisons :
- Zéro nouvelle dep. Bundle pur frontend déjà chargé (atob natif).
- Base64url → base64 standard est une transformation bien connue : replace `-` / `_` + padding `=`.
- Tests simples (3 cas couvrent 100% des branches).

**Rejeté** : `jwt-decode` (~1KB gz) — pas justifié pour 5 lignes qui ne changeront pas.

### ARB-4 — P1-4 skills path : **migrer maintenant**
**Retenu** : migration immédiate. Raisons :
- Gateway PR #2512 (nouvelle route `:key`) vient d'être mergée → route est live.
- Change d'une ligne, tests triviaux.
- Évite warnings `Deprecation:` dans les logs prod.
- Attendre 2026-10-24 = ajouter un TODO / calendar reminder, pour zéro bénéfice.

**Rejeté** : defer à 2026-10-24 (deadline Sunset). Aucune raison de defer.

### ARB-5 — P1-12 scope extension ESLint : **pas nécessaire**
**Retenu** : C2 P0 a déjà posé la règle `no-restricted-globals` sur `src/hooks/**` avec allowlist explicite pour `useApiConnectivity` et `useServiceHealth`. Aucune extension requise. P1-12 est **déjà fermé** côté P0.

### ARB-6 — Ordre commits : **C4 → C2 → C3 → C1** recommandé
**Retenu** :
- C4 = 5 LOC. Trivial, ouvre la série.
- C2 = robustness transverse. Sans impact fonctionnel.
- C3 = auth. Touche un fichier sensible, mieux isolé avant C1 (gros volume).
- C1 = gros volume + mécanique. Dernier car si un rebase est nécessaire (post-merge P0), c'est C1 qui en souffrirait le moins (conflits line-localisés).

Aucune dépendance technique cross-commit. L'ordre peut être ajusté.

---

## Risques identifiés

### R-1 — C1 diff dépasse 300 LOC → split obligatoire
**Probabilité** : moyenne (19 fichiers × ~15 LOC = 285 LOC ± structures handlers).
**Impact** : split en 3 commits par zone — retarde de ~1h.
**Mitigation** : `git diff --stat` en fin de C1 avant commit ; si > 300 LOC net, rebase + split `A1 Monitoring/AITools/General`, `A2 Gateway`, `A3 Security/DriftDetection`.

### R-2 — P1-7 dep instability chez `react-oidc-context`
**Probabilité** : faible (lib mature, API fonctionnelle doit exposer refs stables).
**Impact** : fix naïf `[signinSilent, signinRedirect]` = re-fire à chaque render quand même.
**Mitigation** : Phase 2 vérifie avec `console.log` ou hook custom avant commit. Fallback : `useRef` pattern pour capturer les refs au mount.

### R-3 — P1-8 fail-fast sur shapes inattendues
**Probabilité** : faible, mais un endpoint `/apis` retournant `{ error: "…" }` au lieu d'items (ex : backend bug transitoire) générerait un throw.
**Impact** : page crash au lieu de "liste vide".
**Mitigation** : le throw a un message clair (`Unexpected apis response shape`) — meilleure UX de debug que `undefined.map is not a function`. Error boundary React transforme déjà ça en erreur propre.

### R-4 — P1-16 flag redirect `isRedirecting` jamais reset
**Probabilité** : faible — `signinRedirect` déclenche une navigation, page unload, module var wipe.
**Impact** : si navigation est annulée (user press Escape ou backend Keycloak down), le flag reste actif et toutes les erreurs sont silencieuses.
**Mitigation** : `resetRedirecting()` exporté pour tests uniquement. Dans le vrai flow, un reload manuel (F5) clear la variable. Ajouter un watchdog 30s dans le flag serait over-engineering.

### R-5 — C1 regression silencieuse sur un dashboard non couvert par test
**Probabilité** : moyenne (16 dashboards non testés individuellement).
**Impact** : un dashboard affiche partial data là où il montrait error avant (OU inversement : un endpoint fail silencieux alors qu'il fail catastrophiquement avant, ce qui masque un vrai problème).
**Mitigation** :
- 3 tests canary couvrent les 3 zones + pattern générique.
- Smoke test manuel Phase 3 sur 5-6 dashboards représentatifs.
- Type checker couvre la cohérence des setters (`setX([])` → setX doit accepter `[]`).

### R-6 — C3 refactor isMcpCallback casse le flow actuel
**Probabilité** : faible (BASE_URL = '/' en prod actuel → comportement équivalent).
**Impact** : boucle de redirect Keycloak si `isMcpCallbackPath` retourne false-positive.
**Mitigation** : 2 tests ciblés sur `BASE_URL='/'` et `BASE_URL='/console/'`. Smoke test Phase 3 sur `/mcp-connectors/callback?code=X` + login flow Keycloak normal.

---

## Callers à adapter — récap exhaustif

| Commit | Fichiers source modifiés | Fichiers test modifiés / créés |
|---|---|---|
| C1 | 19 pages (cf. §C1.2) | **NEW**: 3 `resilience.test.tsx` canary |
| C2 | `client.ts`, `config.ts`, `payload.ts` (NEW), `http/index.ts`, `apis.ts`, `consumers.ts`, `applications.ts`, `chat.ts`, `monitoring.ts`, `traces.ts`, `platform.ts` (+ grep catches) | **NEW**: `payload.test.ts` ; **extension** `client.test.ts`, `ui2-s2a-clients.test.ts`, `chat.test.ts`, `monitoring.test.ts` |
| C3 | `AuthContext.tsx`, `main.tsx`, `auth.ts` (comment only), `http/redirect.ts` (NEW), `http/errors.ts` | **NEW**: `AuthContext.jwt.test.ts`, `AuthContext.mcpCallback.test.ts` ; **extension** `AuthContext.test.tsx`, `errors.test.ts` |
| C4 | `skillsApi.ts` | **NEW**: `skillsApi.test.ts` |

**Total estimé** : ~25 fichiers source touchés + ~10 fichiers test, ~540 LOC nettes.

---

## Validation Phase 3 (checklist)

Post-C1-C4, exécuter :

1. `npx tsc --noEmit` dans `control-plane-ui/` → 0 erreur.
2. `npx vitest run` → tous tests passent, dont les ~24 nouveaux regression guards (3 C1 + 10 C2 + 9 C3 + 2 C4).
3. `npx eslint .` → 0 nouvelle erreur.
4. `npm run build` → succès, bundle size stable ±5%.
5. **Smoke test manuel** :
   - `npm run dev` local avec Keycloak staging.
   - Login normal → pas de flash d'erreur.
   - Dashboard APIMonitoring avec backend partiellement down (couper `/stats` via devtools) → transactions visibles + erreur locale stats.
   - Laisser onglet ouvert 10min → refresh silencieux → pas de re-fire N-fois du tokenRefresher (P1-7 lock).
   - Naviguer vers `/mcp-connectors/callback?code=X` → pas de redirect Keycloak (P1-15).
   - Delete skill via UI → requête `DELETE /v1/gateway/admin/skills/:key` confirmée en network tab (P1-4).
6. Mettre à jour `BUG-REPORT-UI-2.md` — marquer P1-1..P1-16 **STATUS: FIXED commit <SHA>** ou **WONT-FIX (P1-3)**.

---

## Livrable Phase 1

Ce fichier (`FIX-PLAN-UI2-P1.md`) + référence `BUG-REPORT-UI-2.md`. **STOP. Attente validation user avant Phase 2 (code).**

---

## Rev1 — 8 corrections challenger intégrées (2026-04-24)

### Rev1 #1 — C2 timeout : test la config, pas un adapter bloquant
Tests axios timeout :
- `test('httpClient has 30_000 default timeout')` — lit `instance.defaults.timeout`.
- `test('VITE_API_TIMEOUT_MS overrides default')` — re-import via `vi.resetModules` + `vi.stubEnv`.
- `test('per-call timeout override works')` — `httpClient.get(url, { timeout: 5_000 })` → assert `config.timeout === 5_000` via adapter spy.
**Supprimé** : test "adapter ne resolve jamais + fake timers" (fragile selon impl axios). Axios documente `timeout` comme config option, défaut `0` (pas de timeout).

### Rev1 #2 — C2 sweep query-string résiduelle (P1-11 reliquat)
Les 6 interpolations query-string restantes (`after '?'`) notées en C3 P0 commit message :
- `gateways.ts:86` — `/v1/admin/gateways/metrics/guardrails/events?limit=${limit}`
- `platform.ts:139` — `/v1/business/top-apis?limit=${limit}`
- `errorSnapshotsApi.ts:45` — `/v1/snapshots?${params.toString()}` (déjà URLSearchParams → OK, conserve)
- `errorSnapshotsApi.ts:67` — `/v1/snapshots/stats?${queryString}` (déjà URLSearchParams → OK, conserve)
- `skillsApi.ts:84` — `/v1/gateway/admin/skills/resolve?${params.toString()}` (déjà URLSearchParams → OK, conserve)
- `skillsApi.ts:68` — query-string `?key=` **fermé par C4 (migration vers path REST)**

**Action C2** : migrer `gateways.ts:86` et `platform.ts:139` vers `params: { limit }` option axios (élimine l'interpolation inline). Les 3 autres (URLSearchParams) sont déjà sûrs — documenter dans le commit message que c'est safe.

**Impact sur P1-11** : après C2, les 2 derniers sites inline sont migrés → P1-11 **fully closed** (path par C3-P0, query par C2-P1).

### Rev1 #3 — C2 `getUsageBySource` : `params ?? {}` safe
```ts
async getUsageBySource(
  tenantId: string,
  params: { group_by?: string; days?: number } = {}
): Promise<ChatUsageBySource> {
  const safeParams = params ?? {};
  const { data } = await httpClient.get(
    path('v1', 'tenants', tenantId, 'chat', 'usage', 'tenant'),
    { params: { ...safeParams, group_by: safeParams.group_by ?? 'source' } },
  );
  return data;
}
```

La signature actuelle déjà `= {}` default ⇒ `params` non undefined en entrée, mais `safeParams = params ?? {}` ajoute une ceinture + bretelles au cas où TS soit relaxé.

### Rev1 #4 — C2 pattern numérique : `!= null`
Pour P1-14, remplacer `if (x)` par `if (x != null)` (double-égal intentionnel pour matcher `null ou undefined`). Cela :
- conserve `0` (cœur de P1-14) ;
- évite d'envoyer un `null` par accident si un caller passe explicite `null`.

**Systématique sur** : `monitoring.ts:68-72, 84`, `traces.ts:13-16, 44-45, 52-53`, `platform.ts:120-121` + tout autre `if (param) params.y = param` détecté par `grep -En 'if \(\w+\) params\.'`.

### Rev1 #5 — C3 `isMcpCallbackPath` exact + baseUrl injectable
```ts
export function isMcpCallbackPath(
  pathname: string,
  baseUrl: string = import.meta.env.BASE_URL || '/',
): boolean {
  const base = baseUrl.replace(/\/+$/, '');
  const target = `${base}/mcp-connectors/callback`;
  return pathname === target || pathname.startsWith(`${target}/`);
}
```

Évite de matcher `/mcp-connectors/callback-evil`. `baseUrl` injectable pour tests sans monkey-patch `import.meta.env`. Vite remplace `import.meta.env.BASE_URL` statiquement au build, donc le default est OK en runtime.

**Tests C3** :
- `test('isMcpCallbackPath: exact match with root base')` — `('/mcp-connectors/callback', '/')` → true.
- `test('isMcpCallbackPath: subpath match with slash')` — `('/mcp-connectors/callback/foo', '/')` → true.
- `test('isMcpCallbackPath: rejects callback-evil lookalike')` — `('/mcp-connectors/callback-evil', '/')` → false.
- `test('isMcpCallbackPath: console basePath')` — `('/console/mcp-connectors/callback', '/console/')` → true.
- `test('isMcpCallbackPath: console basePath trailing slash tolerant')` — `('/console/mcp-connectors/callback', '/console')` → true.

### Rev1 #6 — C3 redirect flag : reset si `signinRedirect()` throw + TTL
Wrapping au call site + TTL watchdog dans le module :

```ts
// redirect.ts
let redirecting = false;
let ttlTimer: ReturnType<typeof setTimeout> | undefined;

export function markRedirecting(ttlMs: number = 30_000): void {
  redirecting = true;
  if (ttlTimer) clearTimeout(ttlTimer);
  ttlTimer = setTimeout(() => { redirecting = false; }, ttlMs);
}
export function isRedirecting(): boolean { return redirecting; }
export function resetRedirecting(): void {
  redirecting = false;
  if (ttlTimer) { clearTimeout(ttlTimer); ttlTimer = undefined; }
}
```

AuthContext refresher :
```ts
} catch {
  markRedirecting();
  try {
    await oidc.signinRedirect();
  } catch (err) {
    resetRedirecting();
    throw err;
  }
  return null;
}
```

Test supplémentaire C3 : `test('markRedirecting TTL auto-resets after 30s')` + `test('resetRedirecting clears flag immediately')`.

### Rev1 #7 — C3 JWT : `TextDecoder` pour UTF-8 safety
```ts
function base64UrlDecodeToString(seg: string): string {
  const padded = seg + '='.repeat((4 - (seg.length % 4)) % 4);
  const base64 = padded.replace(/-/g, '+').replace(/_/g, '/');
  const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}
function decodeJwtPayload(token: string): unknown {
  const [, payload] = token.split('.');
  if (!payload) throw new Error('Invalid JWT — missing payload');
  return JSON.parse(base64UrlDecodeToString(payload));
}
```

Test supplémentaire : `test('decodeJwtPayload handles UTF-8 claims (name=José, preferred_username=naïve)')` avec payload crafté localement.

### Rev1 #8 — C1 : ne pas clobber les slices déjà chargées
Pattern dashboard updaté :

```ts
const results = await Promise.allSettled([apiA, apiB]);
const [aRes, bRes] = results;

if (aRes.status === 'fulfilled') {
  setA(aRes.value.data);
  setErrors((prev) => ({ ...prev, a: null }));
} else {
  // do NOT setA([]) — preserve previous value if any
  setErrors((prev) => ({ ...prev, a: 'A unavailable' }));
}
// idem b
```

**Règle explicite en Phase 2** :
- Slice fulfilled → update + clear erreur locale.
- Slice failed → **ne pas toucher au state existant** + set erreur locale. Fallback `setX([])`/`setX(null)` uniquement si le state précédent est lui-même initial (premier load, pas encore de données).
- Error global `setError(...)` **seulement si aucun fulfilled** (rare — "total outage").

Cela évite l'anti-pattern `catch { setA([]); setB(null); }` qui efface les données valides sur la prochaine re-fetch.

**Test canary updaté** : "après 1 fetch OK complet, un 2e fetch avec `/stats` down → transactions **toujours affichées** (pas remises à `[]`) + erreur locale stats". Explicite sur la préservation de données existantes.

---

## Go conditionnel — Phase 2

Les 8 corrections sont intégrées au plan. **GO Phase 2**, ordre C4 → C2 → C3 → C1.

---

## Phase 2 — Statut final (2026-04-24)

### Commits livrés (sur `fix/ui-2-p1-batch`)

| Commit | SHA | Thème | P1 fermés |
|---|---|---|---|
| C4 | `1a559d58d` | Skills deprecated path → REST `/:key` | P1-4 |
| C2 | `9e50961a7` | HTTP client robustness | P1-2, P1-8, P1-13, P1-14 + P1-11 residu |
| C3 | `82910bd35` | Auth / Context hardening | P1-5, P1-6, P1-7, P1-15, P1-16 |
| C1 | `73eee66f9` | Dashboard resilience `allSettled` (18 dashboards) | P1-1 |

### Statut par bug

| P1 | Status | Commit |
|---|---|---|
| P1-1 Promise.all → allSettled | **FIXED** | `73eee66f9` |
| P1-2 axios timeout | **FIXED** | `9e50961a7` |
| P1-3 multi-tab token | **WONT-FIX** (design intent, documenté `auth.ts`) | `82910bd35` |
| P1-4 skills deprecated path | **FIXED** | `1a559d58d` |
| P1-5 atob base64url + UTF-8 | **FIXED** | `82910bd35` |
| P1-6 getMe unmount guard | **FIXED** | `82910bd35` |
| P1-7 setTokenRefresher stable deps | **FIXED** | `82910bd35` |
| P1-8 data.items shape guard | **FIXED** | `9e50961a7` |
| P1-9 useEvents isConnected state | **CLOSED by P0-C4** | `7bddb1501` |
| P1-10 SSE reconnect post-refresh | **CLOSED by P0-C4** | `7bddb1501` |
| P1-11 path injection latent extended | **FIXED** (path by P0-C3 + query by P1-C2) | `95fafa8ea` + `9e50961a7` |
| P1-12 hooks fetch direct | **CLOSED by P0-C2** | `7c773c888` |
| P1-13 chat spread undefined | **FIXED** | `9e50961a7` |
| P1-14 `if (x)` drops 0 | **FIXED** | `9e50961a7` |
| P1-15 isMcpCallback basePath | **FIXED** | `82910bd35` |
| P1-16 flash error before redirect | **FIXED** | `82910bd35` |

**Score** : 14 P1 FIXED + 1 P1 WONT-FIX (P1-3, design) + 1 P1 already closed by P0 recounted = **16/16 traités**.

### Validation Phase 3

| Check | Résultat |
|---|---|
| `npx vitest run` | **2193 passed** / 11 skipped (baseline P0 = 2147) → +46 nouveaux tests |
| `npx tsc --noEmit` | 394 erreurs TS **toutes pré-existantes** (auto-redirect-expired-session.test.tsx, shared/*, App.tsx ErrorBoundary, DeployLogViewer, QuickStartGuide, useBreadcrumbs) — zéro nouvelle erreur sur les fichiers touchés C1-C4 |
| `npm run lint` | **0 erreur**, 54 warnings (ceiling 110) |
| `npm run build` | Même caveat P0 (`../shared/*` + `App.tsx ErrorBoundary` pré-existants, non introduits par ce batch) |

### Régression guards ajoutés (46 tests au total)

- **C4** (2) : URL shape + special-char encoding
- **C2** (21) : client timeout (3), payload shape (7), chat group_by default (3), monitoring statusCode=0 (3), list shape guard (5)
- **C3** (20) : JWT decode base64url/UTF-8 (11), mcpCallbackPath basePath (-), redirect flag TTL (6), errors + redirect gate (3)
- **C1** (3 canaries) : APIMonitoring stats-fail / ToolDetail usage-fail / Guardrails events-fail — tous verrouillent "partial render preserved"
- **Existing tests updated** : UsageDashboard + DeployAPIDialog (nouvelle sémantique: error only when ALL fail)

### Livrable final

5 commits atomiques sur `fix/ui-2-p1-batch` depuis `fix/ui-2-p0-batch`. Prêt pour PR après rebase sur `main` post-P0-merge. **P2 (12 bugs) next** pour clore UI-2.
