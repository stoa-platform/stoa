# FIX-PLAN-UI2-P0 — Phase 1 (plan only, NO code)

> **Source** : `BUG-REPORT-UI-2.md` — 10 P0 findings.
> **Branche** : `fix/ui-2-p0-batch` depuis `main@73d696409` (stoa-gateway 0.9.13).
> **Worktree** : `/Users/torpedo/hlfh-repos/stoa-ui-2-fix` (audit worktree `stoa-ui-2-audit` gardé en référence).
> **Méthode** : Plan → **STOP** → Phase 2 (code) après validation user.
> **Rev1 (2026-04-24)** : intégré 5 corrections du challenger (C1 null-path reject, timer cleanup, timeout injectable ; C3 docstring + URLSearchParams note ; C4 custom fetch + vrai refresh + eventTypesKey JSON.stringify). C1 exporte désormais un helper réutilisable par C4.

## Résumé — 4 commits atomiques

| # | Thème | P0 fermés | LOC estimé | Files | Risk |
|---|---|---|---|---|---|
| C1 | Refresh token core + dual-write auth (+ helper exporté) | P0-1, P0-2, P0-3, P0-9, P0-10 | ~280 net | 5 modified + 1 new test | moyen — touche refresh flow, tests réels neufs |
| C2 | usePrometheus → httpClient | P0-7 | ~40 net | 1 modified + 1 new ESLint rule | faible |
| C3 | Path encoding systémique | P0-6 | ~150 net (mechanical) | 30 modified + 1 new helper | faible (mechanical, UUID=no-op) |
| C4 | SSE polyfill fetch-event-source + vrai refresh sur 401 | P0-4, P0-5, P0-8 | ~150 net | 2 modified + 1 dep + 1 new test | moyen — nouvelle dep + remplace EventSource + refresh actif |

**Ordre d'exécution recommandé** : C1 → C2 → C3 → C4 (C4 consomme le helper refresh exporté par C1 — ordre désormais obligatoire entre C1 et C4).

---

## Arbitrages — résolus en Phase 1

### ARB-1 — Timeout `tokenRefresher()` : **30 secondes**

**Retenu** : `30_000ms`, lu **dynamiquement** à chaque appel (pas figé au module load) pour permettre les overrides tests. Raisons :
- Keycloak silent renew via iframe PKCE prend typiquement 500ms-3s en prod ; 30s est 10× la normale.
- Au-delà, l'utilisateur perçoit la page comme "figée" ; mieux vaut rejeter vite et redirect.
- Configurable via `config.auth.refreshTimeoutMs` avec default `30_000` (surchargement possible via env var `VITE_AUTH_REFRESH_TIMEOUT_MS` pour staging si Keycloak lent).
- **Rev1** : `refreshWithTimeout()` accepte un param optionnel `timeoutMs` et lit `config.auth.refreshTimeoutMs` à chaque appel (non figé).

**Rejeté** : 60s (trop long côté UX) ; 10s (trop agressif, faux-positifs possibles sur connexions lentes).

### ARB-2 — `clearAuthToken` déjà exposé : **OK, rien à ajouter**

Vérifié : `src/services/http/auth.ts:21-23` expose déjà `export function clearAuthToken(): void { authToken = null; }`. Importé dans `refresh.ts` via `./auth` (ajout d'import). Rien à exposer de plus.

### ARB-3 — Test strategy pour `refresh.test.ts` : **vitest + adapter axios mock manuel**

**Retenu** : utiliser un adapter axios custom injecté via `axios.create({ adapter })`. Pattern léger (~30 LOC helper), 100% déterministe, zéro dépendance nouvelle.

**Rejeté** :
- `axios-mock-adapter` — tiers, moins contrôlable sur timing async.
- `nock` — HTTP level, trop lourd pour tester un interceptor.
- `vi.mock('axios')` — casse l'instance injectée par `installRefreshInterceptor`.

**Sketch** :
```ts
// dans refresh.test.ts
import axios from 'axios';
import { installRefreshInterceptor } from './refresh';

function makeInstance(adapter: (config: any) => Promise<any>) {
  const instance = axios.create({ adapter });
  installRefreshInterceptor(instance);
  return instance;
}
```
L'adapter reçoit les configs, retourne des `{ status, data, headers, config }` selon le scénario. Contrôle total sur les timings via `await new Promise(r => setTimeout(r, X))` dans l'adapter.

### ARB-4 — Policy auth SSE backend : **Bearer header requis — Option D (polyfill)**

**Vérifié empiriquement** (grep `control-plane-api/src/auth/dependencies.py` + `routers/events.py`) :
- Endpoint `/v1/events/stream/{tenant_id}` utilise `Depends(get_current_user)` + `@require_tenant_access`.
- `get_current_user` n'accepte que `Authorization: Bearer <jwt>` via `HTTPBearer` (ou `X-Operator-Key` pour S2S — non applicable au navigateur).
- Pas de lecture de cookie, pas de fallback query-param.
- `VITE_API_URL` en prod = `https://api.gostoa.dev` — **cross-origin** depuis `console.gostoa.dev`. Pas de cookie session cross-origin.

**Conclusion factuelle** : le SSE actuel via `EventSource` natif **ne peut pas** envoyer `Authorization: Bearer` → le backend retourne **401 à chaque connexion** → `onerror` fire → `EventSource` retry automatiquement avec même URL → 401 en boucle silencieuse.

La fonctionnalité `useDeployEvents` (utilisée dans `Deployments.tsx:531` — déploiements live progress) est donc **cassée en prod** aujourd'hui. L'UI fonctionne car `loadHistoricalLogs` (polling HTTP) est un fallback implicite, mais les updates temps-réel sont mortes silencieusement.

**Décision Commit 4** : **Option D — polyfill `@microsoft/fetch-event-source`**.

**Rev1 — design correction** : le type `FetchEventSourceInit.headers` est `Record<string, string>` (pas une fonction). Le callback `headers: () => ({...})` **ne compilera pas**. Le design correct utilise l'option `fetch` custom de la lib pour passer un wrapper qui relit `getAuthToken()` à chaque invocation réseau (retry inclus).

De plus : relire le token à chaque retry ne suffit pas si rien ne déclenche un refresh. Un 401 sur SSE avec le reste de l'app idle réessaierait indéfiniment le même token. **C4 doit donc réutiliser un helper refresh exporté par C1** (`refreshAuthTokenWithTimeout()`) et l'appeler dans `onopen(401)` avant de throw une erreur retriable.

Justifications :
- Permet `Authorization: Bearer ${getAuthToken()}` header via `authFetch` custom.
- Re-read du token + **déclenchement d'un refresh actif** à chaque 401 → refresh transparent avec coalescing (helper exporté par C1 respecte la queue).
- Bundle size : ~2.9 KB gzipped (vérifié sur bundlephobia).
- Stable (released 2022, maintained), Microsoft-owned, dépendance directe sans transitives lourdes.
- Supporte `AbortController` natif → cleanup propre sur unmount.

Alternative écartée : custom polyfill `fetch` + `ReadableStream` interne (~80 LOC à tester + maintenance) — risque plus grand de miss d'edge cases (line buffering, chunk boundaries, retry logic, last-event-id propagation).

---

## COMMIT 1 — Refresh token core + dual-write auth state + helper exporté

**Bugs fermés** : P0-1, P0-2, P0-3, P0-9, P0-10
**Risque** : moyen — touche le flow le plus critique de l'auth.
**Mitigation** : commit **lock par 8 tests réels neufs** qui importent `installRefreshInterceptor` / `refreshAuthTokenWithTimeout` directement.

### C1.1 — Modifications de code

#### `src/services/http/refresh.ts` (riskiest change)

**Changements** :

1. L34 chemin queue : ajout `originalRequest._retry = true;` avant `return instance(originalRequest)` (P0-1).
2. Ajout `refreshWithTimeout()` — `Promise.race` avec timer **cleared** sur résolution successful, lit `config.auth.refreshTimeoutMs` dynamiquement, accepte override param (**Rev1 correction #1 + #2 + #3**).
3. Ajout `refreshAuthTokenWithTimeout()` — helper **exporté** qui encapsule getTokenRefresher + refreshWithTimeout + setAuthToken + clearAuthToken, réutilisable par C4 (**Rev1 correction helper shared**).
4. Branche null token : `clearAuthToken()` avant `drainRefreshQueue({ rejectWith: error })` **+ return Promise.reject(error)** (P0-2 + **Rev1 correction #1 explicit reject**).
5. `clearAuthToken()` dans le `catch (refreshError)` branch (P0-2).
6. Import `clearAuthToken` depuis `./auth`, import `config` depuis `../../config`.

**Sketch `refreshWithTimeout` avec timer cleanup** :

```ts
function refreshWithTimeout(
  refresher: TokenRefresher,
  timeoutMs?: number
): Promise<string | null> {
  const effectiveTimeout = timeoutMs ?? config.auth?.refreshTimeoutMs ?? 30_000;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const timeoutPromise = new Promise<never>((_, reject) => {
    timer = setTimeout(
      () => reject(new Error(`Token refresh timeout after ${effectiveTimeout}ms`)),
      effectiveTimeout
    );
  });

  return Promise.race([refresher(), timeoutPromise]).finally(() => {
    if (timer) clearTimeout(timer); // Rev1 #2 — avoid pending timers
  });
}
```

**Sketch `refreshAuthTokenWithTimeout` helper exporté** :

```ts
/**
 * Trigger a token refresh respecting the single-flight queue.
 * Returns the new token on success, null if no refresher is registered,
 * throws on timeout / refresher error (after clearing auth state).
 * Reused by C4 (SSE 401 handler).
 */
export async function refreshAuthTokenWithTimeout(): Promise<string | null> {
  const refresher = getTokenRefresher();
  if (!refresher) return null;

  // If a refresh is already in flight, wait on the shared queue to coalesce.
  if (getIsRefreshing()) {
    return new Promise<string | null>((resolve, reject) => {
      enqueueRefresh({ resolve, reject });
    });
  }

  setIsRefreshing(true);
  try {
    const newToken = await refreshWithTimeout(refresher);
    if (newToken) {
      setAuthToken(newToken);
      drainRefreshQueue({ resolveWith: newToken });
      return newToken;
    }
    clearAuthToken();
    const err = new Error('Token refresh returned null — session expired');
    drainRefreshQueue({ rejectWith: err });
    throw err;
  } catch (err) {
    clearAuthToken();
    drainRefreshQueue({ rejectWith: err });
    throw err;
  } finally {
    setIsRefreshing(false);
  }
}
```

**Interceptor refactor (uses helper internally)** :

```ts
export function installRefreshInterceptor(instance: AxiosInstance): void {
  instance.interceptors.response.use(
    (response) => response,
    async (error: AxiosError) => {
      const originalRequest = error.config as RetriableConfig | undefined;
      const tokenRefresher = getTokenRefresher();

      if (
        error.response?.status === 401 &&
        originalRequest &&
        !originalRequest._retry &&
        tokenRefresher
      ) {
        originalRequest._retry = true; // P0-1 set BEFORE await

        try {
          const newToken = await refreshAuthTokenWithTimeout();
          if (newToken && originalRequest.headers) {
            originalRequest.headers.Authorization = `Bearer ${newToken}`;
          }
          if (newToken) {
            return instance(originalRequest);
          }
          // newToken === null: refresher absent. Fall through to reject.
          return Promise.reject(error);
        } catch (refreshError) {
          // helper already cleared auth and rejected queue
          return Promise.reject(refreshError);
        }
      }

      applyFriendlyErrorMessage(error);
      return Promise.reject(error);
    }
  );
}
```

**Note** : le helper encapsule la logique de queue/coalescing. L'interceptor bénéficie automatiquement de `enqueueRefresh` via `refreshAuthTokenWithTimeout()` quand `isRefreshing === true`. Cela simplifie le flow et centralise la logique timeout/clear/reject en un seul point.

#### `src/services/api.ts:208-220`

Supprime le dual-write sur `httpClient.defaults.headers.common['Authorization']` :

```ts
// APRÈS
setAuthToken(token: string): void {
  setAuthTokenCore(token);
}

clearAuthToken(): void {
  clearAuthTokenCore();
}
```

Le `request` interceptor (`interceptors.ts:4-15`) lit `getAuthToken()` à chaque requête → la valeur module-scope est la source unique de vérité. `defaults.headers.common` devient inutile.

#### `src/services/mcpGatewayApi.ts:210-216`

Suppression complète des 2 méthodes no-ops.

**Impact downstream** : vérifié — les 2 seuls callers sont dans `AuthContext.tsx:146, 174`. Pas d'autre usage (grep repo-wide).

#### `src/contexts/AuthContext.tsx`

Suppression des 2 appels `mcpGatewayService.{set,clear}AuthToken`. Import `mcpGatewayService` **conservé** — toujours utilisé implicitement via ses autres méthodes (verified through `src/pages/AITools/*.tsx`, `FederationAccounts/ToolAllowListModal.tsx`).

#### `src/config.ts` (ajout)

Ajouter `auth.refreshTimeoutMs` :

```ts
auth: {
  refreshTimeoutMs: Number(import.meta.env.VITE_AUTH_REFRESH_TIMEOUT_MS) || 30_000,
},
```

#### `src/services/http/index.ts`

Export `refreshAuthTokenWithTimeout` pour usage C4.

### C1.2 — Tests de régression — **locks P0-1 à P0-3, P0-9**

Nouveau fichier : `src/services/http/refresh.test.ts`.

1. `test('401 solo: refresh + retry succeeds with new token')`
2. `test('parallel 401s: single refresh call, queue replays all with new token')`
3. `test('queued request replay sets _retry flag to prevent cascade refresh')` — LOCK P0-1.
4. `test('null token from refresher clears authToken and rejects queue')` — LOCK P0-2.
5. `test('refresh error (throw) clears authToken and rejects queue')` — LOCK P0-2.
6. `test('refresh hang > timeout clears authToken and rejects queue')` — LOCK P0-3. Mock refresher = `new Promise(() => {})`, config timeout 100ms.
7. `test('401 after successful refresh replay does not trigger new refresh')` — LOCK P0-1.
8. **Rev1 #2** `test('successful refresh clears the timeout timer')` — LOCK timer cleanup. Mock refresher resolve <timeout, vérifier via `vi.useFakeTimers` + `vi.getTimerCount()` que le timer est cleared.

Nouveau fichier : `src/services/api.test.ts`.

9. `test('apiService.setAuthToken does not mutate httpClient.defaults.headers')` — LOCK P0-9.
10. `test('apiService.clearAuthToken does not touch httpClient.defaults.headers')`.

Total : **10 nouveaux tests**, ~200 LOC de test.

### C1.3 — Commit message

```
fix(ui/services/http): eliminate refresh token cascade and dual-write auth state

Refresh token flow had 5 interacting P0 bugs:
- _retry flag not propagated on queue replay → cascade N-refreshs if retry 401s
- Null token path did not clear auth and did not explicitly reject → stale
  resolution possible on the interceptor promise chain
- tokenRefresher() had no timeout → hang blocked queue indefinitely
- Dual-write on httpClient.defaults.headers vs module-scope authToken created
  a stale-but-visible auth state post-refresh (debug confusion)
- mcpGatewayService.setAuthToken was a no-op with confusing call sites
- Zero dedicated test on services/http core — all "regression" tests simulated
  logic in parallel instead of importing installRefreshInterceptor

Fix:
- Set _retry=true on both trigger and queued replay paths
- Export refreshAuthTokenWithTimeout() helper for reuse (SSE 401 path — C4)
- clearAuthToken() before drainRefreshQueue on null/error paths + explicit
  Promise.reject(error) return
- Promise.race wrapper with configurable 30s timeout, timer cleared on
  success to avoid pending timers (fake-timer safe), timeout read
  dynamically for test override
- Remove httpClient.defaults.headers dual-write in façade
- Remove mcpGatewayService auth no-ops + AuthContext call sites
- Add src/services/http/refresh.test.ts with 8 real-code regression tests
- Add src/services/api.test.ts with 2 dual-write single-source-of-truth tests

Closes: P0-1, P0-2, P0-3, P0-9, P0-10 (BUG-REPORT-UI-2.md)
```

---

## COMMIT 2 — usePrometheus → httpClient + ESLint fetch ban

**Bugs fermés** : P0-7
**Risque** : faible.

### C2.1 — Modifications de code

#### `src/hooks/usePrometheus.ts`

Remplacer les 2 sites `fetch()` par `httpClient.get()`. Drop `accessToken` capture, laisser le request interceptor injecter Bearer.

**Simplification** : plus besoin de `mountedRef` pour protéger le `setError`/`setData` si on passe au pattern `useQuery` React Query. **Décision** : ne pas migrer vers React Query dans ce commit (out-of-scope).

#### ESLint : `no-restricted-globals` sur `fetch` dans hooks

Ajouter dans `.eslintrc.cjs` (ou fichier équivalent) override sur `src/hooks/**/*.{ts,tsx}`.

**Rev1 note** : `no-restricted-globals` ne bloque pas `window.fetch(...)` explicit. Si futur contournement via `window.fetch`, ajouter `no-restricted-properties` sur `window.fetch`. Pour ce batch P0, on laisse la règle standard ; CI grep planifiée post-batch si signal.

Allowlist via `// eslint-disable-next-line no-restricted-globals -- <raison>` :
- `useApiConnectivity.ts:17` — health endpoint public (`/health`), sans auth by design.
- `useServiceHealth.ts:33, 61` — probe cross-origin URLs arbitraires, no-cors mode.

### C2.2 — Tests de régression — **lock P0-7**

Étendre `src/hooks/usePrometheus.test.ts` :

1. `test('usePrometheusQuery calls httpClient.get, not fetch()')`
2. `test('usePrometheusQuery 401 triggers refresh interceptor flow')`
3. `test('usePrometheusRange calls httpClient.get with correct params')`
4. `test('usePrometheus timeout goes through axios not AbortSignal')`

### C2.3 — Commit message

```
fix(ui/hooks): route usePrometheus through httpClient to enable refresh flow

usePrometheus.{Query,Range} called fetch() directly with a raw access_token
captured from useAuth(). After a Keycloak silent renew the captured token
was stale, so Prometheus polls 401'd and showed "unavailable" while the
rest of the app (routing via httpClient + refresh interceptor) kept working.

Fix:
- Replace fetch() with httpClient.get() in 2 sites (Query + Range)
- Drop accessToken capture: request interceptor injects Bearer header
- Axios timeout replaces AbortSignal.timeout (same effect, consistent stack)
- Add ESLint no-restricted-globals on fetch in src/hooks/** with allowlist
  for legitimate unauth usage (useApiConnectivity, useServiceHealth)

Closes: P0-7 (BUG-REPORT-UI-2.md)
```

---

## COMMIT 3 — Path encoding systémique

**Bugs fermés** : P0-6
**Risque** : faible (mechanical + UUID = no-op).

### C3.1 — Nouveau helper

`src/services/http/path.ts` (new) :

```ts
/**
 * Build an absolute URL path from raw path segments.
 * Always returns a leading slash followed by each segment encoded
 * via encodeURIComponent.
 *
 * Pass segments WITHOUT slashes — each segment is treated as a single
 * opaque identifier. A segment containing '/' will be encoded to '%2F'
 * and will NOT create a hierarchical path. Use for interpolating
 * runtime values (tenantId, apiId, slug, etc.) into path templates.
 *
 * Examples:
 *   path('v1', 'tenants', tenantId)               → '/v1/tenants/<enc>'
 *   path('v1', 'tenants', tenantId, 'apis', apiId) → '/v1/tenants/<enc>/apis/<enc>'
 *
 * Query params should still go through axios `params` option (not here).
 */
export function path(...segments: string[]): string {
  return '/' + segments.map(encodeURIComponent).join('/');
}
```

**Rev1 correction C3 docstring** : corrigé la note sur leading slash (toujours préfixé, jamais conditionnel). Règle stricte : ne jamais passer de segment avec slash intentionnel. Si un futur endpoint a un path hiérarchique comme donnée métier, utiliser un helper distinct, pas contourner.

Export depuis `src/services/http/index.ts`.

### C3.2 — Fichiers à migrer (30)

Tous listés par grep `grep -rln '\`/v1/.*\${.*}' src/services/`.

**Domain clients (22)** — tous dans `src/services/api/*.ts` : admin.ts, apis.ts, applications.ts, chat.ts, consumers.ts, contracts.ts, credentialMappings.ts, deployments.ts, gatewayDeployments.ts, gateways.ts, git.ts, llm.ts, monitoring.ts, platform.ts, promotions.ts, session.ts, subscriptions.ts, tenants.ts, toolPermissions.ts, traces.ts, webhooks.ts, workflows.ts.

**Siblings legacy (7)** — `src/services/*Api.ts` + `*Service.ts` : backendApisApi.ts, diagnosticService.ts, errorSnapshotsApi.ts, externalMcpServersApi.ts, federationApi.ts, mcpConnectorsApi.ts, mcpGatewayApi.ts, proxyBackendService.ts.

**Core** : `src/services/http/sse.ts` — `${tenantId}` + eventTypes query (sera remplacé complètement par C4, mais C3 prépare le URL).

### C3.3 — Exemple de migration (`tenants.ts`)

```ts
// AVANT
const { data } = await httpClient.get(`/v1/tenants/${tenantId}`);

// APRÈS
import { path } from '../http';
const { data } = await httpClient.get(path('v1', 'tenants', tenantId));
```

### C3.4 — `sse.ts` (cas spécifique avant C4)

```ts
// AVANT
export function createEventSource(tenantId: string, eventTypes?: string[]): EventSource {
  const params = eventTypes ? `?event_types=${eventTypes.join(',')}` : '';
  const url = `${config.api.baseUrl}/v1/events/stream/${tenantId}${params}`;
  return new EventSource(url);
}

// APRÈS C3 (avant refactor C4)
import { path } from './path';
export function createEventSource(tenantId: string, eventTypes?: string[]): EventSource {
  const search = new URLSearchParams();
  if (eventTypes?.length) search.set('event_types', eventTypes.join(','));
  const qs = search.toString();
  const url = `${config.api.baseUrl}${path('v1', 'events', 'stream', tenantId)}${qs ? '?' + qs : ''}`;
  return new EventSource(url);
}
```

**Rev1 correction C3 URLSearchParams note** : `URLSearchParams.set('event_types', 'a,b')` encodera la virgule en `%2C` dans la sérialisation `toString()`. Le backend reçoit la valeur décodée `a,b`, le flow est correct. Note précédente (« le `,` n'a pas besoin d'encoding et `set()` le laisse passer ») **était inexacte** : `set()` ne passe pas le `,` en clair, `toString()` l'encode. Pas d'impact fonctionnel, juste correction de commentaire.

### C3.5 — Tests de régression — **lock P0-6**

Nouveau fichier : `src/services/http/path.test.ts`.

1. `test('path() encodes special characters in segments')`
2. `test('path() is no-op on UUID segments')`
3. `test('path() handles empty segments')`

Étendre `src/test/services/api/ui2-s2a-clients.test.ts` (ou équivalent) :

4. `test('tenantsClient.get encodes tenantId via path helper')`
5. `test('sse createEventSource encodes tenantId in URL')`

### C3.6 — Commit message

```
refactor(ui/services): systematize URL path encoding via helper

30 files interpolated runtime values (tenantId, apiId, slug, etc.) into URL
paths without encodeURIComponent. UUID-only IDs today, but any future slug
or email in a path segment = injection vector (/, ?, #, unicode). Pattern
was inconsistent: mcpGatewayApi.ts already encoded toolName, others didn't.

Fix:
- Add src/services/http/path.ts helper: path(...segments) → '/enc1/enc2'
- Export from services/http/index.ts (single HTTP surface)
- Migrate 22 domain clients + 7 siblings + sse.ts to use helper
- URLSearchParams for sse.ts event_types query (toString() encodes comma
  to %2C, backend decodes back to 'a,b' — round-trip verified)
- path.test.ts covers 3 encoding scenarios (special, UUID, empty)

Closes: P0-6 (BUG-REPORT-UI-2.md)
```

---

## COMMIT 4 — SSE polyfill (fetch-event-source) avec custom fetch + refresh actif

**Bugs fermés** : P0-4, P0-5, P0-8
**Risque** : moyen — ajoute dépendance npm + remplace `EventSource` + consomme le helper refresh de C1.
**Backend decision** : **résolue** (ARB-4) — Option D polyfill.
**Rev1 corrections** : headers callback → custom authFetch ; 401 → déclenche refresh actif (helper C1) ; eventTypesKey → JSON.stringify ; `handleEvent` accepte EventLike (zéro cast).

### C4.1 — Dépendance npm

```
npm install @microsoft/fetch-event-source
```

Zéro dependency transitive.

### C4.2 — Refactor `src/services/http/sse.ts` — **Rev1 design**

```ts
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { getAuthToken, clearAuthToken } from './auth';
import { refreshAuthTokenWithTimeout } from './refresh';
import { config } from '../../config';
import { path } from './path';

export interface SseConnection {
  close(): void;
}

export interface SseEvent {
  data: string;
  event?: string;
  id?: string;
}

export interface SseHandlers {
  onMessage: (event: SseEvent) => void;
  onOpen?: () => void;
  onError?: (error: unknown) => void;
}

/**
 * Custom fetch wrapper that re-reads getAuthToken() at each retry.
 * fetch-event-source's `headers` option is a static Record<string,string>
 * captured once at init; using a custom `fetch` is the only way to re-read
 * the token on each network call.
 */
function authFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  const token = getAuthToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  } else {
    headers.delete('Authorization');
  }
  return fetch(input, { ...init, headers });
}

class RetriableError extends Error {}
class FatalError extends Error {}

export function openEventStream(
  tenantId: string,
  eventTypes: string[] | undefined,
  handlers: SseHandlers
): SseConnection {
  const controller = new AbortController();
  const search = new URLSearchParams();
  if (eventTypes?.length) search.set('event_types', eventTypes.join(','));
  const qs = search.toString();
  const url = `${config.api.baseUrl}${path('v1', 'events', 'stream', tenantId)}${qs ? '?' + qs : ''}`;

  fetchEventSource(url, {
    signal: controller.signal,
    fetch: authFetch,
    openWhenHidden: false,
    onopen: async (response) => {
      if (response.ok) {
        handlers.onOpen?.();
        return;
      }
      if (response.status === 401) {
        // Attempt a real refresh (coalesced via shared queue). On success,
        // throw RetriableError so the lib retries with the refreshed token.
        try {
          await refreshAuthTokenWithTimeout();
          throw new RetriableError(`SSE 401 — retrying after refresh`);
        } catch (err) {
          if (err instanceof RetriableError) throw err;
          // Refresh failed — clear auth and stop retrying.
          clearAuthToken();
          throw new FatalError(`SSE auth refresh failed: ${String(err)}`);
        }
      }
      if (response.status >= 400 && response.status < 500) {
        throw new FatalError(`SSE rejected: ${response.status}`);
      }
      throw new RetriableError(`SSE transient failure: ${response.status}`);
    },
    onmessage: (msg) => {
      handlers.onMessage({ data: msg.data, event: msg.event, id: msg.id });
    },
    onerror: (err) => {
      handlers.onError?.(err);
      if (err instanceof FatalError) {
        throw err; // stops retry loop
      }
      // Default: return undefined → lib retries with backoff.
    },
  }).catch((err) => {
    handlers.onError?.(err);
  });

  return {
    close: () => controller.abort(),
  };
}
```

### C4.3 — Refactor `src/hooks/useEvents.ts` — **Rev1 design**

```ts
import { useEffect, useCallback, useRef, useState, useMemo } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { openEventStream, type SseConnection, type SseEvent } from '../services/http/sse';
import type { Event } from '../types';

interface UseEventsOptions {
  tenantId: string;
  eventTypes?: string[];
  onEvent?: (event: Event) => void;
  enabled?: boolean;
}

export function useEvents({ tenantId, eventTypes, onEvent, enabled = true }: UseEventsOptions) {
  const queryClient = useQueryClient();
  const connectionRef = useRef<SseConnection | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [lastError, setLastError] = useState<unknown>(null);

  // Rev1 — stabilize eventTypes via JSON.stringify (robust even if types contain commas)
  const eventTypesKey = useMemo(() => JSON.stringify(eventTypes ?? []), [eventTypes]);
  const stableEventTypes = useMemo(
    () => eventTypes ?? [],
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional content-based stabilization
    [eventTypesKey]
  );

  // Rev1 — accept EventLike (no unsafe cast to MessageEvent)
  const handleEvent = useCallback(
    (event: SseEvent) => {
      try {
        const data = JSON.parse(event.data) as Event;
        onEvent?.(data);
        switch (data.type) {
          case 'api-created':
          case 'api-updated':
          case 'api-deleted':
            queryClient.invalidateQueries({ queryKey: ['apis', tenantId] });
            break;
          case 'deploy-started':
          case 'deploy-progress':
          case 'deploy-success':
          case 'deploy-failed':
            queryClient.invalidateQueries({ queryKey: ['deployments', tenantId] });
            queryClient.invalidateQueries({ queryKey: ['apis', tenantId] });
            break;
          case 'app-created':
          case 'app-updated':
          case 'app-deleted':
            queryClient.invalidateQueries({ queryKey: ['applications', tenantId] });
            break;
          case 'tenant-created':
          case 'tenant-updated':
            queryClient.invalidateQueries({ queryKey: ['tenants'] });
            break;
        }
      } catch (error) {
        console.error('Failed to parse event:', error);
      }
    },
    [queryClient, tenantId, onEvent]
  );

  useEffect(() => {
    if (!enabled || !tenantId) return;

    const connection = openEventStream(tenantId, stableEventTypes, {
      onOpen: () => {
        setIsConnected(true);
        setLastError(null);
      },
      onMessage: handleEvent,
      onError: (err) => {
        setIsConnected(false);
        setLastError(err);
      },
    });
    connectionRef.current = connection;

    return () => {
      connection.close();
      connectionRef.current = null;
      setIsConnected(false);
    };
  }, [tenantId, enabled, handleEvent, stableEventTypes]);

  return {
    close: () => connectionRef.current?.close(),
    isConnected,
    lastError,
  };
}
```

### C4.4 — Impact sur `src/services/api.ts` (façade)

Supprime `createEventSource` sur le service + son import. Seul caller (`useEvents.ts`) migré dans ce même commit.

### C4.5 — Tests de régression — **lock P0-4, P0-5, P0-8**

Nouveau fichier : `src/services/http/sse.test.ts`.

1. `test('authFetch injects Authorization Bearer header from getAuthToken')`
2. `test('authFetch re-reads token on subsequent calls')` — LOCK P0-5. Setup 2 tokens séquentiels, vérifier que le 2nd fetch envoie le nouveau.
3. `test('authFetch deletes Authorization when no token set')`
4. `test('openEventStream URL-encodes tenantId')` — double-guard P0-6.
5. `test('close() aborts the fetchEventSource connection')`.
6. **Rev1 lock** `test('onopen 401 triggers refreshAuthTokenWithTimeout before retry')` — mock `refreshAuthTokenWithTimeout`, simuler 401 dans `onopen`, vérifier l'appel helper + throw RetriableError.
7. `test('onopen 401 with refresh failure throws FatalError')` — mock helper rejects, vérifier pas de retry loop.

Extension `src/hooks/useEvents.test.ts` :

8. `test('useEvents stable across re-renders when eventTypes content unchanged')` — LOCK P0-8. Render avec `['a', 'b']`, re-render avec `['a', 'b']` literal fresh → `openEventStream` appelé **une fois**.
9. `test('useEvents re-opens stream when eventTypes content changes')` — complément.
10. `test('useEvents exposes isConnected = true on onOpen')`
11. `test('useEvents exposes lastError on onError')`
12. `test('handleEvent receives SseEvent shape (no MessageEvent cast)')` — LOCK Rev1.

### C4.6 — Commit message

```
fix(ui/sse): replace EventSource with fetch-event-source + active refresh on 401

EventSource (DOM native) cannot send custom headers. Backend
/v1/events/stream/:tenant_id requires Authorization: Bearer via HTTPBearer
(see control-plane-api/src/auth/dependencies.py:78). In prod, VITE_API_URL
is cross-origin (api.gostoa.dev ← console.gostoa.dev), no cookie session
→ SSE silently 401-looped since rewrite. useDeployEvents (Deployments.tsx
live progress) was broken; page fell back to loadHistoricalLogs polling.

Additionally:
- After Keycloak silent renew, EventSource kept the original URL and could
  not use the new token (no reconnect logic).
- useEvents's eventTypes array dep was identity-sensitive, any caller
  passing an inline literal would rebuild SSE on every render.

Fix:
- Add @microsoft/fetch-event-source (~3KB gz, Microsoft-maintained)
- Rewrite sse.ts: openEventStream(tenantId, eventTypes, handlers) returns
  SseConnection with close(). Custom fetch wrapper (authFetch) re-reads
  getAuthToken() on each network call (retries included) — the lib's
  headers option is static, so a custom fetch is required.
- onopen(401) actively triggers refreshAuthTokenWithTimeout() (helper
  exported by C1), then throws RetriableError to trigger a retry with the
  refreshed token. RetriableError / FatalError discriminate transient vs
  permanent failures.
- useEvents: migrate to SseConnection, expose isConnected + lastError,
  stabilize eventTypes via JSON.stringify(contents) memo key, accept
  SseEvent shape directly (drop unsafe MessageEvent cast).
- Remove apiService.createEventSource façade (single caller migrated).
- sse.test.ts: 7 regression tests (auth header, token refresh, encoding,
  abort, 401 refresh flow, FatalError path).
- useEvents.test.ts: 5 new tests (eventTypes stability, state, event shape).

Closes: P0-4, P0-5, P0-8 (BUG-REPORT-UI-2.md)
```

---

## Callers à adapter — récap exhaustif

### Par commit

| Commit | Fichiers source modifiés | Fichiers test modifiés / créés |
|---|---|---|
| C1 | `refresh.ts`, `api.ts`, `mcpGatewayApi.ts`, `AuthContext.tsx`, `config.ts`, `http/index.ts` | **NEW**: `refresh.test.ts` ; `api.test.ts` |
| C2 | `usePrometheus.ts`, `.eslintrc.cjs`, `useApiConnectivity.ts`, `useServiceHealth.ts` | Extension `usePrometheus.test.ts` |
| C3 | `path.ts` (NEW), `http/index.ts`, 29 domain/sibling clients, `sse.ts` | **NEW**: `path.test.ts` ; extension `ui2-s2{a,b,c,d}-clients.test.ts` |
| C4 | `sse.ts` (remplacé), `useEvents.ts`, `api.ts` (remove createEventSource) | **NEW**: `sse.test.ts` ; extension `useEvents.test.ts` |

---

## Risques identifiés

(R-1 à R-8 inchangés depuis v0, voir §Risques original. Ajout Rev1 ci-dessous.)

### R-9 — Helper refresh consumed by SSE loop if refresh hangs on server side (C4)

**Probabilité** : moyenne si Keycloak est lent.
**Impact** : `onopen(401)` appelle `refreshAuthTokenWithTimeout()` qui timeout après 30s → throw → FatalError → retry loop stoppé → app perd SSE jusqu'au remount. Mais pas de boucle infinie.
**Mitigation** : FatalError arrête `fetchEventSource` ; user action (re-nav) remount le hook et retry. Comportement acceptable.

---

## Recommandation ordre & split

**Recommandé** : 4 commits dans l'ordre **C1 → C2 → C3 → C4** — ordre **strict** désormais car C4 consomme le helper exporté par C1.

Raisons :
- C1 débloque tout (core refresh + helper exporté + single source of truth + tests).
- C2 est un petit fix rapide qui valide indirectement C1.
- C3 est mechanical, peut être fait en parallèle de C2 sans conflit.
- C4 nécessite C1 mergé (import `refreshAuthTokenWithTimeout`).

---

## Validation Phase 3 (checklist)

Post-C4, exécuter :

1. `npx tsc --noEmit` dans `control-plane-ui/` → 0 erreur.
2. `npx vitest run` → tous tests passent, **dont les 19+ nouveaux regression guards**.
3. `npx eslint .` → 0 nouvelle erreur ; nouvelle rule respectée.
4. `npm run build` → succès, bundle size `du -sh dist/assets/*.js` ±5% baseline.
5. **Smoke test manuel** (obligatoire — criticité refresh + SSE actif) :
   - `npm run dev` local avec Keycloak staging + session courte (2 min).
   - Page Deployments avec un déploiement en cours → events SSE arrivent.
   - Laisser 1 onglet ouvert, attendre silent renew → SSE continue de recevoir events.
6. Mettre à jour `BUG-REPORT-UI-2.md` — marquer P0-1..P0-10 **STATUS: FIXED commit <SHA>**.

---

## Livrable Phase 1 + Rev1

Ce fichier (`FIX-PLAN-UI2-P0.md`) intègre les 5 corrections du challenger (2026-04-24). **GO Phase 2**.
