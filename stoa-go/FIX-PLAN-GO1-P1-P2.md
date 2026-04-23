# FIX-PLAN-GO1-P1-P2

> **Document status**: planning artifact for branches `fix/go-1-p1-batch`
> (commits 4–5) and `fix/go-1-p2-batch` (commit 6). Lifetime: commits with
> the branches, archived to `stoa-docs/audits/2026-04-23-go-1/` together
> with `FIX-PLAN-GO1-P0.md` and `BUG-REPORT-GO-1.md` once the full GO-1
> cleanup series is merged. No dedicated Linear ticket (GO-1 = audit code
> name). Owner: @PotoMitan.

**Target branches**:
- `fix/go-1-p1-batch` off `main` (after P0 `#2492` merges)
- `fix/go-1-p2-batch` off `fix/go-1-p1-batch` (stacked)

**Prerequisite**: PR `#2492` (P0 batch) green in CI and merged before starting Phase 2.

**Commits prévus**: 3 atomiques, testables isolément, chacun avec régression guards.

**Source de référence**: `BUG-REPORT-GO-1.md` (sections High + Medium + Low).

**Statut**: PHASE 1 — plan uniquement, pas de code.

---

## Scope recap (post P0)

C.4 et C.5 ont été absorbés dans le commit 2 du P0 (`a085ecbad`) — ils ne reviennent pas ici.

| Bug | Commit cible | Fichier principal | Criticality |
|---|---|---|---|
| H.1 | Commit 4 (avec H.2) | `webmethods_sync.go:114` | dead code |
| H.2 | Commit 4 | `webmethods_spec.go:34-61` | High (démo) |
| H.4 | Commit 5 | `webmethods_policy.go:22-46` | High (CAB-2079) |
| H.5 | Commit 6 | `webmethods_sync.go` + `webmethods_spec.go` | High (latent) |
| H.3 | Commit 6 | `webmethods_spec.go:110-171` | High (latent 3.x) |
| M.2 | Commit 6 | `webmethods_spec.go:87` | Medium |
| M.3 | Commit 6 | `webmethods_adapter.go:33-48` | Medium (breaking internal) |
| M.4 | Commit 6 | `webmethods_telemetry.go:43-47` | Medium |
| L.1 | Commit 6 | `webmethods_spec.go:15-20` + `webmethods_lifecycle.go:40-67` | Low |
| L.2 | Commit 6 | `webmethods_spec.go:11` | Low |

**M.1 volontairement différé** (round-trip JSON `map[string]interface{}`) — c'est un refactor architectural (walk récursif sans unmarshal), pas un bug fix. Si on veut le traiter, c'est un rewrite dédié avec benchmarks avant/après, hors scope bug-fix.

---

## Commit 4 — H.2 + H.1 : externalDocs walk récursif + dead code

### Approche technique proposée

**Walk récursif map-based après `json.Unmarshal` vers `map[string]interface{}`.**

Logique : une fois la spec décodée en `map[string]interface{}`, parcourir récursivement toutes les valeurs. Pour chaque clé `externalDocs` dont la valeur est un objet JSON (map non-nil, pas déjà une slice), remplacer par un slice d'un élément contenant l'objet. Re-marshaler.

**Pourquoi map-based plutôt que struct typée** :
- Les specs OpenAPI ont des champs d'extension (`x-*`) et des formes partielles (Swagger 2.0 vs 3.0 vs 3.1) qu'une struct typée n'absorbe pas sans perte.
- Le walk est trivial en ~20 LOC en Go idiomatique (switch sur `interface{}`).
- Le cas `externalDocs` inside `x-*` extension sera aussi transformé — sémantiquement équivalent et bénin pour webMethods (il attend array partout si la clé existe).

**Alternative écartée** : parser typé OpenAPI avec chemins fixes (`tags[*].externalDocs`, `paths.*.*.externalDocs`, etc.). Avantage : précis. Inconvénient : quand la spec 3.2 ajoutera un nouveau lieu pour `externalDocs`, il faudra re-toucher le walk. Map-based est pérenne.

### Chemins OpenAPI couverts automatiquement par le walk récursif

- root `externalDocs` (existant, maintenu)
- `tags[*].externalDocs` (OpenAPI 2.0/3.x, Tag Object)
- `paths[*].{get|post|put|delete|patch|options|head|trace}.externalDocs` (Operation Object)
- `components.schemas.<name>.externalDocs` (Schema Object, OpenAPI 3.x)
- `components.schemas.<name>.properties.<field>.externalDocs` (Schema récursif)
- `components.schemas.<name>.items.externalDocs` (array items)
- `components.schemas.<name>.{allOf|oneOf|anyOf}[*].externalDocs` (composition)
- `definitions.<name>.externalDocs` (Swagger 2.0 equivalent)
- Toute extension `x-*.externalDocs` (bonus safe)

Le walk traverse automatiquement maps et slices, donc tout niveau d'imbrication est couvert sans énumération explicite.

### Format de transformation

Identique au top-level actuel : `externalDocs: {...}` → `externalDocs: [{...}]` partout où détecté, quel que soit le niveau.

### H.1 — suppression ligne 114 `data = fixExternalDocs(data)`

**Preuve que c'est safe** :

1. `data` à ce point est le résultat de `json.Marshal(apiPayload)` où `apiPayload` contient uniquement `apiName`, `apiVersion`, `apiDescription`, `type`, `apiDefinition` (nested `json.RawMessage`), `nativeEndpoint`, `resources`, `tags`, `isActive`. **Aucune clé `externalDocs` au top-level.**
2. La version actuelle de `fixExternalDocs` ne regarde que `parsed["externalDocs"]` à la racine — donc elle retourne inchangé sur ce payload.
3. Une fois le walk récursif actif, si on appliquait encore la fonction sur `data`, elle irait trouver les `externalDocs` nested **à l'intérieur du `apiDefinition`** — et là il y a un piège : `apiDefinition` est une `json.RawMessage` intégrée comme string JSON dans la marshalisation du wrapper. Le walk qui traverse le wrapper verrait `apiDefinition: "{\"openapi\":...}"` comme une **string**, pas comme un objet → ne descendrait pas dedans.
4. Donc même avec le walk récursif, appliquer fixExternalDocs sur le wrapper final est un no-op.
5. Le traitement correct est appliqué ligne 104 directement sur `spec` (bytes du spec brut), avant de le wrapper dans `apiDefinition`.

**Conclusion** : ligne 114 est dead code avant ET après le fix H.2. À supprimer sans remplacement.

### Fonctions impactées

| Fichier | Ligne | Changement |
|---|---|---|
| `webmethods_spec.go` | 34-61 | Réécriture complète de `fixExternalDocs` avec walk récursif. Signature inchangée : `fixExternalDocs([]byte) []byte`. |
| `webmethods_sync.go` | 114 | Supprimer `data = fixExternalDocs(data)` (dead code). |

Aucun autre caller à adapter.

### Fixtures de test proposées

**Fixture 1 — root externalDocs** (baseline, confirme pas de régression) :
```json
{"openapi":"3.0.3","info":{"title":"t","version":"1"},"externalDocs":{"url":"https://a","description":"A"}}
```
Expected after: `externalDocs: [{"url":"https://a","description":"A"}]`.

**Fixture 2 — tags externalDocs** :
```json
{"openapi":"3.0.3","info":{"title":"t","version":"1"},"tags":[{"name":"pets","externalDocs":{"url":"https://pets"}},{"name":"users"}],"paths":{}}
```
Expected: `tags[0].externalDocs` wrapped, `tags[1]` untouched.

**Fixture 3 — operation externalDocs** :
```json
{"openapi":"3.0.3","info":{"title":"t","version":"1"},"paths":{"/p":{"get":{"operationId":"g","externalDocs":{"url":"https://op"},"responses":{}}}}}
```
Expected: `paths["/p"].get.externalDocs` wrapped.

**Fixture 4 — components.schemas externalDocs (deep)** :
```json
{"openapi":"3.0.3","info":{"title":"t","version":"1"},"paths":{},"components":{"schemas":{"Pet":{"type":"object","externalDocs":{"url":"https://pet-doc"},"properties":{"owner":{"type":"object","externalDocs":{"url":"https://owner-doc"}}}}}}}
```
Expected: both `Pet.externalDocs` and `Pet.properties.owner.externalDocs` wrapped.

**Fixture 5 — deep combination** (tags + paths + components) :
Combine above fixtures in a single spec, assert every externalDocs is wrapped.

**Fixture 6 — no externalDocs anywhere** : idempotent, output bytes == input bytes (or at least equivalent JSON, accounting for round-trip key ordering).

**Fixture 7 — array already** : `externalDocs: [{"url":"..."}]` at some level → left untouched (not double-wrapped).

**Fixture 8 — invalid JSON** : malformed input → `fixExternalDocs` returns input unchanged (same defensive behaviour as today).

### Régression guards

| Test | Scénario | Fichier |
|---|---|---|
| `TestWebMethodsFixExternalDocs_TopLevel` | Fixture 1 — préserve le comportement actuel | `webmethods_spec_test.go` |
| `TestWebMethodsFixExternalDocs_InTags` | Fixture 2 | idem |
| `TestWebMethodsFixExternalDocs_InOperations` | Fixture 3 | idem |
| `TestWebMethodsFixExternalDocs_InComponents` | Fixture 4 — objet + schéma imbriqué | idem |
| `TestWebMethodsFixExternalDocs_DeepNesting` | Fixture 5 — combinaison | idem |
| `TestWebMethodsFixExternalDocs_NoExternalDocs` | Fixture 6 — idempotence | idem |
| `TestWebMethodsFixExternalDocs_AlreadyArray` | Fixture 7 — pas de double wrap | idem |
| `TestWebMethodsFixExternalDocs_InvalidJSON` | Fixture 8 — defensive | idem |
| `TestWebMethodsSyncRoutes_NoDoubleWrapExternalDocs` | Intégration : un spec avec externalDocs dans tags envoie bien un array (inspecte body POST) | `webmethods_sync_test.go` |

### Risques identifiés

- **R-A** : Le walk récursif peut matcher un `externalDocs` dans un nom d'extension vendor (`x-some.externalDocs`). Sémantiquement bénin pour webMethods (qui n'interprète pas les `x-*`), mais rend la transformation un peu plus générale qu'OpenAPI standard. Mitigation : documenter dans la godoc.
- **R-B** : Perf sur grandes specs (e.g. Swagger avec 500 endpoints × 20 responses chacune). Le walk est O(nodes). Un spec BDF réaliste ~2 MB est traité en < 10 ms. Non-problème sauf pour specs > 50 MB.
- **R-C** : Le round-trip `Unmarshal → Marshal` perd l'ordre des clés. Identique au comportement actuel de `fixExternalDocs`, ne constitue pas une régression.
- **R-D** : Le walk modifie la map en place (re-wrapping), puis Marshal. Si un autre code tient une référence à la map intermédiaire, il verrait la forme transformée — pas le cas ici (map créée et throwaway dans la fonction).

---

## Commit 5 — H.4 : jwtPolicy + ipFilterPolicy mapping

### Approche technique proposée

Ajouter deux cases au switch `mapPolicyConfig` en `webmethods_policy.go:22-46` :

```
case "jwtPolicy":
    return map with webMethods-expected JWT parameter names
case "ipFilterPolicy":
    return map with webMethods-expected IP filter parameter names
```

### Mapping jwtPolicy proposé (hypothèse basée sur webMethods 10.15 API Gateway doc patterns)

**Inputs STOA typiques** (déduit du schema CP-API `PolicyAction.Config` pour type=jwt) :
- `issuer` (string) — URL de l'issuer JWT
- `audience` (string ou []string)
- `jwks_url` (string) — URL JWKS pour la clé publique
- `required_claims` (map[string]string) — optionnel

**Outputs webMethods** (`jwtPolicy.parameters` schema, hypothèse) :
- `jwtIssuer` (string)
- `jwtAudience` (string ou []string)
- `jwksURL` (string)
- `requiredClaims` (map/object)

### Mapping ipFilterPolicy proposé

**Inputs STOA** :
- `mode` (string : "allow" | "deny")
- `ip_list` ([]string) — CIDR ou IPs

**Outputs webMethods** (hypothèse) :
- `ipFilterMode` (string : "ALLOW" | "DENY", uppercase — cohérent avec M.2 spec hygiene)
- `ipList` ([]string)

### Validation de l'hypothèse

L'audit initial ne dispose pas des docs webMethods 10.15 certifiées. Trois options :

1. **Demander à @PotoMitan** de valider les noms exacts via accès au portail IBM webMethods.
2. **Tester en staging** contre la POC client (VPS webMethods — IP in `infra-status.md` / private repo, resolved at integration time via `${WM_STAGING_URL:?set-me}`) avant merge.
3. **Committer la meilleure hypothèse avec `// WM-10.15-HYPOTHESIS` marker** et un test d'intégration optionnel qui tape le vrai wM (skip par défaut, activable via `INTEGRATION_WM_URL`).

**Recommandation** : option 3 — committer l'hypothèse avec marker explicite, **ne pas bloquer la démo sur la validation**, et convertir à la première Linear d'intégration quand Christophe aura validé. Le fallback `default: return config` actuel produit le même résultat qu'aujourd'hui (échec silencieux wM-side) — on passe donc d'un échec silencieux à un essai éclairé.

Si @PotoMitan confirme les noms avant merge, remplacer le marker et c'est règlé.

### Fonctions impactées

| Fichier | Ligne | Changement |
|---|---|---|
| `webmethods_policy.go` | 22-46 | Ajouter cases `jwtPolicy` et `ipFilterPolicy` au switch, avec marker hypothèse. |
| `webmethods_policy.go` | 13-19 | Ajouter `"jwt": "jwtPolicy"` et `"ip_filter": "ipFilterPolicy"` au mapping (déjà présents, OK). |

### Fixtures de test proposées

**Fixture jwt** :
```
STOA config: {"issuer":"https://keycloak.gostoa.dev/realms/oasis","audience":"stoa-portal","jwks_url":"https://keycloak.gostoa.dev/realms/oasis/protocol/openid-connect/certs"}
```
Expected wM params: `{"jwtIssuer":"https://keycloak.gostoa.dev/realms/oasis","jwtAudience":"stoa-portal","jwksURL":"https://keycloak.gostoa.dev/realms/oasis/protocol/openid-connect/certs"}`.

**Fixture ipFilter** :
```
STOA config: {"mode":"allow","ip_list":["10.0.0.0/8","192.168.1.1"]}
```
Expected wM params: `{"ipFilterMode":"ALLOW","ipList":["10.0.0.0/8","192.168.1.1"]}`.

### Régression guards

| Test | Scénario |
|---|---|
| `TestMapPolicyConfig_JwtPolicy` | Fixture jwt — mapping direct |
| `TestMapPolicyConfig_IpFilterPolicy` | Fixture ipFilter — mode uppercased |
| `TestApplyPolicy_JwtEndToEnd` | httptest mock wM ; ApplyPolicy envoie payload avec `type: jwtPolicy` et parameters mappés ; assert body reçu côté mock |
| `TestApplyPolicy_IpFilterEndToEnd` | idem pour ipFilter |
| `TestMapPolicyConfig_UnknownTypePassthrough` | Baseline — `default:` passthrough reste actif pour types non cors/throttling/logging/jwt/ipFilter |

### Risques identifiés

- **R-A** : noms de champs exacts possiblement différents de l'hypothèse (ex: `issuer` vs `jwtIssuer` vs `jwt_issuer`). Mitigation : marker `// WM-10.15-HYPOTHESIS` et test d'intégration optionnel.
- **R-B** : types de valeurs (`audience` string vs array). Si webMethods n'accepte que l'une des deux, la détection auto (`if slice`) règle.
- **R-C** : échec silencieux aujourd'hui → échec explicite demain. Une policy STOA qui passait en no-op côté webMethods va maintenant renvoyer 400 visible. C'est le comportement voulu, mais à signaler en release notes.

---

## Commit 6 — P2 cleanup : H.5 + H.3 + M.2 + M.3 + M.4 + L.1 + L.2

### Ordre dans le commit (high → low priority)

1. **H.5** — `json.Valid(spec)` check après chaque transform (fail-closed sur corruption)
2. **H.3** — `stripSwagger2ResponseRefs` étendu aux responses OpenAPI 3.x
3. **M.2** — `fixSecuritySchemeTypes` couvre aussi le champ `scheme`
4. **M.3** — `Detect` propage erreurs réseau au caller
5. **M.4** — `parseEpochMillis` via `strconv.ParseInt` (parsing total)
6. **L.1** — `sanitizeWMName` collision warn
7. **L.2** — `openAPI31Re` → JSON parse-based

### H.5 — emplacement exact des checks `json.Valid`

Deux stratégies candidate :

**A. Wrapper centralisé** dans `webmethods_spec.go` :
```
safeTransform(orig []byte, apply func([]byte) []byte) []byte {
    out := apply(orig)
    if !json.Valid(out) { return orig }
    return out
}
```
Appelé à chaque étape dans `webmethods_sync.go:102-107`.

**B. Check in-place** à la fin de chaque fonction `fixExternalDocs`, `fixSecuritySchemeTypes`, `stripSwagger2ResponseRefs` : elles ne retournent le marshalé que si valide, sinon retournent l'input original.

**Recommandation** : **B**. Plus localisé, chaque fonction est self-contained, pas de nouveau type. Les fonctions actuelles font déjà un fallback sur l'original si Marshal échoue — on ajoute juste `json.Valid` check au fallback path.

Important : la transformation walk-based introduite en H.2 peut construire un JSON valide structurellement mais qui diffère sémantiquement. `json.Valid` ne garantit pas le sens, seulement la syntaxe. Pour la sémantique, les tests regression couvrent.

### H.3 — `stripSwagger2ResponseRefs` étendu à OpenAPI 3.x

**Nom** : renommer en `stripResponseSchemas` (ou `stripResponseRefs`) — plus précis maintenant qu'on couvre les deux formats.

**OpenAPI 3.x** : responses sous `paths[*].<method>.responses.<code>.content.<mime>.schema`. Strip le champ `schema` (ou remplacer par `{"type":"object"}`).

**Détection du format** : `openapi` key présent → 3.x traitement, `swagger: "2.0"` → 2.0 traitement (existant). Sinon, skip.

**Risque** : changer le nom casse les callers. Vérifier — appel unique dans `webmethods_sync.go:106`. Rename + update.

### M.2 — `fixSecuritySchemeTypes` + `scheme`

Ajouter `"scheme"` à la liste `[]string{"type", "in"}` ligne 87. Seuls les schemes `http` ont un champ `scheme` (values : `basic`, `bearer`, `digest`, etc.). webMethods semble vouloir `BASIC` / `BEARER` uppercased selon les notes d'audit.

### M.3 — `Detect` propage les erreurs

**Changement de sémantique** :
- Avant : `return false, nil` sur network error (silent).
- Après : `return false, err` sur network error (propagated).

**Callers** :
- `internal/connect/discovery.go:69-91` (`autoDetect`) itère sur `[webmethods, kong, gravitee]` et appelle `adapter.Detect(ctx, adminURL)`. Actuellement : ignore l'error (`if ok, _ := ...`). Avec le change, l'autoDetect doit :
  - Soit continuer à ignorer l'erreur (network error = "pas ce gateway, try next")
  - Soit short-circuit sur certains types d'erreurs

**Recommandation** : `autoDetect` log l'erreur (context visible) et continue vers le suivant. Pas de short-circuit sémantique, juste une trace.

**Côté interface** : `GatewayAdapter.Detect(ctx, adminURL) (bool, error)` — signature déjà correcte, juste les implémentations qui retournaient `nil` qui changent.

### M.4 — `parseEpochMillis` via `strconv.ParseInt`

Trivial :
```
before: _, err := fmt.Sscanf(s, "%d", &ms); return ms, err
after:  return strconv.ParseInt(s, 10, 64)
```

**Risque** : aucun. `strconv.ParseInt` rejette tout input non-total-décimal, ce qui est le comportement voulu.

### L.1 — `sanitizeWMName` collisions

**Stratégie** : ajouter un log warning quand deux routes distinctes normalisent au même nom wM.

**Emplacement du check** : dans `SyncRoutes` (pas dans `sanitizeWMName` — la fonction elle-même ne sait pas), juste avant le loop :

```
seen := make(map[string]string) // wmName → original route name
for _, route := range routes {
    wmName := sanitizeWMName("stoa-" + route.Name)
    if prev, collision := seen[wmName]; collision && prev != route.Name {
        log.Printf("warn: sanitizeWMName collision — routes %q and %q both map to %q",
            prev, route.Name, wmName)
    }
    seen[wmName] = route.Name
    // ... existing logic
}
```

**Non breaking** — juste du log.

**Pas d'erreur explicite** — la collision effective crée 1 API wM pour 2 routes STOA (la 2ème écrase la 1ère via PUT). L'erreur serait plus propre mais c'est un changement comportemental. Log warning = observabilité sans rupture, conforme à l'esprit du batch.

### L.2 — `openAPI31Re` → JSON parse-based

Refactor `downgradeOpenAPI31` :
```
before: if !openAPI31Re.Match(spec) { return spec }
        return openAPI31Re.ReplaceAll(spec, []byte(`"openapi": "3.0.3"`))
after:  parsed := map[string]interface{}{}
        if err := json.Unmarshal(spec, &parsed); err != nil { return spec }
        v, _ := parsed["openapi"].(string)
        if !strings.HasPrefix(v, "3.1.") { return spec }
        parsed["openapi"] = "3.0.3"
        out, err := json.Marshal(parsed)
        if err != nil { return spec }
        return out
```

**Risque** : round-trip round-trip loses key ordering. Déjà le cas avec les autres fonctions. Pas de régression sémantique.

**Trade-off** : `regexp.Match` scanne le spec sans allocation lourde ; le JSON parse alloue la map complète. Sur grosses specs (~ MB), l'allocation JSON pèse ~10× plus. Accepté : le fix se produit sur un downgrade déjà rare (3.1 = peu adopté), et le coût est négligeable sur les tailles BDF.

### Fonctions impactées (récap)

| Fichier | Section | Changement |
|---|---|---|
| `webmethods_spec.go:11` | `openAPI31Re` + `downgradeOpenAPI31` | L.2 : regex → JSON parse |
| `webmethods_spec.go:34-61` | `fixExternalDocs` | H.5 : json.Valid check (walk déjà appliqué en commit 4) |
| `webmethods_spec.go:66-108` | `fixSecuritySchemeTypes` | M.2 : ajouter "scheme" à la liste ; H.5 json.Valid check |
| `webmethods_spec.go:110-171` | `stripSwagger2ResponseRefs` → `stripResponseSchemas` | H.3 : étendre à OpenAPI 3.x ; H.5 check ; **rename** |
| `webmethods_sync.go:106` | appel à stripResponseSchemas | Rename propagation |
| `webmethods_sync.go:80+` | boucle SyncRoutes | L.1 : collision detection pré-loop |
| `webmethods_adapter.go:33-48` | `Detect` | M.3 : propager `err` |
| `internal/connect/discovery.go:69-91` | `autoDetect` | M.3 : log l'erreur |
| `webmethods_telemetry.go:43-47` | `parseEpochMillis` | M.4 : strconv.ParseInt |

### Fixtures / Régression guards

| Test | Scénario | Bug |
|---|---|---|
| `TestValidateSpecAfterTransform_InvalidJSON` | Inject transform that produces invalid JSON → original returned | H.5 |
| `TestStripResponseSchemas_OpenAPI3` | 3.0 spec avec `content.*.schema.$ref` → schema stripped | H.3 |
| `TestStripResponseSchemas_Swagger2Preserved` | Baseline — le comportement 2.0 reste | H.3 |
| `TestFixSecuritySchemeTypes_HTTPScheme` | `{"type":"http","scheme":"bearer"}` → `{"type":"HTTP","scheme":"BEARER"}` | M.2 |
| `TestDetect_NetworkErrorPropagated` | adminURL inatteignable → `Detect` retourne `(false, err)` | M.3 |
| `TestAutoDetect_LogsPropagatedError` | autoDetect reçoit l'error et log + passe au suivant | M.3 |
| `TestParseEpochMillis_RejectsPartial` | `"123abc"` → error, `"123"` → 123 | M.4 |
| `TestSyncRoutes_SanitizeCollisionLogged` | Deux routes "foo/bar" + "foo bar" → warn log, 1 API apply | L.1 |
| `TestDowngradeOpenAPI31_ViaJSONParse` | `"openapi":"3.1.0"` → `"3.0.3"` ; pas de match sur `"description":"references openapi 3.1.0"` | L.2 |

### Risques identifiés

- **R-A (M.3)** : breaking change interne. `autoDetect` doit logger l'erreur sans short-circuiter. Test explicite `TestAutoDetect_LogsPropagatedError`.
- **R-B (H.3 rename)** : `stripSwagger2ResponseRefs` → `stripResponseSchemas`. Callers locaux au package. No external.
- **R-C (L.1 collision warning)** : pure log, non bloquant. Si opérateur ignore le warn et les deux routes écrasent, comportement identique à aujourd'hui (API wM écrasée par PUT du second).
- **R-D (H.5 fail-closed)** : si un fix quelque part produit un JSON invalide, on renvoie l'original non-fixé au wM → wM peut refuser l'original aussi. Comportement identique à aujourd'hui (pas de régression), mais met l'erreur en amont (log) plutôt qu'en aval (wM response 400).
- **R-E (perf L.2)** : JSON parse sur spec complète pour simple check de version. Sur specs de 10+ MB, ajoute quelques ms. Accepté — le code a déjà des round-trips similaires dans les autres fix functions.

---

## Phase 2 — ordre d'exécution (après validation)

1. **Prérequis** : PR `#2492` (P0) green + mergée.
2. **Commit 4** : H.2 + H.1 dans `fix/go-1-p1-batch` depuis `main`. 9 tests regression.
3. **Commit 5** : H.4 sur `fix/go-1-p1-batch`. 5 tests regression. PR → review → merge.
4. **Commit 6** : P2 cleanup sur `fix/go-1-p2-batch` depuis `main` (ou stacked sur P1). 9 tests regression.

Après chaque commit : `go test ./... -race -count=1` doit passer.

## Phase 3 — validation globale (final, après commit 6)

- `go vet ./...` ; `go test ./... -race -count=1` ; `golangci-lint run` ; `go build ./cmd/...`
- `BUG-REPORT-GO-1.md` — marquer H.1, H.2, H.3, H.4, H.5, M.2, M.3, M.4, L.1, L.2 comme `FIXED — commit <sha>`.
- M.1 annoté `DEFERRED — requires recursive walk refactor, out of bug-fix scope`.

---

## Questions à arbitrer avant Phase 2

1. **H.4 jwt/ipFilter** : valider les noms de champs webMethods avec @PotoMitan avant commit, ou committer avec marker `// WM-10.15-HYPOTHESIS` et valider plus tard ? Recommandation : marker + test staging.
2. **H.3 rename** `stripSwagger2ResponseRefs` → `stripResponseSchemas` : OK ou garder le nom historique et juste étendre la logique ? Recommandation : renommer (plus précis).
3. **L.1 collision** : warn log uniquement, ou erreur bloquante dès que détecté ? Recommandation : warn log (le batch ne doit pas durcir au-delà du bug scope).
4. **M.3 `Detect` error propagation** : mettre à jour tous les `autoDetect` callers dans le même commit, ou isoler ? Recommandation : même commit (cohérence).
5. **Stacking P1 → P2** : brancher P2 sur P1 (stacked PR) ou recréer depuis main après P1 merge ? Recommandation : depuis main après merge (diff plus clair pour review).

J'attends ton feedback sur ces 5 points avant Phase 2 — et/ou le green CI sur `#2492`.
