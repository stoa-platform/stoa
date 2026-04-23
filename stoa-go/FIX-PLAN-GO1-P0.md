# FIX-PLAN-GO1-P0

> **Document status**: planning artifact for branch `fix/go-1-p0-batch`,
> committed together with the fix for reviewer context. Lifetime: remains
> alongside the branch through review; once the P0 batch is merged and
> superseded by later batches (P1/P2 plans land in sibling files), this
> document is a historical record of the decisions that shaped the first
> three commits. To be relocated to `stoa-docs/audits/2026-04-23-go-1/`
> alongside BUG-REPORT-GO-1.md at archival time. No dedicated Linear
> ticket (GO-1 is the module code name used in the audit prompt).

**Target branch**: `fix/go-1-p0-batch` (off `main`)
**Commits prévus**: 3 atomiques, testables isolément, chacun avec régression guards.
**Source de référence**: `BUG-REPORT-GO-1.md` (section Critical).
**Statut**: PHASE 1 validée — passage Phase 2.

## Décisions validées (2026-04-23)

1. **C.1 propagé à Kong dans le même commit** (commit 3) — même classe de défaut.
2. **C.2 non propagé à Gravitee** — laisser TODO explicite dans `gravitee.go` pointant vers le ticket de suivi.
3. **`GetFailedRoutes()` + `failedRoutesProvider` supprimés immédiatement** — pas de shim.
4. **`sync.Mutex` sur `syncedHashes`** — pas `sync.Map`. Follow-up potentiel : keyed lock / singleflight par `wmName` si la duplication polling+SSE devient bruyante.
5. **`SyncResult` reste minimal** (`struct{ FailedRoutes map[string]string }`), MAIS commit 2 absorbe aussi C.4 + C.5 pour garantir qu'aucune route n'est silencieusement "non atteinte" — sinon `FailedRoutes` seul ne permet pas de distinguer succès vs non-traité.
6. **1 retry max POST→PUT**, et le snapshot `existingAPIs` est rafraîchi avec l'ID trouvé pour que `verifyAndActivate` et la suite du batch utilisent des données cohérentes.

### Ajustements intégrés au plan original

- **A** : Commit 2 inclut C.4 (verifyAndActivate halt) + C.5 (deactivate halt). Remplacer les `return err` par accumulation dans `FailedRoutes` + `continue`. Tests regression ajoutés pour chaque.
- **B** : Dans `sse.go`, le fallback `syncErr` est comportement **requis** (pas optionnel) : si `syncErr != nil`, la route est marquée failed avec `result.FailedRoutes[depID]` si présent, sinon `syncErr.Error()`.
- **C** : Dans le fallback 409 POST→PUT, après `listAPIsIndexedByName` de refresh, mettre à jour `existingAPIs[wmName] = newID` pour que la suite du batch (et `verifyAndActivate`) voie la valeur fraîche.

---

## Inventaire partagé (lu avant de rédiger les 3 plans)

### Callers actuels de `SyncRoutes` et `FailedRoutes`

| Site | Fichier:ligne | Rôle |
|---|---|---|
| Call #1 (polling) | `internal/connect/routes.go:118` | Batch de toutes les routes, via ticker 30s |
| Call #2 (SSE) | `internal/connect/sse.go:228` | Single route, par deployment event |
| `GetFailedRoutes()` consommateur | `internal/connect/routes.go:133-139` | Type assertion `failedRoutesProvider` |
| Mock test polling | `internal/connect/sync_test.go:137` | `mockSyncAdapter.SyncRoutes` |
| Mock test SSE | `internal/connect/sse_test.go:24` | `mockSSEAdapter.SyncRoutes` |

### Implémenteurs de l'interface `GatewayAdapter.SyncRoutes`

| Adapter | Fichier | 409 handling | `FailedRoutes` exposé |
|---|---|---|---|
| Kong | `adapters/kong.go:233` | Pas de 409 explicite (POST `/config`) | Non |
| Gravitee | `adapters/gravitee.go:175` | 409 = OK continue (ligne 233) | Non |
| webMethods | `adapters/webmethods_sync.go:70` | 409 = silent `continue` (ligne 139) | Oui, via map partagée |
| Mock polling | `internal/connect/sync_test.go:137` | — | Non |
| Mock SSE | `internal/connect/sse_test.go:24` | — | Non |

### Instanciation unique

`internal/connect/discovery.go:60,76` — **une seule** instance `WebMethodsAdapter` est créée (pas de pool ni per-goroutine). L'adapter est ensuite passé par argument à `StartRouteSync` (lance la goroutine polling) et `StartDeploymentStream` (lance la goroutine SSE), donc effectivement partagé entre goroutines sans aucune synchro.

### Étendue des bugs partagés entre adapters

- **C.1 (RemovePolicy partial delete)** : `kong.go:208-226` a **exactement le même bug** (`return nil` après 1er match). Gravitee `RemovePolicy` est un stub `not yet implemented` — pas affecté. **Fix 3 doit propager à Kong.**
- **C.2 (409 silent skip)** : Gravitee accepte aussi 409 silencieusement (`gravitee.go:233-236`) mais sans `syncedHashes` ni `FailedRoutes` donc sans l'effet cascade cagneux. Discutable si on propage. Recommandation : laisser Gravitee en l'état pour ce batch, documenter comme tech debt.
- **C.3/C.6 (race FailedRoutes)** : **wM uniquement**. Kong et Gravitee n'ont pas d'état mutable par-route exposé. Fix 1 est ciblé wM + refactor interface.

---

## Fix 1 — C.3 + C.6 : Race conditions FailedRoutes / syncedHashes

**Pourquoi en premier** : les deux bugs partagent la même cause — état mutable partagé. Fix les deux d'un coup, bloque les futurs bugs similaires, et le Fix 2 (C.2) en dépend (il doit écrire dans `FailedRoutes` / `SyncResult` sans course).

### Approche technique proposée

**Transformer `FailedRoutes` d'état interne mutable en valeur de retour immuable.**

1. Introduire un type `adapters.SyncResult` :
   ```
   type SyncResult struct {
       FailedRoutes map[string]string // deployment_id → error
   }
   ```
   Map créée fraîche à chaque appel, jamais partagée.

2. Modifier la signature de l'interface `GatewayAdapter.SyncRoutes` :
   ```
   SyncRoutes(ctx, adminURL, []Route) (SyncResult, error)
   ```
   La `SyncResult` est toujours retournée (même sur error), avec la map partielle remplie pour les routes traitées avant l'échec global.

3. Supprimer `FailedRoutes` + `GetFailedRoutes()` du `WebMethodsAdapter`. `syncedHashes` reste interne mais devient thread-safe.

4. Protéger `syncedHashes` avec `sync.Mutex` (voir justification plus bas).

### Callers impactés (liste exacte)

| Fichier | Ligne | Changement requis |
|---|---|---|
| `adapters/adapter.go` | 66 | Changer signature interface `SyncRoutes` → retourne `(SyncResult, error)` |
| `adapters/adapter.go` | — | Ajouter `type SyncResult struct { FailedRoutes map[string]string }` |
| `adapters/webmethods_adapter.go` | 10-30 | Supprimer champ `FailedRoutes`, supprimer méthode `GetFailedRoutes()`. Garder `syncedHashes` + ajouter `hashesMu sync.Mutex` |
| `adapters/webmethods_sync.go` | 70-184 | Signature ; supprimer ligne 77 (`w.FailedRoutes = make(...)`) ; déclarer `result := SyncResult{FailedRoutes: map[string]string{}}` en début ; écrire dans `result.FailedRoutes[route.DeploymentID]` (ligne ~151) ; remplacer reads/writes de `syncedHashes` par helper sous mutex ; retour `return result, nil/err` partout |
| `adapters/kong.go` | 233-340 + 343-374 | Signature uniquement ; retourner `SyncResult{}` vide (Kong ne track pas par-route, acceptable) |
| `adapters/gravitee.go` | 175-240 | Signature uniquement ; retourner `SyncResult{}` vide |
| `adapters/webmethods_sync_test.go` | 4 tests | Adapter les assertions à la nouvelle signature |
| `adapters/kong_test.go` | tests SyncRoutes | Idem |
| `adapters/gravitee_test.go` | tests SyncRoutes | Idem |
| `internal/connect/routes.go` | 118-139 | Remplacer `syncErr := adapter.SyncRoutes(...)` par `result, syncErr := adapter.SyncRoutes(...)`. Supprimer entièrement le bloc `type failedRoutesProvider interface + type-assert` (lignes 133-139). Lire `result.FailedRoutes` directement |
| `internal/connect/sse.go` | 228 | Remplacer par `result, syncErr := adapter.SyncRoutes(ctx, adminURL, []adapters.Route{route})`. Pour single-route flow, la lecture de `result.FailedRoutes[event.DeploymentID]` donne le message précis (enrichissement possible du `errMsg` actuel — optionnel mais propre) |
| `internal/connect/sync_test.go` | 137 | Adapter `mockSyncAdapter.SyncRoutes` à la nouvelle signature |
| `internal/connect/sse_test.go` | 24 | Adapter `mockSSEAdapter.SyncRoutes` à la nouvelle signature |

### Décisions structurelles à arbitrer

**1. Interface publique vs wrapper**

**Options** :
- (A) Modifier `GatewayAdapter.SyncRoutes` pour retourner `(SyncResult, error)`
- (B) Garder l'interface, ajouter une méthode `SyncRoutesV2` / garder `failedRoutesProvider`
- (C) Garder l'interface, protéger `FailedRoutes` avec mutex

**Recommandation : A**.
- Justification : (C) préserve l'architectural wart qui a causé les bugs (état partagé mutable) ; un futur contributeur ajoutera un autre field mutable et on repartira. (B) multiplie la surface et laisse `GetFailedRoutes` comme trap. (A) casse une interface interne (pas publique — module `internal/` non-exporté hors du repo), touche 5 fichiers, mais ferme le problème par construction.
- Coût de (A) : modifier 3 adapters + 2 mocks + 2 callers. ~80 LOC touchées, ~40 nettes.
- Coût de (C) : ~15 LOC mutex + laisser la dette.

**2. `sync.Mutex` vs `sync.Map` pour `syncedHashes`**

**Recommandation : `sync.Mutex`** (avec field lowercase `hashes`).
- Justification : le pattern d'accès est read-check-then-write (`if lastHash, ok := ...; ok && lastHash == ...` puis plus tard `w.syncedHashes[wmName] = route.SpecHash`). Sous `sync.Map`, ce check-then-write n'est pas atomique → on doit utiliser `LoadOrStore` avec de la logique tordue. Avec un `sync.Mutex` classique on prend le lock sur les deux opérations de la même iteration et c'est transparent. Perf non critique (un appel par route, quelques µs).
- Pattern d'accès : `w.hashes.Get(name)` / `w.hashes.Set(name, hash)` helpers privés OU accès in-line avec `w.hashesMu.Lock()/Unlock()`. Recommandation inline pour éviter de multiplier les helpers triviaux.

**3. `GetFailedRoutes()` + type-assertion `failedRoutesProvider` — supprimer ou deprecated ?**

**Recommandation : supprimer maintenant.**
- Justification : code interne (`internal/connect/`), pas de consommateur externe possible. Garder en deprecated = dette. Le `BUG-REPORT-GO-1.md` les identifie comme les racines de C.6 — les laisser serait signer pour un reversement.
- Côté `routes.go:133-139`, le bloc entier disparaît. Remplacer par lecture directe du `result.FailedRoutes`.

**4. Kong/Gravitee doivent-ils aussi exposer un `SyncResult` riche ?**

**Recommandation : non pour ce commit.**
- Justification : Kong fait un POST `/config` atomique (tout-ou-rien, pas de par-route), Gravitee n'est pas en prod aujourd'hui (pas de CAB client Gravitee). Retourner `SyncResult{FailedRoutes: nil}` est honnête et conforme à leur comportement. Si on voulait faire mieux plus tard, ce serait un fix séparé (tech debt documenté).
- Le caller `routes.go` tolère déjà le cas `FailedRoutes` vide avec fallback `syncErr != nil && len(failedMap) == 0` (branche ligne 154). Cette branche reste valide.

**5. Sémantique `SyncResult` sur erreur globale**

Quand `SyncRoutes` renvoie `err != nil`, `SyncResult.FailedRoutes` contient-il ce qui a été partiellement rempli ?
- **Recommandation : oui**, remplir `FailedRoutes` avec ce qu'on a (fail-partial), et retourner `err` si ≥1 route a échoué ou erreur globale. Le caller peut distinguer "toute la sync a échoué" (err != nil && len(result.FailedRoutes) == 0) vs "erreurs per-route" (err != nil && len > 0).
- Ceci préserve le contrat actuel (`syncErr` retourné à la fin si `len(syncErrors) > 0`).

### Régression guards proposés

| Test | Scénario couvert | Fichier cible |
|---|---|---|
| `TestWebMethodsSyncRoutes_ConcurrentCalls` | Lance 10 goroutines × SyncRoutes(10 routes chacune) en parallèle, `-race`. Vérifie pas de panic, pas d'écrasement de `syncedHashes`. | `webmethods_sync_test.go` |
| `TestWebMethodsSyncRoutes_PollingSSEIsolation` | Goroutine A fait SyncRoutes(batch fail) → lit `result.FailedRoutes`. Goroutine B déclenche SyncRoutes(single route) entre temps. Vérifie que la `result` de A n'est pas écrasée. | `webmethods_sync_test.go` |
| `TestWebMethodsSyncedHashes_ConcurrentReadWrite` | 50 goroutines × 100 iterations check-and-update `hashes`, `-race`. Vérifie pas de `concurrent map write` panic. | `webmethods_sync_test.go` |

### Risques identifiés

- **Risque A** : les mocks `mockSyncAdapter` / `mockSSEAdapter` utilisent la vieille signature → break compilation multiple fichiers. Mitigation : grep complet `SyncRoutes(` avant commit, adapter tous les mocks en un seul changeset.
- **Risque B** : `routes.go:154` branche "`syncErr != nil && len(failedMap) == 0`" est garde-fou pour Kong/Gravitee. Vérifier qu'elle reste sémantiquement correcte avec `result.FailedRoutes` au lieu du map externe — sémantique identique, safe.
- **Risque C** : sérialisation JSON de `SyncResult` — pas requis (reste interne au process), mais si un jour on veut le logger / tracer, l'ajouter sans problème.
- **Risque D** : perf sur 100 routes + mutex lock/unlock par route. ~100 × 2 acquires = négligeable (< 10µs total).
- **Risque E** : le polling + SSE peuvent maintenant tourner en parallèle *sans* race sur les maps, mais **rien ne protège contre deux appels concurrents à `listAPIsIndexedByName`** côté wM (deux GET sur `/rest/apigateway/apis`). OK pour wM (read-only, idempotent), juste du trafic dupliqué. Pas scope de ce fix, noter.

---

## Fix 2 — C.2 : 409 Conflict handling complet

**Prérequis** : Fix 1 mergé (on écrit dans `result.FailedRoutes`, pas dans un state partagé).

### Approche technique proposée

Remplacer le `continue` silencieux par une logique à 3 branches :

1. **409 reçu en réponse à POST** : l'entité existe sous ce nom mais n'était pas dans notre `existingAPIs` snapshot (race, concurrence, out-of-band creation). Fallback : re-lister via `listAPIsIndexedByName` → retrouver l'ID → retenter en PUT une fois. Si re-list retourne toujours pas l'ID, fail-closed vers `FailedRoutes`.

2. **409 reçu en réponse à PUT** : conflit de version / contenu (wM rejette l'update). Pas de fallback automatique possible sans logique métier (mergé, forcé, etc.) → marquer dans `FailedRoutes` avec raison claire et message structuré.

3. **`syncedHashes` mis à jour UNIQUEMENT sur succès final 2xx**. Jamais sur 409, jamais sur error path.

### Pseudo-flow (pas du code final)

```
Si POST retourne 409:
  Re-lister APIs (1 call supplémentaire)
  Si trouve l'ID du wmName:
    Retenter 1 fois en PUT sur /apis/<id>
    Si PUT 2xx: considérer succès, continuer verifyAndActivate
    Si PUT non-2xx: ajouter à FailedRoutes avec détail ("409 → PUT fallback failed: ...")
    Si PUT 409: ajouter à FailedRoutes ("409 persistent conflict")
  Sinon (pas dans re-list):
    FailedRoutes = "409 on POST but API not found in re-list (ghost conflict?)"

Si PUT retourne 409:
  FailedRoutes = "409 on PUT (version/content conflict)"
  Ne pas update syncedHashes
  continue vers route suivante
```

### Callers impactés

Aucun en dehors de `webmethods_sync.go`. Le format de `FailedRoutes` étant déjà une string libre, les consommateurs (`routes.go`, `sse.go`) n'ont pas besoin de changements — ils logguent + propagent au CP.

### Décisions structurelles à arbitrer

**1. Distinction 409 POST vs 409 PUT**

- Détection triviale : `method` est connu (variable locale `method` ligne 116 du code actuel). Traçage `if resp.StatusCode == http.StatusConflict && method == http.MethodPost { ... }` vs `http.MethodPut`.
- **Recommandation** : branche explicite sur `method`.

**2. Stratégie fallback POST → PUT : combien de retry max ?**

- **Recommandation : 1 retry max** (pas de boucle). Justification :
  - Si POST 409 + re-list trouve → PUT. Si PUT 2xx → OK. Si PUT 409 → persistent conflict, pas utile de boucler.
  - Si POST 409 + re-list ne trouve PAS → bizarre (ghost) → fail closed.
  - Boucler exposerait à des tight loops si wM est en état pathologique (eg. écrit sur lect stale constamment).
- **Pas de backoff/sleep** — le timeout client HTTP (10s) protège déjà contre des tempêtes.

**3. Timeout par tentative ?**

- **Recommandation : laisser le `w.client.Timeout: 10 * time.Second` du client HTTP actuel.** Pas de timeout per-retry custom. Si quelqu'un veut un budget total, c'est via le `ctx` (context.WithTimeout) en amont. Scope hors de ce fix.

**4. Cas "409 sur POST mais API pas dans le re-list"**

- **Recommandation : fail closed vers FailedRoutes**, message explicite : `"409 conflict but API not present in gateway after re-list; possible ghost (cache/race) or indexer lag"`.
- Ne PAS retenter — on ne sait pas quoi retenter (POST renverrait 409 encore). Mettre dans FailedRoutes, laisser CP décider (peut requeue au prochain cycle).

**5. Conditions exactes de mise à jour de `syncedHashes`**

- **Recommandation explicite** : update `hashes[wmName] = route.SpecHash` **uniquement après** :
  (a) réponse finale 2xx (POST initial OU PUT fallback)
  (b) `verifyAndActivate` réussi
  (c) pas d'erreur accumulée pour cette route

  Tout autre chemin (409 résiduel, error 5xx, verify error) → hash non mis à jour → re-sync au prochain cycle. Correct par construction.

**6. Format des messages dans `FailedRoutes`**

Template recommandé :
```
"webmethods <method> <wmName> failed (<code>): <truncated_detail>"
```
où `<method>` = POST / PUT / PUT-fallback / verifyAndActivate / deactivate. Préfixe explicite pour que ops puissent `grep failed | awk` dans les logs centralisés.

### Régression guards proposés

| Test | Scénario couvert |
|---|---|
| `TestWebMethodsSyncRoutes_409OnPostFallbackToPut` | Mock renvoie 409 sur POST ; re-list inclut l'API → PUT 2xx → route classée applied |
| `TestWebMethodsSyncRoutes_409OnPutTracked` | Mock renvoie 409 sur PUT initial → `result.FailedRoutes[dep-id]` contient message explicite, hash non mis à jour |
| `TestWebMethodsSyncRoutes_409PostAPINotInList` | Mock renvoie 409 sur POST ; re-list ne contient pas l'API → `result.FailedRoutes` rempli, pas de boucle |
| `TestWebMethodsSyncRoutes_409DoesNotUpdateHash` | POST 409 → sync immédiat suivant avec MÊME hash → doit retenter (preuve que hash non mis à jour) |

### Risques identifiés

- **Risque A** : `listAPIsIndexedByName` doublé (appel initial + re-list sur 409) → +1 call par route 409. Acceptable : 409 est rare en régime normal.
- **Risque B** : PUT fallback peut encore renvoyer 409 → boucle infinie potentielle si on retry en boucle. Mitigation : **1 retry max, pas de boucle**. Recommandation ferme.
- **Risque C** : mock server des tests existants peut casser si on ajoute la 2ème route re-list. Mitigation : nouveaux tests ont leur propre mock dédié ; tests existants ne devraient pas émettre de 409 donc pas impactés.
- **Risque D** : sémantique du `SpecHash` n'est pas mise à jour en cas d'échec → polling cycle suivant retente. Pour un 409 PUT persistant, on retentera indéfiniment. **C'est le bon comportement** (échec visible → CP peut remédier), mais à monitorer (alerting).

---

## Fix 3 — C.1 : RemovePolicy supprime toutes les matches

**Prérequis** : aucun. Indépendant. Peut théoriquement commit en parallèle, mais gardons l'ordre pour isolation du batch.

### Approche technique proposée

Dans `webmethods_policy.go` et `kong.go` :

1. Collecter TOUS les policy actions matchants dans une slice.
2. Faire DELETE sur chacun, accumuler erreurs individuelles.
3. Si au moins une suppression réussit, logguer le compte.
4. Si au moins une échoue : retourner une erreur `fmt.Errorf("removed %d/%d policies, last error: %w", success, total, lastErr)`.
5. Pas de match = return nil (idempotent préservé).

### Callers impactés

Aucun en dehors des deux fichiers modifiés :
- `adapters/webmethods_policy.go:146-193` — réécrire `RemovePolicy`
- `adapters/kong.go:187-229` — réécrire `RemovePolicy` avec le même pattern (plugin-based plutôt que policyAction-based, mais même forme)

Les consommateurs (pas identifiés dans `internal/connect/` — `RemovePolicy` semble seulement appelé via tests aujourd'hui, à vérifier au moment du commit) ne voient qu'un changement sémantique : idempotence renforcée sur N matchings.

### Décisions structurelles à arbitrer

**1. Comportement sur erreurs partielles : 1ère, dernière, ou wrap de toutes ?**

**Recommandation : retour de la dernière erreur avec count explicite**.
- Format : `"removed %d/%d policies; %d failed; last error: %w"`.
- Justification :
  - `errors.Join` (Go 1.20+) est propre mais le format wrap est moins grep-friendly pour ops.
  - 1ère erreur seule = perte d'info.
  - "dernière + count" = ops sait combien ont échoué, le message lisible, et le `%w` garde la chaîne d'erreur pour `errors.Is/As`.

**2. Log sur `deletedCount > 1` ?**

**Recommandation : log.Printf WARN** avec texte `webmethods: RemovePolicy removed N duplicate policy actions for API=<name> type=<type>`.
- Justification : signaler la présence de doublons pour investigation upstream. Niveau warn (pas error) parce que la suppression a réussi. Le niveau est implicite puisque l'adapter utilise `log` standard — on préfixe le message avec `warn:` pour tri via grep/fluentd.

**3. Idempotence : 0 match = nil, N match supprimés = nil, mix succès/échec ?**

**Recommandation** :
- 0 match : nil (idempotent, inchangé)
- N match tous supprimés : nil + log si N > 1
- N match, ≥1 échec : erreur wrap avec count "removed X/N, failed Y/N"
- N match, 0 suppression réussie (tous erreurs) : erreur claire "removed 0/N policies: <last err>"

La sémantique : l'appelant sait au moins qu'on a essayé, et peut retrier.

**4. Kong doit-il avoir le même comportement ?**

**Oui, propagation obligatoire**. `kong.go:208-226` a le même bug exact. Le fix doit inclure Kong dans le même commit (ça rentre dans la philosophie "C.1" — le bug est la **classe de design**, pas une instance wM). Tests de régression à dédoubler pour Kong.

### Régression guards proposés

| Test | Scénario couvert | Fichier |
|---|---|---|
| `TestWebMethodsRemovePolicy_MultipleMatches` | wM retourne 3 policies avec `TemplateKey == "corsPolicy"` ; vérifier 3 DELETEs envoyés, nil retourné, log warn présent | `webmethods_policy_test.go` |
| `TestWebMethodsRemovePolicy_PartialFailure` | 3 matches ; 2ème DELETE renvoie 500 ; vérifier erreur retournée contient "2/3" et wrap la 500 | `webmethods_policy_test.go` |
| `TestWebMethodsRemovePolicy_NoMatches` | Aucune policy correspondante ; vérifier 0 DELETE, nil retourné | `webmethods_policy_test.go` |
| `TestKongRemovePolicy_MultipleMatches` | Kong retourne 2 plugins `name == "rate-limiting"` ; vérifier 2 DELETEs | `kong_test.go` |
| `TestKongRemovePolicy_PartialFailure` | Idem wM, côté Kong | `kong_test.go` |

### Risques identifiés

- **Risque A** : ordre de delete important ? Non — wM retourne les policies dans l'ordre qu'il veut ; on DELETE toutes. Pas de dépendance ordre.
- **Risque B** : si wM a un bug où il recreate une policy entre nos deletes (race côté serveur), on peut rater une. Acceptable — le prochain cycle re-tentera.
- **Risque C** : PSF (partial success failure) pourrait être mal compris par le caller qui traite "erreur" comme "rien n'a marché". Vérifier que `ApplyPolicy` / retry patterns upstream sont tolérants. Ce scope est hors du fix actuel, documenter comme à surveiller.
- **Risque D** : Kong utilise `policyType` comme nom direct (Kong plugin name), pas de mapping `wmPolicyTypeMapping`. Le code actuel Kong fait match sur `name == policyType` — ça ne change pas, la structure reste identique.

---

## Phase 2 — ordre d'exécution

Après validation de ce plan :

1. **Commit 1** = Fix 1 (C.3 + C.6) — change interface `SyncRoutes`, propage à Kong/Gravitee/mocks/callers, ajoute mutex sur hashes, introduit `SyncResult`, supprime `GetFailedRoutes()`. 3 tests regression.
2. **Commit 2** = Fix 2 (C.2) — implémente 409 branching + PUT fallback dans `webmethods_sync.go` uniquement. 4 tests regression.
3. **Commit 3** = Fix 3 (C.1) — réécrit `RemovePolicy` wM + Kong avec collect-all + partial-fail. 5 tests regression.

Après chaque commit : `go test ./... -race -count=1` doit passer.

## Phase 3 — validation globale

- `go vet ./...`
- `go test ./... -race -count=1`
- `golangci-lint run`
- `go build ./cmd/stoa-connect ./cmd/stoactl`
- `git log --oneline main..HEAD` = exactement 3 commits
- `BUG-REPORT-GO-1.md` mis à jour : C.1, C.2, C.3, C.6 marqués `FIXED — commit <sha>`

---

## Questions ouvertes à arbitrer avant Phase 2

1. **Propager le fix C.1 à Kong** : confirmé (même bug). OK ?
2. **Ne PAS propager C.2 à Gravitee** : laisser le `continue` sur 409 Gravitee en l'état (tech debt documenté), car pas de client Gravitee en prod et pas de `syncedHashes` pathologique. OK ?
3. **Supprimer `GetFailedRoutes()` + `failedRoutesProvider`** immédiatement (pas deprecated) : OK ?
4. **`sync.Mutex` sur `hashes`** plutôt que `sync.Map` : OK ?
5. **Format de `SyncResult`** : `struct{ FailedRoutes map[string]string }` minimaliste, extensible plus tard si besoin. OK ?
6. **1 retry max** sur POST→PUT fallback (pas de boucle) : OK ?

J'attends ton feedback sur ces 6 points avant de démarrer Phase 2.
