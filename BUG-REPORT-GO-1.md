# BUG-REPORT-GO-1

> **Document status**: audit artifact produced for branch
> `fix/go-1-p0-batch`. Lifetime: reviewable until the P0 + P1 + P2 batches
> ship; then move to `stoa-docs/audits/2026-04-23-go-1/` as a permanent
> engineering record. No dedicated Linear ticket yet (GO-1 is the module
> code name used in the audit prompt, not a tracker ID). Owner:
> @PotoMitan; update the "P0 batch status" table as later batches close
> the remaining H.*/M.*/L.* findings.

**Module**: GO-1 — stoa-connect webMethods adapter
**Path**: `stoa-go/internal/connect/adapters/`
**Scope**: 13 production files, ~2 100 LOC (after split PR #2459 `1559863bb`)
**Method**: line-by-line audit of the 3 user-flagged suspects + scan des fichiers adjacents (OIDC, credentials, discover, lifecycle, http, telemetry) + trace des consommateurs (`connect/routes.go`, `connect/sse.go`)
**Date**: 2026-04-23

## P0 batch status

| Bug | Status | Commit |
|---|---|---|
| C.1 — RemovePolicy partial delete | FIXED | `567c7ddf6` |
| C.2 — 409 Conflict silent skip | FIXED | `a085ecbad` |
| C.3 — syncedHashes race | FIXED | `a137d59b8` |
| C.4 — verifyAndActivate halt-batch | FIXED | `a085ecbad` |
| C.5 — DeactivateAPI halt-batch | FIXED | `a085ecbad` |
| C.6 — FailedRoutes shared state | FIXED | `a137d59b8` |

Branch: `fix/go-1-p0-batch`. P1/P2 remain open — see sections below.

---

## Executive summary

**17 bugs identifiés, dont 6 critiques.**

Les 3 suspects flaggés par le brief sont **tous confirmés**, mais **pas exactement aux endroits anticipés** :

1. **Policy sync asymétrique** → confirmé, mais le vrai trou n'est PAS côté OIDC (qui est délégué à `webmethods_oidc.go` via l'interface `OIDCAdapter` séparée). Le trou est dans `RemovePolicy` : la boucle `return nil` après la **première** correspondance → si webMethods a créé plusieurs `policyActions` du même template (doublon, race d'apply, ou upgrade qui a laissé l'ancienne), seule la première est supprimée, le reste reste **actif côté gateway**. Bug de sécurité fonctionnel.

2. **Retries dans SyncRoutes** → **il n'y a aucun retry**. Le 409 Conflict est silencieusement `continue`, sans fallback vers PUT, sans mise à jour de `syncedHashes`, et sans ack d'erreur. Résultat : route bloquée en boucle (re-tente à chaque cycle), jamais marquée `applied`, CP reste en état `pending`.

3. **Spec hygiene** → les 4 fonctions (`downgradeOpenAPI31`, `fixExternalDocs`, `fixSecuritySchemeTypes`, `stripSwagger2ResponseRefs`) ont des pièges regex + couverture partielle. La plus grave : `fixExternalDocs(data)` ligne 114 est **dead code** (appliqué après marshal sur un payload où `externalDocs` est nested dans `apiDefinition`).

En plus des 3 suspects, **une race condition data prod** : `FailedRoutes` et `syncedHashes` sont partagés entre la goroutine polling (`routes.go:118`) et la goroutine SSE (`sse.go:228`), sans mutex. Le reset `w.FailedRoutes = make(map[string]string)` à chaque call écrase les erreurs en cours. **Ça peut faire passer une route failed pour applied** si polling et SSE se croisent.

---

## Critical (6)

### C.1 — RemovePolicy ne supprime que la PREMIÈRE policy action matchante — FIXED (commit `567c7ddf6`, wM + Kong)

**File**: `webmethods_policy.go:170-189`

```go
for _, p := range policies.PolicyActions {
    if p.TemplateKey == wmType || p.TemplateKey == policyType {
        deleteURL := fmt.Sprintf("%s/rest/apigateway/policyActions/%s", adminURL, p.ID)
        // ... DELETE request ...
        return nil   // ← BUG: returns after first match
    }
}
```

**Impact** : si webMethods a **plusieurs** policy actions du même template pour une API (doublon créé par un `ApplyPolicy` concurrent, crash mid-apply qui a laissé un orphelin, ou upgrade qui a changé le nom mais pas le template), `RemovePolicy` n'en supprime qu'une. Les autres restent **actives côté gateway** alors que STOA les croit désactivées. Côté BDF/Engie, ça signifie qu'une policy rate-limit "supprimée" peut continuer à s'appliquer silencieusement — **divergence sécurité fonctionnelle**.

Corollaire : pas d'idempotence réelle. Premier `RemovePolicy` laisse N-1 policies, deuxième en laisse N-2, etc. Le test `webmethods_policy_test.go` ne couvre pas le cas multi-match.

**Fix suggéré** :
```go
var lastErr error
found := false
for _, p := range policies.PolicyActions {
    if p.TemplateKey == wmType || p.TemplateKey == policyType {
        found = true
        if err := w.doDelete(ctx, fmt.Sprintf("%s/rest/apigateway/policyActions/%s", adminURL, p.ID)); err != nil {
            lastErr = err
        }
    }
}
if lastErr != nil { return lastErr }
_ = found // no match = idempotent nil (unchanged)
return nil
```

---

### C.2 — SyncRoutes 409 Conflict silencieusement ignoré, sans retry, sans hash update — FIXED (commit `a085ecbad`)

**File**: `webmethods_sync.go:139-141`

```go
if resp.StatusCode == http.StatusConflict {
    continue
}
```

**Impact en cascade** :

1. **Pas de fallback POST→PUT.** Scénario : `listAPIsIndexedByName` retourne un snapshot stale (race avec un autre client webMethods, ou entrée concurrente). Le code décide `method = POST`, webMethods répond 409 "name already exists". Le code `continue`, sans re-lister, sans tenter un PUT. **Route jamais appliquée, jamais acknowledgée.**

2. **`syncedHashes[wmName]` n'est PAS mis à jour** (ligne 174-176 est sautée par le `continue`). Au prochain cycle de sync, même hash, même résultat : re-POST, re-409, re-continue. **Boucle infinie silencieuse** — la route consomme 1 call/cycle jusqu'à ce qu'un opérateur découvre le problème.

3. **`FailedRoutes[route.DeploymentID]` n'est PAS renseigné** (ligne 150-152 sautée aussi). La route n'apparaît ni en `failed`, ni en `applied`. `connect/routes.go:141-163` va la classer `applied` par défaut (branche `else` ligne 158). **CP reçoit un ack "applied" pour une route qui n'a jamais touché webMethods.** C'est le bug le plus dangereux du rapport.

4. **Pas de distinction "409 sur POST" (entité existe) vs "409 sur PUT" (version/gen conflict).** Les deux méritent des traitements différents.

**Fix suggéré** : sur 409 après POST, relister + retenter en PUT avec l'ID trouvé. Sur 409 après PUT, logger + marquer `FailedRoutes` avec `conflict` pour que CP régénère. Toujours mettre à jour `syncedHashes` seulement sur succès réel.

---

### C.3 — Race condition sur `FailedRoutes` et `syncedHashes` — FIXED (commit `a137d59b8`)

**File**: `webmethods_adapter.go:10-25`, `webmethods_sync.go:77, 95, 151, 174`

`WebMethodsAdapter` embed deux maps mutées sans mutex :
```go
syncedHashes map[string]string
FailedRoutes map[string]string
```

**Consommateurs concurrents** :
- `internal/connect/routes.go:118` — polling loop (toutes les N secondes)
- `internal/connect/sse.go:228` — SSE event consumer (async, par deployment event)

Les deux partagent la **même instance** `*WebMethodsAdapter` (construite une seule fois au démarrage — voir `connect/connect.go`). Rien ne sérialise les appels.

**Scénarios catastrophiques** :

- Polling boucle sur 20 routes, remplit `FailedRoutes` pour routes 1-3 échouées. SSE event arrive mid-boucle → entre dans SyncRoutes → **ligne 77 `w.FailedRoutes = make(map[string]string)` wipe** les erreurs du polling. `connect/routes.go:151` voit un map vide, classe les 3 routes échouées comme `applied`. **CP reçoit un ack menteur.**

- Deux goroutines lisent/écrivent `syncedHashes[wmName]` simultanément → panic Go runtime `concurrent map read and map write` (fatal, crash l'agent).

**Fix suggéré** : soit un `sync.Mutex` autour des accès map, soit mieux — `FailedRoutes` devient un retour de `SyncRoutes` (pas un état interne), et `syncedHashes` protégé par mutex ou remplacé par un `sync.Map`.

**Test** : aucun test ne couvre concurrence. Ajouter un `TestWebMethodsSyncRoutes_Concurrent` avec deux `go adapter.SyncRoutes(...)` et `go test -race`.

---

### C.4 — `verifyAndActivate` error halts entire sync loop — FIXED (commit `a085ecbad`)

**File**: `webmethods_sync.go:168-172`

```go
if apiID != "" {
    if err := w.verifyAndActivate(ctx, adminURL, apiID, wmName); err != nil {
        return err   // ← returns from SyncRoutes
    }
}
```

**Impact** : une seule route dont l'activation échoue **arrête tout le sync**. Les routes 4, 5, …, N ne sont ni tentées, ni marquées, ni acknowledgées. Contrairement au bloc non-2xx (ligne 142-154) qui utilise `syncErrors` + `continue`, ce chemin fait un hard return.

Pire : les routes skippées par ce return n'ont **aucune entrée** dans `FailedRoutes` → `connect/routes.go:151` les classifie `applied` par défaut. CP reçoit un ack positif pour des routes jamais touchées.

**Fix suggéré** : utiliser le même pattern `syncErrors` / `FailedRoutes` que pour les statuts non-2xx.

---

### C.5 — `DeactivateAPI` error halts entire sync loop (même pattern que C.4) — FIXED (commit `a085ecbad`)

**File**: `webmethods_sync.go:85-89`

```go
if err := w.DeactivateAPI(ctx, adminURL, existingID); err != nil {
    return fmt.Errorf("deactivate route %s: %w", route.Name, err)
}
```

Même problème : une route désactivée qui échoue à se désactiver kill tout le batch. Un wM en état dégradé (503 temporaire) cascade en 100% des routes suivantes classées `applied` par défaut.

**Fix** : collecter dans `syncErrors` + `FailedRoutes`, `continue`.

---

### C.6 — Polling ack pollué par SyncRoutes appelé depuis SSE — FIXED (commit `a137d59b8`)

**File**: `webmethods_sync.go:77`, `internal/connect/sse.go:228`, `internal/connect/routes.go:118-138`

Ceci est le "dual-channel" bug, séparé de C.3 :

`sse.go:228` appelle `adapter.SyncRoutes(ctx, adminURL, []adapters.Route{route})` avec **une seule** route → dans l'adapter :
- ligne 71 : `listAPIsIndexedByName` — fait un GET complet `/rest/apigateway/apis`
- ligne 77 : `w.FailedRoutes = make(map[string]string)` — **wipe** le map global

Mais `connect/routes.go:138` lit `adapter.(frp).GetFailedRoutes()` après son propre SyncRoutes. Si l'ordre temporel est :
1. polling call SyncRoutes → remplit FailedRoutes[dep-42] = "..."
2. SSE event arrive mid-batch → wipe FailedRoutes
3. polling re-lit FailedRoutes → vide → classe dep-42 comme `applied`

Le résultat atterrit dans un POST `route-sync-ack` vers CP qui marque la route en succès. **Silent data corruption** du côté contract STOA.

Fix couplé avec C.3 : `FailedRoutes` ne doit pas être un état partagé mutable.

---

## High (5)

### H.1 — `fixExternalDocs(data)` ligne 114 est dead code

**File**: `webmethods_sync.go:114`

```go
data, err := json.Marshal(apiPayload)
// ...
data = fixExternalDocs(data)  // ← no-op
```

`apiPayload` a un top-level `externalDocs` ? Non — il a `apiName`, `apiVersion`, `type`, `apiDefinition`. Le `externalDocs` (s'il existe) est **à l'intérieur** de `apiDefinition`. La fonction `fixExternalDocs` fait `parsed["externalDocs"]` sur le top-level → `nil` → return `spec` unchanged. Ligne 104 suffisait.

**Impact** : confusion du code, pas de bug fonctionnel direct (ligne 104 traite déjà le cas). À supprimer, et à remplacer par une version récursive qui traite `tags[].externalDocs`, `paths[].*.externalDocs`, `components.schemas.*.externalDocs` — que la version actuelle ne gère pas du tout.

---

### H.2 — `fixExternalDocs` ne gère que le top-level

**File**: `webmethods_spec.go:34-61`

OpenAPI 3.x autorise `externalDocs` comme **objet unique** aux niveaux :
- root (traité ✓)
- chaque élément de `tags[]` (NON traité)
- chaque opération `paths[].{get,post,...}.externalDocs` (NON traité)
- parfois dans schemas (NON traité)

Si un spec a `externalDocs` ailleurs qu'à la racine (très courant dans les specs générées par stoplight, swaggerhub, fastapi), il passe en l'état à webMethods → webMethods attend un array, crash la deserialization → **500 sur PUT**. L'erreur retourne au ligne 144-154 comme "webmethods api sync failed" sans détail utile.

**Fix suggéré** : walk récursif qui wrappe chaque `externalDocs: {...}` → `externalDocs: [{...}]` quel que soit le niveau.

---

### H.3 — `stripSwagger2ResponseRefs` ne gère pas OpenAPI 3.x

**File**: `webmethods_spec.go:110-171`

Le comment ligne 113 dit "Swagger 2.0 RefProperty parser". Mais OpenAPI 3.x peut avoir le même pattern de crash avec `content.<mime>.schema.$ref`. Le code gate strictement sur `bytes.Contains(spec, []byte("swagger"))` (ligne 115) et ne strip que `r["schema"]` (ligne 153, format Swagger 2.0).

**Impact** : un OpenAPI 3.x avec `$ref` dans response content schema passe tel quel → wM 10.15 peut crasher de la même façon. Pas observé en prod (BDF envoie du Swagger 2.0 via webMethods Designer), mais Engie/LV peuvent envoyer du 3.x. Risque latent démo juin.

**Fix suggéré** : détecter `openapi: 3.x` et strip aussi `content.<mime>.schema` récursivement (ou mieux : remplacer par `{type: object}`).

---

### H.4 — `mapPolicyConfig` ne mappe PAS `jwtPolicy` / `ipFilterPolicy`

**File**: `webmethods_policy.go:22-46`

Le switch gère `corsPolicy`, `throttlingPolicy`, `logInvocationPolicy`. `jwtPolicy` et `ipFilterPolicy` tombent dans `default: return config` (ligne 44). Donc la config STOA brute est envoyée à webMethods telle quelle.

Si STOA attend `{"issuer": "...", "audience": "..."}` mais webMethods attend `{"jwtIssuer": "...", "audienceClaim": "..."}`, wM renvoie 400 "invalid policy params". L'erreur bubble up correctement via `ApplyPolicy` (bien, contrairement à SyncRoutes), mais la policy reste non appliquée.

**Impact démo** : si la démo BDF exige JWT policy (vrai, vu CAB-2079 Auth/RBAC), le apply échoue silencieusement (log seulement).

**Fix** : ajouter les cases manquants, ou documenter explicitement que ces types doivent être envoyés déjà-mappés par CP.

Test `webmethods_policy_test.go:TestApplyPolicy` teste seulement `cors` + `throttling`. Couverture à étendre.

---

### H.5 — `buildSyncPayload` + invalid JSON spec = request corrompue silencieuse

**File**: `webmethods_sync.go:17-28`, `adapters/adapter.go:37`

`route.OpenAPISpec` est un `json.RawMessage`. Dans `buildSyncPayload` :
```go
"apiDefinition": json.RawMessage(spec),
```

Quand `json.Marshal(apiPayload)` s'exécute, si `spec` a été corrompu en amont (troncature réseau, mauvais fix dans fixExternalDocs qui a renvoyé du JSON invalide), **le Marshal peut renvoyer un buffer invalide sans erreur** (RawMessage ne valide pas toujours — comportement dépend de la version Go). Le POST/PUT vers webMethods envoie du JSON malformé → 400 avec error body obscur.

**Mitigation**: après chaque fonction de hygiène, ajouter un `json.Valid(spec)` check. Si false, logger + soit skip (fail closed) soit envoyer le spec original sans transformation.

---

## Medium (4)

### M.1 — Round-trip `json.Unmarshal(map[string]interface{}) → Marshal` perd précision numérique et ordre des clés

**Files**: `webmethods_spec.go` lignes 36, 67, 120

Les fonctions `fixExternalDocs`, `fixSecuritySchemeTypes`, `stripSwagger2ResponseRefs` decode en `map[string]interface{}` puis re-encode. Conséquences :
- entiers > 2^53 deviennent float64 (rare dans OpenAPI mais possible dans `example`)
- ordre des clés change (peut casser hash de spec calculé côté wM si utilisé pour dedup — probablement non, mais à vérifier)
- strings utf-8 sont re-encodées avec échappements Go (`<` → `<` par défaut si SetEscapeHTML)

**Impact** : cosmétique/edge cases. Note mais pas blocker.

---

### M.2 — `fixSecuritySchemeTypes` n'uppercase pas `scheme` des schemes HTTP

**File**: `webmethods_spec.go:87`

```go
for _, field := range []string{"type", "in"} {
```

Manque le champ `scheme` (pour type `http`) qui vaut `basic`/`bearer` — docs webMethods pour wM 10.15 demandent `BASIC`/`BEARER` uppercase pour certaines versions. Si Engie pousse un spec avec `{"type": "http", "scheme": "bearer"}`, le `type` devient `HTTP` mais `scheme` reste `bearer` → wM peut rejeter.

**Fix trivial** : ajouter `"scheme"` à la liste.

---

### M.3 — `Detect` masque toutes les erreurs réseau

**File**: `webmethods_adapter.go:33-48`

```go
resp, err := w.client.Do(req)
if err != nil {
    return false, nil   // ← nil error
}
```

Si wM est unreachable (DNS fail, timeout), `Detect` retourne `(false, nil)` — indistinguable de "wM is up, but endpoint 404". Conséquence : le caller choisit un autre adapter (Kong?) ou skippe wM sans logguer la cause réelle. À BDF, on peut finir à debug pourquoi "wM n'est pas détecté" alors que c'est juste un firewall temporaire.

**Fix** : retourner l'erreur, laisser le caller décider (avec éventuel wrapper qui log+swallow si besoin).

---

### M.4 — `parseEpochMillis` accepte silencieusement les formats corrompus

**File**: `webmethods_telemetry.go:43-47`

```go
_, err := fmt.Sscanf(s, "%d", &ms)
return ms, err
```

`Sscanf("abc123def", "%d", ...)` renvoie `0, error` ✓. Mais `Sscanf("123abc", "%d", ...)` renvoie `123, nil` (succès partiel). Timestamp tronqué accepté comme valide → event horodaté en **1970**. Peu d'impact réel (wM envoie du bon format), mais corrompt les dashboards si format change.

**Fix** : utiliser `strconv.ParseInt(s, 10, 64)` qui exige parsing total.

---

## Low (2)

### L.1 — `sanitizeWMName` peut créer des collisions

**File**: `webmethods_spec.go:15-20`

```go
wmNameRe = regexp.MustCompile(`[^a-zA-Z0-9._-]`)
```

Toutes les chars invalides mappées sur `-` → `stoa/foo` et `stoa.foo` et `stoa foo` deviennent tous `stoa-foo`. Collision silencieuse → 2 routes STOA → 1 API webMethods. Selon qui POST en premier, la seconde échoue (ou update la première via PUT).

**Fix** : append un hash court du nom original si collision détectée dans `listAPIsIndexedByName`.

---

### L.2 — `openAPI31Re` peut matcher dans une string value

**File**: `webmethods_spec.go:11`

```go
openAPI31Re = regexp.MustCompile(`"openapi"\s*:\s*"3\.1\.\d+"`)
```

Si un spec a un example `"description": "This was openapi: '3.1.0' before"` contenant littéralement cette sous-chaîne (improbable mais possible dans metadata), elle est réécrite. Cosmétique.

**Fix** : utiliser un parser JSON plutôt qu'un regex pour le champ `openapi`.

---

## Scope hors bugs — notes de design

- **Pas de retry HTTP**. `w.client` est un `http.Client{Timeout: 10s}` sans transport avec retry. Une latence pic wM > 10s = hard fail. Pattern des consommateurs (polling) absorbe via le prochain cycle, mais SSE single-shot n'a pas cette safety net.
- **Pas de rate-limiting côté client**. Un batch de 100 routes = 100+ GET list apis + 100 POST/PUT + 100 GET verify = 300+ calls séquentiels sur wM. Pas de coalescing du `listAPIsIndexedByName` (appelé une fois par call, OK).
- **`DeleteAPI` ignore l'erreur de deactivate** (ligne 123 : `_ = w.DeactivateAPI(...)`). Intentionnel selon comment, mais masque les vrais problèmes.
- **Tests ne couvrent pas 409, 500, timeout, ou concurrence**. Voir `webmethods_sync_test.go` — 4 tests, tous happy path.

---

## Priorité de fix (recommandation)

**P0 — avant démo juin** :
- C.2 (409 silent skip + no retry) — cause la plus probable de "route ne se sync pas" inexplicable
- C.3 + C.6 (race conditions) — cause silencieuse d'acks mensongers vers CP
- C.1 (RemovePolicy partial delete) — sécurité fonctionnelle BDF

**P1 — pour stabilité** :
- C.4, C.5 (hard returns qui kill le batch)
- H.2 (externalDocs non-racine) — selon format des specs clients
- H.4 (jwtPolicy / ipFilterPolicy non mappés)

**P2 — hygiène** :
- H.1 (dead code ligne 114)
- H.3 (OpenAPI 3.x $ref) — latent
- M.1-M.4, L.1-L.2

---

## Références

- Suspect 1 (policy sync) → §C.1, H.4
- Suspect 2 (SyncRoutes retries) → §C.2, C.3, C.4, C.5, C.6
- Suspect 3 (spec hygiene) → §H.1, H.2, H.3, H.5, M.1, M.2, L.2
- Scope élargi → §M.3, M.4, L.1

Tests de régression manquants pour CHAQUE bug C.1-C.6. Suggérer un ticket `CAB-GO-1-hardening` avec couverture race + 409 + multi-policy-delete + OIDC multi-action.
