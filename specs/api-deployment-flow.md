# STOA Demo — API Deployment Flow Contract

> **Statut**: v0.1 — 2026-04-25. Contrat transverse pour garder le flux Console
> `/api-deployments` fonctionnel.
> **Relation au scope démo**: complément à `demo-scope.md`, non bloquant pour
> `scripts/demo-smoke-test.sh` tant qu'une décision écrite ne l'ajoute pas au
> smoke minimal provider/runtime.
> **ADRs sources**: ADR-040 (Born GitOps multi-environment), ADR-059
> (Promotion Deploy Chain — closed loop), ADR-059 stoa-docs (single deployment
> path via SSE), ADR-035 (Gateway Adapter Pattern), ADR-036 (Gateway
> Auto-Registration).

## 1. Pourquoi ce contrat

La page Console `/api-deployments` traverse plusieurs concepts backend:
`Deployment`, `Promotion`, `GatewayDeployment` et `ApiGatewayAssignment`.
Ces objets ne représentent pas le même niveau de vérité:

- `Deployment` et `Promotion` décrivent une intention ou un lifecycle métier.
- `GatewayDeployment` décrit l'état réel attendu/observé sur une gateway.
- `ApiGatewayAssignment` décrit les cibles par défaut d'une API dans un environnement.

Le risque principal est qu'une PR corrige une surface locale tout en cassant le
flux complet: promotion acceptée mais aucun déploiement gateway créé, statut
Console interprété comme "synced" sans ack gateway, sélection d'environnement
incohérente, ou rollback qui laisse une route active.

Ce fichier fige le contrat transverse. Il sert de référence pour les PR qui
touchent promotions, assignments, gateway deployments, sync engine, gateways ou
la page Console `/api-deployments`.

## 1.1 Alignement ADR

Ce contrat est un contrat de flux Console/runtime. Il ne remplace pas les ADRs:

- **ADR-040 — Born GitOps multi-environment**: Git/UAC reste la source de
  gouvernance pour les changements de configuration, particulièrement en
  production. Le flux de cette spec ne doit pas réintroduire un "UI click to
  prod" sans approbation. En dev/staging, l'UI peut créer une intention de
  déploiement; en production, elle doit suivre le mode read/promote défini par
  l'environnement.
- **ADR-059 — Promotion Deploy Chain**: une promotion n'est complète qu'après
  boucle fermée `promote -> deploy -> ack -> promoted|failed`. Le lien direct
  `GatewayDeployment.promotion_id` est contractuel pour lever l'ambiguïté
  `api_id + target_environment`.
- **ADR-059 — Single Path via SSE**: la cible d'architecture est
  `Console -> CP API -> STOA Link SSE -> gateway -> callback -> CP API`. Le
  SyncEngine et l'inline sync sont des chemins legacy/de transition, pas des
  dépendances que ce contrat doit préserver.
- **ADR-035 / ADR-036**: les gateways restent abstraites par adapter/capability
  et auto-enregistrées avec identité d'environnement. Le filtre env/gateway de
  la Console doit respecter cette identité.

ADR-040 et ADR-059 ne parlent pas exactement du même niveau:

- ADR-040 définit la vérité configurationnelle et la gouvernance
  multi-environnement: Git/UAC/stoa.yaml est la source de vérité, surtout pour
  staging/prod.
- ADR-059 définit le chemin d'exécution runtime simplifié: CP matérialise une
  intention en `GatewayDeployment`, le Link/gateway applique, puis ack. Dans ce
  chemin, Git peut être un side-effect asynchrone en dev/demo, mais il ne devient
  pas une preuve runtime.

Ce contrat tranche donc ainsi: Git/UAC est la vérité configurationnelle,
`GatewayDeployment` est la vérité d'exécution, et la Console affiche l'écart
entre desired state et observed state.

## 1.2 Source de vérité

Le contrat ne définit pas un déploiement "vers une gateway". Il définit la
réconciliation d'un desired state Git/UAC vers une ou plusieurs cibles gateway
déclarées pour un environnement. Les gateways n'initient pas la vérité de
configuration; elles appliquent et acquittent une génération de desired state.

| Objet | Rôle | Source de vérité |
|-------|------|------------------|
| Git/UAC/stoa.yaml | configuration déclarative, overlays par environnement, gouvernance | vérité configurationnelle |
| CP matérialisé | cache DB/API du desired state résolu | projection réconciliable, pas source primaire prod |
| GatewayDeployment | cible d'exécution par gateway et génération de desired state | vérité runtime/exécution |
| Gateway observed state | état réellement observé/reporté par Link/gateway | preuve d'application ou drift |
| Gateway health | connectivité/heartbeat/reboot | vérité connectivité seulement |
| Promotion | intention/lifecycle env -> env | jamais preuve runtime seule |

Chaîne conceptuelle:

```text
Git/UAC/stoa.yaml desired state
→ CP materialized desired state
→ environment overlay resolved
→ gateway assignments/capabilities resolved
→ N GatewayDeployment target states
→ Link/gateway applies locally
→ ack / failed / drift observed state
→ Console displays desired vs observed
```

## 2. Scénario cible

| # | Étape | Surface | API/Commande | Preuve |
|---|-------|---------|--------------|--------|
| ADF-0 | Déclarer le desired state | Git/UAC + cp-api | UAC/stoa.yaml + overlays env ou raccourci dev/demo | desired state idempotent prêt |
| ADF-1 | Réconcilier en dev | Console/API | `POST /v1/tenants/{t}/apis/{api}/deploy` comme raccourci dev/demo avec `gateway_ids` | `GatewayDeployment` créé `pending/syncing` pour chaque cible |
| ADF-2 | Ack gateway | STOA Link/gateway + cp-api | callback Link ou `route-sync-ack` legacy | `sync_status=synced`, `last_sync_success` non nul |
| ADF-3 | Voir l'état Console | Console | `/api-deployments` | Ligne API/gateway/env visible, statut runtime affiché |
| ADF-4 | Préparer auto-deploy env cible | cp-api | assignment `auto_deploy=true` pour target env | assignment listé avec gateway du même env |
| ADF-5 | Promouvoir dev→staging | Console/API | create + approve promotion | promotion `promoting`, deployments gateway créés |
| ADF-6 | Compléter promotion après ack | cp-api | gateway deployments liés tous `synced` | promotion `promoted` seulement après sync réel |
| ADF-7 | Gérer absence de cible | Console/API | promotion sans assignment target | erreur/warning explicite, jamais succès silencieux |
| ADF-8 | Changer d'environnement | Console | global env selector ou filtre local | gateway invalide désélectionnée, aucune cible cross-env |
| ADF-9 | Rollback/undeploy | Console/API | reverse promotion, Git revert, ou undeploy | intention de suppression puis route absente gateway |

`Deploy` signifie: réconcilier un desired state vers les gateways cibles. Ce
n'est pas un push CP -> gateway. Pour les chemins dev/demo, `POST /deploy` est
un raccourci qui crée ou matérialise une intention de desired state; il ne doit
pas devenir le chemin canonique prod.

## 2.1 Modes gateway supportés

Le contrat de déploiement est commun, mais le transport et la preuve d'ack
dépendent du mode de gateway. La Console ne doit pas assimiler `online` à
`synced`: `online` prouve seulement le heartbeat/connectivité agent, pas
l'application de la route.

| Mode gateway | Exemple | Identité CP | Transport de déploiement | Preuve `synced` | Contraintes runtime |
|--------------|---------|-------------|---------------------------|-----------------|---------------------|
| Legacy VM via STOA Connect | webMethods/Kong/Gravitee en VM, `connect-webmethods-dev` | gateway `self_register`, nom logique agent + gateway canonique DB | pull agent `GET /v1/internal/gateways/routes?gateway_name={agent_name}`; SSE peut accélérer mais le polling reste obligatoire | `POST /v1/internal/gateways/{gateway_id}/route-sync-ack` avec `deployment_id` appliqué | le `backend_url` doit être joignable depuis la VM; une URL Kubernetes `*.svc.cluster.local` est invalide sauf tunnel/réseau partagé explicite |
| STOA Gateway edge/gateway | `stoa-gateway` central ou edge MCP | gateway auto-enregistrée ou seedée dans l'env cible | route registry CP consommée par la gateway, par polling ou SSE selon l'implémentation active | ack gateway/agent ou état route-table observé, corrélé au `deployment_id` | chemin public canonique `/apis/{api_name}/{*path}`; le backend doit être joignable depuis la gateway |
| STOA Gateway sidecar | `stoa-link-wm-dev`, sidecar proche d'une gateway legacy | gateway `self_register` typée sidecar dans l'env cible | pull/ack agent-managed comme STOA Connect, ou adapter direct seulement si le sidecar est réellement joignable depuis CP | route ack côté sidecar avec `deployment_id`, puis route active côté gateway locale | la résolution DNS/backend est locale au sidecar; une erreur DNS côté CP ne doit pas être utilisée pour juger un sidecar agent-managed |

Invariants spécifiques:

- Chaque gateway expose une capacité de déploiement dérivée, par exemple
  `agent_pull_ack`, `stoa_gateway_registry` ou `direct_adapter`. La Console doit
  afficher cette capacité et adapter ses actions de test.
- Une gateway `self_register` est agent-managed par défaut: CP ne doit pas
  tenter un push direct si l'agent est le chemin déclaré.
- Le mapping nom agent -> gateway DB est contractuel. Le lookup doit accepter le
  nom logique annoncé par l'agent (`STOA_INSTANCE_NAME`) et le réconcilier avec
  la gateway canonique auto-enregistrée, sans créer de cible cross-env.
- `GatewayInstance.environment`, `ApiGatewayAssignment.environment` et
  `GatewayDeployment.environment` doivent être identiques pour une même cible.
  Les alias `prod`/`production` doivent être normalisés avant toute sélection ou
  promotion.

## 3. Invariants

### 3.1 Source de vérité des statuts

`GatewayDeployment.sync_status` est la source de vérité runtime pour la Console.
`Promotion.status=promoted` ne signifie jamais "gateway synced" sans
`GatewayDeployment` lié et acquitté.

Le statut de déploiement et le statut de santé/connectivité gateway sont deux
axes distincts. Une route déjà acquittée `synced` ne doit pas repasser `failed`
uniquement parce qu'un healthcheck gateway échoue, qu'une gateway webMethods de
démo redémarre, ou qu'un agent rate un heartbeat. Dans ce cas, la route reste
`synced` et la gateway devient `offline`, `restarting`, `stale`, ou
`unreachable` sur l'axe connectivité.

Un `GatewayDeployment` déjà `synced` ne peut changer vers `error`, `drifted` ou
`deleting` que dans ces cas:

- une nouvelle génération de desired state est demandée et son application
  échoue;
- un undeploy/rollback explicite crée une intention de suppression;
- un drift detector confirme, après retour online/retry, que la route attendue
  n'existe plus ou ne correspond plus au desired state;
- un opérateur force un resync et l'ack de cette nouvelle tentative échoue.

Statuts utilisateur canoniques à exposer sur `/api-deployments`:

| Statut UI | Condition minimale |
|-----------|--------------------|
| `not_deployed` | aucun `GatewayDeployment` pour API + env |
| `no_target_gateway` | promotion/deploy demandé mais aucune cible gateway valide |
| `pending` | `GatewayDeployment.sync_status=pending` |
| `syncing` | `GatewayDeployment.sync_status=syncing` |
| `synced` | tous les `GatewayDeployment` attendus sont `synced` |
| `partial` | au moins un gateway `synced`, au moins un non-synced |
| `failed` | au moins un `error`, aucun `pending/syncing` récupérable |
| `drifted` | au moins un `drifted` |
| `deleting` | undeploy/rollback en suppression active |

Axes UI obligatoires pour une ligne `/api-deployments`:

| Axe | Source | Exemple | Ne doit pas masquer |
|-----|--------|---------|---------------------|
| Déploiement | `GatewayDeployment.sync_status`, `desired_generation`, `last_synced_generation` | `synced`, `pending`, `failed` | le nom API et la gateway cible |
| Connectivité gateway | heartbeat, route-sync poll, dernier ack agent | `online`, `restarting`, `offline`, `stale` | un deployment déjà `synced` |
| Runtime call optionnel | test manuel ou smoke ciblé | `2xx`, `404`, backend unreachable | la preuve d'ack gateway |

### 3.1.1 Agrégation multi-gateway

Une API peut avoir N cibles gateway par environnement. Chaque cible valide crée
un `GatewayDeployment` distinct, lié à la même génération de desired state.

Statut agrégé Console par API + environnement:

| Cas | Statut agrégé |
|-----|---------------|
| 0 cible gateway valide | `no_target_gateway` |
| tous les targets de la génération courante sont `synced` | `synced` |
| au moins un target `synced`, au moins un target `pending/syncing/error` | `partial` |
| aucun target `synced` et au moins un `error` final | `failed` |
| au moins un target `drifted`, tous les autres `synced` | `drifted` |
| au moins un target `drifted` et au moins un target non-synced | `partial_drifted` |
| au moins un target `deleting` | `deleting` |

L'agrégat ne doit jamais masquer les statuts par gateway: la Console doit
permettre de voir quelle cible est `synced`, `pending`, `error`, `drifted` ou
offline.

### 3.2 Assignments et gateways

- Un `ApiGatewayAssignment.environment` doit correspondre à
  `GatewayInstance.environment`.
- Une promotion avec `auto_deploy` attendu mais sans assignment cible doit
  retourner un signal explicite: erreur bloquante, warning actionnable, ou étape
  UI de choix gateway. Le résultat `0 deployment` silencieux est interdit.
- Un changement d'environnement ne doit jamais conserver une gateway sélectionnée
  dans un autre environnement.

### 3.3 Promotion et sync

- L'approbation d'une promotion qui déclenche des deployments doit lier chaque
  `GatewayDeployment.promotion_id` à la promotion source.
- La promotion ne peut passer à `promoted` automatiquement que si les
  `GatewayDeployment` liés sont tous `synced`.
- Si au moins un deployment lié passe `error` et qu'aucun n'est encore
  `pending/syncing`, la promotion doit devenir `failed`, conformément à
  ADR-059. Le détail de failure doit indiquer le nombre de gateways en échec.

### 3.4 Rollback et suppression

- Un rollback qui retire une API d'un environnement doit créer une intention
  explicite côté gateway: reverse promotion, Git revert réconcilié, ou
  `GatewayDeployment.sync_status=deleting` selon le chemin retenu par
  l'environnement.
- Une route gateway encore active après rollback doit apparaître comme drift ou
  suppression en attente, pas comme succès.

### 3.5 Timeouts et gateway down

- Une gateway down ne doit pas être confondue avec une dérive métier.
- Un deployment bloqué en `pending/syncing` doit avoir un délai maximal
  observable et une transition explicite vers `error`, `stale`, ou `retrying`.
  En architecture cible ADR-059 SSE, une perte de connexion Link laisse
  l'intention en attente jusqu'au reconnect/catch-up, mais la Console doit
  rendre cette attente visible.
- La Console doit afficher un état actionnable: re-sync, inspect gateway, ou
  supprimer la cible.

### 3.6 Colonnes minimales de la Console

Le tableau `/api-deployments` doit permettre de comprendre où l'API est
déployée sans ouvrir le détail.

Colonnes minimales:

- API: nom catalogue ou `desired_state.api_name`
- Environment: env normalisé (`dev`, `staging`, `prod`)
- Gateway: nom lisible de la gateway, nom logique agent si différent, et type
  (`stoa-connect`, `stoa-gateway`, `sidecar`, `legacy`)
- Deployment status: statut stable dérivé du `GatewayDeployment`
- Gateway status: connectivité/heartbeat séparée du statut de déploiement
- Last route ack: `last_sync_success` ou dernier `route-sync-ack`
- Promotion: lien/état promotion si le deployment vient d'une promotion

FAIL si le tableau affiche seulement "gateway unreachable" ou un point rouge
global sans montrer que l'API reste déployée sur une gateway précédemment
acquittée.

### 3.7 Déploiement vers environnements supérieurs

Le chemin attendu n'est pas le même selon l'environnement:

| Source | Cible | Déclencheur | Contrôle | Completion |
|--------|-------|-------------|----------|------------|
| local/dev | dev | deploy direct Console/API autorisé | gateway cible explicite ou assignment dev | ack gateway sur chaque `GatewayDeployment` |
| dev | staging | promotion `dev -> staging` | assignment staging `auto_deploy=true` ou choix explicite gateway staging | promotion `promoted` seulement après ack de toutes les gateways staging |
| staging | prod | promotion contrôlée/GitOps selon ADR-040 | approbation requise, pas de click-to-prod silencieux | prod `promoted` seulement après ack gateway prod ou signal GitOps équivalent |

Pour staging/prod:

- la promotion crée un `GatewayDeployment` par gateway cible valide;
- chaque gateway utilise son mode de transport déclaré;
- l'état promotion reste `promoting` tant que les deployments liés ne sont pas
  tous `synced`;
- une gateway temporairement offline conserve le deployment en attente ou
  `synced + gateway offline` selon qu'elle avait déjà ack la génération courante;
- aucun `Promotion.status=promoted` n'est autorisé avec `0` deployment créé.

Règles par environnement:

- **dev**: la Console/API peut créer une intention directe. Cette intention doit
  être dérivable d'un UAC/stoa.yaml ou réconciliée vers Git en side-effect selon
  le mode ADR-059.
- **staging**: la promotion ou un changement Git est le chemin recommandé. Un
  succès staging exige des `GatewayDeployment` cibles et des acks gateway, pas
  seulement une promotion approuvée.
- **prod**: pas de click-to-prod silencieux. La Console génère une PR Git ou
  suit le chemin GitOps approuvé par ADR-040, sauf emergency path explicitement
  audité. Une écriture directe prod ne peut pas être le chemin nominal.

## 4. Acceptance tests

### ADF-G1 — Desired state Git/UAC présent

Préparer un UAC/stoa.yaml pour une API et ses overlays d'environnement.

PASS si:
- le desired state contient l'API, les paramètres gateway et l'upstream
- les overlays `dev`, `staging`, `prod` expriment uniquement les différences
  d'environnement
- la spec est idempotente et versionnable dans Git

### ADF-G2 — CP matérialise le desired state

Réconcilier le desired state dans CP.

PASS si CP expose une projection matérialisée contenant:
- API/catalog identity
- desired generation/hash
- environment overlay résolu
- gateway targets candidates

FAIL si CP invente une configuration runtime qui ne peut pas être retracée vers
Git/UAC/stoa.yaml, sauf raccourci dev/demo explicitement marqué.

### ADF-G3 — Assignments et capabilities résolus

Résoudre les gateways cibles pour un environnement.

PASS si:
- les `ApiGatewayAssignment` et capabilities gateway produisent N targets valides
- les targets cross-env sont refusées
- le mode de transport de chaque target est connu avant création du deployment

### ADF-G4 — N GatewayDeployments créés

Créer ou matérialiser l'intention vers un environnement avec N targets.

PASS si un `GatewayDeployment` distinct existe par target, avec:
- `environment`
- gateway id/name
- transport/capability
- desired generation/hash
- `promotion_id` si issu d'une promotion

### ADF-G5 — Chaque gateway ack sa cible

Faire appliquer la génération courante par chaque Link/gateway cible.

PASS si:
- chaque target ack son `deployment_id`
- le statut agrégé reflète les statuts par gateway
- la Console permet de voir chaque cible et son dernier ack

### ADF-0 — Seed idempotent

Préparer:
- tenant `demo`
- API catalogue `demo-api-deploy-flow`
- gateway `gateway-dev-demo` en `dev`
- gateway `gateway-staging-demo` en `staging`
- aucun `GatewayDeployment` résiduel pour cette API, sauf si le test les nettoie

PASS si le seed est relançable sans doublons et retourne les IDs utiles.

### ADF-1 — Deploy dev direct crée un GatewayDeployment

`POST /v1/tenants/{tenant}/apis/{api}/deploy` avec
`{"environment":"dev","gateway_ids":["gateway-dev-demo"]}` retourne `201`.

Ce endpoint est un raccourci dev/demo qui matérialise une intention de desired
state vers des targets. Il n'est pas le chemin canonique prod.

PASS si un `GatewayDeployment` existe pour API + gateway dev avec statut
`pending` ou `syncing`.

### ADF-2 — Ack gateway synchronise l'état runtime

Après exécution par STOA Link et callback CP, ou via `route-sync-ack` dans le
chemin legacy encore présent:

PASS si le deployment a:
- `sync_status=synced`
- `last_sync_success` non nul
- `actual_state` renseigné ou preuve équivalente que la gateway a appliqué la route

NOTE: un passage par SyncEngine ou inline sync peut être accepté comme compat
legacy pendant la migration, mais ne doit pas devenir le contrat cible.

### ADF-3 — Console affiche la vérité runtime

La page `/api-deployments` charge les gateway deployments.

PASS si la ligne affiche:
- nom API issu de `desired_state.api_name` ou du catalog
- gateway cible avec nom lisible et type/capacité de déploiement
- environnement gateway
- statut dérivé de `GatewayDeployment.sync_status`
- statut de connectivité gateway séparé du statut deployment
- last sync basé sur `last_sync_success`

FAIL si la page affiche un succès basé uniquement sur `Deployment.completed_at`
ou `Promotion.completed_at`.

FAIL si une gateway offline/restarting fait repasser une API déjà `synced` en
`failed` sans nouvelle génération, undeploy, ou drift confirmé.

### ADF-4 — Assignment target env valide

Créer un assignment staging `auto_deploy=true` vers `gateway-staging-demo`.

PASS si:
- l'assignment est listé par
  `GET /v1/tenants/{tenant}/apis/{api}/gateway-assignments?environment=staging`
- le backend refuse ou signale toute gateway dont `GatewayInstance.environment`
  ne correspond pas à l'environnement de l'assignment

### ADF-5 — Promotion crée les GatewayDeployments attendus

Créer puis approuver une promotion `dev -> staging`.

PASS si:
- la promotion passe `promoting`
- au moins un `GatewayDeployment` est créé pour chaque assignment
  `auto_deploy=true` de l'environnement cible
- chaque deployment créé référence la promotion via `promotion_id`
- l'intention de déploiement est livrée au Link/gateway par le chemin cible
  SSE/callback, ou par `route-sync-ack` legacy tant que la migration n'est pas
  terminée

### ADF-6 — Promotion complétée après sync réel

Quand tous les `GatewayDeployment` liés à la promotion sont `synced`:

PASS si la promotion devient `promoted` et expose une preuve de completion.

FAIL si la promotion devient `promoted` alors qu'aucun deployment gateway lié
n'existe ou qu'un deployment lié est encore `pending/syncing/error`.

Si un deployment lié est `error` et qu'aucun deployment lié n'est encore
`pending/syncing`, la promotion doit devenir `failed`.

### ADF-7 — Promotion sans assignment ne réussit pas silencieusement

Supprimer les assignments staging puis approuver une promotion `dev -> staging`.

PASS si le système retourne ou expose explicitement:
- `no_target_gateway`
- ou une erreur bloquante
- ou une tâche d'action utilisateur "configure target gateway"

FAIL si la promotion peut être comprise comme réussie alors que `0`
`GatewayDeployment` a été créé.

### ADF-8 — Changement d'environnement ne garde pas une gateway invalide

Dans le dialog de deploy Console:
1. choisir `dev`
2. sélectionner une gateway dev
3. changer vers `staging`

PASS si la sélection gateway est remise à zéro ou remplacée uniquement par des
gateways staging.

FAIL si une gateway dev peut être soumise pour un déploiement staging.

### ADF-9 — Rollback/undeploy retire la route gateway

Déclencher rollback ou undeploy d'un deployment synced.

PASS si:
- le deployment devient `deleting` ou une intention équivalente est créée par
  reverse promotion / Git revert selon l'environnement
- la gateway retire la route
- la Console n'affiche plus l'ancienne route comme `synced`

## 5. Validation cible

### ADF-10 — Legacy VM via STOA Connect

Déployer une API vers une gateway legacy VM agent-managed, par exemple
`connect-webmethods-dev`.

PASS si:
- CP crée un `GatewayDeployment` pour la gateway canonique de l'environnement
- l'agent récupère la route via `GET /v1/internal/gateways/routes` en utilisant
  son nom logique
- l'agent applique la route via l'adapter gateway local
- l'agent envoie `route-sync-ack`
- la Console affiche `synced` uniquement après cet ack

FAIL si:
- la Console utilise le heartbeat `online` comme preuve de sync
- CP tente un push direct vers une gateway `self_register` agent-managed
- le déploiement reste invisible car le nom agent ne correspond pas au nom
  canonique DB

### ADF-11 — STOA Gateway edge/gateway

Déployer `demo-httpbin` vers une STOA gateway edge/gateway.

PASS si:
- la route est chargée dans la route table gateway
- `GET {GATEWAY_URL}/apis/demo-httpbin/get` répond non-404 avec une clé valide
- l'état Console est dérivé du `GatewayDeployment` et de la preuve gateway, pas
  d'un `Deployment.completed_at`

### ADF-12 — STOA Gateway sidecar

Déployer une API vers une STOA gateway sidecar dans l'environnement cible.

PASS si:
- le sidecar reçoit l'intention par le chemin agent-managed déclaré
- le backend configuré est résoluble depuis le sidecar
- l'ack `deployment_id` marque le `GatewayDeployment` `synced`
- un échec DNS ou gateway local remonte en `error` actionnable avec le nom de la
  cible fautive

FAIL si:
- CP marque la cible `error` uniquement parce qu'il ne peut pas résoudre le nom
  interne du sidecar alors que le mode déclaré est agent-managed
- une promotion dev->staging/prod est `promoted` avant l'ack sidecar

### ADF-13 — Promotion multi-mode fermée

Configurer des assignments `auto_deploy=true` vers au moins deux modes gateway
différents dans l'environnement cible, puis approuver une promotion.

PASS si:
- un `GatewayDeployment` est créé par cible valide
- chaque cible utilise son transport déclaré
- la promotion reste `promoting` tant que toutes les cibles ne sont pas
  `synced`
- la promotion devient `failed` si une cible est en `error` final

FAIL si la promotion réussit avec `0` deployment ou avec seulement une partie
des modes gateway acquittés.

### ADF-14 — Reboot gateway ne casse pas le statut déployé

Déployer une API vers une gateway webMethods de démo via STOA Connect, attendre
`sync_status=synced`, puis simuler un reboot gateway ou un heartbeat manquant.

PASS si:
- le `GatewayDeployment` reste `synced` pour la génération déjà acquittée
- la Console affiche la gateway `offline`, `restarting`, `stale` ou équivalent
  sur l'axe connectivité
- le tableau conserve le nom de la gateway et le dernier ack connu

FAIL si le statut principal de déploiement devient rouge/`failed` uniquement à
cause du healthcheck.

### ADF-15 — Drift confirmé après retour online

Après ADF-14, remettre la gateway online puis forcer une vérification qui
confirme que la route n'existe plus.

PASS si le deployment devient `drifted` ou demande un resync explicite, avec
preuve que la route attendue manque après retour online.

FAIL si un état offline temporaire est traité immédiatement comme drift.

### ADF-16 — Promotion vers staging/prod attend les acks cibles

Créer une promotion `dev -> staging` puis `staging -> prod` avec assignments
valides dans chaque environnement.

PASS si:
- chaque promotion crée ses propres `GatewayDeployment` liés par `promotion_id`
- les gateways staging/prod affichent leur nom dans le tableau
- la promotion ne devient `promoted` qu'après ack de toutes les gateways cibles
- une gateway cible déjà `synced` ne repasse pas `failed` sur simple reboot

FAIL si prod est marqué promoted avec `0` deployment, avec une gateway cross-env,
ou avec une gateway seulement healthcheckée mais jamais ack.

Court terme:
- ajouter un smoke API-level ciblé, par exemple
  `scripts/api-deployment-flow-smoke.sh`
- ajouter un test Playwright Console ciblé sur `/api-deployments`
- garder ce contrat non bloquant pour `demo-smoke-test.sh`

Commandes cibles:

```bash
# API-level, à créer
./scripts/api-deployment-flow-smoke.sh

# UI-level, à créer
cd e2e && npx playwright test api-deployment-flow.spec.ts
```

Critère GO pour toute PR touchant ce flux:
- ADF-G1 à ADF-G5 passent ou restent explicitement inchangés pour toute PR qui
  touche Git/UAC/stoa.yaml, reconciliation CP, assignments, capabilities ou
  matérialisation deployment
- ADF-1, ADF-2, ADF-3 passent ou restent explicitement inchangés par la PR
- ADF-5, ADF-6, ADF-7 passent pour toute PR promotion/assignment/sync
- ADF-8 passe pour toute PR Console deploy dialog ou environment selector
- ADF-9 passe pour toute PR rollback/undeploy
- ADF-14, ADF-15, ADF-16 passent pour toute PR qui touche healthcheck gateway,
  drift detection, promotion, ou la table `/api-deployments`

## 6. Blockers connus

| # | Blocker | Sévérité | Étapes impactées |
|---|---------|----------|------------------|
| A-B1 | `auto_deploy_on_promotion()` peut retourner `[]` sans signal utilisateur clair | P0 | ADF-5, ADF-7 |
| A-B2 | `promotion_id` n'est pas garanti sur tous les deployments créés par approval direct | P0 | ADF-5, ADF-6 |
| A-B3 | assignment env/gateway non validé comme contrainte métier forte | P1 | ADF-4, ADF-8 |
| A-B4 | timeout explicite de sync adapter non contractuel | P1 | ADF-2, ADF-6 |
| A-B5 | rollback ne garantit pas une intention `deleting` sur les anciens deployments | P1 | ADF-9 |
| A-B6 | `/api-deployments` n'est pas encore couvert par un smoke transverse | P1 | ADF-3, ADF-8 |
| A-B7 | chemins legacy SyncEngine/inline sync encore visibles dans le code malgré ADR-059 SSE cible | P1 | ADF-2, ADF-5 |
| A-B8 | capacité de déploiement gateway non exposée/normalisée (`agent_pull_ack`, `stoa_gateway_registry`, `direct_adapter`) | P0 | ADF-10, ADF-11, ADF-12, ADF-13 |
| A-B9 | statut de déploiement et healthcheck gateway mélangés dans la Console | P0 | ADF-3, ADF-14, ADF-15 |
| A-B10 | flow staging/prod insuffisamment contracté côté assignments, promotion et ack | P0 | ADF-5, ADF-6, ADF-13, ADF-16 |
| A-B11 | spec encore trop `GatewayDeployment`-first si Git/UAC desired state n'est pas vérifié avant matérialisation | P0 | ADF-G1, ADF-G2, ADF-G3, ADF-G4, ADF-G5 |

## 7. Révisions

| Date | Auteur | Changement |
|------|--------|------------|
| 2026-04-25 | Codex | Création initiale du contrat API deployment flow |
| 2026-04-25 | Codex | Alignement explicite ADR-040/ADR-059/ADR-035/ADR-036 |
| 2026-04-25 | Codex | Ajout du contrat multi-mode legacy VM/STOA gateway/STOA sidecar |
| 2026-04-25 | Codex | Séparation statut déploiement vs health gateway et promotion env supérieurs |
| 2026-04-25 | Codex | Réorientation Git/UAC desired-state-first selon ADR-040 et ADR-059 |
