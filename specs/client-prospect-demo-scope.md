# STOA Demo — Client / Prospect Scope

> **Statut**: v1.0 — 2026-04-24. Complément au contrat technique `demo-scope.md`.
> **But**: couvrir la démo commerciale côté prospect/client, sans remplacer le smoke provider CLI.

## 1. Pourquoi ce contrat

`demo-scope.md` prouve que la verticale technique fonctionne: API déclarée,
route gateway provisionnée, subscription créée, appel gateway OK, preuve observable.

La démo client/prospect doit prouver autre chose: un prospect peut découvrir STOA,
s'onboarder, trouver une API, obtenir un accès, faire un premier appel, puis voir
son usage pendant que l'équipe STOA voit la conversion dans la Console.

Ces deux démos sont complémentaires:
- `demo-smoke-test.sh`: contrat provider/runtime, binaire, bloquant.
- Ce fichier: contrat client/prospect, humain-visible, à automatiser ensuite en Playwright.

## 2. Scénario cible client/prospect

| # | Étape | Surface | Commande/API | Preuve |
|---|-------|---------|--------------|--------|
| C0 | Seed démo client | cp-api + DB | seed `prospect-demo`, tenant, user, API publiée | Données idempotentes prêtes |
| C1 | Signup prospect | Portal public | `POST /v1/self-service/tenants` puis status | `202` puis tenant `ready` |
| C2 | Voir la conversion prospect | Console | `/admin/prospects` + `/v1/admin/prospects/metrics` | Prospect visible, funnel mis à jour |
| C3 | Parcours onboarding | Portal | `/onboarding` | 4 étapes visibles: use case, app, subscribe, first call |
| C4 | Découvrir l'API | Portal | `/discover`, `/apis/{id}` + `GET /v1/portal/apis` | API démo publiée visible |
| C5 | Créer une application client | Portal | `/workspace?tab=apps` ou onboarding | Application créée avec credentials affichables |
| C6 | Souscrire à l'API | Portal + cp-api | `POST /v1/subscriptions` | Subscription créée (`pending` ou `active`) |
| C7 | Approbation si nécessaire | Console | `/subscriptions` + `POST /v1/subscriptions/{id}/approve` | Subscription active |
| C8 | Premier appel client | Portal sandbox ou curl | `/apis/{id}/test` ou gateway URL | HTTP 2xx, payload backend |
| C9 | Usage client visible | Portal | `/usage`, `/executions` | Appel visible dans calls/usage |
| C10 | Monitoring opérateur visible | Console/Grafana | `/monitoring`, Grafana traces/metrics | Transaction corrélée visible |

## 3. Surfaces et contrats à préserver

### 3.1 Portal public / client

| Surface | Route UI | API backend |
|---------|----------|-------------|
| Signup | `/signup` | `POST /v1/self-service/tenants`, `GET /v1/self-service/tenants/{tenant_id}/status` |
| Onboarding | `/onboarding` | apps + catalog + subscriptions |
| Catalogue | `/discover`, `/apis/{id}` | `GET /v1/portal/apis`, `GET /v1/portal/apis/{id}` |
| Sandbox | `/apis/{id}/test` | gateway URL issue de l'API ou du deployment |
| Workspace apps | `/workspace?tab=apps` | `GET/POST /v1/applications` |
| Subscriptions | `/workspace?tab=subscriptions` | `GET /v1/subscriptions/my`, `POST /v1/subscriptions` |
| Usage | `/usage`, `/executions` | `GET /v1/usage/me*`, `GET /v1/usage/me/executions*` |

### 3.2 Console opérateur / prospect

| Surface | Route UI | API backend |
|---------|----------|-------------|
| Prospects | `/admin/prospects` | `GET /v1/admin/prospects`, `GET /v1/admin/prospects/metrics` |
| Subscription approvals | `/subscriptions` | `GET /v1/subscriptions/tenant/{tenant_id}/pending`, `POST /v1/subscriptions/{id}/approve` |
| Monitoring | `/monitoring` | `GET /v1/monitoring/transactions` |
| Grafana embed | `/observability/grafana` | Grafana datasources `prometheus`, `opensearch-traces`, `tempo` |

## 4. Deltas versus `demo-scope.md`

| Delta | Impact | Décision |
|-------|--------|----------|
| `demo-scope.md` exclut le Portal public et la UI | Incompatible avec une démo prospect | Ce fichier devient le contrat dédié client/prospect |
| Smoke provider exige API key cleartext utilisable | Le Portal REST subscription annonce OAuth2/no API key | Le scénario client doit choisir explicitement API key demo ou OAuth2, pas les deux |
| Catalogue Portal lit `/v1/portal/apis` | Le smoke crée via `/v1/tenants/{tid}/apis` | Le seed client doit publier/promouvoir l'API démo au Portal |
| Subscription peut être `pending` | Le smoke attend `active` | C7 couvre l'approbation Console si nécessaire |
| Usage/executions ne sont pas vérifiés par AT-5 | La démo client doit montrer la valeur après appel | C9 devient preuve obligatoire du parcours client |
| Prospects dashboard existe mais n'est pas relié au signup | Conversion non prouvée | C0/C1/C2 doivent créer un lien `invite/prospect → tenant/user` |

## 5. Acceptance tests client/prospect

### CPD-0 — Seed client idempotent

Préparer:
- tenant `demo-client`
- user client `client-demo@gostoa.local`
- prospect/invite `prospect-demo@gostoa.local`
- API publiée `demo-api-client` visible dans `/v1/portal/apis`
- gateway route active vers mock backend
- credentials admin Console + client Portal documentés dans `.env.demo`

PASS si le seed est relançable sans doublons et retourne les IDs utiles.

### CPD-1 — Signup self-service

`POST /v1/self-service/tenants` avec un payload prospect de test retourne `202`
et un `poll_url`. Le polling retourne `ready` dans un délai borné.

Pour une démo locale rapide, ce test peut être SKIP si le tenant est pré-seedé,
mais le skip doit être explicite dans le rapport.

### CPD-2 — Prospect visible dans la Console

`GET /v1/admin/prospects` contient le prospect démo et
`GET /v1/admin/prospects/metrics` expose un funnel non vide.

PASS humain: `/admin/prospects` montre le prospect, son statut et une timeline.

### CPD-3 — Onboarding Portal

Le client accède à `/onboarding` et voit les 4 étapes:
1. choix du use case
2. création application
3. sélection API
4. premier appel / configuration

PASS si le parcours n'aboutit pas à une page vide, une erreur auth, ou une API list vide.

### CPD-4 — Catalogue API visible

`GET /v1/portal/apis?search=demo-api-client` retourne au moins une API publiée.
`/apis/{id}` affiche nom, version, description, auth type et environnement déployé.

### CPD-5 — Application client créée

Créer une application depuis le Portal ou l'API client. PASS si l'app est listée
dans `/workspace?tab=apps` et si les credentials requis pour l'étape C8 sont
disponibles selon le mode choisi.

### CPD-6 — Subscription client active

Créer une subscription via `POST /v1/subscriptions`.

PASS si:
- `active`: continuer directement vers CPD-8
- `pending`: CPD-7 doit l'approuver

FAIL si aucune clé, aucun client OAuth, et aucune URL d'appel ne permettent de
réaliser le premier appel.

### CPD-7 — Approval Console si nécessaire

Si CPD-6 retourne `pending`, la Console `/subscriptions` doit permettre
l'approbation. L'API `POST /v1/subscriptions/{id}/approve` doit retourner
une subscription active.

### CPD-8 — Premier appel client

Le client appelle l'API depuis `/apis/{id}/test` ou via curl gateway documenté.

PASS si:
- HTTP 2xx
- payload du mock backend reçu
- `X-Stoa-Request-Id` présent

### CPD-9 — Usage visible côté client

Après CPD-8, `/usage` ou `/executions` montre l'appel du client dans un délai
raisonnable.

PASS si l'appel est attribuable à l'application ou subscription créée.

### CPD-10 — Monitoring visible côté opérateur

Après CPD-8, `/monitoring` et/ou Grafana montrent la transaction avec
`request_id`, `tenant`, `api` ou `route`.

PASS si la même activité peut être expliquée à un prospect: appel → métrique/log/trace.

## 6. Blockers spécifiques client/prospect

| # | Blocker | Sévérité | Étapes impactées |
|---|---------|----------|------------------|
| C-B1 | Pas de seed `demo-client` + prospect + API publiée | P0 | CPD-0..CPD-4 |
| C-B2 | Lien signup → prospect conversion non garanti | P1 | CPD-1, CPD-2 |
| C-B3 | Mode d'auth client non tranché (API key vs OAuth2) | P0 | CPD-6, CPD-8 |
| C-B4 | Subscription Portal peut rester pending sans chemin d'approbation démo | P1 | CPD-6, CPD-7 |
| C-B5 | Portal sandbox peut appeler API detail au lieu de gateway réelle | P0 | CPD-8 |
| C-B6 | Usage/executions dépend de Prometheus/Loki et peut rester vide localement | P1 | CPD-9 |
| C-B7 | Prospects dashboard admin existe mais pas inclus dans smoke/Playwright | P2 | CPD-2 |

## 7. Validation recommandée

Court terme:
- garder `demo-smoke-test.sh` pour AT-0..AT-5 provider
- créer ensuite `scripts/client-prospect-demo-smoke.sh` pour CPD-0..CPD-10 API-level
- créer un test Playwright `e2e/client-prospect-demo.spec.ts` pour les surfaces UI

Critère GO démo client:
- CPD-0, CPD-3, CPD-4, CPD-6, CPD-8 passent
- CPD-2, CPD-9, CPD-10 visibles humainement ou marqués WARN explicite
- aucun blocker C-B1/C-B3/C-B5 ouvert

## 8. Révisions

| Date | Auteur | Changement |
|------|--------|------------|
| 2026-04-24 | Codex | Création initiale du contrat client/prospect |
