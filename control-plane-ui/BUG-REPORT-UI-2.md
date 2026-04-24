# BUG-REPORT-UI-2 — Audit fonctionnel services/http + services/api/* + consumers

> **STATUS** : **UI-2 CLOSED** (2026-04-24) — 38/38 findings traités. Détail en §UI-2 CLOSED ci-dessous.

---

## UI-2 CLOSED (2026-04-24)

Module **UI-2 officiellement clos**. Tous les findings P0/P1/P2 sont fixed, documented WONT-FIX, already-fixed par un batch précédent, ou deferred avec owner/ticket.

### Score final

| Sévérité | Total | Fixed | WONT-FIX (documented) | Deferred (ticket) |
|---|---|---|---|---|
| P0 | 10 | 10 | 0 | 0 |
| P1 | 16 | 15 | 1 (P1-3 design intent) | 0 |
| P2 | 12 | 7 fixed + 2 already-fixed (P2-3, P2-10) | 3 (P2-2, P2-4, P2-7 inline docs) | 2 (P2-11, P2-12 → CAB-2164) |
| **TOTAL** | **38** | **34** | **4** | **2** (1 ticket) |

### Batches

| Batch | Branch | Commits | PR / Status |
|---|---|---|---|
| P0 (10 fixed) | `fix/ui-2-p0-batch` | C1 `a88c98902`, C2 `7c773c888`, C3 `95fafa8ea`, C4 `7bddb1501` | #2514 (merged) |
| P1 (14 fixed + 1 WONT-FIX) | `fix/ui-2-p1-batch` | C4 `1a559d58d`, C2 `9e50961a7`, C3 `82910bd35`, C1 `73eee66f9` | en cours |
| P2 (7 fixed + 3 WONT-FIX + 2 already-fixed + 2 deferred) | `fix/ui-2-p2-batch` | C1 (squash TBD) | en cours |

### Deferred (suivi)

- **[CAB-2164](https://linear.app/hlfh-workspace/issue/CAB-2164)** — UI-3 Cleanup : absorbe P2-11 (REWRITE-BUGS.md zombies) + P2-12 (`any` pervasif 17 sites `gateways.ts`/`gatewayDeployments.ts`). Priority P2.

### Next

CP-2 (Python), GW-2 (Rust), UI-1 W1 (OpenAPI schemas drift). UI-2 ne nécessite plus de passage.

---

> **Date audit** : 2026-04-24
> **Scope** : `control-plane-ui/src/services/` (rewrite UI-2, 7 fichiers `http/` + 22 domain clients + façade + 11 siblings legacy) + consumers React (hooks, pages, `AuthContext`).
> **Baseline** : branche `audit/ui-2` depuis `main@73d696409` (stoa-gateway 0.9.13).
> **Méthode** : Phase audit only. Aucun fix. Chaque finding cite `fichier:ligne`. Marque `HYPOTHÈSE À VÉRIFIER` quand l'impact dépend d'un comportement backend non-auditable ici.
> **Référence rewrite** : `REWRITE-PLAN.md`. `REWRITE-BUGS.md` **absent** (pas produit par le rewrite — voir B2 ; suivi dans CAB-2164).

---

## Executive summary

| Sévérité | Total | Top zones |
|---|---|---|
| **P0** | 10 | Refresh-token race/lifecycle (3), SSE auth/lifecycle (3), fetch() bypass direct (1), dual-write auth state (1), zero dedicated core test (1), useEvents reconnect loop latent (1) |
| **P1** | 16 | `Promise.all` systémique (25+ dashboards), client timeout absent, path injection latent (URI-encode), data-shape fallback silencieux, multi-tab divergence, deprecated skills path, getMe after-unmount, atob on base64url, dual-write defaults.headers |
| **P2** | 12 | Catch swallow, no-ops confus, error UX, mutable module state, axios re-submit sans clone, etc. |
| **TOTAL** | **38** |

### Top 3 risques immédiats (avant fix)

1. **Refresh token — replay de la file sans propager `_retry` (P0-1)**. Après refresh, les requêtes enqueuées rejouent via `instance(originalRequest)` ligne `refresh.ts:34` ; `originalRequest._retry` n'est pas `true` sur ce chemin. Si le nouveau token est accepté par l'endpoint qui a fire le refresh MAIS rejeté par un autre endpoint (RBAC spécifique, clock drift backend, ou token valide mais audience différente), la requête enqueuée re-rentre dans l'intercepteur, re-déclenche un refresh, etc. Cascade N-refreshs en chaîne pour chaque requête parallèle concernée.
2. **SSE sans cycle de vie auth (P0-4, P0-5, P0-8)**. `new EventSource(url)` ne supporte pas `Authorization` header → auth soit anonyme (backend doit accepter) soit par cookie soit par query (pas présent ici). Aucune reconnexion après refresh token : le `EventSource` créé reste attaché à l'**ancien token** tant que la page est ouverte. Si le backend l'évalue, 401 silencieux ; si pas de reconnect logic côté app, les events manquent sans indication UI.
3. **`Promise.all` systémique sur les dashboards (P1-1)**. 25+ dashboards pattern `[a, b] = await Promise.all([apiA, apiB])` : un endpoint down = écran entier vide (catch générique qui reset tout). `getGatewayStatus` prouve qu'`allSettled` était le bon choix (commentaire CAB-1887 G2 dans `gatewayApi.ts:58`) — pattern non propagé.

---

## Critical (P0)

### P0-1 — Refresh queue : `_retry` flag non propagé sur le replay → cascade N-refreshs possible

**Fichier** : `src/services/http/refresh.ts:27-35`, `refresh.ts:38`, `refresh.ts:49`

Le chemin d'une requête enqueuée pendant un refresh :

```ts
// refresh.ts L27-35
if (getIsRefreshing()) {
  return new Promise<string | null>((resolve, reject) => {
    enqueueRefresh({ resolve, reject });
  }).then((token) => {
    if (token && originalRequest.headers) {
      originalRequest.headers.Authorization = `Bearer ${token}`;
    }
    return instance(originalRequest);   // ← replay SANS set _retry
  });
}
```

La requête **déclencheur du refresh** fait `originalRequest._retry = true;` avant `await tokenRefresher()` (L38). Les requêtes de la **file d'attente**, elles, font `return instance(originalRequest)` **sans** mettre `_retry = true`.

Conséquence : si la requête enqueuée rejoue et reçoit à nouveau `401` (cas réaliste : nouveau token valide pour l'endpoint déclencheur mais pas pour celui-là — RBAC à scope différent, ou audience JWT incorrecte, ou clock drift), elle rentre à nouveau dans l'intercepteur. Comme son `_retry` n'est **toujours pas** set, le check `!originalRequest._retry` ligne 24 passe, et elle déclenche un **second refresh** (ou se re-enqueue si un autre est en cours). Cascade silencieuse.

**Reproduction** :
1. Deux requêtes `A` et `B` partent en parallèle, chacune 401.
2. `A` gagne la course, set `_retry`, déclenche refresh.
3. `B` arrive après `A._retry = true`, voit `isRefreshing = true`, s'enqueue.
4. Refresh OK, `A` rejoue avec nouveau token → OK.
5. `B` rejoue depuis la queue avec nouveau token → 401 (ex : `B` cible un endpoint où le nouveau token n'a pas le scope requis).
6. `B._retry` est **toujours** `undefined` (non set sur le chemin queue) → rentre dans le block L22 → refresh déclenché à nouveau.

**Fix direction** : set `originalRequest._retry = true` sur le chemin queue avant `return instance(originalRequest)` (refresh.ts:34).

---

### P0-2 — Refresh null token : pas de `clearAuthToken()`, ancien token reste utilisé

**Fichier** : `src/services/http/refresh.ts:50-52`

```ts
const newToken = await tokenRefresher();
if (newToken) { ... }
// Token refresh returned null — session expired, reject queued requests
drainRefreshQueue({ rejectWith: error });
```

Si `tokenRefresher()` retourne `null` (session expirée côté backend), on rejette la queue, on `setIsRefreshing(false)` dans le `finally`, on retombe sur `applyFriendlyErrorMessage(error); return Promise.reject(error);`. **L'ancien token reste stocké dans `authToken` module var** (auth.ts:8).

Conséquence : toute requête subséquente ré-utilise un token **connu mort** jusqu'à son propre 401, déclenchant un nouveau refresh → nouveau null → boucle de reject. Le user voit N erreurs "session expirée" en cascade au lieu d'un redirect immédiat.

**Reproduction** :
1. Session Keycloak expire server-side.
2. Request A → 401 → refresh → `signinSilent` resolved sans token → refresher return null.
3. `refresh.ts` rejette la queue mais **ne clear pas `authToken`**.
4. Request B part (ex : auto-refetch React Query 60s) → request interceptor lit `getAuthToken()` → ancien token → 401 à nouveau → nouveau refresh → nouveau null, etc.

Le `AuthContext.tsx:188, 191` appelle `oidc.signinRedirect()` dans le refresher avant de retourner null, ce qui **déclenche un redirect URL**. Mais entre le `signinRedirect` (action asynchrone du navigateur) et le redirect effectif, N cycles de refresh peuvent se produire.

**Fix direction** : dans `refresh.ts:52`, ajouter `clearAuthToken()` avant `drainRefreshQueue({ rejectWith: error })`. Idem sur le chemin `catch (refreshError)` ligne 53-55.

---

### P0-3 — Refresh sans timeout : queue bloquée indéfiniment si `tokenRefresher` hang

**Fichier** : `src/services/http/refresh.ts:42`, `src/services/http/auth.ts:10-11`

```ts
setIsRefreshing(true);
try {
  const newToken = await tokenRefresher();   // ← pas de timeout
  ...
} finally {
  setIsRefreshing(false);
}
```

`tokenRefresher()` (wire depuis `AuthContext.tsx:181` = `oidc.signinSilent`) peut hang arbitrairement : iframe OIDC silent renew sans response, MITM, backend Keycloak down, etc. Il n'y a pas de `Promise.race` avec un timeout.

Conséquences :
1. `isRefreshing = true` reste vrai indéfiniment.
2. Toutes les requêtes 401 suivantes s'enqueuent éternellement (L28 `enqueueRefresh`).
3. `refreshQueue` grandit sans limite (pas de max size).
4. Aucune requête n'est rejetée, aucun redirect, UI figée.

**Fix direction** : wrap `tokenRefresher()` dans `Promise.race([tokenRefresher(), new Promise((_, rej) => setTimeout(() => rej(new Error('refresh timeout')), 30_000))])`. Cleanup queue + clearAuthToken + redirect sur timeout.

---

### P0-4 — SSE sans authentification côté UI (EventSource ne supporte pas Authorization)

**Fichier** : `src/services/http/sse.ts:3-7`

```ts
export function createEventSource(tenantId: string, eventTypes?: string[]): EventSource {
  const params = eventTypes ? `?event_types=${eventTypes.join(',')}` : '';
  const url = `${config.api.baseUrl}/v1/events/stream/${tenantId}${params}`;
  return new EventSource(url);   // ← pas de token
}
```

`EventSource` (DOM API standard) **ne supporte pas** les headers custom — le bearer token ne peut pas être envoyé. Les seules options pour authentifier :
- Cookie HTTP-only (nécessite `withCredentials: true` qui n'est pas mis).
- Query string `?token=<jwt>` (pas présent).
- Endpoint ouvert (fuite multi-tenant).

**HYPOTHÈSE À VÉRIFIER côté backend** : comment `/v1/events/stream/:tenant_id` s'authentifie-t-il ?
- Si **ouvert** → n'importe qui connaissant `tenant_id` reçoit les events de ce tenant. Data leakage.
- Si **cookie session** → il faut `new EventSource(url, { withCredentials: true })`, ce qui n'est **pas** le cas ici. Donc broken aussi.
- Si **token query** → il faut l'injecter (et le token apparaît dans server access logs, ce qui est mauvais).

Actuellement : créer un EventSource vers cet endpoint **en étant non authentifié** depuis le browser revient au même résultat qu'en étant authentifié. Cela suggère soit endpoint ouvert, soit backend accepte cookie présent, soit broken dès qu'auth est requis.

**Fix direction** : clarifier la politique avec backend. Si auth requise, passer à l'API `EventSource` avec `withCredentials: true` + cookie auth, **ou** à un polyfill `fetch`-based (e.g. `@microsoft/fetch-event-source`) qui supporte les headers.

---

### P0-5 — SSE ne reconnecte pas après refresh token

**Fichier** : `src/services/http/sse.ts:3-7`, `src/hooks/useEvents.ts:56-74`

Si l'auth SSE transite par token (cookie OAuth renouvelé à chaque refresh, ou query `?token=` capturé au moment du `createEventSource`), après un refresh token côté HTTP :
- Le `EventSource` existant reste connecté avec les credentials **d'origine** (ancien token).
- Le backend peut rejeter à la prochaine validation (TTL du JWT/session).
- `EventSource` natif **reconnecte automatiquement** avec la même URL → même ancien token → loop 401.

Aucune logique dans `useEvents.ts` ne surveille `getAuthToken()` pour recréer le `EventSource` sur changement. L'`onerror` (L65-68) se contente de `console.error`, commentaire : "EventSource will automatically reconnect" — ce qui **n'aide pas** si la cause est un token expiré.

**Fix direction** : subscribe au changement de token (expose un callback depuis `http/auth.ts`, ou prop `token` dans `useEvents` qui re-trigger l'effect). Fermer et recréer `EventSource` à chaque refresh.

---

### P0-6 — Path injection latente : `tenantId`/`eventTypes` non URI-encoded

**Fichier** : `src/services/http/sse.ts:4-5`, pattern répandu

```ts
const params = eventTypes ? `?event_types=${eventTypes.join(',')}` : '';
const url = `${config.api.baseUrl}/v1/events/stream/${tenantId}${params}`;
```

- `tenantId` interpolé brut dans le path. Si `tenantId` contient `/`, `?`, `#` (peu probable côté backend, mais si un jour un tenant mal validé côté input), URL malformée ou injection de query/fragment.
- `eventTypes.join(',')` non encodé. Si un event type contient `&` ou `=`, scission de la query string.

Pattern étendu dans les domain clients (tenants.ts, consumers.ts, deployments.ts, webhooks.ts, contracts.ts, promotions.ts, etc.) : tous interpolent `${tenantId}`, `${apiId}`, `${consumerId}`, `${deploymentId}`, `${certId}`, `${webhookId}`, `${deliveryId}`, `${mappingId}`, etc. sans `encodeURIComponent`. `mcpGatewayApi.ts` le fait bien (`encodeURIComponent(toolName)` L63/75/167) — incohérence notable.

**Impact réaliste** : faible si les IDs sont toujours des UUIDs backend-générés. Mais la défense-en-profondeur exige l'encoding ; un changement côté backend (slugs, emails, etc.) ouvrirait la fenêtre.

**Fix direction** : helper `const path = (segments: string[]) => '/' + segments.map(encodeURIComponent).join('/');` et migration progressive.

---

### P0-7 — `usePrometheus.ts` bypass complet du refresh logic via `fetch()` direct

**Fichier** : `src/hooks/usePrometheus.ts:42-46`, `101-105`

```ts
const response = await fetch(url, {
  signal: AbortSignal.timeout(10_000),
  headers: { Authorization: `Bearer ${accessToken}` },   // ← fetch direct
});
if (!response.ok) throw new Error(`Prometheus returned ${response.status}`);
```

`accessToken` est lu depuis `useAuth().accessToken` (AuthContext `oidc.user.access_token`). Ce token peut être **expiré** entre deux polls (`refreshInterval = 15_000ms`) : si le silent renew n'a pas encore réussi, `accessToken` est l'ancien.

Quand Prometheus (le backend `/api/v1/metrics`) renvoie 401 :
- Pas d'intercepteur axios → pas de refresh.
- `!response.ok` → throw `"Prometheus returned 401"`.
- User voit "Prometheus unavailable" ou un dashboard vide.

Le comportement attendu serait que le 401 déclenche le flow de refresh standard (même que les autres requêtes authentifiées). Ici, le fetch direct court-circuite.

**Reproduction** : laisser l'onglet dashboard prometheus ouvert > durée de vie du token Keycloak (typiquement 5 min sans silent renew). Au prochain poll : "Prometheus unavailable" alors que tout le reste de l'app fonctionne.

**Impact aggravé** : ESLint `no-restricted-imports` bannit axios hors `services/http/**` mais **ne bannit pas `fetch`**. Le pattern peut être copié. Déjà le cas dans `useApiConnectivity.ts` (L17) et `useServiceHealth.ts` (L33).

**Fix direction** : passer via `httpClient` exposé par `services/http`, ou créer un helper `authenticatedFetch` qui partage le token state + gère 401.

---

### P0-8 — `useEvents` : `eventTypes` array identity → risque de reconnect loop latent

**Fichier** : `src/hooks/useEvents.ts:74`

```ts
useEffect(() => {
  if (!enabled || !tenantId) return;
  const eventSource = apiService.createEventSource(tenantId, eventTypes);
  ...
  return () => { eventSource.close(); ... };
}, [tenantId, eventTypes, enabled, handleEvent]);
```

`eventTypes` est un paramètre `string[] | undefined` passé par le caller. Si un caller passe un **array literal** dans le JSX (`useEvents({ tenantId, eventTypes: ['deploy-started', ...] })`), chaque render crée une nouvelle référence → l'effect re-fire → `close()` + nouveau `EventSource` à **chaque re-render** du caller.

**État actuel** : le seul caller identifié (`useDeployEvents.ts:86`) passe `DEPLOY_EVENT_TYPES` qui est une constante module-level (`L6`) — identity stable. Pas de bug **aujourd'hui**, mais latence de bug pour tout futur caller.

**HYPOTHÈSE À VÉRIFIER** : confirmer que c'est bien le seul caller courant, et que l'auto-import n'induira pas de pattern bug-prone dans les nouveaux callers.

**Fix direction** : stabiliser la ref avec `useMemo(() => eventTypes, [eventTypes?.join(',')])` dans `useEvents` avant de passer au create, OU documenter de façon visible (`// Caller MUST pass a stable array reference`).

---

### P0-9 — Dual-write auth state (façade `api.ts:208-211` + `mcpGatewayService` no-op)

**Fichier** : `src/services/api.ts:208-211`, `src/services/mcpGatewayApi.ts:210-216`, `src/contexts/AuthContext.tsx:145-146`

```ts
// api.ts:208
setAuthToken(token: string): void {
  setAuthTokenCore(token);
  httpClient.defaults.headers.common['Authorization'] = `Bearer ${token}`;  // (A)
}
```

```ts
// AuthContext.tsx:145-146
apiService.setAuthToken(token);
mcpGatewayService.setAuthToken(token);   // ← no-op (voir mcpGatewayApi.ts:210)
```

Deux problèmes combinés :

**(a) `mcpGatewayService.setAuthToken` est un no-op** (`mcpGatewayApi.ts:210-212`) avec commentaire "auth token is managed by apiService". Le call subsiste dans `AuthContext`. Un développeur qui lit le code peut penser que l'auth est dédoublée et ajouter du code reposant sur une propagation inexistante. Dead call avec effet de surface intentionnel trompeur.

**(b) `httpClient.defaults.headers.common['Authorization']` n'est jamais mis à jour par le refresh interceptor** (`refresh.ts:44` → `setAuthToken(newToken)` pointe vers `auth.ts:setAuthToken` qui ne touche que `authToken`, pas `defaults.headers.common`). Résultat :
- Après le premier login : `authToken = X` ET `defaults.headers.common.Authorization = Bearer X`.
- Après un refresh : `authToken = Y` MAIS `defaults.headers.common.Authorization = Bearer X` (obsolète).

En pratique, le `request` interceptor (interceptors.ts:5-14) override per-request via `getAuthToken()` → les requêtes partent avec le bon token. Mais :
- Toute utilisation directe de `httpClient` (dans un test, un debug, futur migration) lirait `defaults.headers.common` et enverrait **l'ancien** token.
- Dual source of truth confusion : si quelqu'un `console.log(httpClient.defaults.headers.common.Authorization)` pour debug, il verra un token **obsolète**.

**Fix direction** :
1. Supprimer la ligne `(A)` dans `api.ts:210` (le request interceptor suffit).
2. Supprimer la ligne `(B)` dans `api.ts:219` (`delete httpClient.defaults.headers.common['Authorization']` devient redondant).
3. Supprimer `mcpGatewayService.setAuthToken(token)` et `mcpGatewayService.clearAuthToken()` de `AuthContext.tsx` + leurs déclarations no-op.

---

### P0-10 — Zéro test unitaire dédié pour `services/http/*` core

**Fichiers** : `src/services/http/*.ts` (7 fichiers), `src/__tests__/regression/auto-redirect-expired-session.test.tsx`, `src/contexts/AuthContext.test.tsx`

- Aucun fichier `services/http/*.test.ts`.
- Les 5 tests `src/test/services/api/ui2-s2{a,b,c,d}-clients.test.ts` mockent `httpClient` et testent uniquement que chaque domain client fait le bon `httpClient.get/post` — pas le comportement du core.
- `auto-redirect-expired-session.test.tsx` (271 lignes, 73 mentions de `refresh`/`401`) **simule** la logique dans une fonction locale `simulate401Handler` (L35-69) parallèle au vrai code. Il **n'importe pas** `installRefreshInterceptor` et ne teste pas `refresh.ts` directement. Une régression dans `refresh.ts` (ex : le bug P0-1) ne serait **pas** détectée par ce test.

Bilan : la zone la plus risquée du module (refresh + queue + interceptors) n'a **aucun** test de régression **sur le code réel**. Tout le flux dépend d'un test qui garantit la forme de sa propre réimplémentation.

**Fix direction** : écrire `src/services/http/refresh.test.ts` qui importe `installRefreshInterceptor`, crée une vraie instance axios + adaptateur mock, exerce les 6 scénarios clés (401 solo, 401 parallèles, retry flag, session expired, hang timeout, chaîne refresh→retry→401→rejected).

---

## High (P1)

### P1-1 — `Promise.all` systémique sans `allSettled` (25+ dashboards)

**Fichiers** :
- `src/pages/Applications.tsx:130`, `src/pages/Deployments.tsx:389`, `src/pages/APIMonitoring.tsx:552`, `src/pages/ErrorSnapshots.tsx:561`, `src/pages/HegemonDashboard.tsx:448`, `src/pages/Business/BusinessDashboard.tsx:247`, `src/pages/GatewayGuardrails/GuardrailsDashboard.tsx:95`, `src/pages/GatewayObservability/GatewayObservabilityDashboard.tsx:111`, `src/pages/GatewayDeployments/DeployAPIDialog.tsx:58`, `src/pages/GatewayDeployments/GatewayDeploymentsDashboard.tsx:52`, `src/pages/AITools/UsageDashboard.tsx:41`, `src/pages/AITools/ToolDetail.tsx:41`, `src/pages/AITools/MySubscriptions.tsx:39`, `src/pages/ApiDeployments/ApiDeploymentsDashboard.tsx:67`, `src/pages/DriftDetection/DriftDetection.tsx:93`, `src/pages/AnalyticsDashboard/AnalyticsDashboard.tsx:154`, `src/pages/GatewaySecurity/GatewaySecurityDashboard.tsx:42`, `src/pages/SecurityPosture/SecurityPostureDashboard.tsx:184,198,215`, `src/pages/ToolPermissionsMatrix.tsx:75,182`
- 5 bons patterns isolés : `src/pages/ChatUsageDashboard.tsx:75`, `src/pages/LLMCost/LLMCostDashboard.tsx:77`, `src/pages/AITools/ToolCatalog.tsx:53`, `src/pages/ApiTraffic/ApiTrafficDashboard.tsx:178`, `src/services/gatewayApi.ts:61`

Exemple `APIMonitoring.tsx:552-570` :
```ts
const [txnResponse, statsResponse] = await Promise.all([
  apiService.get('/v1/monitoring/transactions'),
  apiService.get('/v1/monitoring/transactions/stats'),
]);
...
setTransactions(txnResponse.data.transactions);
setStats(statsResponse.data);
} catch (_err) {
  setError('Transaction monitoring is unavailable');
  setTransactions([]);   // ← écrase même si txns était OK
  setStats(null);
}
```

Si seul `/stats` échoue (endpoint partiel en prod), **les transactions sont effacées** et l'UI montre "unavailable" complet alors que 50% de la donnée est dispo.

Le code de `gatewayApi.ts:58-87` prouve que le pattern correct est connu (commentaire `CAB-1887 G2 : getGatewayStatus now throws when all endpoints fail`). Non propagé.

**Fix direction** : migration progressive vers `Promise.allSettled` par dashboard, chaque slice a son propre état `{ data, error }` exposé à la UI.

---

### P1-2 — `axios.create` sans `timeout`

**Fichier** : `src/services/http/client.ts:4-11`

```ts
return axios.create({
  baseURL: config.api.baseUrl,
  headers: { 'Content-Type': 'application/json' },
  // pas de timeout
});
```

Par défaut axios = `timeout: 0` (= aucun timeout). Si le backend hang (pod stuck, LB retry en cours, socket half-open), la requête hang **indéfiniment** côté browser. Combiné avec l'absence d'`AbortController` dans la plupart des consumers React, un composant démonté continue à détenir des promesses non résolues indéfiniment.

**Fix direction** : `timeout: 30_000` par défaut dans `client.ts`, override par appel si besoin (long-running endpoints genre `/deploy`).

---

### P1-3 — Multi-tab : `authToken` diverge entre onglets (module-scope var)

**Fichier** : `src/services/http/auth.ts:8`

```ts
let authToken: string | null = null;   // module-scope PAR bundle chargé
```

Chaque onglet charge le bundle JS indépendamment → chaque onglet a sa **propre** variable `authToken`. Les tokens Keycloak sont stockés en `sessionStorage` (`main.tsx:45`) — qui est **par onglet**, pas partagé.

Scénario : 
- Onglet A : user login, token T1 en memory + sessionStorage A.
- Onglet B (ouvert après) : OIDC silent SSO → token T2 en memory + sessionStorage B.
- Onglet A : silent renew s'effectue, token T3 en memory A (sessionStorage A).
- Onglet B : continue avec T2 jusqu'à son propre silent renew.

Pas de sync entre onglets. Si le backend révoque T1/T2 (logout, etc.), les onglets découvrent à leur prochain 401.

**Impact** : moyen — l'app tourne, chaque onglet refresh de son côté. Mais :
- Si un logout action est faite dans un onglet, l'autre continue à travailler avec un token potentiellement révoqué (cache server-side pas forcément instantané).
- Deux onglets qui subissent un 401 simultané vont chacun lancer un silent renew en parallèle → 2 round-trips Keycloak au lieu de 1.

**Fix direction** : écouter `storage` event sur `sessionStorage` (ne marche pas si chaque onglet a sa propre session storage) ; ou utiliser `BroadcastChannel` pour sync token entre tabs ; ou accepter le coût et documenter.

**HYPOTHÈSE À VÉRIFIER** : `main.tsx:45` choisit explicitement `sessionStorage` pour réduire blast radius XSS, ce qui implique la divergence. C'est probablement intentionnel ; à clarifier dans un ADR.

---

### P1-4 — `skillsApi.ts` utilise le path **deprecated** GW-1 P2-3

**Fichier** : `src/services/skillsApi.ts:67-68`

```ts
async deleteSkill(key: string): Promise<void> {
  await apiService.delete(`/v1/gateway/admin/skills?key=${encodeURIComponent(key)}`);
}
```

Ce path a été marqué deprecated côté gateway (PR #2512, GW-1 P2-3) — le gateway renvoie désormais headers `Deprecation: @<epoch>`, `Sunset: 2026-10-24`, `Link: <...>; rel="successor-version"` sur cet endpoint. Le nouveau chemin REST est `DELETE /v1/gateway/admin/skills/:key`.

Côté UI : continue d'utiliser l'ancien, va générer des warnings de deprecation en prod à partir du merge de #2512.

**Fix direction** : migrer `/v1/gateway/admin/skills?key=X` → `/v1/gateway/admin/skills/:key` dans `skillsApi.ts:68`. Deadline : **2026-10-24** (Sunset gateway).

---

### P1-5 — `atob` sur `base64url` : JWT decode fragile

**Fichier** : `src/contexts/AuthContext.tsx:100-103`

```ts
const payload = JSON.parse(atob(oidcUser.access_token.split('.')[1]));
roles = payload.realm_access?.roles || [];
} catch (e) {
  console.warn('Failed to decode access_token for roles', e);
}
```

`atob` attend du **base64 standard** (alphabet `+`, `/`, padding `=`). Les JWT utilisent **base64url** (`-`, `_`, pas de padding). Quand les caractères non-URL-safe sont absents du payload, ça fonctionne par chance ; quand ils sont présents, `atob` lève `InvalidCharacterError`. Le catch swallow l'erreur → roles = `[]` silencieusement → **utilisateur perd toutes ses permissions**.

**Reproduction** : un tenant_id, preferred_username, ou claim custom qui contient des caractères rendant le base64url divergent du base64. Erreur intermittente selon les tokens.

**Fix direction** : utiliser `jose` ou `jwt-decode` (tree-shakeable) au lieu de `atob` manuel. Ou pad + replace manuellement : `.replace(/-/g, '+').replace(/_/g, '/')` + padding `===`.

---

### P1-6 — `AuthContext.getMe()` résout après unmount → setState on unmounted

**Fichier** : `src/contexts/AuthContext.tsx:155-166`

```ts
apiService.getMe()
  .then((me) => {
    if (me.role_display_names) {
      setUser((prev) => prev ? { ...prev, role_display_names: me.role_display_names } : prev);
    }
  })
  .catch(() => {});
```

Pas de guard `mountedRef`, pas d'`AbortController`. Si AuthProvider démonte pendant que `getMe()` est en vol (HMR en dev, logout + remount après auth change), le `.then` fire `setUser` sur un composant démonté → React console.warn, pas crash, mais pattern qui cache de vrais memory leaks si le `setUser` appelle un reducer qui déclenche des side-effects.

**Fix direction** : `mountedRef` guard OU `AbortController` + signal passé à `apiService.getMe()` (nécessite ajout de signal dans les domain clients).

---

### P1-7 — `setTokenRefresher` re-set à chaque render (`oidc` dep instable)

**Fichier** : `src/contexts/AuthContext.tsx:180-195`

```ts
useEffect(() => {
  apiService.setTokenRefresher(async () => { ... });
}, [oidc]);
```

`oidc` vient de `useOidcAuth()` — identity probablement instable (`react-oidc-context` retourne un nouvel objet à chaque render quand `isLoading`/`isAuthenticated` changent). Le refresher est redéfini à chaque render. Pas catastrophique (setter idempotent) mais :
- Closure capturée sur un `oidc` potentiellement obsolète si l'effect rate un render (bug React classique).
- Allocation inutile.

**Fix direction** : dep `[oidc.signinSilent, oidc.signinRedirect]` (refs stables exposées par la lib) au lieu de `[oidc]`.

---

### P1-8 — Data-shape fallback silencieux `data.items ?? data`

**Fichiers** : `src/services/api/apis.ts:10, 17`, `src/services/api/consumers.ts:10`, `src/services/api/applications.ts:9`, `src/services/proxyBackendService.ts:50-53`

```ts
return data.items ?? data;
```

Si le backend change une response pagination vers un array direct (ou inversement), le frontend **masque** la divergence : le code retourne soit l'items array, soit l'objet entier casté comme `Tenant[]`. Si `data` devient `{ total: 5, page: 1 }` sans items, le fallback retourne l'objet typé faussement → crash plus loin avec message obscur (`undefined.map is not a function`).

**Fix direction** : valider explicitement que `data.items` est un array, sinon throw avec un message clair. Ou utiliser Zod sur les responses.

---

### P1-9 — `useEvents.onerror` : pas d'état UI exposé

**Fichier** : `src/hooks/useEvents.ts:65-68`

```ts
eventSource.onerror = (error) => {
  console.error('EventSource error:', error);
  // EventSource will automatically reconnect
};
```

Aucun `setState` pour signaler "connection broken" ou "reconnecting". Le user ne voit pas que les événements temps-réel sont coupés. Le hook retourne `{ close }` seulement, pas un `isConnected` ni un `lastError`.

**Impact** : un déploy en cours n'affiche plus de progress events si la connexion SSE tombe ; l'utilisateur ne sait pas si c'est parce que le deploy est silent ou parce que la connexion est morte.

**Fix direction** : exposer `{ isConnected, lastError, close }` ; updatable via `onopen`/`onerror`.

---

### P1-10 — SSE ne reconnecte pas sur token refresh (loop 401 silencieux)

**Fichiers** : `src/services/http/sse.ts`, `src/hooks/useEvents.ts:60-73`

Détaillé en P0-5. Classé ici P1 parce que l'**occurrence** dépend de la politique d'auth SSE (P0-4 en HYPOTHÈSE). Si SSE est réellement auth (cookie ou query token), ceci devient P0 ; si non-auth, l'impact tombe.

---

### P1-11 — Path injection latent étendue (UUID aujourd'hui, cas limites demain)

Voir P0-6. Re-noté P1 car l'impact dépend de l'assumption "tous les IDs sont des UUIDs server-générés". Si un jour un slug user-controlled (email, nom de gateway avec espaces, etc.) rentre dans l'un de ces templates, injection immédiate. 20+ fichiers concernés.

---

### P1-12 — `useApiConnectivity.ts` et `useServiceHealth.ts` bypass `httpClient` via `fetch()`

**Fichiers** : `src/hooks/useApiConnectivity.ts:17`, `src/hooks/useServiceHealth.ts:33, 61`

Même pattern que P0-7 (usePrometheus) mais avec un impact moindre :
- `useApiConnectivity` appelle `/health` non-authentifié (OK).
- `useServiceHealth` sert à probe des URLs externes en `HEAD` — OK par design.

Le risque : ces 3 hooks sont les patterns visibles de "fetch direct" dans le repo. Un développeur qui fait copier/coller pour un nouvel endpoint authentifié (ex : polling custom) va bypasser `httpClient` sans s'en rendre compte.

**Fix direction** : ESLint rule `no-restricted-globals` sur `fetch` dans `src/hooks/**` + whitelist explicite (`/* eslint-disable no-restricted-globals */ // justification`).

---

### P1-13 — `chat.ts:getUsageBySource` : spread override avec `undefined` force le backend vers un défaut non voulu

**Fichier** : `src/services/api/chat.ts:95-103`

```ts
async getUsageBySource(
  tenantId: string,
  params: { group_by?: string; days?: number } = {}
): Promise<ChatUsageBySource> {
  const { data } = await httpClient.get(`...`, {
    params: { group_by: 'source', ...params },   // ← spread overrides
  });
  return data;
}
```

Si le caller passe `{ group_by: undefined, days: 7 }` (facile par omission), le spread met `group_by: undefined`, axios **skip les params undefined**, donc la requête part **sans `group_by`** → backend applique son propre défaut. Le caller pensait hériter du défaut `'source'` du client ; il ne l'a pas.

Pas un bug critique (le backend a un default), mais contre-intuitif.

**Fix direction** : `params: { ...params, group_by: params.group_by ?? 'source' }` (fallback inversé).

---

### P1-14 — `monitoring.ts` : `if (statusCode)` skip la valeur `0`

**Fichier** : `src/services/api/monitoring.ts:71`

```ts
if (statusCode) params.status_code = statusCode;
```

`0` est falsy → jamais envoyé. `0` n'est pas un HTTP status valide, donc peu grave en pratique, mais pattern copié ailleurs (`traces.ts:13`, etc.). Si un jour un param numérique où `0` est sémantique (offset 0 en pagination), même classe de bug.

**Fix direction** : check `!== undefined` plutôt que truthy.

---

### P1-15 — `AuthContext.isMcpCallback` : check `startsWith` fragile aux basePaths

**Fichier** : `src/contexts/AuthContext.tsx:202`

```ts
const isMcpCallback = window.location.pathname.startsWith('/mcp-connectors/callback');
```

Si l'app est servie avec un `basePath` différent de `/` (ex : `/console/mcp-connectors/callback`), le check ne matche pas → le callback OAuth MCP est interprété comme un callback Keycloak → redirect boucle/auth cassée.

**HYPOTHÈSE À VÉRIFIER** : la config Vite actuelle semble servir à la racine (pas vu de `base` config). À confirmer pour les déploiements.

**Fix direction** : utiliser le router React (`useLocation()`) au lieu de `window.location.pathname`, ou builder le path avec `import.meta.env.BASE_URL`.

---

### P1-16 — Flash d'erreur avant redirect login

**Fichier** : `src/contexts/AuthContext.tsx:188, 191`

Dans le refresher, `oidc.signinRedirect()` est appelé **avant** `return null`. Le `return null` fait rejeter le queue → `applyFriendlyErrorMessage(error)` → erreur affichée dans l'UI. Entre le moment où `signinRedirect` initie la navigation (async côté browser) et le déchargement effectif de la page, l'UI affiche **un flash d'erreur** technique au user. UX dégradée.

**Fix direction** : flag global `isRedirecting` qui fait que l'error boundary / global toast skip les erreurs pendant le redirect.

---

## Medium (P2)

### P2-1 — `interceptors.ts` error callback sans friendly-error — **FIXED** (P2 batch C1)

`src/services/http/interceptors.ts:13` : `(error) => Promise.reject(error)`. Le response interceptor applique `applyFriendlyErrorMessage`, pas le request. Cas rare (échec de transformation request), mais inconsistent.

### P2-2 — Axios re-submit `originalRequest` sans clone — **WONT-FIX** (P2 batch C1, inline comment + canary test)

`src/services/http/refresh.ts:34, 49` : `instance(originalRequest)` passe le **même objet config**. Axios peut muter `data`/`headers`/`params` via transformers ; un retry pourrait double-JSON-stringify ou appliquer deux fois un transformer. **HYPOTHÈSE À VÉRIFIER** : axios 1.x gère ça en interne (peu probable de casser en pratique), mais le pattern reste fragile.

### P2-3 — `mcpGatewayService.setAuthToken`/`clearAuthToken` no-ops — **ALREADY FIXED by P0-C1 `a88c98902`**

`src/services/mcpGatewayApi.ts:210-216`. Voir P0-9. Dead code avec effet de surface trompeur.

### P2-4 — `accessToken` exposé dans le React context — **WONT-FIX** (P2 batch C1, reinforced JSDoc; long-term fix via backend-signed URL tracked separately)

`src/contexts/AuthContext.tsx:225, 233`. Volontaire pour Grafana iframe auth, mais tout composant enfant peut le lire → **risque de leak** si une dépendance tiers (extension, widget analytics) accède à `useAuth()`. Documenté dans l'interface (`// Raw Keycloak JWT for Grafana iframe auth`) mais pas protégé.

### P2-5 — `useServiceHealth.ts:76` catch generic — **FIXED** (P2 batch C1; AbortError vs network distinguished)

`} catch { setStatus('unavailable'); }` — swallow, pas de distinction AbortError vs network. Pas de setState guard sur unmount → warning React en cas de timeout après unmount. Bénin, à nettoyer.

### P2-6 — `useServiceHealth` fetch non-abort sur unmount — **FIXED** (P2 batch C1; effect-scoped AbortController + `abortedByUnmount` flag)

Le `AbortController` est scoped à l'appel, pas à l'effect. À l'unmount, le fetch continue en arrière-plan jusqu'au timeout 5s.

### P2-7 — Module-scope mutable state exposé via getters publics — **WONT-FIX** (P2 batch C1, doc block + ESLint `no-restricted-imports` on http/auth internals)

`src/services/http/auth.ts:33-54` : `getIsRefreshing`, `setIsRefreshing`, `enqueueRefresh`, `drainRefreshQueue` exportés. Nécessaires pour le split code, mais exposer mutation pub des internals ouvre la porte à corruption accidentelle depuis un autre module. Envisager un namespace class ou IIFE.

### P2-8 — `useEvents.ts:20` cast `as Event` sans schema — **FIXED** (P2 batch C1; `isValidEvent` type guard + drop unknown types)

JSON.parse puis cast. Si le backend envoie un event d'un type non géré par le switch (L26-48), fallback = aucun action (OK), mais un event mal formé peut crash le `onEvent` user callback (L23). Pas de validation Zod.

### P2-9 — Console logs résiduels en prod — **FIXED** (P2 batch C1; gated behind `import.meta.env.DEV`)

`src/hooks/useEvents.ts:50, 66` (`console.error`), `src/contexts/AuthContext.tsx:103` (`console.warn`). Acceptable pour debug, mais pas de filtering prod → logs SDK clients. À router vers un logger pivotable.

### P2-10 — `gateways.ts:86` URL params inline au lieu de `params` — **ALREADY FIXED by P1-C2 `9e50961a7`** (P1-11 residu sweep)

```ts
async getGuardrailsEvents(limit = 20): Promise<any> {
  const { data } = await httpClient.get(
    `/v1/admin/gateways/metrics/guardrails/events?limit=${limit}`   // ← inline
  );
}
```

Inconsistence avec le reste du fichier qui utilise `{ params: {...} }`. Pour `limit: number`, sans risque, mais pattern à aligner.

### P2-11 — Zombies preservés (REWRITE-PLAN A.2) — ticket follow-up — **DEFERRED** to [CAB-2164](https://linear.app/hlfh-workspace/issue/CAB-2164)

~40 méthodes zombies sont co-localisées dans les domain clients. Non-bug (décision de rewrite), mais **non documentées dans `REWRITE-BUGS.md`** (qui est **absent** du repo). La promesse du plan §A.2 ("Noter dans REWRITE-BUGS.md") n'est pas tenue.

### P2-12 — `any` pervasif sur gateways/deployments — **DEFERRED** to [CAB-2164](https://linear.app/hlfh-workspace/issue/CAB-2164) (17 sites: `gateways.ts`=13, `gatewayDeployments.ts`=4)

REWRITE-PLAN §F.7 documenté. `any` dans gateways.ts (12 occurrences), gatewayDeployments.ts (7 occurrences), façade. Non-bug mais dette typesafety.

---

## Scope hors bugs — notes de design

### D.1 — Absence de `REWRITE-BUGS.md`

Le plan §A.2 engage à créer un `REWRITE-BUGS.md` listant les zombies et les findings gardés pour UI-3. Le fichier n'existe pas. Trois options :
1. Générer le fichier à partir du présent rapport (les P2-11 et P2-12).
2. Marquer les méthodes zombies via un commentaire `// UI-3 cleanup candidate` au niveau de chaque occurrence.
3. Créer un ticket Linear `UI-3` dédié avec la liste.

Recommandation : (3) + ajout du ticket ID dans `REWRITE-PLAN.md`.

### D.2 — `sessionStorage` vs refresh state

`authToken` est en module-scope (volatile au reload) tandis que le token Keycloak source est en `sessionStorage` (persistant au reload de l'onglet, `main.tsx:45`). Sur un hard refresh (F5) : le module-scope est wiped, mais le `sessionStorage` reste. `AuthContext` récupère le token depuis `oidc.user.access_token` et le re-injecte via `apiService.setAuthToken` au prochain `useEffect` L137-147. OK dans le flow normal, mais toute requête partie **avant** que `setAuthToken` ne soit ré-appelé (ex : query React Query avec `staleTime: 0` qui refetch immédiatement) partirait sans token. À confirmer ou documenter comme invariant.

### D.3 — ESLint `no-restricted-imports` couvre axios, pas fetch

Le bonus §E.6 du plan ajoute une règle qui bannit `import axios` hors `services/http/**`. La règle **ne couvre pas** `fetch` global. Trois hooks utilisent déjà `fetch` direct (P0-7, P1-12). Le périmètre du lint devrait s'étendre.

### D.4 — Tests ui2-s2a..s3 : surface mais pas profondeur

Les 5 fichiers `src/test/services/api/ui2-s*.test.ts` testent chaque domain client sur le "happy path" (vi.mock httpClient, assert call URL/method). C'est suffisant pour valider que le rewrite n'a pas changé les URL, pas pour valider le comportement end-to-end avec refresh, timeout, SSE, interceptors. La dette est concentrée dans P0-10.

---

## Priorité de fix (ordre suggéré)

### Batch P0 (hotfix, avant prochaine release)
1. **P0-1** — propager `_retry` sur le replay queue (`refresh.ts:34`).
2. **P0-2** — `clearAuthToken()` sur null-token path (`refresh.ts:52, 54`).
3. **P0-3** — timeout sur `tokenRefresher()` (`refresh.ts:42`).
4. **P0-9** — supprimer dual-write token + no-ops (`api.ts:210, 219`, `mcpGatewayApi.ts:210-216`, `AuthContext.tsx:146, 174`).
5. **P0-10** — écrire `src/services/http/refresh.test.ts` réel (+ `sse.test.ts` minimal). Cela lock les 4 fixes P0 précédents.

### Batch P0-cadre (nécessite décisions)
6. **P0-4** — clarifier politique auth SSE avec backend. Si auth requise et non présente → bug critique à fixer sur deux bords.
7. **P0-5 / P0-8** — découle de P0-4.
8. **P0-6** — helper `encodeURIComponent` systémique (pattern étendu sur ~20 fichiers). Migration progressive, commit par domaine.
9. **P0-7** — `usePrometheus.ts` via `httpClient` au lieu de fetch direct.

### Batch P1 (sprint courant)
10. **P1-2** — `timeout: 30_000` dans `client.ts`.
11. **P1-4** — migration skills DELETE `/:key` vers path RFC compliant (deadline 2026-10-24).
12. **P1-5** — JWT decode robuste base64url (`jwt-decode` ou manuel correct).
13. **P1-6** — guard `mounted` sur `getMe()` dans AuthContext.
14. **P1-8** — retirer `data.items ?? data` (ou typer strictement).
15. **P1-9** — exposer `isConnected` depuis `useEvents`.

### Batch P1 — refactor paralléle (hors critical path)
16. **P1-1** — migration dashboards `Promise.all → allSettled`. Par dashboard, pas tout d'un coup.
17. **P1-3** — sync multi-tab via BroadcastChannel (ou ADR pour justifier la divergence).
18. **P1-7** — deps stables `setTokenRefresher` effect.

### Batch P2 (backlog)
19-30. Voir section P2 — nettoyage lisibilité, pas de bug bloquant.

---

## Comparaison avec les 3 bug-hunts précédents

| Module | Total | P0 | P1 | P2 |
|---|---|---|---|---|
| GO-1 (Go) | 14 | 6 | 5 | 3 |
| CP-1 (Python) | 21 | 8 | 8 | 5 |
| GW-1 (Rust) | 20 | 8 | 7 | 5 |
| **UI-2 (TS)** | **38** | **10** | **16** | **12** |

UI-2 produit **plus** que les 3 précédents. Deux raisons :
1. **La surface est plus large** : rewrite récent + consumers React + SSE + refresh + 22 clients + 11 siblings = beaucoup de chemins async indépendants.
2. **Les bugs de concurrence JS sont plus nombreux** que les précédents modules (React setState lifecycle, EventSource, fetch vs axios, multi-tab, etc.).

La catégorie C (refresh token — crucial UX) est la zone la plus fournie : **4 P0** (P0-1, P0-2, P0-3, P0-9) + 3 P1 directement liés (P1-3, P1-5, P1-6). Cohérent avec le brief "sois particulièrement rigoureux sur la catégorie C".

---

**STOP**. Fin de Phase 1 audit. (Historique : les batches P0/P1/P2 ont depuis fermé les 38 findings — voir §UI-2 CLOSED en tête.)
