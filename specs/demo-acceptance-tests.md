# STOA Demo — Acceptance Tests

> **Statut**: v1.0 — 2026-04-24. Référence exécutable du contrat démo.
> **Script canonique**: `scripts/demo-smoke-test.sh` (voir `validation-commands.md`).

## Principe

Chaque étape du scénario démo (`demo-scope.md` §2) a un test d'acceptance binaire : **PASS ou FAIL** en mode réel. Les étapes sont idempotentes et réexécutables. Les mocks autorisés sont marqués `[MOCK OK]`, mais un mock ne peut jamais produire le verdict `DEMO READY`.

## Sémantique des verdicts

| Verdict | Exit | Signification |
|---------|------|---------------|
| `REAL_PASS — DEMO READY` | 0 | AT-0..AT-5 passent sans mock critique ; la démo est réellement prouvée |
| `CONTRACT_DRY_RUN` | 0 | `--dry-run-contract` valide la structure script/spec sans stack live ; la démo n'est pas prouvée |
| `MOCK_PASS` | 0 | `MOCK_MODE=all` valide le chemin mocké ; la démo n'est pas prouvée |
| `FAIL — DEMO NOT READY` | 1 ou 2 | Au moins un blocker réel empêche le scénario |

`MOCK_MODE=auto` est traité comme un mode réel strict : il ne convertit jamais un blocker en PASS silencieux.

## Pré-conditions (AT-0)

Avant lancement, ces ressources doivent exister (seed minimal) :

- Base cp-api démarrée (port 8000) avec healthz 200
- Gateway démarrée (port 8081 avec le compose démo, ou `GATEWAY_URL` explicite en mode natif) avec healthz 200
- Un tenant `demo` (UUID déterministe) en DB
- Un backend HTTP mock démarré (port 9090) qui répond `200 {"ok":true}` sur `GET /ping`
- **[MOCK OK]** `GIT_SYNC_ON_WRITE=false` — le sync vers `stoa-catalog` est désactivé pour la démo
- **[MOCK OK]** `STOA_OTEL_ENDPOINT` vide si pas de collecteur OTEL → no-op, acceptable pour AT-5 ; AT-5b sera marqué INFO/WARN
- Auth: Keycloak local OU bypass dev `STOA_DISABLE_AUTH=true` pour cp-api écriture (à proscrire en prod)

Fail pre-condition ⇒ abort early, pas d'exécution des AT-1..AT-5.

## AT-1 — Déclarer une API

**Given** pre-conditions OK
**When** `POST ${API_URL}/v1/tenants/${TENANT_ID}/apis` avec body:
```json
{
  "name": "demo-api",
  "display_name": "demo-api",
  "version": "1.0.0",
  "protocol": "http",
  "backend_url": "http://mock-backend:9090",
  "paths": [{"path": "/ping", "methods": ["GET"]}]
}
```
**Then**:
- HTTP 201
- Réponse contient `id` (UUID) et `name=demo-api`
- `GET /v1/tenants/${TENANT_ID}/apis/${API_ID}` renvoie 200 avec le même payload

**Exit code**: 0 si les 3 assertions passent, 1 sinon.

## AT-2 — Provisionner la route gateway

**Given** AT-1 PASS, `API_ID` connu
**When** `POST ${API_URL}/v1/tenants/${TENANT_ID}/deployments` avec body:
```json
{
  "api_id": "${API_ID}",
  "environment": "dev",
  "gateway_id": "${GATEWAY_ID}"
}
```
**Then**:
- HTTP 201
- Dans un délai ≤ 30s : `GET ${GATEWAY_URL}/health` reste 200 ET la route est atteignable (retry AT-4 peut valider)
- **[MOCK OK]** Le polling route-sync peut être forcé par SIGHUP à la gateway (`kill -HUP $PID`) si on ne veut pas attendre le tick

**Exit code**: 0 si 201 + route active avant timeout, 1 sinon.

## AT-3 — Créer une souscription applicative

**Given** AT-1 PASS
**When**:
1. `POST ${API_URL}/v1/tenants/${TENANT_ID}/applications` avec `{"name": "demo-app", "display_name": "demo-app"}`  → récupérer `APP_ID`
2. `POST ${API_URL}/v1/subscriptions` ou `POST ${API_URL}/v1/tenants/${TENANT_ID}/applications/${APP_ID}/subscribe/${API_ID}` avec `X-Demo-Mode: true`
3. Alternative single-shot : `POST ${API_URL}/v1/tenants/${TENANT_ID}/applications/${APP_ID}/subscribe/${API_ID}`

En mode démo/dev borné (`STOA_DISABLE_AUTH=true` + `X-Demo-Mode: true`),
la création d'application retourne une application déterministe sans client
Keycloak pour éviter que le smoke dépende des credentials admin Keycloak locaux.
Ce comportement est interdit hors mode démo explicite.

**Then**:
- HTTP 201 sur subscription
- Réponse contient `api_key` (cleartext, one-time) en mode `X-Demo-Mode: true`
- `status: active`

**Exit code**: 0 si clé API récupérée et non-vide, 1 sinon.

## AT-4 — Appeler l'API via la gateway

**Given** AT-2 PASS ET AT-3 PASS, `API_KEY` connu
**When**: `GET ${GATEWAY_URL}/apis/${DEMO_API_NAME}/get -H "X-Api-Key: ${API_KEY}"`

Chemin canonique figé: `/apis/{api_name}/{*path}`. Le smoke ne probe plus
plusieurs shapes.

**Then**:
- HTTP 200
- Body contient `"ok": true` (payload du mock backend)
- Headers de réponse incluent `X-Stoa-Request-Id` (header corrélation injecté par la gateway)

**Retry policy**: 5 tentatives espacées de 2s pour absorber le lag de route-sync. Après 10s = FAIL.

**Exit code**: 0 si 200 + body mock attendu, 1 sinon.

## AT-5 — Preuve observable

**Given** AT-4 PASS (au moins 1 appel effectué)
**When**:
1. `GET ${GATEWAY_URL}/metrics | grep -E 'proxy_requests_total|mcp_tool_calls_total'`
2. Récupérer les logs stdout de la gateway (ou `docker logs stoa-gateway`) sur les 60 dernières secondes

**Then**:
- Au moins une métrique Prometheus avec `_total` strictement > 0 (compteur incrémenté par AT-4)
- Au moins une ligne log JSON contenant `api_id=${API_ID}` OU `tenant=demo` OU `request_id=${X_STOA_REQUEST_ID}` issue d'AT-4
- **[MOCK OK]** Trace OTEL = non bloquant (no-op si endpoint vide), mais vérifié par AT-5b quand la stack observabilité est disponible

**Exit code**: 0 si métrique > 0 ET log corrélé trouvé, 1 sinon.

## AT-5b — Visibilité observabilité (nice-to-have)

**Given** AT-4 PASS et AT-5 PASS
**When** une ou plusieurs surfaces sont configurées:
1. `GET ${GRAFANA_URL}/api/health`
2. `GET ${GRAFANA_URL}/api/datasources/uid/prometheus`
3. `GET ${GRAFANA_URL}/api/datasources/uid/opensearch-traces` OU `GET ${GRAFANA_URL}/api/datasources/uid/tempo`
4. `GET ${CONSOLE_URL}/monitoring`
5. `GET ${PORTAL_URL}/usage`

**Then**:
- Grafana est joignable et a au moins la datasource Prometheus
- Si OTEL est actif, Grafana expose `OpenSearch Traces` ou `Tempo`
- Console `/monitoring` est routable côté UI
- Portal `/usage` est routable côté UI, et le dashboard Grafana embarqué est activable via `VITE_GRAFANA_URL`

**Exit code**: non-bloquant. AT-5b ne change pas le verdict `demo-smoke-test.sh` v1 ; il produit seulement une ligne `[INFO]`, `[PASS]` ou `[WARN]`.

## AT-6 — Cleanup (optionnel, non-bloquant)

`DELETE` subscription → application → api (reverse order). Non-bloquant : le script laisse les ressources si échec cleanup, signale en warning.

## Règle d'agrégation

- `demo-smoke-test.sh` affiche `REAL_PASS — DEMO READY` ⟺ AT-0 à AT-5 tous PASS sans mock
- `demo-smoke-test.sh --dry-run-contract` peut exit 0 avec `CONTRACT_DRY_RUN`, jamais `DEMO READY`
- `MOCK_MODE=all demo-smoke-test.sh` peut exit 0 avec `MOCK_PASS`, jamais `DEMO READY`
- AT-6 peut FAIL sans impacter le verdict (warning seulement)
- Chaque AT est logué avec timestamp + durée + détail FAIL

## Évolution

Toute modification du contrat implique:
1. Mettre à jour `demo-scope.md` §2 (source de vérité)
2. Mettre à jour cet AT
3. Mettre à jour `scripts/demo-smoke-test.sh`
4. Mention dans `demo-readiness-report.md` "Historique"

Jamais l'inverse (ne jamais réaligner la spec sur un test adhoc).
