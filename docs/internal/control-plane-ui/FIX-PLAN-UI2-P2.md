# FIX-PLAN-UI2-P2 — Phase 1 (plan only, NO code)

> **Source** : `BUG-REPORT-UI-2.md` — 12 P2 findings (Medium).
> **Branche** : `fix/ui-2-p2-batch` depuis `fix/ui-2-p1-batch` (P0 mergé `#2514`, P1 PR pas encore mergée).
> **Worktree** : `/Users/torpedo/hlfh-repos/stoa-ui-2-fix` (même que P0/P1).
> **Méthode** : Plan → **STOP** → Phase 2 (code) après validation user.
> **Référence P0** : 4 commits — C1 `a88c98902`, C2 `7c773c888`, C3 `95fafa8ea`, C4 `7bddb1501`.
> **Référence P1** : 4 commits — C4 `1a559d58d`, C2 `9e50961a7`, C3 `82910bd35`, C1 `73eee66f9`.
> **Rev1 (2026-04-24)** : 6 corrections user intégrées (cf. §Rev1 en bas du fichier).

---

## Résumé exécutif

**Objectif** : fermer le module UI-2 (38 findings). 12 items P2 à traiter.

| Classe | Items | Action |
|---|---|---|
| **Already fixed** | P2-3, P2-10 | Skip (anti-redondance P0/P1) |
| **Code fix** | P2-1, P2-5, P2-6, P2-8, P2-9 | 1 commit unique (sweep défensif) |
| **Documented / WONT-FIX** | P2-2, P2-4, P2-7 | Comment blocks dans source, pas de refacto |
| **Deferred to UI-3 cleanup** | P2-11, P2-12 | Ticket Linear + référence dans `REWRITE-PLAN.md` |

**Plan de commit** : **1 seul commit** `refactor(ui/services): close P2 cleanup batch (5 findings)` — les 5 fixes tiennent dans une seule intervention défensive cohérente (~50-80 LOC net + 3 tests canary max). P2-2, P2-4, P2-7 = comment-only (pas de commit séparé). P2-11/P2-12 = action Linear, pas de code.

---

## Anti-redondance avec P0 et P1 — détail

| P2 | Status | Proof | Verification |
|---|---|---|---|
| **P2-3** `mcpGatewayService.setAuthToken`/`clearAuthToken` no-ops | **CLOSED by P0-C1 (`a88c98902`)** | `grep setAuthToken\|clearAuthToken src/services/mcpGatewayApi.ts` → 0 hit. AuthContext n'appelle plus `mcpGatewayService.setAuthToken(token)`. | ✓ lu |
| **P2-10** `gateways.ts:86` URL params inline | **CLOSED by P1-C2 (`9e50961a7`) — P1-11 residu sweep** | `src/services/api/gateways.ts:85-90` utilise `params: { limit }` option axios (+ commentaire `// P1-11 residu`). Plus d'interpolation inline. | ✓ lu |

Restent **10 P2 ouverts** : P2-1, P2-2, P2-4, P2-5, P2-6, P2-7, P2-8, P2-9, P2-11, P2-12.

---

## Fiches des 12 P2

### P2-1 — `interceptors.ts` error callback sans friendly-error — **OPEN**

- **Résumé** : le response interceptor applique `applyFriendlyErrorMessage` côté error (via `refresh.ts`), le request interceptor se contente de `(error) => Promise.reject(error)`. Cas rare (échec de transformation de la config de requête) mais inconsistent.
- **Fichier:ligne** : `src/services/http/interceptors.ts:13`
- **Check anti-redondance** : OPEN. P0-C1 n'a pas touché au request interceptor.
- **Approche de fix** : remplacer `(error) => Promise.reject(error)` par `(error) => { applyFriendlyErrorMessage(error); return Promise.reject(error); }`. Import `applyFriendlyErrorMessage` depuis `./errors`.
- **Régression guard** : trivial, 1 test unit sur `interceptors.test.ts` (ou nouveau) : injecter un error dans la request interceptor chain via `httpClient.interceptors.request.use` simulé → vérifier que le message utilisateur est décoré.

---

### P2-2 — Axios re-submit `originalRequest` sans clone — **WONT-FIX (documenté)**

- **Résumé** : `refresh.ts:100` `return instance(originalRequest)` passe le même objet config à axios. Les transformers axios peuvent muter `data`/`headers`/`params` ; un retry pourrait théoriquement double-transformer.
- **Fichier:ligne** : `src/services/http/refresh.ts:100`
- **Check anti-redondance** : OPEN mais plus subtil qu'à l'audit. P0-C1 a déjà ajouté `originalRequest._retry = true` (cette mutation est idempotente). La ligne 100 reste le seul replay path.
- **Approche de fix** : **WONT-FIX** — axios 1.x applique les transformers une fois, documenté dans sa doc (`transformRequest` s'exécute à l'envoi, pas à la retry). La `RetriableConfig` ne subit pas de double transform en pratique. Cloner `originalRequest` introduirait plus de risques que de bénéfices (perte des metadatas axios internes, cassure du type `AxiosRequestConfig`).
- **Action** : ajouter un bloc commentaire 3-5 lignes au-dessus de `refresh.ts:100` expliquant pourquoi on ne clone pas (ancrage de décision pour futur mainteneur).
- **Régression guard** : 1 test unit dans `refresh.test.ts` : requête initiale avec `data: { foo: 1 }`, trigger 401 → refresh → replay → vérifier que le body sérialisé reçu par l'adapter est toujours `'{"foo":1}'` (pas `'{\"foo\":1}'` double-encoded). Lock la stabilité du comportement axios.

---

### P2-3 — `mcpGatewayService.setAuthToken`/`clearAuthToken` no-ops — **ALREADY FIXED**

- **Résumé** : les 2 méthodes no-op supprimées dans P0-C1.
- **Fichier:ligne** : `src/services/mcpGatewayApi.ts:210-216` (historique) — aujourd'hui absent.
- **Check anti-redondance** : **CLOSED by P0-C1 (`a88c98902`)**. Vérifié par `grep setAuthToken src/services/mcpGatewayApi.ts` (0 hit). AuthContext n'appelle plus les 2 méthodes (voir `a88c98902` commit body).
- **Approche de fix** : aucune — skip.

---

### P2-4 — `accessToken` exposé dans le React context — **WONT-FIX (documenté)**

- **Résumé** : `AuthContext.tsx:23, 256, 264, 275` exposent `accessToken: string | null` au context React. Tout composant enfant peut lire via `useAuth().accessToken`. Volontaire pour Grafana iframe, mais surface d'attaque : une extension navigateur, widget analytique, ou dep compromise qui lit le context peut exfiltrer le JWT brut.
- **Fichier:ligne** : `src/contexts/AuthContext.tsx:23` (interface), `:256, 264, 275` (value)
- **Check anti-redondance** : OPEN. Pas touché par P0/P1 (délibéré).
- **Arbitrage** : 3 options explorées dans l'énoncé :
  - **(a) Wrapper `useGrafanaToken()`** avec doc : déplace la surface mais ne la réduit pas (un composant malveillant importerait le hook).
  - **(b) Accept + doc renforcée** : actuel + ADR. Rien de nouveau.
  - **(c) Fix réel : backend signe l'URL Grafana** : nécessite endpoint backend (`POST /v1/grafana/signed-url` → `{url, exp}`), scope auth backend, modif du Grafana iframe component. Out-of-scope pour un P2 UI-only.
- **Décision** : **WONT-FIX pour le scope P2 UI**, option (c) est la bonne mais nécessite ticket dédié cross-stack (`CAB-grafana-signed-url`).
- **Action** :
  - Ajouter un commentaire JSDoc renforcé sur `accessToken` dans l'interface `AuthContextType` (mention des 2 seuls consumers légitimes : Grafana iframe + future signed URL flow).
  - Grep des consumers pour s'assurer que seuls 1-2 fichiers lisent `accessToken` (attendu : `GrafanaIframe.tsx`, éventuellement `useGrafanaIframe.ts`). Documenter la liste dans le commentaire.
  - Créer un ticket Linear de follow-up : **`UI-3-grafana-signed-url`** (P2, cross-stack) pour supprimer l'exposition à terme.
- **Régression guard** : 1 test `AuthContext.accessToken.consumers.test.ts` qui parse les imports du dossier `src/` et vérifie que `useAuth()` n'est pas lu pour son `accessToken` hors whitelist (test "garde-fou" qui fail si un nouveau consumer apparaît). **Optionnel** — coût de faux-positifs si trop strict. Alternative : 1 test statique basique (compile-only).

---

### P2-5 — `useServiceHealth` catch generic + pas de distinction AbortError — **OPEN**

- **Résumé** : `useServiceHealth.ts:78` `} catch { setStatus('unavailable'); }` swallow toute erreur. Un `AbortError` (fetch cancelled par le timeout ou par un unmount) est traité comme "service down" → faux-positif UI.
- **Fichier:ligne** : `src/hooks/useServiceHealth.ts:78` (probe principale), voir aussi `:25-26, 61` (AbortController setup).
- **Check anti-redondance** : OPEN. P0-C2 n'a touché qu'à `usePrometheus` (et a whitelisté `useServiceHealth` pour l'ESLint fetch ban, voir `9e50961a7` commit body).
- **Approche de fix** : typer le catch et distinguer `AbortError` :
  ```ts
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') return; // intentional cancel
    setStatus('unavailable');
  }
  ```
  Appliquer aux 2-3 sites du hook (ligne 78 + éventuel autre catch plus bas).
- **Régression guard** : 1 test unit : créer un `AbortController`, appeler le hook, abort avant timeout → vérifier que `status` reste `'checking'` ou `'available'` (pas `'unavailable'`).

---

### P2-6 — `useServiceHealth` fetch non-abort sur unmount — **OPEN**

- **Résumé** : l'`AbortController` est scoped à l'appel (ligne 25-26), pas à l'effect. À l'unmount, le fetch continue jusqu'au timeout 5s, puis fait un `setState` sur composant démonté (warning React).
- **Fichier:ligne** : `src/hooks/useServiceHealth.ts:25-26, 61`, `useEffect` wrapper à localiser.
- **Check anti-redondance** : OPEN. Lien étroit avec P2-5 — fix conjointement.
- **Approche de fix** :
  - Lever l'`AbortController` au niveau du `useEffect`.
  - `return () => { controller.abort(); clearTimeout(timeoutId); }` dans le cleanup.
  - Cumuler avec le fix P2-5 : le catch détecte `AbortError` → skip le setState.
  - Bonus défensif : `mountedRef` en fallback (pattern déjà utilisé dans `AuthContext` post-P1-C3).
- **Régression guard** : 1 test unit : render `useServiceHealth`, unmount avant fin du timeout → vérifier qu'aucun `setState` n'est appelé post-unmount (spy React console.error). **Combiné avec P2-5** = 1 seul test au total pour les deux (scénario "abort on unmount").

---

### P2-7 — Module-scope mutable state exposé via getters publics — **WONT-FIX (documenté)**

- **Résumé** : `src/services/http/auth.ts:26-29` déclare `authToken`, `tokenRefresher`, `isRefreshing`, `refreshQueue` en module-scope mutable, exporte `getIsRefreshing`, `setIsRefreshing`, `enqueueRefresh`, `drainRefreshQueue` côté public. Nécessaire pour le split code refresh/auth/interceptors, mais ouvre la porte à corruption accidentelle (un module tiers pourrait `setIsRefreshing(true)` sans enqueue).
- **Fichier:ligne** : `src/services/http/auth.ts:26-29`, `:31-80` pour les exports.
- **Check anti-redondance** : OPEN. P0-C1 a stabilisé les sémantiques mais n'a pas encapsulé.
- **Arbitrage** : 3 options explorées :
  - **(a) Namespace class `RefreshStateManager`** : encapsule le state, expose `getInstance()` via singleton. Migration = modifier 3-4 fichiers (`refresh.ts`, `interceptors.ts`, `api.ts` éventuellement). ~40 LOC refacto.
  - **(b) Closure IIFE** : même état mais via `const state = (() => { let isRefreshing = false; return { get: ..., set: ..., enqueue: ... }; })();`. Moins verbeux que (a).
  - **(c) WONT-FIX + comment block** : conserver le design actuel + bloc doc en tête du fichier qui documente l'intent ("exports are internals for `services/http/*`, consumer modules outside `services/http/**` should NEVER import these").
- **Décision** : **(c) WONT-FIX**. Raisons :
  - Refacto (a) ou (b) = 40 LOC non-cosmétiques sur un chemin critique (auth) → risque > bénéfice pour un P2.
  - L'ESLint rule `no-restricted-imports` posée par P0-C2 limite déjà les imports d'axios hors `services/http/**`. Ajouter une rule similaire pour `./auth` exports internals = meilleur ROI.
  - La protection réelle n'est pas "encapsulation au runtime" mais "lint rule à l'import" — déjà partiellement en place.
- **Action** :
  - Ajouter un bloc commentaire en tête de `auth.ts` explicitant : "These exports are internals of `services/http/*`. Do not import outside this module. Use the façade `apiService` for consumer code."
  - Ajouter une règle ESLint `no-restricted-imports` sur `src/services/http/auth.ts` → bannir l'import depuis `src/**` sauf `src/services/http/**` et `src/services/api.ts`. Whitelist via path pattern dans `.eslintrc.cjs`.
- **Régression guard** : trivial, pas de test dédié (la règle ESLint est son propre test — un import illicite casse le build).

---

### P2-8 — `useEvents` JSON.parse cast `as Event` sans schema — **OPEN**

- **Résumé** : `useEvents.ts:32` fait `const data = JSON.parse(event.data) as Event;` puis un `switch (data.type)`. Si le backend envoie un event mal formé ou un type inconnu, le cast aveugle peut crash le callback utilisateur (ligne 33, `onEvent?.(data)`). Le `try/catch` autour (L58-62) attrape le `JSON.parse` throw mais pas une propriété manquante.
- **Fichier:ligne** : `src/hooks/useEvents.ts:32`, switch `:33-56`
- **Check anti-redondance** : OPEN. P0-C4 a refactoré les handlers SSE mais gardé le cast brut.
- **Arbitrage** : 2 options :
  - **(a) Zod schema** : ajoute ~3KB bundle (Zod) + définition schema discriminated union. Overkill pour un P2.
  - **(b) Type guard manuel minimal** : `function isValidEvent(x: unknown): x is Event { return !!x && typeof x === 'object' && 'type' in x && typeof (x as { type: unknown }).type === 'string'; }`. Fail-fast si malformed.
- **Décision** : **(b)** — type guard manuel. Zod n'est pas présent dans le projet côté runtime (pas dans package.json frontend sauf vérif) ; l'ajouter pour un seul site = mauvais ROI. Le type guard manuel couvre 95% des régressions (data.type absent ou non-string = cause la plus probable de crash).
- **Approche de fix** :
  ```ts
  const parsed: unknown = JSON.parse(event.data);
  if (!isValidEvent(parsed)) {
    console.warn('SSE: dropped event with unexpected shape', parsed);
    return;
  }
  onEvent?.(parsed);
  switch (parsed.type) { ... }
  ```
- **Régression guard** : 1 test unit : simuler `SseEvent` avec `event.data = '{"foo": "bar"}'` (pas de `type`) → vérifier qu'aucun `onEvent` n'est invoqué et qu'aucun `queryClient.invalidateQueries` ne fire. Lock le comportement fail-safe.

---

### P2-9 — Console logs résiduels en prod — **OPEN**

- **Résumé** : 2 `console.warn`/`console.error` restants dans le code runtime (post-P1) :
  - `src/hooks/useEvents.ts:60` — `console.error('Failed to parse event:', error);`
  - `src/contexts/AuthContext.tsx:106` — `console.warn('Failed to decode access_token for roles', e);`
- **Fichier:ligne** : voir ci-dessus.
- **Check anti-redondance** : OPEN. P0/P1 n'ont pas touché.
- **Arbitrage** : 2 options :
  - **(a) Logger pivotable** : nouvelle dep ou nouveau module `src/utils/logger.ts` avec `logger.warn/error`. Filter `import.meta.env.DEV` au runtime. Pattern scalable mais nécessite migration tout le codebase à terme.
  - **(b) Garde minimale via `import.meta.env.DEV`** : `if (import.meta.env.DEV) console.warn(...)` inline aux 2 sites. Zéro dep, ROI immédiat pour un P2.
- **Décision** : **(b)** + note de suivi dans un ticket Linear pour l'option (a) (scaler progressivement).
- **Approche de fix** :
  ```ts
  // useEvents.ts:60
  if (import.meta.env.DEV) console.error('Failed to parse event:', error);

  // AuthContext.tsx:106
  if (import.meta.env.DEV) console.warn('Failed to decode access_token for roles', e);
  ```
  **Note** : les logs d'erreur utiles (P1-5 decodeJwtPayload throw explicite déjà plus propre) restent dans le flow Error Boundary ; cette modif ne coupe que le **noise silencieux** en prod.
- **Régression guard** : 1 test unit : avec `vi.stubEnv('DEV', false)` (ou `vi.stubGlobal`), déclencher le catch → vérifier `console.warn` n'est pas appelé. **Optionnel** : cost-benefit probablement négatif pour 2 sites. **Décision** : pas de test dédié, lint-only suffit.

---

### P2-10 — `gateways.ts:86` URL params inline — **ALREADY FIXED**

- **Résumé** : P1-11 residu sweep par P1-C2.
- **Fichier:ligne** : `src/services/api/gateways.ts:85-90` — utilise désormais `params: { limit }` option axios.
- **Check anti-redondance** : **CLOSED by P1-C2 (`9e50961a7`)** — commentaire inline `// P1-11 residu: use axios params option rather than inline template string.`
- **Approche de fix** : aucune — skip.

---

### P2-11 — REWRITE-BUGS.md absent (zombies UI-3) — **DEFERRED to Linear ticket**

- **Résumé** : `REWRITE-PLAN.md §A.2` engage à produire `REWRITE-BUGS.md` listant les ~40 méthodes zombies (domain clients `src/services/api/*`) co-localisées. Fichier absent du repo.
- **Fichier:ligne** : N/A (fichier manquant).
- **Check anti-redondance** : OPEN (process, pas de code).
- **Arbitrage** : 3 options listées dans l'audit §D.1 :
  - **(a) Ticket Linear `UI-3-cleanup`** avec la liste des zombies + absorber P2-12 (les 17 sites `any`). Recommandation audit.
  - **(b) Créer `REWRITE-BUGS.md`** dans `control-plane-ui/` avec la liste dans ce batch.
  - **(c) Skip** — process, pas du code.
- **Décision** : **(a) ticket Linear `UI-3-cleanup`**. Raisons :
  - Audit §D.1 recommande explicitement (3), aligné avec (a) ici.
  - `REWRITE-BUGS.md` dans le repo deviendrait rapidement obsolète (pas de discipline de maintenance). Linear est la source de vérité pour le backlog, pas un fichier markdown.
  - Absorption P2-12 : ticket cross-fait (typer les 17 `any`) + zombies est cohérent (tout UI-3 cleanup).
- **Action** :
  - Créer ticket Linear : **`UI-3 — Cleanup: remove zombie domain methods + type `any` in gateways/deployments`** (team ID `624a9948-a160-4e47-aba5-7f9404d23506`, label `component:control-plane-ui`, priority `P2`).
  - Description :
    - Source : `REWRITE-PLAN.md §A.2` + `BUG-REPORT-UI-2.md P2-11 + P2-12`.
    - Liste des zombies : à produire via `grep -l "^export (async )?function" src/services/api/*.ts` + diff avec callers réels (grep des imports).
    - Liste des `any` : `grep -n ": any\b\|<any>" src/services/api/gateways.ts src/services/api/gatewayDeployments.ts` (gateways.ts=13, gatewayDeployments.ts=4, total 17).
    - Sub-tasks : (1) audit zombies + removal, (2) typer les 17 `any` via `Schemas['X']` de UI-1, (3) lock CI via lint rule `no-explicit-any` sur `src/services/api/**`.
  - Ajouter référence au ticket dans `REWRITE-PLAN.md` (1 ligne sous §A.2) : `> **Suivi** : zombies + typesafety tracés dans [UI-3 cleanup](<linear-url>).`
- **Régression guard** : N/A (process). Vérif finale : le ticket Linear est créé et la ligne `REWRITE-PLAN.md` existe.

---

### P2-12 — `any` pervasif sur gateways/deployments — **DEFERRED to Linear ticket UI-3**

- **Résumé** : 17 occurrences `any` dans `src/services/api/gateways.ts` (13) + `src/services/api/gatewayDeployments.ts` (4). Dette typesafety reconnue dans `REWRITE-PLAN.md §F.7`. **Note** : l'audit mentionne 19 occurrences (12 + 7) ; le compte courant post-P1 est 13 + 4 = 17 (peut refléter corrections accessoires P1 ou décompte différent).
- **Fichier:ligne** : `src/services/api/gateways.ts` (13 sites), `src/services/api/gatewayDeployments.ts` (4 sites).
- **Check anti-redondance** : OPEN. P0/P1 n'ont pas typé.
- **Arbitrage** : 3 options listées dans l'énoncé :
  - **(a) Typer progressivement via `Schemas['X']` de UI-1 dans ce commit** : nécessite lecture des schemas backend OpenAPI/TS (UI-1 contrat). Risque de divergence schema si les backend schemas ne sont pas complets. 17 sites × 2 types (request, response) = 30-50 LOC, + validation sur les callers (ciblé). **Non négligeable** pour un P2.
  - **(b) Différer en UI-3-cleanup (ticket follow-up)** : aligné avec P2-11. Typage est un projet cohérent avec les zombies (même fichiers touchés).
  - **(c) Accepter comme dette tracée** : sans ticket, la dette devient invisible.
- **Décision** : **(b) différer au ticket UI-3-cleanup** (même ticket que P2-11). Raisons :
  - Typage des 17 sites nécessite revue contract-first avec UI-1 schemas — pas un sweep mécanique.
  - Cohérence avec P2-11 (même fichiers, même rewrite cleanup) : 1 ticket, 1 PR future.
  - L'audit classe P2-12 comme "dette typesafety" pas comme bug bloquant — approprié de le traiter en cycle dédié.
- **Action** : absorber dans le ticket Linear `UI-3 — Cleanup` créé pour P2-11. Mentionner explicitement dans la description. Pas de commit dans ce batch.
- **Régression guard** : N/A.

---

## Plan de commit — **1 commit unique**

### COMMIT C1 — P2 cleanup batch (5 code fixes + 3 commentaires + 1 ESLint rule)

**Bugs fermés par code** : P2-1, P2-5, P2-6, P2-8, P2-9.
**Bugs fermés par documentation inline** : P2-2, P2-4, P2-7 (comment blocks + 1 ESLint rule).
**Bugs déférés (ticket Linear)** : P2-11, P2-12.
**Bugs skipped (already fixed)** : P2-3, P2-10.
**Risque** : faible (sweep défensif, aucune logique critique touchée).

### C1.1 — Modifications de code

#### `src/services/http/interceptors.ts:13` (P2-1)
```ts
(error) => {
  applyFriendlyErrorMessage(error);
  return Promise.reject(error);
}
```
Import `applyFriendlyErrorMessage` depuis `./errors`.

#### `src/services/http/refresh.ts` autour de `:100` (P2-2 WONT-FIX, commentaire)
Bloc commentaire 3-5 lignes :
```ts
// Intentionally passing the same originalRequest reference (no clone).
// Axios 1.x applies transformers once at send-time; the `_retry` flag is
// idempotent and config internals (cancelToken, adapter, etc.) should be
// preserved across replay. Cloning would risk breaking axios invariants.
return instance(originalRequest);
```

#### `src/contexts/AuthContext.tsx:23` (P2-4 WONT-FIX, JSDoc)
```ts
/**
 * Raw Keycloak JWT used by the Grafana iframe auth flow and future
 * signed-URL refactor. Exposed on the context by design — consumers MUST
 * be in the allowlist below. Adding new consumers requires a security
 * review (track token leak surface).
 *
 * Known consumers (2026-04-24):
 * - src/components/GrafanaIframe.tsx (Grafana iframe auth injection)
 *
 * Follow-up: Linear UI-3-grafana-signed-url — replace raw JWT exposure
 * with backend-signed URLs (endpoint TBD).
 */
accessToken: string | null;
```

Vérifier le grep des consumers en Phase 2 (`grep -rln 'accessToken' src/ --include=*.tsx --include=*.ts | xargs grep -l 'useAuth()'`), mettre à jour la liste JSDoc si plus de consumers que prévu.

#### `src/hooks/useServiceHealth.ts` (P2-5 + P2-6 combinés)

Restructurer le `useEffect` :
```ts
useEffect(() => {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 5000);

  const probe = async () => {
    try {
      const response = await fetch(url, { signal: controller.signal, method: 'HEAD', mode: 'no-cors' });
      // ... existing status inference
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      setStatus('unavailable');
    } finally {
      clearTimeout(timeoutId);
    }
  };

  void probe();

  return () => {
    controller.abort(); // unmount-safe cleanup (P2-6)
    clearTimeout(timeoutId);
  };
}, [url]);
```

#### `src/services/http/auth.ts` en tête (P2-7 WONT-FIX, commentaire + ESLint rule)

Bloc commentaire ~8 lignes :
```ts
/**
 * Internal state and getters/setters for the HTTP auth layer.
 *
 * WARNING: exports from this file are INTERNAL to `src/services/http/**`.
 * Do not import them from consumer code (pages, hooks, contexts). Use the
 * façade `apiService` (src/services/api.ts) instead.
 *
 * Enforcement: .eslintrc.cjs `no-restricted-imports` bans this module
 * from consumers.
 *
 * Related: P2-7 (BUG-REPORT-UI-2.md) — encapsulation deferred, lint-level
 * enforcement preferred over runtime class refactor.
 */
```

Ajouter ESLint rule dans `.eslintrc.cjs` (ou fichier équivalent) :
```js
// overrides / rules block
{
  files: ['src/**/*.{ts,tsx}'],
  excludedFiles: ['src/services/http/**', 'src/services/api.ts', 'src/services/**/*.test.ts'],
  rules: {
    'no-restricted-imports': ['error', {
      patterns: [{
        group: ['*/services/http/auth', '*/services/http/refresh', '*/services/http/interceptors'],
        message: 'HTTP auth internals are private to services/http/**. Use apiService façade.',
      }],
    }],
  },
}
```
**Rev-check** : vérifier que la rule ne casse pas P0/P1 tests (`src/__tests__/**` ou `src/test/**`). Whitelist tests explicitement.

#### `src/hooks/useEvents.ts:32` (P2-8)

Ajouter type guard local avant usage :
```ts
function isValidEvent(x: unknown): x is Event {
  return (
    !!x &&
    typeof x === 'object' &&
    'type' in x &&
    typeof (x as { type: unknown }).type === 'string'
  );
}

// handleEvent body:
try {
  const parsed: unknown = JSON.parse(event.data);
  if (!isValidEvent(parsed)) {
    if (import.meta.env.DEV) console.warn('SSE: dropped event with unexpected shape', parsed);
    return;
  }
  onEvent?.(parsed);
  switch (parsed.type) { ... }
} catch (error) {
  if (import.meta.env.DEV) console.error('Failed to parse event:', error);
}
```

**Note** : cumule P2-8 (type guard) + P2-9 (prod-silence via `import.meta.env.DEV`).

#### `src/contexts/AuthContext.tsx:106` (P2-9)

```ts
} catch (e) {
  if (import.meta.env.DEV) console.warn('Failed to decode access_token for roles', e);
}
```

### C1.2 — Tests de régression — **3 tests canary**

1. **`src/services/http/interceptors.test.ts`** (extend or new) : `test('request error path calls applyFriendlyErrorMessage')` — lock P2-1.
2. **`src/hooks/useServiceHealth.test.ts`** (extend) : `test('unmount aborts in-flight probe without triggering setState(unavailable)')` — lock P2-5 + P2-6 combinés.
3. **`src/hooks/useEvents.test.ts`** (extend) : `test('handleEvent drops events missing type field without invoking onEvent')` — lock P2-8.

**Tests écartés** (coût > bénéfice pour un P2 cleanup) :
- P2-2 test refresh.ts body-not-double-transformed (requiert mock adapter custom pour une assertion secondaire).
- P2-4 test statique consumers (risque faux-positifs, mieux traité via code review).
- P2-7 test ESLint rule (la rule est son propre test).
- P2-9 test prod-silence (2 sites, lint-only acceptable).

**Total nouveaux tests C1** : **3 tests canary**.

### C1.3 — Actions Linear (P2-11 + P2-12)

En parallèle du commit, créer **1 ticket Linear** :
- **Titre** : `UI-3 — Cleanup: remove zombie domain methods + type `any` in gateways/deployments`
- **Team** : `624a9948-a160-4e47-aba5-7f9404d23506` (STOA)
- **Label** : `component:control-plane-ui` (via MCP linear `save_issue`)
- **Priority** : `P2`
- **Description** : cf. P2-11 fiche ci-dessus.
- **Référence dans `REWRITE-PLAN.md`** : ajouter 1 ligne sous §A.2 renvoyant à l'URL du ticket.

### C1.4 — Commit message

```
refactor(ui/services): close P2 cleanup batch (5 findings)

Defensive hardening across interceptors, hooks and context. The remaining
3 P2 items (P2-2 axios replay clone, P2-4 accessToken surface, P2-7
module-scope exports) are addressed as documented WONT-FIX with inline
comment blocks + 1 ESLint rule — refactors would introduce risk without
commensurate bug-fixing value.

- P2-1: interceptors request error now calls applyFriendlyErrorMessage
  (consistency with response interceptor).
- P2-5 + P2-6: useServiceHealth distinguishes AbortError from network
  failure AND aborts in-flight probe on unmount via effect-scoped
  AbortController (no more setState on unmounted component).
- P2-8: useEvents adds lightweight type guard on SSE event.data shape —
  drops events with missing/non-string `type` without invoking onEvent or
  triggering query invalidation.
- P2-9: gate 2 residual console.error/warn behind import.meta.env.DEV
  (useEvents.ts, AuthContext.tsx).
- P2-2 (WONT-FIX): inline comment on refresh.ts:100 documenting why
  originalRequest is not cloned across replay (axios 1.x transformer
  semantics + config internals preservation).
- P2-4 (WONT-FIX): reinforced JSDoc on AuthContextType.accessToken with
  explicit consumer allowlist + follow-up reference to UI-3-grafana-signed-url
  ticket for long-term backend-signed URL refactor.
- P2-7 (WONT-FIX): comment block on services/http/auth.ts + ESLint
  no-restricted-imports rule banning http/auth/refresh/interceptors
  imports from consumer code (services/http/** and services/api.ts
  whitelisted).

Deferred to Linear UI-3 cleanup ticket:
- P2-11: REWRITE-BUGS.md zombies list.
- P2-12: `any` typing in gateways.ts (13) + gatewayDeployments.ts (4).

Regression guards: 3 new tests (interceptors request error, useServiceHealth
unmount abort, useEvents malformed event drop).

Closes: P2-1, P2-2, P2-4, P2-5, P2-6, P2-7, P2-8, P2-9 (BUG-REPORT-UI-2.md)
Deferred: P2-11, P2-12 (Linear UI-3 cleanup ticket)
Already-fixed: P2-3 (P0-C1 a88c98902), P2-10 (P1-C2 9e50961a7)
```

---

## Arbitrages — résolus en Phase 1

### ARB-1 — Nombre de commits : **1 seul**

**Retenu** : 1 commit monolithique pour les 8 items P2 open (5 code + 3 doc). Raisons :
- Sweep défensif cohérent (~50-80 LOC net + 3 tests canary) — bien sous la limite 300 LOC.
- Les 3 items doc (P2-2, P2-4, P2-7) sont des commentaires + 1 ESLint rule, pas un refacto — pas de bénéfice à les isoler.
- Review plus simple avec un seul diff couvrant tout le module.

**Rejeté** : 2-3 commits (split code/doc ou split par fichier). Zéro bénéfice review.

### ARB-2 — P2-2 `originalRequest` clone : **WONT-FIX avec commentaire**

**Retenu** : pas de clone. Documenté inline.
**Rejeté** : clone via `{ ...originalRequest }` — risque de casser les invariants axios internes (cancelToken, adapter refs, signal passthrough).

### ARB-3 — P2-4 `accessToken` surface : **WONT-FIX + follow-up ticket**

**Retenu** : JSDoc renforcé + ticket Linear `UI-3-grafana-signed-url` pour fix réel (option c de l'énoncé) à terme.
**Rejeté** : hook wrapper `useGrafanaToken()` — déplace la surface sans la réduire. Pire, crée l'illusion d'une protection.

### ARB-4 — P2-7 module-scope state : **WONT-FIX + ESLint rule**

**Retenu** : comment block + lint rule. Enforcement au lint suffit pour un P2.
**Rejeté** : refacto namespace class / IIFE closure — 40 LOC refacto non-cosmétique sur chemin critique auth. ROI négatif vs risque d'introduire un bug.

### ARB-5 — P2-8 Zod vs type guard : **type guard manuel**

**Retenu** : `isValidEvent(x)` 5 lignes. Zéro nouvelle dep.
**Rejeté** : Zod — pas présent dans le bundle frontend aujourd'hui (à vérifier en Phase 2, mais la supposition est vraie), ajout pour 1 site = mauvais ROI.

### ARB-6 — P2-9 prod-silence : **`import.meta.env.DEV` inline**

**Retenu** : gate minimale aux 2 sites, ~2 lignes touchées.
**Rejeté** : module `src/utils/logger.ts` pivotable — scalable mais hors scope P2 (migration codebase complète).

### ARB-7 — P2-11 / P2-12 REWRITE-BUGS.md + any typing : **Linear ticket UI-3 unique**

**Retenu** : 1 ticket `UI-3 — Cleanup` absorbant les 2 items. Aligné avec audit §D.1 option (3).
**Rejeté** : 
- Créer `REWRITE-BUGS.md` dans le repo (risque de devenir obsolète).
- Typer les 17 `any` dans ce batch (nécessite contract-first review avec UI-1, hors scope P2 sweep).

---

## Risques identifiés

### R-1 — ESLint rule `no-restricted-imports` sur `http/auth.ts` casse tests existants

**Probabilité** : moyenne. Les tests P0/P1 (`refresh.test.ts`, `AuthContext.test.tsx`) importent probablement directement depuis `services/http/auth` ou `refresh`.
**Impact** : build casse.
**Mitigation** : whitelist explicite dans la rule pour `src/**/*.test.ts` + `src/__tests__/**` + `src/services/http/**` + `src/services/api.ts`. Vérifier en Phase 2 par `npm run lint` avant commit.

### R-2 — JSDoc consumer allowlist P2-4 devient obsolète

**Probabilité** : haute (maintenance manuelle à chaque nouveau consumer).
**Impact** : doc stale, surface inconnue.
**Mitigation** : ticket Linear `UI-3-grafana-signed-url` (option c) adresse le fond. Le JSDoc est un stopgap pour 3-6 mois max.

### R-3 — Type guard `isValidEvent` trop permissif

**Probabilité** : faible. Le guard accepte `{ type: 'unknown-string' }` qui passe le switch sans case → fallback silencieux. Acceptable (pattern actuel post-P0).
**Impact** : un event non-géré passe au `onEvent` callback user (qui peut crash sur autre prop).
**Mitigation** : documenter dans le guard que seul le `type: string` est validé ; les callers custom sont responsables de leur propre validation sur les autres props. Alternatif : whitelist les types via un enum (plus strict mais plus lourd à maintenir). **Gardé simple** pour P2.

### R-4 — `import.meta.env.DEV` gate casse en SSR ou worker

**Probabilité** : très faible (CP-UI est une SPA Vite, pas de SSR).
**Impact** : N/A.
**Mitigation** : N/A.

### R-5 — Linear ticket UI-3 manque de définition

**Probabilité** : moyenne (absorption P2-11 + P2-12 sans scoping précis).
**Impact** : ticket dormant, dette invisible.
**Mitigation** : description du ticket (cf. P2-11 fiche) inclut la liste exacte des fichiers + lignes + sub-tasks. Assigner à un owner (Christophe ou delegate) lors de la création.

---

## Callers à adapter — récap exhaustif

| Commit | Fichiers source modifiés | Fichiers test modifiés / créés |
|---|---|---|
| C1 | `src/services/http/interceptors.ts`, `src/services/http/refresh.ts` (comment only), `src/contexts/AuthContext.tsx` (JSDoc + L106), `src/hooks/useServiceHealth.ts`, `src/hooks/useEvents.ts`, `src/services/http/auth.ts` (comment only), `.eslintrc.cjs` (ou équivalent) | Extension `interceptors.test.ts` (ou new), extension `useServiceHealth.test.ts`, extension `useEvents.test.ts` |

**Total estimé** : ~7 fichiers source touchés + ~3 fichiers test, ~60-80 LOC nettes, +3 tests.

---

## Validation Phase 3 (checklist)

Post-C1 :

1. `npx tsc --noEmit` dans `control-plane-ui/` → 0 nouvelle erreur (baseline P0+P1 : 394 erreurs pré-existantes documentées dans FIX-PLAN-UI2-P1.md §Phase 3).
2. `npx vitest run` → tous tests passent, dont les 3 nouveaux regression guards. Baseline P1 : 2193 passed. Cible P2 : **≥2196 passed**.
3. `npx eslint .` → 0 nouvelle erreur. Nouvelle rule `no-restricted-imports` sur `http/auth` respectée (whitelist effective).
4. `npm run build` → succès, même caveat `../shared/*` + `App.tsx ErrorBoundary` pré-existants.
5. **Actions non-code** :
   - Ticket Linear `UI-3 — Cleanup` créé via MCP Linear `save_issue` (team ID, label, priority P2).
   - `REWRITE-PLAN.md §A.2` référence le ticket en 1 ligne.
6. **Mise à jour `BUG-REPORT-UI-2.md`** :
   - Marquer P2-1, P2-2, P2-4, P2-5, P2-6, P2-7, P2-8, P2-9 **STATUS: FIXED (or WONT-FIX) commit <SHA>**.
   - P2-3 → **STATUS: ALREADY FIXED by P0-C1 `a88c98902`**.
   - P2-10 → **STATUS: ALREADY FIXED by P1-C2 `9e50961a7`**.
   - P2-11, P2-12 → **STATUS: DEFERRED to Linear `<UI-3-ticket-url>`**.
   - **Ajouter en-tête "UI-2 CLOSED"** : total **38 findings traités** = 10 P0 + 14 P1 + 1 WONT-FIX (P1-3) + 1 closed-by-P0 (P1-9..P1-12 compté distinctement) + 8 P2 fixed + 2 already-fixed-by-P0/P1 + 2 deferred-UI-3.

**Décompte final** : 38 bugs. P0 (10/10 fixed), P1 (14/16 fixed + 1 WONT-FIX + 1 closed-by-P0-recount), P2 (8/12 fixed + 2 already-fixed + 2 deferred).

---

## Livrable Phase 1

Ce fichier (`FIX-PLAN-UI2-P2.md`) + référence `BUG-REPORT-UI-2.md`. **STOP. Attente validation user avant Phase 2 (code + Linear ticket).**

---

## Rev1 — 6 corrections user intégrées (2026-04-24)

### Rev1 #1 — P2-2 commentaire Axios replay correct

Le commentaire initial disait "Axios 1.x applies transformers once" — pas assez safe. Reformulation :

```ts
// Intentionally replaying the same Axios config reference.
// With Axios defaults, already-serialized JSON data is stable across replay.
// A shallow clone would not restore the original pre-transform payload and
// could drop Axios internals (adapter, signal, cancel metadata, headers).
// If custom transformRequest logic is introduced, it must remain idempotent
// under refresh retry; see refresh.test.ts regression coverage.
return instance(originalRequest);
```

**Test conservé** : 4e test canary (au lieu de 3) — "retry does not double-encode default JSON body". Protège la décision WONT-FIX contre un futur transformer custom non-idempotent.

### Rev1 #2 — P2-1 guard `isAxiosError` avant `applyFriendlyErrorMessage`

Le request interceptor error path peut recevoir un non-`AxiosError` (erreur de transformation pre-send). Éviter de casser `applyFriendlyErrorMessage`.

```ts
import axios from 'axios';

(error) => {
  if (axios.isAxiosError(error)) {
    applyFriendlyErrorMessage(error);
  }
  return Promise.reject(error);
}
```

### Rev1 #3 — P2-5/P2-6 distinguer unmount abort vs timeout abort

Sans distinction, un service qui dépasse 5s resterait `'checking'` au lieu de devenir `'unavailable'`.

```ts
useEffect(() => {
  let abortedByUnmount = false;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 5000);

  const probe = async () => {
    try {
      const response = await fetch(url, { signal: controller.signal, method: 'HEAD', mode: 'no-cors' });
      // ... existing status inference
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        if (!abortedByUnmount) setStatus('unavailable'); // timeout → unavailable
        return;
      }
      setStatus('unavailable');
    } finally {
      clearTimeout(timeoutId);
    }
  };
  void probe();

  return () => {
    abortedByUnmount = true;
    controller.abort();
    clearTimeout(timeoutId);
  };
}, [url]);
```

### Rev1 #4 — P2-7 ESLint patterns avec aliases Vite

Vite utilise `@/` comme alias vers `src/`. La règle doit couvrir les deux formes :

```js
patterns: [{
  group: [
    '@/services/http/auth',
    '@/services/http/refresh',
    '@/services/http/interceptors',
    '*/services/http/auth',
    '*/services/http/refresh',
    '*/services/http/interceptors',
  ],
  message: 'HTTP auth internals are private to services/http/**. Use apiService façade.',
}]
```

Whitelist `src/__tests__/**` + `src/test/**` + `**/*.test.{ts,tsx}` + `src/services/http/**` + `src/services/api.ts`.

### Rev1 #5 — P2-8 dropper les event types inconnus

Schema hardening : les types inconnus ne sont pas transmis à `onEvent`, seulement les types whitelistés.

```ts
function isValidEvent(x: unknown): x is Event {
  return !!x && typeof x === 'object' && 'type' in x && typeof (x as { type: unknown }).type === 'string';
}

try {
  const parsed: unknown = JSON.parse(event.data);
  if (!isValidEvent(parsed)) {
    if (import.meta.env.DEV) console.warn('SSE: dropped event with unexpected shape', parsed);
    return;
  }
  switch (parsed.type) {
    case 'api-created':
    case 'api-updated':
    case 'api-deleted':
    case 'deploy-started':
    case 'deploy-progress':
    case 'deploy-success':
    case 'deploy-failed':
    case 'app-created':
    case 'app-updated':
    case 'app-deleted':
    case 'tenant-created':
    case 'tenant-updated':
      onEvent?.(parsed);
      // queryClient invalidations for this case
      break;
    default:
      if (import.meta.env.DEV) console.warn('SSE: dropped unknown event type', parsed.type);
  }
} catch (error) {
  if (import.meta.env.DEV) console.error('Failed to parse event:', error);
}
```

### Rev1 #6 — P2-9 pas de promesse de test prod-silence

`import.meta.env.DEV` est statique sous Vite ; stubber dans les tests est fragile. Code inline suffit, pas de test dédié.

### Décompte final — formulation simplifiée

Remplace la phrase "P1 (14/16 fixed + 1 WONT-FIX + 1 closed-by-P0-recount)" confuse par :

> **UI-2 CLOSED** : tous les findings P0/P1/P2 sont fixed, documented WONT-FIX, already-fixed by earlier batch, ou deferred avec owner/ticket. 38/38 traités.

### Tests canary — 4 au lieu de 3

1. Request interceptor error path calls `applyFriendlyErrorMessage` on `AxiosError` (P2-1).
2. **Refresh retry does not double-encode default JSON body (P2-2 WONT-FIX lock)**.
3. `useServiceHealth` unmount abort does NOT set `'unavailable'`; timeout abort DOES set `'unavailable'` (P2-5 + P2-6 combinés).
4. `useEvents` drops malformed event and dropped unknown event types without invoking `onEvent` or query invalidation (P2-8).

**Go Phase 2**.

---

## Phase 2 — Statut final (2026-04-24)

### Commits livrés

Single commit on `fix/ui-2-p2-batch`. Squash TBD.

### Statut par bug (P2)

| P2 | Status | Mechanism |
|---|---|---|
| P2-1 interceptors friendly-error | **FIXED** | isAxiosError guard + applyFriendlyErrorMessage |
| P2-2 axios replay clone | **WONT-FIX** (documented) | Inline comment on refresh.ts:100 + canary test locking no double-encode |
| P2-3 mcpGateway no-ops | **ALREADY FIXED** by P0-C1 `a88c98902` | grep verified — 0 hits |
| P2-4 accessToken context surface | **WONT-FIX** (documented) | Reinforced JSDoc; long-term fix via backend-signed URL (separate ticket) |
| P2-5 useServiceHealth catch generic | **FIXED** | AbortError distinction in catch |
| P2-6 useServiceHealth unmount abort | **FIXED** | Effect-scoped AbortController + `abortedByUnmount` flag |
| P2-7 module-scope state | **WONT-FIX** (documented) | Doc block + ESLint `no-restricted-imports` on http/auth internals (alias-aware patterns) |
| P2-8 useEvents cast `as Event` | **FIXED** | `isValidEvent` type guard + whitelist switch; unknown types dropped |
| P2-9 console logs prod | **FIXED** | Gated behind `import.meta.env.DEV` |
| P2-10 gateways.ts inline params | **ALREADY FIXED** by P1-C2 `9e50961a7` | P1-11 residu sweep |
| P2-11 REWRITE-BUGS.md | **DEFERRED** to CAB-2164 | Linear ticket UI-3 Cleanup |
| P2-12 `any` pervasif | **DEFERRED** to CAB-2164 | 17 sites tracked in the same ticket |

**Score** : 7 FIXED + 3 WONT-FIX documented + 2 already-fixed + 2 deferred = **12/12 traités**.

### Linear ticket créé

**[CAB-2164 — UI-3 — Cleanup](https://linear.app/hlfh-workspace/issue/CAB-2164)** (Priority P2, Backlog) — absorbe P2-11 + P2-12. DoD: zombies supprimés/documentés, 0 `any` dans `gateways.ts` + `gatewayDeployments.ts`, ESLint override locked sur `src/services/api/**`.

### Validation Phase 3

| Check | Résultat |
|---|---|
| `npx vitest run` | **2206 passed** / 11 skipped (baseline P1 = 2193) → +13 nouveaux tests (4 canary + 9 extensions) |
| `npx tsc --noEmit` | 394 erreurs pré-existantes (identique P1 baseline) — **0 nouvelle erreur** sur les fichiers touchés |
| `npm run lint` | **0 erreur**, 54 warnings (baseline P1 = 54) — identique |
| `npm run build` | Même caveat `../shared/*` + `App.tsx ErrorBoundary` pré-existants — **aucune régression** |

### Régression guards ajoutés (4 canary + extensions)

- **interceptors.test.ts** (new, 2 tests) : AxiosError → applyFriendlyErrorMessage ; non-AxiosError → skip.
- **refresh.test.ts** (+1 test) : retry does not double-encode default JSON body.
- **useServiceHealth.test.ts** (+2 tests) : unmount abort silent, timeout abort → 'unavailable'.
- **useEvents.test.ts** (+3 tests) : drop missing-type, drop non-string-type, drop unknown event type.

### Livrable

1 commit sur `fix/ui-2-p2-batch` + ticket Linear CAB-2164 + BUG-REPORT-UI-2.md marqué **UI-2 CLOSED**. Module UI-2 officiellement clos.
