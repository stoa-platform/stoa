# STOA Demo — Validation Commands

> **Statut**: v1.0 — 2026-04-24. Commandes exécutables alignées sur `Makefile` racine et `scripts/`.
> Toute divergence entre ce fichier et le Makefile = bug à signaler, pas à ignorer.

## 1. Vérification du chemin démo (la commande qui compte)

```bash
./scripts/demo-smoke-test.sh
```

Affiche `REAL_PASS — DEMO READY` uniquement si AT-0..AT-5 de
`demo-acceptance-tests.md` passent sans mock critique.

Modes non réels explicites:

```bash
# Valide le contrat/script sans stack live. Ne prouve pas la démo.
./scripts/demo-smoke-test.sh --dry-run-contract

# Valide le chemin mocké. Ne prouve pas la démo.
MOCK_MODE=all ./scripts/demo-smoke-test.sh
```

`MOCK_MODE=auto` est strict: il ne transforme pas un blocker réel en PASS.

Variables d'environnement (defaults documentés dans le script) :

| Var | Default | Description |
|-----|---------|-------------|
| `API_URL` | `http://localhost:8000` | Base URL cp-api |
| `GATEWAY_URL` | `http://localhost:8080` | Base URL stoa-gateway |
| `MOCK_BACKEND_URL` | `http://localhost:9090` | Mock HTTP backend vu par le poste dev pour AT-0 |
| `MOCK_BACKEND_UPSTREAM_URL` | `http://mock-backend:9090` | Mock HTTP backend vu par la gateway en compose |
| `DEMO_GATEWAY_PATH` | `/apis/${DEMO_API_NAME}/get` | Chemin gateway canonique AT-4 |
| `TENANT_ID` | `demo` (slug, résolu en UUID par cp-api) | Tenant démo |
| `DEMO_ADMIN_TOKEN` | vide | JWT admin pour écrire côté cp-api. Si vide, le script passe en `STOA_DISABLE_AUTH=true` mode (dev only) |
| `ROUTE_SYNC_GRACE_SECS` | `30` | Délai d'attente pour route visible en gateway après AT-2 |
| `OBS_VISIBILITY_CHECK` | `auto` | Lance AT-5b nice-to-have (`off` pour désactiver) |
| `GRAFANA_URL` | `http://localhost:3001` | Grafana local pour vérifier health + datasources |
| `GRAFANA_USER` / `GRAFANA_PASSWORD` | `admin` / `admin` | Basic auth Grafana local |
| `CONSOLE_URL` | `http://localhost:3000` | Console UI locale (`/monitoring`) |
| `PORTAL_URL` | `http://localhost:3002` | Developer Portal local (`/usage`) |

## 2. Boot local démo (pré-requis avant AT-0)

### Option A — docker-compose (recommandé)
```bash
# Stack minimale: postgres, keycloak, cp-api, gateway, mock-backend
docker compose -f deploy/docker-compose/docker-compose.yml up -d \
    postgres keycloak control-plane-api stoa-gateway mock-backend

# Attendre healthy
docker compose -f deploy/docker-compose/docker-compose.yml ps

# Seed minimal (tenant demo + gateway enregistrée)
make seed-dev  # OU: SEED_PROFILE=demo python3 -m control-plane-api/scripts.seeder
```

### Option B — native (dev rapide)
```bash
# Terminal 1
make run-api             # cp-api sur :8000

# Terminal 2
make run-gateway         # stoa-gateway sur :8080

# Terminal 3 (backend mock only, if compose is not used)
docker compose -f deploy/docker-compose/docker-compose.yml up -d mock-backend
export MOCK_BACKEND_UPSTREAM_URL=http://localhost:9090
```

## 3. Lint (pré-conditions PR démo-ready)

```bash
# Tous les linters de la démo (cp-api + gateway + CLI)
make lint-api            # ruff + black (cp-api)
make lint-gateway        # cargo fmt --check + clippy -D warnings
cd stoa-go && make lint  # ou golangci-lint run ./...
```

Règle : **aucun warning clippy** côté gateway (`-D warnings`). Pas de `#[allow(...)]` ajouté sans justification.

## 4. Tests (scope démo uniquement)

```bash
# Gateway unit + tests ciblés démo
cd stoa-gateway && cargo test --lib                   # default features, no kafka/k8s
cd stoa-gateway && cargo test --test integration_*    # intégration légère

# cp-api tests qui touchent apis/deployments/subscriptions/applications
cd control-plane-api && pytest tests/routers/test_apis.py tests/routers/test_subscriptions.py \
    tests/routers/test_deployments.py tests/routers/test_applications.py \
    --cov=src --cov-fail-under=70 -q

# stoa-go CLI tests apply/get/subscription
cd stoa-go && go test ./internal/cli/cmd/apply/... ./internal/cli/cmd/get/... \
    ./internal/cli/cmd/subscription/... ./pkg/client/...
```

## 5. Build (démo peut-elle se déployer ?)

```bash
# Gateway image community (no features)
cd stoa-gateway && cargo build --release

# cp-api image
cd control-plane-api && docker build -t stoa/cp-api:demo .

# stoactl binary
cd stoa-go && make build-stoactl
# produit bin/stoactl
```

## 6. Ordre de validation avant d'ouvrir une PR "démo-related"

1. `./scripts/demo-smoke-test.sh` sur main → baseline (doit être soit `REAL_PASS`, soit `FAIL` figé documenté)
2. Appliquer la PR localement
3. `make lint-api lint-gateway` (plus `go lint` si touche stoactl)
4. Tests du §4 pertinents (au minimum la surface touchée)
5. `./scripts/demo-smoke-test.sh` après PR → verdict
6. Delta documenté dans description PR : `REAL_PASS` avant + après, ou `FAIL` → `REAL_PASS` si bug-fix

Une PR qui fait dégrader le verdict smoke (`REAL_PASS` → `FAIL`, `MOCK_PASS`, ou `CONTRACT_DRY_RUN`) est **NO-GO automatique**.

## 7. Commandes de debug ciblées démo

```bash
# État DB minimal démo
psql $DATABASE_URL -c "SELECT count(*) FROM apis WHERE tenant_id='${TENANT_ID}';"
psql $DATABASE_URL -c "SELECT status, count(*) FROM subscriptions GROUP BY status;"

# Route table live gateway
curl -s http://localhost:8080/admin/routes | jq .      # si admin API exposée
curl -s http://localhost:8000/v1/internal/gateways/routes?gateway_name=demo | jq .
curl -sI http://localhost:8080/apis/demo-api-smoke/get

# Logs gateway corrélés à un request_id
docker logs stoa-gateway 2>&1 | grep "request_id=${REQUEST_ID}"

# Grafana datasources visibles pour la démo
curl -s -u "${GRAFANA_USER}:${GRAFANA_PASSWORD}" http://localhost:3001/api/datasources/uid/prometheus | jq .name
curl -s -u "${GRAFANA_USER}:${GRAFANA_PASSWORD}" http://localhost:3001/api/datasources/uid/opensearch-traces | jq .name
curl -s -u "${GRAFANA_USER}:${GRAFANA_PASSWORD}" http://localhost:3001/api/datasources/uid/tempo | jq .name

# Console / Portal surfaces humaines
curl -sI http://localhost:3000/monitoring
curl -sI http://localhost:3002/usage

# Forcer reload route côté gateway sans attendre tick
kill -HUP $(pgrep stoa-gateway)
```

## 8. Matrix de couverture commandes → étapes démo

| Commande | AT couvert |
|----------|-----------|
| `make seed-dev` | AT-0 pré-conditions |
| `docker compose up …` | AT-0 pré-conditions |
| `./scripts/demo-smoke-test.sh` | AT-0 → AT-5 réel (`REAL_PASS` seulement si aucun mock) |
| `./scripts/demo-smoke-test.sh --dry-run-contract` | Contrat script/spec (`CONTRACT_DRY_RUN`, pas démo prête) |
| `MOCK_MODE=all ./scripts/demo-smoke-test.sh` | Chemin mocké (`MOCK_PASS`, pas démo prête) |
| `OBS_VISIBILITY_CHECK=auto ./scripts/demo-smoke-test.sh` | AT-5b nice-to-have Grafana/Console/Portal |
| `make lint-api lint-gateway` | gate PR, pas runtime démo |
| `make test-api test-gateway` | confiance PR, pas runtime démo |
| `cargo build --release` | emballage image démo |
| `make build-stoactl` | emballage CLI démo |

## 9. Intégration CI observationnelle

Le workflow `.github/workflows/demo-smoke.yml` est volontairement
**observationnel** tant que le smoke réel n'a pas produit au moins un
`REAL_PASS — DEMO READY` local.

À chaque PR, il exécute :

```bash
bash -n scripts/demo-smoke-test.sh
./scripts/demo-smoke-test.sh --no-observability-ui
```

Il publie dans `$GITHUB_STEP_SUMMARY` :
- le code de sortie de `bash -n`
- le code de sortie du smoke réel
- la ligne `Verdict: ...`
- le dernier blocker `[FAIL] ...`
- les 80 dernières lignes du log

Il upload aussi les logs en artifact `demo-smoke-*`.

Tant que `DEMO_SMOKE_BLOCKING` vaut `false` (défaut), un verdict
`FAIL — DEMO NOT READY` ne fait **pas** échouer le job GitHub. Le résultat
sert à observer le prochain blocker réel sans bloquer la cadence des PR IA.

Passage en gate bloquant, uniquement après premier `REAL_PASS` local :

```text
GitHub variable DEMO_SMOKE_BLOCKING=true
```

ou lancement manuel du workflow avec `blocking=true`.

## 10. Démo client/prospect

Le parcours client/prospect est spécifié séparément dans
`specs/client-prospect-demo-scope.md`.

Validation cible future:

```bash
# API-level, à créer
./scripts/client-prospect-demo-smoke.sh

# UI-level, à créer
cd e2e && npx playwright test client-prospect-demo.spec.ts
```

Surfaces à vérifier manuellement tant que ces scripts n'existent pas:

```bash
curl -s http://localhost:8000/v1/portal/apis | jq .
curl -sI http://localhost:3002/signup
curl -sI http://localhost:3002/onboarding
curl -sI http://localhost:3002/discover
curl -sI http://localhost:3002/usage
curl -sI http://localhost:3000/admin/prospects
curl -sI http://localhost:3000/subscriptions
```
