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

### F.6 — `bufio.Scanner` buffer 64KB (fix in-flight S5)

**Lieu** : `sse.go:146` — `scanner := bufio.NewScanner(resp.Body)`.

**Symptôme** : un event SSE avec `desired_state` volumineux (OpenAPI spec inlinée > 64KB) dépasse le buffer scanner défaut (`bufio.MaxScanTokenSize` = 64KB). Comportement :
1. Scanner retourne `false` silencieusement.
2. Boucle sort.
3. `scanner.Err()` serait `bufio.ErrTooLong` **mais n'est jamais lu** par le code actuel.
4. La fonction retourne `fmt.Errorf("SSE stream ended")` — l'erreur réelle est perdue.
5. Outer loop reconnecte, même event arrive à nouveau, même truncation. Boucle infinie de reconnect.

**Preuve** : `grep -n "scanner.Err()" internal/connect/sse.go` → ligne 172, mais la condition est seulement évaluée si la boucle `for scanner.Scan()` se termine "proprement" — or `ErrTooLong` met aussi fin à la boucle, donc en théorie `scanner.Err()` attrape bien l'erreur. À vérifier côté comportement observé.

**Fix S5** :
```go
scanner := bufio.NewScanner(resp.Body)
scanner.Buffer(make([]byte, 0, 64<<10), 1<<20) // 1 MB max
```
Et `sseStream.Run(ctx, sink) error` retourne `scanner.Err()` explicite (ne reformule pas en "stream ended").

**Régression guard** : test avec `data:` > 64KB → `sink` reçoit le message entier sans truncation.

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

## Non-bugs relevés mais conscients

- **`a.client.Timeout = 15s`** global vs SSE override via nouveau `http.Client{Transport: a.client.Transport}` (ligne 129) : OK, le otelhttp transport est partagé correctement. Juste une alloc par reconnect, négligeable.
- **Seuil `reRegisterThreshold = 3`** avant re-register : sémantique conservée (ADR-057), extrait en const.
- **Ack timing at-least-once** : documenté, conservé.
