# STOA Demo — Architecture Rules (contrats figés)

> **Statut**: v1.0 — 2026-04-24. Ces contrats sont figés pendant toute la durée du rewrite.
> **Règle dure**: toute PR qui enfreint un contrat figé est **NO-GO par défaut**, même si elle améliore autre chose.

## 1. Périmètre architectural démo (verticale unique)

```
┌────────────────┐        ┌──────────────────┐       ┌───────────────┐
│   stoactl /    │  HTTPS │  control-plane-  │       │               │
│   curl (CLI)   ├───────►│  api (FastAPI)   │◄─────►│   Postgres    │
└────────────────┘   REST │  port 8000       │       │   (api,app,   │
                          └──────┬───────────┘       │    sub,depl)  │
                                 │ route-sync        └───────────────┘
                                 │ (polling GET OR SSE)
                                 ▼
                          ┌──────────────────┐
                          │  stoa-gateway    │       ┌───────────────┐
  client démo ────HTTP───►│  (Rust, Axum)    ├──────►│  mock-backend │
  + X-Api-Key             │  port 8081       │       │  (httpbin)    │
                          │  /apis/*path     │       │  port 9090    │
                          └──────┬───────────┘       └───────────────┘
                                 │
                                 ▼
                     Prometheus /metrics + JSON stdout logs
                     + optional OTEL visibility in Grafana/Console/Portal
```

Tout composant non présent dans ce diagramme (Portal, Console UI, Kafka, OpenSearch, vault-gostoa, Keycloak-federation, stoa-catalog, stoa-connect en scope restreint) est **hors chemin démo provider/runtime**. Peut exister, ne doit pas être requis pour `demo-smoke-test.sh` `REAL_PASS`.

## 2. Contrats figés (ne JAMAIS casser en rewrite)

### 2.1 HTTP endpoints cp-api (URL + method + status code + shape minimal)

Auth démo provider/runtime :

- Auth réelle : JWT Keycloak valide via `Authorization: Bearer`.
- Bypass démo/dev borné : `STOA_DISABLE_AUTH=true` côté cp-api **et** header
  `X-Demo-Mode: true` sur la requête.
- `STOA_DISABLE_AUTH=true` est interdit en `ENVIRONMENT=production` et doit
  faire échouer le boot cp-api.
- Dans ce mode explicite seulement, `POST /v1/tenants/{tid}/applications`
  peut retourner une application synthétique `demo-{tenant}-{app}` sans créer
  de client Keycloak. Hors smoke démo, les applications restent des clients
  Keycloak réels.

| Endpoint | Method | Status OK | Champs min réponse |
|----------|--------|-----------|--------------------|
| `/v1/tenants/{tid}/apis` | POST | 201 | `id`, `name` |
| `/v1/tenants/{tid}/apis` | GET | 200 | `items[]` avec `id`, `name` |
| `/v1/tenants/{tid}/apis/{id}` | GET | 200 | `id`, `name`, `backend_url` |
| `/v1/tenants/{tid}/applications` | POST | 201 | `id`, `name` |
| `/v1/tenants/{tid}/applications/{id}/subscribe/{api_id}` | POST | 200 | `subscription_id`, `api_key`, `api_key_prefix` en mode `X-Demo-Mode: true`; sinon message historique |
| `/v1/subscriptions` | POST | 201 | `id`, `api_key` ou `api_key_prefix`, `status="active"` |
| `/v1/tenants/{tid}/deployments` | POST | 201 | `id`, `status` |
| `/v1/internal/gateways/routes?gateway_name=X` | GET | 200 | liste de routes avec `api_id`, `path` |
| `/health` | GET | 200 | n/a |

### 2.2 HTTP endpoints gateway

| Endpoint | Method | Status OK | Comportement |
|----------|--------|-----------|---------------|
| `/health` | GET | 200 | body indifférent |
| `/metrics` | GET | 200 | format Prometheus text |
| `/apis/{api_name}/{*path}` | GET/POST/… | 200/…  | chemin gateway canonique démo. `api_name` est le slug retourné par `POST /v1/tenants/{tid}/apis`; proxy vers backend configuré, header `X-Stoa-Request-Id` en réponse, vérifie `X-Api-Key` (ou `Authorization: Bearer`) |

### 2.2bis Contrat UAC démo minimal

Le smoke réel peut être UAC-driven via `DEMO_UAC_CONTRACT=specs/uac/demo-httpbin.uac.json`.
Ce contrat ne généralise pas toute l'architecture STOA; il verrouille seulement
la première preuve fonctionnelle "Define once, expose everywhere" sur un contrat,
un endpoint, un chemin gateway:

| Champ | Valeur figée |
|-------|--------------|
| `name` | `demo-httpbin` |
| `tenant_id` | `demo` |
| `version` | `1.0.0` |
| `status` | `published` |
| `classification` | `H` |
| `endpoints[0].methods[0]` | `GET` |
| `endpoints[0].path` | `/get` |
| `endpoints[0].backend_url` | `http://mock-backend:9090` |
| `endpoints[0].operation_id` | `demo_httpbin_get` |
| chemin gateway dérivé | `/apis/demo-httpbin/get` |

Le fallback sans `DEMO_UAC_CONTRACT` reste autorisé pour debug local, mais doit
afficher `WARN — smoke not UAC-driven`.

### 2.3 Format métriques Prometheus

Nom obligatoirement présent: **au moins un** de
- `proxy_requests_total{tenant,api,method,status}`
- `mcp_tool_calls_total{...}`

incrémenté à chaque appel proxyé. Changement de nom = breaking contract démo.

### 2.4 Format logs

Logs gateway en **JSON par ligne**, stdout, contenant au minimum :
- `timestamp`
- `level`
- `message`
- `tenant` (si dispo)
- `api_id` (si dispo) OU `route_prefix`
- `request_id` (UUID, identique à header `X-Stoa-Request-Id`)

Le format `tracing-subscriber` JSON actuel convient.

### 2.5 Visibilité observabilité UI (nice-to-have)

Ces surfaces doivent rester compatibles avec la démo, sans être bloquantes pour le `REAL_PASS` v1:

| Surface | URL locale | Source de données attendue | Preuve |
|---------|------------|----------------------------|--------|
| Grafana | `http://localhost:3001` | `Prometheus`, `Loki`, `OpenSearch Traces`, `Tempo` | `/api/health` OK + datasource provisionnée |
| Console | `http://localhost:3000/monitoring` | `GET /v1/monitoring/transactions` | Page routable + liste transactions quand OTEL existe |
| Portal | `http://localhost:3002/usage` | `GET /v1/usage/me*` + dashboard Grafana embarqué optionnel | Page routable + usage visible pour le consommateur |

Si `STOA_OTEL_ENDPOINT` est défini, la stack compose doit permettre de retrouver la trace via `OpenSearch Traces` (`otel-v1-apm-span-*`) ou `Tempo`. Absence d'OTEL = warning, pas cassage AT-5.

### 2.6 Compatibilité DB consommée par le smoke

Le smoke ne fige pas tout le modèle relationnel. Il fige uniquement la
compatibilité fonctionnelle nécessaire aux endpoints de §2.1 et aux assertions
AT-1..AT-5.

Champs consommés directement ou indirectement par le smoke:
- API: identifiant, tenant, nom, version, backend URL
- Application: identifiant, tenant, nom
- Subscription: identifiant, application, API, statut actif, hash/prefix de clé
- Deployment: identifiant, API, environnement, gateway, statut
- API key: hash/prefix/état actif si les clés sont stockées dans une table séparée

Une migration Alembic peut ajouter des colonnes ou refactorer le stockage interne
si les endpoints de §2.1 gardent leur shape minimale et si AT-1..AT-5 restent
réels. Renommer/supprimer un champ consommé par le smoke sans compatibilité API
= contrat cassé.

### 2.7 Auth modèle démo

- **Un seul mode supporté côté démo**: API key via header `X-Api-Key: stoa_<prefix>_<secret>`
- Le cleartext de cette clé n'est retourné qu'une fois, sur une souscription créée avec `X-Demo-Mode: true`.
- JWT/OAuth reste dispo mais pas dans le smoke path
- mTLS, DPoP, sender-constraint: hors périmètre démo

## 3. Règles structurelles (rewrite peut bouger, mais pas casser les contrats)

1. **Le Config flat gateway (§1 GW-2 REWRITE-PLAN) est figé** tant que la démo n'est pas stable. Le split `config.rs → config/*.rs` (GW-2) est OK car il préserve le contrat TOML/env. Toute nouvelle sous-struct qui casserait un `STOA_*` env var = NO-GO.
2. **Les migrations Alembic** sont additives uniquement pendant le rewrite. Renommage colonne ⟹ Council obligatoire.
3. **Les endpoints listés §2.1 gardent leur URL**. Route rename ⟹ alias 301 pendant ≥ 1 cycle.
4. **stoa-connect** peut évoluer son protocole SSE, mais doit conserver le fallback polling `GET /v1/internal/gateways/routes` pour la démo locale sans SSE.
5. **Feature flags Cargo du gateway** (`kafka`, `k8s`) : la démo tourne en build **default (community, no features)**. Toute dépendance à `kafka` ou `k8s` dans le chemin démo = cassage.

## 4. Contraintes opérationnelles démo

- Démarre **en moins de 60s** sur un laptop (docker-compose + cargo run + pytest minimal startup)
- Tourne **offline** une fois les dépendances pulled (pas besoin réseau externe pendant exécution)
- N'exige **aucun secret en prod** (utilise `.env.demo` figé, clés jetables)
- Utilise **un seul tenant** nommé `demo`, un seul environnement `demo`

## 5. Anti-règles (patterns à refuser en PR)

- "Je refactore et je casse la compatibilité DB consommée par le smoke (§2.6) au passage" → STOP. Split en 2 PR.
- "J'ajoute un middleware obligatoire qui exige X" où X n'est pas seedé dans la démo → STOP.
- "Je remplace `X-Api-Key` par un JWT obligatoire" → STOP, casse AT-4.
- "Je change le format Prometheus pour OpenMetrics+labels différents" → STOP, casse AT-5.
- "Je mets la route `/apis/{api_name}/{*path}` sous un feature flag" → STOP.

## 6. Escalade

Si un rewrite a besoin de casser un contrat figé :
1. Ouvrir une ADR dans `stoa-docs/docs/architecture/adr/` qui documente le breaking change
2. Council obligatoire (seuil 8/10)
3. Mettre à jour `demo-scope.md` §6 et `architecture-rules.md` §2 en même temps que la PR qui casse
4. Ajouter un test de régression qui verrouille le nouveau contrat

Pas d'exception silencieuse.
