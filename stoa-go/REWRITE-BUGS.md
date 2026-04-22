# REWRITE-BUGS — GO-2

Bugs découverts pendant la Phase 1 d'inventaire du refactor `internal/connect/`.
État au 2026-04-22.

Colonne `Fix` :
- `S<n>` = corrigé in-flight dans l'étape correspondante de GO-2.
- `follow-up` = documenté ici, à traiter dans un ticket séparé après GO-2.

---

## Race conditions

### F.1 — Race sur `Agent.gatewayID` (fix in-flight S1)

**Symptôme potentiel** : goroutine heartbeat écrit `a.gatewayID = ""` puis `a.gatewayID = newID` (via `Register`) pendant que 5 autres goroutines lisent `a.gatewayID` pour construire des URLs (`heartbeat`, `discovery`, `fetch-config`, `fetch-routes`, `sync-ack`, `route-sync-ack`, `SSE events`).

**État actuel** : pas détecté par `go test -race` parce que les tests ne lancent pas les goroutines `Start*` simultanément avec un déclenchement de re-register. **Latent, réel en prod si un événement déclenche 3× 404 pendant que d'autres boucles tournent.**

**Preuve** : aucun `sync.Mutex` dans `internal/connect/*.go` (hors adapters). `grep -rn "sync.Mutex\|sync.RWMutex" internal/connect/*.go` → vide.

**Fix S1** : migrer `gatewayID` dans `agentState` derrière `sync.RWMutex`. Accesseurs `GatewayID() string`, `SetGatewayID(id string)`, `ClearGatewayID()`. Tous les callers passent par ces accesseurs.

**Régression guard** : `TestAgentStateRace` avec N goroutines lisant `GatewayID` + 1 goroutine alternant `Clear`/`Set`, sous `-race`.

---

### F.2 — Race sur `Agent.lastDiscoveredAPIs` (fix in-flight S1)

**Symptôme potentiel** : discovery goroutine `runDiscovery` fait `a.lastDiscoveredAPIs = payloads` (assignation de slice), pendant que :
- heartbeat goroutine lit via `a.computeRoutesCount()` (range sur le slice)
- `/health` handler lit via `a.DiscoveredAPIsCount()`

Slice header (ptr+len+cap) non-atomique. Lecture concurrente sans sync = data race.

**Fix S1** :
- `SetDiscoveredAPIs(in []DiscoveredAPIPayload)` copie l'input dans un nouveau slice interne.
- `DiscoveredAPIs() []DiscoveredAPIPayload` retourne une copie.
- `ComputeRoutesCount()` et `DiscoveredAPIsCount()` lisent sous `RLock` (pas de leak de référence).

**Régression guard** : intégré dans `TestAgentStateRace` (goroutine `SetDiscoveredAPIs` en parallèle de `ComputeRoutesCount`).

---

### F.3 — Goroutine SSE peut rester bloquée dans catch-up (follow-up)

**Lieu** : `sse.go:75-107` — `StartDeploymentStream` appelle `RunRouteSync(ctx, ...)` AVANT chaque reconnect. Si `ctx` est cancellé pendant ce `RunRouteSync`, on sort de cette fonction (ses appels HTTP respectent le ctx) mais la boucle externe ne revalide `ctx.Done()` qu'après.

**Impact** : fragile mais correctness OK (le ctx se propage aux HTTP calls). La boucle sort quand même proprement.

**Traitement** : improvement naturel en S9 (`loop_sse.go` recoiffé), sans plus.

---

## SSE transport

### F.6 — `bufio.Scanner` buffer 64KB (FIXED in S5, commit pending)

**Lieu original** : `sse.go:146` (pre-S5) — `scanner := bufio.NewScanner(resp.Body)` sans `scanner.Buffer(...)`.

**Symptôme** : un event SSE avec `desired_state` volumineux (OpenAPI spec inlinée > 64KB) dépasse le buffer scanner défaut (`bufio.MaxScanTokenSize` = 64KB). Comportement observé en théorie :
1. Scanner retourne `false` avec `scanner.Err() == bufio.ErrTooLong`.
2. La boucle sort.
3. `scanner.Err()` ÉTAIT lu (ligne 172 pré-S5) mais l'erreur retournée était ensuite écrasée par le sentinel `fmt.Errorf("SSE stream ended")` — donc le reconnect loop ne voyait jamais la cause réelle dans ses logs.
4. Worst case : reconnect infini avec même event qui retruncate silencieusement.

**Impact en prod** : latent. Jamais observé (les OpenAPI specs actuels passent sous 64KB). Devient un bug visible si un client pousse un spec volumineux (démo BDF type : spec webMethods complet avec ~200 paths).

**Fix appliqué (S5)** :
```go
// transport_sse.go
scanner := bufio.NewScanner(resp.Body)
scanner.Buffer(make([]byte, 0, sseScannerInitialBuf), sseScannerMaxBuf) // 64KB init, 1MB max
// ...
if err := scanner.Err(); err != nil {
    return spanFail(span, fmt.Errorf("SSE read: %w", err), "scanner error")
}
return io.EOF // clean end — distinguishable from scanner failure via errors.Is
```

**Régression guard** (`transport_sse_test.go`) :
1. `TestSSEStreamAcceptsLargeEvent` — 500 KB event, sink doit recevoir le payload complet sans truncation.
2. `TestSSEStreamReportsScannerErrorOnOversizedEvent` — 2 MB event (> 1 MB cap), `errors.Is(err, bufio.ErrTooLong)` doit être true.
3. `TestSSEStreamPropagatesHTTPStatus` — non-200 surfaces proprement.
4. `TestSSEStreamSinkErrorAborts` — sink error interrompt le stream et remonte.

Caller side (`sse.go:StartDeploymentStream`) logue maintenant `"sse-stream: terminal error: <cause>"` avant backoff, plutôt que le générique `"connection lost"`. En production : les logs isolent immédiatement `ErrTooLong` d'une déconnexion réseau.

---

### F.5 — SSE catch-up RouteSync à chaque reconnect = re-push complet (follow-up)

**Lieu** : `sse.go:87` — `a.RunRouteSync(ctx, adapter, adminURL)` est appelé avant CHAQUE tentative de connect, y compris après un disconnect transitoire.

**Impact** : sur un réseau flappy, chaque reconnexion re-pousse TOUTES les routes CP vers le gateway local. Correctness OK (adapter.SyncRoutes idempotent), mais perf : ~100 routes × 1 appel HTTP chacun côté gateway à chaque flap.

**Traitement** : follow-up. Option 1 : ne catch-up qu'après un gap > N secondes. Option 2 : utiliser un `Last-Event-ID` côté SSE (protocol change, lourd).

---

### F.7 — Double-ack possible après reconnect SSE (follow-up côté CP)

**Lieu** : après reconnect SSE, le CP peut re-streamer un event déjà traité. L'agent l'applique à nouveau (idempotent côté adapter) + re-ack.

**Impact** : CP doit dedupe sur `deployment_id` — à vérifier côté `control-plane-api`.

**Traitement** : follow-up côté CP. L'agent reste at-least-once, c'est la sémantique attendue.

---

## Type safety

### F.10 — `ReportDiscovery(ctx, apis interface{})` (fix in-flight S4)

**Lieu** : `connect.go:360-429`.

**Symptôme** : la signature prend `interface{}` et fait marshal/unmarshal pour convertir `adapters.DiscoveredAPI` → `DiscoveredAPIPayload`. Code smell : type safety perdue au compile-time.

**Fix S4** : signature typée `ReportDiscovery(ctx context.Context, apis []DiscoveredAPIPayload) error`. La conversion depuis `adapters.DiscoveredAPI` reste dans `runDiscovery` (discovery.go:146-157) où elle est déjà faite, juste sans le re-marshal gymnastic.

---

### F.11 — `failedRoutesProvider` type-assertion implicite (documenté, reste local)

**Lieu** : `routes.go:133-139` — interface anonyme découverte via cast runtime sur `adapter.(failedRoutesProvider)`.

**Impact** : couplage faible, pas de compile-time check. Seul le `webMethods` adapter l'implémente ; pour kong/gravitee, `failedMap` reste vide et on tombe sur le fallback "global error".

**Traitement** : helper privé `failedRoutesFromAdapter(adapter) map[string]string` dans `sync_route.go` (S7). Pas d'export depuis `adapters/` (hors scope GO-1/GO-2). Dette assumée.

---

## Champs wire morts / obsolètes (follow-up)

### F.8 — `HeartbeatPayload.PoliciesCount` jamais populé

**Lieu** : `connect.go:100` — déclaré `PoliciesCount int \`json:"policies_count"\``, toujours envoyé à 0 car jamais assigné dans `Heartbeat`.

**Traitement** : soit brancher (compter les policies synced via `state`), soit supprimer du wire. Vérifier consommation côté CP avant suppression. Follow-up.

---

### F.9 — `GatewayConfigResponse.PendingDeployments []interface{}` jamais lu

**Lieu** : `sync.go:30` — déclaré, jamais itéré. Légacy d'une spec précédente.

**Traitement** : grep côté `control-plane-api` pour voir si le champ est encore émis ; si non, supprimer la déclaration en suivi. Follow-up.

---

## Divergences polling ↔ SSE fusionnées en S7

### B.1 — Generation field silencieusement droppé sur chemin SSE (FIXED in S7)

**Lieu pré-S7** : `sse.go:handleSyncDeployment` — construisait un `SyncedRouteResult` sans `Generation`. `routes.go:RunRouteSync` le posait correctement via `Generation: r.Generation`.

**Impact** : CAB-1950 introduit un mécanisme de génération-based reconciliation côté CP. Quand un deployment arrive via SSE, l'agent applique la route mais l'ack revient sans generation → le CP ne peut pas vérifier quelle version est déployée. Divergence possible silencieuse entre état CP (base de données) et état gateway local. Jamais flaggé par les tests existants (aucun n'assertait sur `result.Generation` côté SSE).

**Fix S7** : le `routeSyncer` unifié remplit toujours `Generation: r.Generation` quel que soit le chemin d'entrée (polling ou SSE). Regression guard : `TestRouteSyncerAppliedBatch` vérifie explicitement que `Generation` est propagé avec les valeurs exactes.

---

### B.2 — `failedRoutesProvider` type-assert sur polling uniquement (consolidated, no behavior change)

**Divergence** : seul `routes.go:RunRouteSync` faisait le type-assert sur l'interface anonyme `failedRoutesProvider`. Le chemin SSE ignorait ce provider — mais comme SSE traite 1 route à la fois, un `syncErr != nil` mappe forcément vers cette unique route. Résultat fonctionnellement identique.

**Fix S7** : le `routeSyncer` fait le type-assert inconditionnellement. Pour 1 route, `failedMap[dep-id]` détermine le status ; pour N routes, pareil ; pour un adapter sans l'interface, fallback sur le global error. Un seul chemin de résolution per-route, testable en isolation (`TestRouteSyncerPerRouteFailure`).

---

### B.3 — Route sans `deployment_id` silencieusement droppée (visibilité améliorée en S7)

**Lieu pré-S7** : `routes.go:RunRouteSync` faisait `if r.DeploymentID == "" { continue }` sans log. Une route arrivant sans deployment_id = symptôme d'un contract drift CP↔agent (CP est censé toujours tagger), mais était invisible aux ops.

**Fix S7** : le skip reste (on ne peut toujours pas ack sans deployment_id), mais `routeSyncer` logue `"route-sync: skipping route %q — missing deployment_id (CP contract drift?)"`. Regression guard : `TestRouteSyncerSkipsMissingDeploymentID`.

---

## Asymétries policy sync consolidées en S8

### C.1 — `OIDCAdapter` interface asymétrique apply vs remove (documented, out of GO-2 scope)

**Lieu** : `internal/connect/adapters/adapter.go:128-132` — `OIDCAdapter` interface.

**Constat** :
- **Apply side** : 3 méthodes typées (`UpsertAuthServer`, `UpsertStrategy`, `UpsertScope`) + fallback générique `ApplyPolicy` via `GatewayAdapter`.
- **Remove side** : 1 seule méthode typée (`DeleteAuthServer`). `DeleteStrategy` et `DeleteScope` **n'existent pas sur l'interface**.

**Conséquence runtime** : quand le CP émet une `PendingPolicy{PolicyType: "oidc_strategy", Enabled: false}` (i.e. "désactive cette stratégie"), le `policySyncer.remove` tombe sur le fallback `adapter.RemovePolicy(ctx, adminURL, name, "oidc_strategy")`. C'est à l'implémentation concrète (webmethods / kong / gravitee) de reconnaître ce hint string et de faire la bonne chose — ou de no-op silencieusement.

**Bug latent potentiel** : si webmethods.RemovePolicy ne gère pas le type `oidc_strategy`, on a un leak — la strategy reste configurée côté gateway alors que le CP pense l'avoir supprimée. Pas vérifié dans cette passe (hors scope).

**Pourquoi pas fixé en GO-2** : ajouter `DeleteStrategy` / `DeleteScope` touche l'interface dans `adapters/`, qui est le territoire de GO-1 (rewrite adapters terminé). GO-2 se limite à `internal/connect/` hors adapters. Un ticket GO-3 ou un fix ciblé côté webmethods est le bon chemin.

**Preuve de comportement préservé** :
- `TestPolicySyncerRemovesOIDCStrategyViaGenericFallback` vérifie que le disabled `oidc_strategy` passe bien par `RemovePolicy("oidc_strategy")` (pas un crash, pas un chemin typé).
- `TestPolicySyncerRemovesOIDCAuthServer` vérifie que seul `oidc_auth_server` prend le chemin typé `DeleteAuthServer`.

### C.2 — `AliasAdapter` non utilisé dans RunSync (documented, follow-up)

**Lieu** : `internal/connect/adapters/adapter.go:136-139` — `AliasAdapter{UpsertAlias, DeleteAlias}` existe mais aucune référence dans `internal/connect/*.go` hors tests.

**Conséquence** : si le CP émet un `PolicyType: "alias"` (ou similaire), il tombe dans le fallback générique `adapter.ApplyPolicy` — l'interface `AliasAdapter` reste dead code.

**Traitement** : à brancher dans un ticket séparé si le CP doit émettre des policies d'alias côté connect. Pour l'instant : dead code côté connect, utilisé ailleurs (peut-être par stoa-gateway ou stoa-connect côté webmethods adapter interne).

---

## Non-bugs relevés mais conscients

- **`a.client.Timeout = 15s`** global vs SSE override via nouveau `http.Client{Transport: a.client.Transport}` (ligne 129) : OK, le otelhttp transport est partagé correctement. Juste une alloc par reconnect, négligeable.
- **Seuil `reRegisterThreshold = 3`** avant re-register : sémantique conservée (ADR-057), extrait en const.
- **Ack timing at-least-once** : documenté, conservé.
