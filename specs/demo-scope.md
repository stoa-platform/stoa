# STOA Demo Scope — Contrat minimal exécutable

> **Statut**: v1.0 — 2026-04-24. Contrat figé pendant le rewrite.
> **Owner**: humain (Christophe). Les agents n'élargissent pas ce scope sans décision écrite.
> **Source de vérité**: ce fichier. Toute autre spec démo doit y renvoyer.
> **Complément**: le parcours commercial client/prospect est cadré dans `client-prospect-demo-scope.md`.

## 1. Pourquoi ce contrat

Le rewrite STOA produit des PR plus qualitatives (GW-1/GW-2 Rust, GO-1/GO-2 Go, UI-2 React, CP-2 Python), mais chaque module est re-certifié isolément. Il manque **un chemin vertical exécutable** qui prouve que l'ensemble livre encore la proposition de valeur STOA : *"déclarer une API et l'exposer à un consommateur via la gateway, avec preuve observable"*.

Ce scope fige ce chemin. Tant qu'il n'est pas vert bout-en-bout, **aucune autre feature n'est merge-acceptable**.

## 2. Scénario démo cible (5 étapes, non négociables)

| # | Étape | Composant(s) | Commande/API | Preuve |
|---|-------|--------------|--------------|--------|
| 1 | Déclarer une API | cp-api + DB | `POST /v1/tenants/{t}/apis`, dérivé du contrat `specs/uac/demo-httpbin.uac.json` quand `DEMO_UAC_CONTRACT` est fourni | API visible dans `GET /v1/tenants/{t}/apis` |
| 2 | Provisionner la route gateway | cp-api + stoa-gateway | `POST /v1/tenants/{t}/deployments` → gateway polling `GET /v1/internal/gateways/routes` OU `stoa-connect` SSE `GET /v1/internal/gateways/{id}/events` | Route active dans la table gateway (log `Route table reloaded` + réponse non-404 au step 4) |
| 3 | Créer une souscription applicative | cp-api | `POST /v1/tenants/{t}/applications` + `POST /v1/subscriptions` (ou `POST /applications/{id}/subscribe/{api_id}`) | Subscription `active`, clé API retournée (préfixe visible) |
| 4 | Appeler l'API via la gateway | stoa-gateway | `GET {GATEWAY_URL}/apis/demo-httpbin/get` avec header `X-Api-Key: ${KEY}` en mode UAC-driven | HTTP 2xx, payload backend |
| 5 | Preuve observable | stoa-gateway + cp-api | `GET ${GATEWAY_METRICS_URL:-${GATEWAY_URL}/metrics}` + logs JSON stdout | Compteur Prometheus incrémenté (`proxy_requests_total`) + ligne log corrélée (request_id, tenant, route) |
| 5b | Visibilité observabilité (nice-to-have) | Grafana + Console + Portal | Grafana datasource/dashboard, Console `/monitoring`, Portal `/usage` ou dashboard embarqué | La même activité démo est visible dans au moins une surface UI si la stack observabilité est démarrée |

## 3. Surface in-scope (et rien d'autre)

**Binaires**:
- `control-plane-api` (FastAPI) — endpoints listés §2
- `stoa-gateway` (Rust) — routes `/apis/{api_name}/{*path}`, `/health`, `/metrics`
- `stoactl` (Go) — sous-commandes `apply`, `get`, `subscription`, `auth login` seulement

**Backend cible pour l'appel démo**: un mock HTTP (ex. `mock-backends/` ou `httpbin` en conteneur) qui répond 200 JSON. Pas de backend externe réseau.

**Contrat UAC cible**: `specs/uac/demo-httpbin.uac.json`. Le smoke n'est pas
encore une preuve UAC globale: il charge un seul contrat publié, sélectionne le
premier endpoint `GET /get`, et dérive un seul chemin gateway
`/apis/demo-httpbin/get`.

**Auth**: API key (préfixe `stoa_…`) OU JWT Keycloak — un seul mode suffit pour la démo. Choisir API key (plus simple à reproduire).

**Observabilité minimale acceptée**: Prometheus `/metrics` + logs JSON stdout.

**Visibilité nice-to-have**: si Grafana, Console et Portal sont démarrés, la démo doit exposer un chemin humain vérifiable:
- Grafana: dashboard ou Explore utilisant `Prometheus`, `Loki`, `OpenSearch Traces` ou `Tempo`
- Console: page `/monitoring` alimentée par `GET /v1/monitoring/transactions`
- Portal: page `/usage` et/ou dashboard Grafana embarqué si `VITE_GRAFANA_URL` est configuré

OTEL reste non bloquant pour le PASS démo v1, mais il doit être visible dès que `STOA_OTEL_ENDPOINT` et la stack Data Prepper/OpenSearch/Tempo sont actifs.

## 4. Out-of-scope (règles dures — refuser toute PR qui élargit)

Explicitement exclus du contrat provider/runtime. Ces sujets peuvent être couverts
par `client-prospect-demo-scope.md`, mais ne doivent pas devenir requis pour
`demo-smoke-test.sh` `REAL_PASS`:

- Multi-tenant complet (RBAC cross-tenant, invitations, ACL fines)
- RBAC fin (rôles custom, scopes dynamiques) — seul `tenant-admin` suffit
- Portal public (developer portal / catalogue self-service) — voir `client-prospect-demo-scope.md`
- Federation / multi-gateway
- GitOps E2E (sync `stoa-catalog` ↔ DB) — on coupe via `GIT_SYNC_ON_WRITE=false`
- Policies OPA, rate-limiting configurable, MCP, webhooks, Kafka events
- OpenSearch, error snapshots, call-flow pipeline
- UI (Console, Portal) — hors smoke provider, voir `client-prospect-demo-scope.md`
- Benchmarks performance, canary, shadow mode, mTLS
- Multi-env (prod/staging/dev) — un seul env local suffit
- Toute nouvelle feature non cochée au §2

Si une PR rewrite introduit un changement hors de §2 ou §3, la règle par défaut est **NO-GO** sauf décision humaine explicite.

## 5. Cible de validation

Un seul critère binaire, exécuté par `scripts/demo-smoke-test.sh`:

```
$ ./scripts/demo-smoke-test.sh
[PASS] 1/5 API declared
[PASS] 2/5 Route provisioned
[PASS] 3/5 Subscription active
[PASS] 4/5 Gateway call 200
[PASS] 5/5 Observable proof (metric + log)
Verdict: REAL_PASS — DEMO READY
```

Tant que ce script n'affiche pas `REAL_PASS — DEMO READY`, la démo réelle
n'existe pas. `CONTRACT_DRY_RUN` et `MOCK_PASS` peuvent retourner exit 0, mais
signifient seulement que le contrat ou le chemin mocké est cohérent.

Commande de référence UAC-driven:

```
$ DEMO_UAC_CONTRACT=specs/uac/demo-httpbin.uac.json ./scripts/demo-smoke-test.sh
[PASS] UAC contract loaded demo-httpbin v1.0.0
[PASS] UAC endpoint GET /get selected operation_id=demo_httpbin_get
[PASS] UAC Gateway call derived from UAC /apis/demo-httpbin/get
...
```

## 6. Dépendances figées pendant le rewrite

Voir `rewrite-guardrails.md` §Contrats figés:
- Compatibilité DB consommée par le smoke (`apis`, `applications`, `subscriptions`, `deployments`, `api_keys`)
- Endpoints listés §2 (URL + status codes + shape minimal de réponse)
- Route `/apis/{api_name}/{*path}` gateway + comportement auth-header
- Contrat UAC démo `specs/uac/demo-httpbin.uac.json` pour `demo-httpbin` `GET /get`
- Format métrique Prometheus (nom `_total`, labels `tenant`, `api`, `method`, `status`)

Tout autre aspect peut bouger.

## 7. Révisions

| Date | Auteur | Changement |
|------|--------|------------|
| 2026-04-24 | Claude (via `/demo-scope`) | Création initiale |
| 2026-04-24 | Codex | Ajout du premier lien UAC-driven: `demo-httpbin` `GET /get` → `/apis/demo-httpbin/get` |
