# REWRITE-PLAN — GO-2 : durcir `internal/connect/`

**Status** : VALIDATED 2026-04-22 (avec amendements). Prêt pour Phase 2.

**Scope** : `internal/connect/*.go` (hors `adapters/`, hors `telemetry/`)
**LOC actuels (prod)** : 2 127 LOC sur 8 fichiers + `cmd/stoa-connect/main.go` (177 LOC)
**Tests existants** : 69 tests sur 8 fichiers `*_test.go` (1 858 LOC) — `go test -race ./internal/connect/...` : **green baseline**

---

## A. Cartographie du flux actuel

### Processus top-level (`cmd/stoa-connect/main.go`)

```
main() ──► Agent.New(cfg)
        ├─► Register(ctx, port)          ... 1 call HTTP
        ├─► StartHeartbeat(ctx)           ... goroutine #1
        ├─► StartDiscovery(ctx, dcfg)     ... goroutine #2 (spawns adapter)
        ├─► StartSync(ctx, adapter)       ... goroutine #3 — policy sync
        ├─► if SSE enabled:
        │     StartDeploymentStream(..)   ... goroutine #4a — SSE route sync
        │   else:
        │     StartRouteSync(..)          ... goroutine #4b — polling route sync
        ├─► StartCredentialSync(..)       ... goroutine #5 (vault → adapter)
        └─► HTTP srv (health, metrics, /webhook/events)   ... goroutine #6
```

6 goroutines de fond lancées par `Agent.Start*`. Toutes ont un `select { case <-ctx.Done(): return }`. Cancel unifié via `ctx, cancel := context.WithCancel(background)` dans `main()`.

### Flux d'un event SSE (chemin chaud)

```
[CP API] POST /v1/internal/gateways/{id}/events (SSE)
  ▼
sse.go:StartDeploymentStream (goroutine)
  │  outer reconnect loop + expo backoff (2→60s)
  │  AVANT chaque connect: RunRouteSync(ctx, adapter, adminURL)  ◄── catch-up
  ▼
sse.go:streamEvents
  │  http.Client sans timeout, bufio.Scanner (64KB default), parse "event:" / "data:"
  ▼
sse.go:handleSSEEvent  (switch eventType)
  ├─ "heartbeat" → no-op
  └─ "sync-deployment" → handleSyncDeployment
        │  builds SyncStep trace : agent_received, adapter_connected, api_synced
        │  decode DeploymentEvent + desired_state → adapters.Route
        ▼
adapter.SyncRoutes(ctx, adminURL, []Route{route})
        ▼
reportDeploymentResultWithSteps → ReportRouteSyncAck (POST /route-sync-ack)
```

### Flux polling route sync (fallback SSE off)

```
routes.go:RunRouteSync (tick 30s)
  ├─► FetchRoutes (GET /v1/internal/gateways/routes?gateway_name=X)
  ├─► adapter.SyncRoutes(ctx, adminURL, routes)
  ├─► type-assert adapter.(failedRoutesProvider) → per-route status
  ├─► for each route with DeploymentID: build SyncedRouteResult
  └─► ReportRouteSyncAck (POST /route-sync-ack)
```

### Flux policy sync

```
sync.go:RunSync (tick 60s)
  ├─► FetchConfig (GET /v1/internal/gateways/{id}/config)
  ├─► for each PendingPolicy:
  │     switch (policy.PolicyType, adapter.(OIDCAdapter)):
  │       ├─ oidc_auth_server → oidcAdapter.UpsertAuthServer / DeleteAuthServer
  │       ├─ oidc_strategy    → oidcAdapter.UpsertStrategy
  │       ├─ oidc_scope       → oidcAdapter.UpsertScope
  │       └─ default          → adapter.ApplyPolicy / RemovePolicy
  ├─► update Prom metrics (applied, failed, status)
  └─► ReportSyncAck (POST /sync-ack)
```

### Flux heartbeat + re-register

```
connect.go:StartHeartbeat (tick 30s)
  ├─► Heartbeat (POST /heartbeat with uptime, routes_count, discovered_apis)
  │   → 404 = ErrGatewayNotFound
  └─► si 3× 404 consécutifs:
        ├─► a.gatewayID = ""               ◄── WRITE non-mutexed
        └─► Register(ctx, a.healthPort)    ◄── reset gatewayID
```

---

## B. Responsabilités identifiées

Chevauchements ciblés — six couches à démêler :

| Couche | Rôle | Aujourd'hui dispersé dans |
|--------|------|---------------------------|
| **Transport CP** | HTTP client, URL building, headers, JSON roundtrip, tracer spans | `connect.go` (Register/Heartbeat/ReportDiscovery), `sync.go` (FetchConfig/ReportSyncAck/ReportRouteSyncAck), `routes.go` (FetchRoutes) |
| **Transport SSE** | Connexion SSE, reconnect, scanner, wire parsing | `sse.go:streamEvents` (mélangé avec dispatch) |
| **Event dispatch** | Parsing SSE event type → route vers handler métier | `sse.go:handleSSEEvent` + `handleSyncDeployment` (dispatch + business logic collés) |
| **Sync orchestration** | Orchestration `adapter.Sync*` + build `[]SyncStep` + ack | `sync.go:RunSync` (policies), `routes.go:RunRouteSync` (routes polling), `sse.go:handleSyncDeployment` (routes SSE) — **3 chemins parallèles pour les mêmes primitives** |
| **State** | `gatewayID`, `lastDiscoveredAPIs` (mutable, multi-goroutines) — `healthPort` et `cfg` restent immuables | `Agent` struct (connect.go) sans mutex ; failed routes dans adapter via type-assert hack |
| **Retry** | Backoff SSE (concept distinct du seuil heartbeat) | SSE reconnect inline (`sse.go:75-107`) |

### Fonctions > 50 LOC concentrant plusieurs responsabilités

| Fonction | LOC | Responsabilités mélangées |
|----------|-----|---------------------------|
| `sync.go:RunSync` | 115 | fetch + big switch OIDC × 4 × (enabled/disabled) + métriques + ack |
| `routes.go:RunRouteSync` | 94 | fetch + sync + build steps + type-assert failedRoutes + ack |
| `connect.go:ReportDiscovery` | 69 | marshal hack (`interface{}` → remarshal) + HTTP + span + decode |
| `connect.go:Heartbeat` | 67 | build payload + HTTP + 404 handling + metrics |
| `sse.go:streamEvents` | 66 | connect + headers + scanner loop + line parsing + event emission |
| `connect.go:Register` | 67 | build payload + HTTP + decode + log + state mutation |
| `sse.go:handleSyncDeployment` | 54 | decode + build steps + sync + ack |
| `connect.go:StartHeartbeat` | 36 | loop + re-register threshold logic |

---

## C. Découpage fichier cible — FICHIERS PLATS, MÊME PACKAGE `connect`

Raison du flat : en Go, chaque sous-répertoire est un package distinct. Éclater en `sync/`, `loops/`, `dispatcher/` forcerait à sur-exporter les DTOs, introduire des interfaces partout pour briser les cycles, et `sync` conflit avec le package stdlib. Même package = accès direct aux types non-exportés, moins de churn d'imports. Boundaries enforced par convention de nom de fichier.

```
internal/connect/
├── agent.go               (~120)  Agent struct, New, SetTracer, Start*  (top-level composition)
├── config.go              (~180)  Toutes les *Config + *ConfigFromEnv
├── types.go               (~120)  DTOs wire : Registration*, Heartbeat*, Discovery*, PendingPolicy,
│                                   SyncAckPayload, SyncedPolicyResult, SyncedRouteResult, DeploymentEvent
├── state.go               (~100)  agentState{sync.RWMutex, gatewayID, lastDiscoveredAPIs}
│                                   GatewayID() / SetGatewayID() / ClearGatewayID()
│                                   SetDiscoveredAPIs(in) → copy    /   DiscoveredAPIs() → copy
│                                   ComputeRoutesCount(), DiscoveredAPIsCount()
│                                   /!\ healthPort et cfg restent immuables SUR Agent, hors lock.
├── steps.go               (~40)   SyncStep + newSyncStep + helpers
├── errors.go               (~30)   ErrGatewayNotFound + ErrNotRegistered (sentinels)
├── retry.go                (~80)   retry.Policy{Initial, Max, Multiplier} + Policy.Backoff(attempt)
│                                   USAGE : SSE reconnect UNIQUEMENT.
│                                   Le seuil heartbeat reRegisterThreshold=3 RESTE const séparée.
│
├── transport_cp.go        (~280)  cpClient : Register, Heartbeat, ReportDiscovery (typé),
│                                   FetchConfig, FetchRoutes, ReportSyncAck, ReportRouteSyncAck
│                                   1 constructor, 1 http.Client partagé, 1 startSpan helper
├── transport_sse.go       (~180)  sseStream.Run(ctx, sink func(rawEvent) error) error
│                                   Retourne l'erreur terminale du scanner (scanner.Err() inclus).
│                                   scanner.Buffer(initial=64KB, max=1MB) — fix bufio.ErrTooLong.
│                                   Pure transport : aucune dep à adapter/sync.
│
├── dispatcher.go          (~100)  dispatcher.Register(type, handler) + Dispatch(ctx, rawEvent)
│                                   Fermé au single-handler-par-type pattern.
│
├── sync_route.go          (~180)  routeSyncer.SyncRoutes(ctx, []Route) ([]SyncedRouteResult, error)
│                                   UNIQUE chemin partagé par polling + SSE.
│                                   Hébergé ici : le helper privé failedRoutesFromAdapter() qui
│                                   encapsule le type-assert (pas d'export depuis adapters/).
├── sync_policy.go         (~220)  policySyncer.SyncPolicies(ctx, []PendingPolicy) → []SyncedPolicyResult
│                                   Switch OIDC → méthodes privées : applyAuthServer, applyStrategy,
│                                   applyScope, applyGeneric, removeGeneric.
│
├── loop_heartbeat.go      (~80)   runHeartbeat(ctx, Agent) — inclut seuil 3 inchangé
├── loop_sse.go            (~80)   runSSEStream(ctx, ...) — reconnect via retry.Policy + catch-up + dispatch
├── loop_discovery.go      (~60)   runDiscovery(ctx, ...)
├── loop_credentials.go    (~60)   runCredentialSync(ctx, ...)
│   (NB : StartSync tick 60s policy reste inline dans agent.go — trivial — OU ajouté en loop_sync.go)
│
├── metrics.go             (~90)   INCHANGÉ
└── vault.go               (~180)  INCHANGÉ
```

22 fichiers prod (vs 8), tous ≤ 300 LOC. Un seul package, zéro changement d'import pour les callers (`cmd/stoa-connect/main.go` continue d'`import "internal/connect"`).

---

## D. Retry / ack policy

### Dispersion actuelle

| Endroit | Politique | Valeurs hardcodées |
|---------|-----------|--------------------|
| `sse.go:75-107` | expo backoff × 2 cap 60s | 2s, 60s, multiplier 2 |
| `connect.go:317-348` | seuil 3× 404 avant re-register | `reRegisterThreshold = 3` |
| `credentials.go:46-51` | TTL < 300s → renew, fail → re-login | 300 |
| `sync.go`/`routes.go` (ack) | fire-and-forget, log warning | — |
| `http.Client.Timeout` | 15s global | SSE override : `client.Timeout = 0` |

### Proposition (amendée)

**1. `retry.Policy`** — backoff SSE **uniquement** :
```go
type Policy struct {
    Initial    time.Duration
    Max        time.Duration
    Multiplier float64
}
func (p Policy) Backoff(attempt int) time.Duration { /* expo capped */ }
```
Utilisé seulement dans `loop_sse.go`. Configurable via `SSEConfig` (déjà le cas aujourd'hui).

**2. Seuil heartbeat re-register** : **inchangé** à 3. Juste extrait en const :
```go
// connect.go ou loop_heartbeat.go
const reRegisterThreshold = 3
```
Ne PAS mélanger avec `retry.Policy` — sémantique différente (compteur stateful vs backoff timing).

**3. Vault renew** : hors scope GO-2, reste dans `credentials.go`/`vault.go`.

**4. Ack timing — sémantique at-least-once** (inchangée, documentée) :
- Ack APRÈS apply. Si sync fail → ack status="failed". Si ack fail → fire-and-forget (le prochain tick re-synchronisera).
- Pas de retry sur l'ack côté agent.
- Double-ack possible après SSE reconnect : CP doit dedupe sur `deployment_id`.

**5. SSE transport remonte l'erreur terminale** :
```go
// transport_sse.go
func (s *sseStream) Run(ctx context.Context, sink func(rawEvent) error) error
```
- Return `scanner.Err()` si non-nil (inclut `bufio.ErrTooLong`).
- Return `io.EOF`-style pour fermeture propre côté serveur.
- La boucle `runSSEStream` log l'erreur concrète AVANT le backoff, pas juste "connection lost".

---

## E. Plan d'exécution — bottom-up

Chaque étape : commit séparé, tests verts avec `-race` avant commit, pas de régression LOC/coverage.

| # | Étape | Fichiers touchés | Critère vert | Commit |
|---|-------|------------------|--------------|--------|
| **S1** | `state.go` + mutex + copy-on-write | créer `state.go`, migrer `Agent.gatewayID` + `lastDiscoveredAPIs` derrière RWMutex. `SetDiscoveredAPIs` copie l'entrée. `DiscoveredAPIs()` retourne une copie. `ComputeRoutesCount`/`DiscoveredAPIsCount` lisent sous RLock. `healthPort` et `cfg` **restent sur Agent, hors lock** (immuables après `New`). | Tests existants verts. **Nouveau** `TestAgentStateRace` : N goroutines `Heartbeat()` + 1 goroutine `ClearGatewayID` + 1 goroutine `SetDiscoveredAPIs` sous `-race`. | `refactor(connect): extract agentState with RWMutex (GO-2 S1)` |
| **S2** | `retry.go` pour SSE backoff seul | créer `retry.go` avec `Policy{}` + `Backoff(attempt)`. Migrer `StartDeploymentStream` pour l'utiliser. Seuil heartbeat **non-touché** à cette étape. | `sse_test` inchangé (comportement identique, reconnect test adapté éventuellement). Table test `TestRetryPolicyBackoff`. | `refactor(connect): extract retry.Policy for SSE backoff (GO-2 S2)` |
| **S3** | `types.go` + `steps.go` + `errors.go` | déplacer DTOs wire + `newSyncStep` + `ErrGatewayNotFound` + nouveau `ErrNotRegistered`. Remplacer tous les `fmt.Errorf("not registered")` par le sentinel. | Tests verts (déplacement pur). | `refactor(connect): extract wire DTOs + sentinel errors (GO-2 S3)` |
| **S4** | `transport_cp.go` | créer `cpClient{client, tracer, baseURL, apiKey}` avec 7 méthodes HTTP (~30 LOC chacune). **Fix in-flight** : `ReportDiscovery` prend `[]DiscoveredAPIPayload` typé (la conversion depuis `adapters.DiscoveredAPI` reste dans `runDiscovery`). Agent délègue : `a.cp.Register(ctx, ...)`. | Tests HTTP existants adaptés aux signatures typées. | `refactor(connect): extract cpClient HTTP transport (GO-2 S4)` |
| **S5** | `transport_sse.go` avec erreur terminale + buffer fix | créer `sseStream.Run(ctx, sink) error`. Retourner `scanner.Err()`. `scanner.Buffer(make([]byte, 0, 64<<10), 1<<20)`. Aucun appel à adapter/sync dans ce fichier. | `TestStreamEventsParsesSyncDeployment` etc. adaptés à consommer depuis `sink`. Nouveau test : message > 64KB → pas d'ErrTooLong silencieux (le sink reçoit le gros message OU Run retourne l'erreur propre). | `refactor(connect): extract sseStream with error propagation + buffer fix (GO-2 S5)` |
| **S6** | `dispatcher.go` | petit module Dispatcher. `loop_sse.go` (step S9) l'utilisera : SSE → rawEvent → dispatcher.Dispatch. | Nouveau `dispatcher_test.go` (3-4 tests). | `refactor(connect): extract event dispatcher (GO-2 S6)` |
| **S7** | `sync_route.go` unifié | `routeSyncer.SyncRoutes(ctx, []Route) []SyncedRouteResult`. **Point clé** : la duplication `routes.RunRouteSync` ↔ `sse.handleSyncDeployment` converge ici. Le helper privé `failedRoutesFromAdapter()` encapsule le type-assert. | `TestRunRouteSync*` + `TestSSESyncDeployment*` passent via le nouveau syncer. | `refactor(connect): unify route sync path (GO-2 S7)` |
| **S8** | `sync_policy.go` | `policySyncer.SyncPolicies(ctx, []PendingPolicy)`. Switch OIDC → `applyAuthServer` / `applyStrategy` / `applyScope` / `applyGeneric` / `removeGeneric`. | `TestRunSync*` verts. | `refactor(connect): split policy sync by type (GO-2 S8)` |
| **S9** | `loop_*.go` | extraire les boucles hors de l'Agent. `runHeartbeat(ctx, Agent)` garde `const reRegisterThreshold = 3`. `runSSEStream(ctx, ...)` utilise `retry.Policy` + dispatcher + transport_sse. `runDiscovery` / `runCredentialSync` idem. | Tests `TestStartXxxSkipsNoURL` + `TestStartHeartbeat*` verts. | `refactor(connect): extract orchestration loops (GO-2 S9)` |
| **S10** | Cleanup + cmd | supprimer code mort (anciennes méthodes Agent devenues redondantes), adapter `cmd/stoa-connect/main.go` si signature change. `golangci-lint run` vert. | Build + `go test ./... -race` + `golangci-lint run` verts. `find internal/connect -maxdepth 1 -name '*.go' -not -name '*_test.go' \| xargs wc -l \| sort -rn` → max ≤ 300. | `refactor(connect): finalize GO-2 split + cleanup` |

**Validation entre chaque étape** :
```bash
go vet ./... && \
go test ./internal/connect/... -race -count=1 && \
go build ./cmd/stoa-connect && \
find internal/connect -maxdepth 1 -name '*.go' -not -name '*_test.go' | xargs wc -l | sort -rn | head
```

**Test manuel en fin de parcours (S10)** : `STOA_CONTROL_PLANE_URL=http://localhost:8000 STOA_GATEWAY_API_KEY=xxx stoa-connect` + simuler déconnexion réseau → reconnexion propre + pas de double apply côté gateway local.

---

## F. Risques identifiés

### Concurrence — fixés in-flight pendant GO-2

| # | Bug | Impact | Fix étape |
|---|-----|--------|-----------|
| F.1 | RACE `Agent.gatewayID` — heartbeat loop écrit `""` pendant re-register, 5 autres goroutines lisent. `-race` ne flag pas aujourd'hui (tests pas concurrents) mais réel en prod. | latent | **S1** |
| F.2 | RACE `Agent.lastDiscoveredAPIs` — discovery loop écrit slice, `/health` handler + heartbeat `computeRoutesCount` lisent. | latent | **S1** (copy-on-write) |
| F.6 | `bufio.Scanner` buffer défaut 64KB — un event SSE avec `desired_state` volumineux → `bufio.ErrTooLong`, goroutine SSE sort silencieusement (Scanner.Err() non lu aujourd'hui). | latent | **S5** (`scanner.Buffer` + propagation d'erreur) |
| F.10 | `ReportDiscovery(apis interface{})` — marshal/unmarshal hack pour conversion type. | code smell | **S4** (signature typée `[]DiscoveredAPIPayload`) |

### Concurrence — documentés, NOT fixed in-flight

| # | Bug | Raison |
|---|-----|--------|
| F.3 | Goroutine SSE : si ctx cancellé pendant le `RunRouteSync` catch-up, on reste dans ce call. | Fragile mais correctness OK ; l'amélioration naturelle vient avec S9 (loop propre). |
| F.4 | Discovery 1st batch perdu si `gatewayID == ""` au moment du call. | Récupéré au tick suivant (60s), impact faible. |
| F.5 | SSE catch-up RouteSync à chaque reconnect = re-push complet au gateway local. | Perf, pas correctness. Hors scope ; ticket follow-up si la démo montre un problème. |
| F.7 | Double-ack possible après reconnect SSE. | CP doit dedupe sur `deployment_id` (à vérifier côté CP-API). Hors scope agent. |

### Champs morts / obsolètes

| # | Champ | Traitement |
|---|-------|------------|
| F.8 | `HeartbeatPayload.PoliciesCount` déclaré, jamais populé. | Documenté dans `REWRITE-BUGS.md`, laissé en place (wire stability). Fix follow-up. |
| F.9 | `GatewayConfigResponse.PendingDeployments []interface{}` déclaré, jamais lu. | Idem. Vérifier côté CP si encore émis. |

### Type safety

| # | Item | Traitement |
|---|------|------------|
| F.11 | `failedRoutesProvider` type-assertion implicite. | **Helper local privé** dans `sync_route.go`, pas d'export depuis `adapters/` (hors scope GO-1/GO-2). Dette documentée. |

### Ce qu'on ne touche PAS

- Protocole wire CP ↔ agent (ADR-057 + ADR-059). Zéro changement : event types SSE, structure payloads, headers, endpoints.
- Interfaces `adapters.GatewayAdapter / OIDCAdapter / AliasAdapter` (GO-1 territory).
- `cmd/stoa-connect/main.go` sauf adaptations forcées par signature Agent.
- `telemetry/` et `pkg/config/`.

---

## Décisions validées (2026-04-22)

1. **Fichiers plats, même package** `connect` — pas de sous-packages.
2. **Seuil `reRegisterThreshold = 3`** conservé inchangé, juste extrait en const.
3. **SSE transport** expose l'erreur terminale via `Run(ctx, sink) error`.
4. **`state.go`** mute `gatewayID` + `lastDiscoveredAPIs` avec RWMutex + COW sur slice. `healthPort` et `cfg` restent immuables sur Agent.
5. **Fix in-flight** : F.1 (race gatewayID, S1), F.2 (race slice, S1), F.6 (Scanner buffer, S5), F.10 (`ReportDiscovery` typé, S4).
6. **`failedRoutesProvider`** reste un helper local dans `sync_route.go`, pas d'export `adapters/`.
7. **Nouvelle branche** `refactor/go-2-connect-split` depuis `main`.

---

**GO Phase 2.**
