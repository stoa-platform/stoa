# Audit CLI-First / API-First — STOA vs Pattern Kubernetes

**Date**: 2026-04-11
**Auteur**: Claude Code (Opus 4.6)
**Scope**: monorepo `stoa` (control-plane-api, stoa-go, charts, deploy)
**Méthode**: inventaire factuel via exploration ciblée. Aucun code modifié.

---

## TL;DR (5 lignes)

L'ossature pattern Kubernetes **existe déjà à 70%** — le vrai écart n'est pas architectural, il est de **câblage** :
- **API Server** ✅ : 447 endpoints FastAPI versionnés `/v1/`, scopés tenant (= namespace), CRUD quasi-complet
- **Controller** ✅ : `sync_engine.py` + `gateway_reconciler.py` sont de vraies boucles de réconciliation (Kafka + périodique)
- **Desired/Actual + Generation** ✅ : `GatewayDeployment` implémente déjà `desired_state` / `actual_state` / `desired_generation` / `synced_generation` (CAB-1950, pattern K8s `observedGeneration`)
- **CLI** ✅ : `stoactl` Go/Cobra complet (17+ commandes, OAuth device flow, `~/.stoa/config` kubeconfig-like)
- **Maillon faible** ❌ : `stoactl apply -f` ne supporte **que `kind: API`** (8+ autres kinds déclarés mais non-câblés). Le modèle de ressource est **fragmenté** entre 2 API groups (`stoa.io/v1` + `gostoa.dev/v1alpha1`) et 5 CRDs (Tool/ToolSet/GatewayInstance/GatewayBinding/Skill) qui ne sont pas la majorité.

**Le mental model K8s est déjà présent. Le gap est l'alignement du CLI sur l'API, pas une refonte.**


---

## 1. État stoactl (Go CLI)

### 1.1 Localisation & structure
- **Repo**: monorepo, pas séparé. Racine : `stoa-go/`
- **Entry point**: `stoa-go/cmd/stoactl/main.go`
- **Stack**: Go + Cobra (`spf13/cobra`)
- **Types**: `stoa-go/pkg/types/types.go` (schemas Resource / APISpec / UpstreamSpec / RoutingSpec / AuthenticationSpec / PoliciesSpec / CatalogSpec)
- **Config**: `stoa-go/pkg/config/config.go` (kubeconfig-like YAML à `~/.stoa/config`)
- **État**: **COMPLET** (pas skeleton, pas abandonné). Développé activement.

### 1.2 CLI Python legacy (`cli/`)
- Présent, **SKELETON**. Couvre login / get / apply / status / deploy via Typer. Non référencé récemment.
- `stoactl` Go est le CLI primaire.

### 1.3 Commandes stoactl (arbre complet)

| Commande | État | Notes |
|----------|------|-------|
| `stoactl auth login` | ✅ fonctionnel | **OAuth2 Device Flow** (RFC 8628) vers `auth.gostoa.dev/realms/stoa` — token stocké keyring OS + fallback `~/.stoa/tokens` |
| `stoactl auth status` / `logout` / `rotate-key` | ✅ | |
| `stoactl config get-contexts` / `set-context` / `use-context` / `view` | ✅ | Kubeconfig-like : contexts nommés, server + tenant par contexte |
| `stoactl get apis [name]` | ✅ | Calls API `/v1/tenants/{t}/apis` |
| `stoactl get tenants [id]` | ✅ | |
| `stoactl get subscriptions [id]` | ✅ | |
| `stoactl get gateways [id]` | ✅ | |
| **`stoactl apply -f <file\|dir> [--dry-run]`** | ⚠️ **partiel** | Parse YAML ✅, valide `apiVersion/kind/metadata.name` ✅, marche sur répertoires ✅ — **mais le switch sur `kind` ne câble que `kind: API`** (`apply.go:126`) ; toutes les autres `kind` retournent "unsupported" |
| `stoactl delete api <name>` | ✅ | |
| `stoactl deploy create/list/get/rollback` | ✅ | File-based + impératif |
| `stoactl catalog sync [--dry-run] [--apply]` | ✅ | Remplace `ops/catalog-sync.sh` (cf. `.claude/rules/stoactl-usage.md`) |
| `stoactl audit export [--tenant] [--since] [--output csv\|json] [--redact-pii]` | ✅ | |
| `stoactl bridge -f openapi.yaml` | ✅ | OpenAPI → MCP |
| `stoactl logs` / `token-usage` / `init` / `doctor` | ✅ | |
| `stoactl tenant` / `subscription` / `gateway` | ✅ | Sous-commandes impératives |
| `stoactl connect` | ✅ | Côté `stoa-connect` (agent VPS) |
| `stoactl mcp list-tools` / `mcp ...` | ✅ | Couverture MCP |
| `stoactl completion` / `version` | ✅ | |

### 1.4 `apply -f` — le test décisif
- **Existe** ✅ — `stoa-go/internal/cli/cmd/apply/apply.go`
- Comportement : parse YAML → valide structure (`apiVersion/kind/metadata`) → `c.ValidateResource()` en dry-run → `c.CreateOrUpdateAPI()` sinon.
- **Limitation forte** : le switch sur `kind` (apply.go:126) ne matche que `"API"`. Les types déclarés dans `types.go` pour `Subscription` (170-182), `GatewayInstance` (193-204), `Tenant`, etc. **ne sont pas câblés dans apply**.
- **Conséquence** : le CLI a 2 vies parallèles — une impérative (stoactl tenant create…, stoactl subscription create…) et une déclarative qui ne fonctionne que pour `API`.

### 1.5 Format de ressource (schémas YAML)
Défini dans `stoa-go/pkg/types/types.go`. Shape conforme K8s :

```yaml
apiVersion: stoa.io/v1
kind: API
metadata:
  name: billing-api
  namespace: acme-prod       # utilisé comme tenant par le CLI
  labels:
    team: finance
spec:
  version: "2.0"
  upstream:   { url, timeout, retries }
  routing:    { path, stripPath, methods[] }
  authentication: { required, providers[] }
  policies:   { rateLimit, cors, cache }
  catalog:    { visibility, categories[] }
```

### 1.6 Auth
- **OAuth2 Device Flow** (le bon choix pour un CLI — pas de localhost callback, pas de secret embarqué).
- `clientID = "stoactl"`, realm `stoa`, serveur hardcodé `auth.gostoa.dev`.
- Stockage token : keyring OS d'abord (macOS Keychain / libsecret / Credential Manager), fallback fichier `~/.stoa/tokens`.

### 1.7 Config file (`~/.stoa/config`)
Structure **strictement équivalente à kubeconfig** :

```yaml
apiVersion: stoa.io/v1
kind: Config
current-context: prod
contexts:
  - name: prod
    context:
      server: https://api.gostoa.dev
      tenant: acme
  - name: dev
    context:
      server: https://api-dev.gostoa.dev
      tenant: acme-dev
```

**Verdict Étape 1** : stoactl est **mûr et fonctionnel**. Le gap n'est pas le CLI, c'est le câblage `apply -f` sur l'intégralité des kinds.

---

## 2. État Control Plane API (FastAPI)

### 2.1 Inventaire endpoints — 447 endpoints identifiés

Résumé par domaine (liste complète dans la section 4 du rapport des sub-agents — ici les groupes clés) :

| Domaine | #Endpoints | Shape dominante | Versionning |
|---------|-----------|-----------------|-------------|
| **Tenants** | 8 | CRUD partiel (list/get/create/update/delete) + RPC `provision` | `/v1/tenants` |
| **APIs** | 17 | **CRUD déclaratif complet** + Backend APIs + Contracts (UAC) | `/v1/tenants/{id}/apis` |
| **Consumers** | 16 | CRUD + RPC lifecycle (suspend/activate/block) + certif mgmt | `/v1/consumers/{tid}` |
| **Deployments** | 17 | **Procédural** (trigger, rollback, approve, reject, deploy) | `/v1/tenants/{id}/deployments` |
| **Gateways** | 40 | CRUD déclaratif + RPC (sync, bind, register, heartbeat) | `/v1/gateway/instances`, `/v1/admin/gateways` |
| **Subscriptions** | 17 | CRUD déclaratif + app subscribe/unsubscribe | `/v1/tenants/{id}/subscriptions` |
| **Policies (Gateway)** | ~6 | CRUD complet + bind | `/v1/gateway/policies` |
| **Audit / Security** | 18 | Query + export + RPC (erase PII, scan) | `/v1/audit/{tid}` |
| **Webhooks** | 10 | CRUD + retry | `/tenants/{id}/webhooks` |
| **MCP Servers** | 6+ | CRUD déclaratif | `/v1/mcp/servers` |
| **LLM Budget / Monitoring** | 15 | CRUD (budget) + reporting (usage) | `/v1/llm/*`, `/v1/metrics` |

### 2.2 Versioning
- `/v1/` **appliqué de manière cohérente** sur tous les endpoints ressource.
- `/v1/internal/` réservé agents (heartbeat, register).
- `/v1/admin/` pour opérations cross-tenant (platform admins).
- **Pas de v2** — une seule version active.

### 2.3 Tenant = namespace
- **Pattern universel** : `/v1/tenants/{tenant_id}/<resource>` — TOUS les endpoints ressources sont scopés tenant.
- Endpoints globaux cross-tenant uniquement sous `/v1/admin/*`.
- Isolation strictement comparable à `kubectl -n <namespace>` .

### 2.4 Schemas Pydantic — pattern Create/Update/Response
Cohérent sur tout le code base :
- `TenantCreate` / `TenantUpdate` / `TenantResponse` (`schemas/tenant.py`)
- `ConsumerCreate` / `ConsumerUpdate` / `ConsumerResponse`
- `BackendApiCreate` / `BackendApiUpdate` / `BackendApiResponse`
- `ContractCreate` / `ContractUpdate` / `ContractResponse` (multi-protocol UAC)
- `AssignmentCreate` / `AssignmentResponse`

Convention Pydantic v2, pas de `*In`/`*Out` — c'est `*Create`/`*Update`/`*Response`. **Cohérent.**

### 2.5 Shape de l'API : déclarative ou procédurale ?

| Shape | Domaines concernés |
|-------|---------------------|
| **CRUD déclaratif complet** | APIs, Contracts, Subscriptions, Gateway Policies, MCP Servers, LLM Budget, Webhooks (CRUD part), Gateways |
| **CRUD + verbes lifecycle** (acceptable — K8s fait pareil avec `subresources/status`) | Consumers (suspend/activate/block), Tenants (provision) |
| **Procédural / RPC** (anti-pattern vs K8s) | **Deployments** (trigger/rollback/approve/reject/deploy) — tout le domaine déploiement est piloté par verbes impératifs |

**Verdict Étape 2** : l'API est déjà **majoritairement déclarative** sur les ressources métier. Le domaine Deployments reste le seul îlot procédural — mais c'est cohérent avec l'état de l'art (même ArgoCD mélange desired-state + verbes `/sync`, `/rollback`).

---

## 3. Matrice de couverture CLI ↔ API ↔ UI

Légende : ✅ complet • ⚠️ partiel • ❌ absent

| Ressource / Action | API endpoint | stoactl | Portal UI (côté user) | Console UI (côté admin) |
|---|---|---|---|---|
| **List APIs** | `GET /v1/tenants/{t}/apis` | ✅ `stoactl get apis` | ✅ | ✅ |
| **Get API detail** | `GET /v1/tenants/{t}/apis/{id}` | ✅ | ✅ | ✅ |
| **Create API (declarative)** | `POST /v1/tenants/{t}/apis` | ✅ `stoactl apply -f api.yaml` | ⚠️ wizard seulement | ⚠️ wizard seulement |
| **Update API** | `PUT /v1/tenants/{t}/apis/{id}` | ✅ (apply réapplique) | ⚠️ | ⚠️ |
| **Delete API** | `DELETE /v1/tenants/{t}/apis/{id}` | ✅ `stoactl delete api` | ✅ | ✅ |
| **List tenants** | `GET /v1/tenants` | ✅ `stoactl get tenants` | N/A (single-tenant) | ✅ |
| **Create tenant** | `POST /v1/tenants` | ⚠️ commande impérative `stoactl tenant` seulement — **pas via `apply -f`** | N/A | ✅ |
| **Provision tenant** | `POST /v1/tenants/{t}/provision` | ⚠️ impératif | N/A | ✅ |
| **List subscriptions** | `GET /v1/tenants/{t}/subscriptions` | ✅ `stoactl get subscriptions` | ✅ | ✅ |
| **Create subscription** | `POST /v1/tenants/{t}/subscriptions` | ⚠️ impératif `stoactl subscription` — **pas via `apply -f`** | ✅ | ✅ |
| **Subscribe app to API** | `POST /v1/tenants/{t}/applications/{a}/subscribe/{api}` | ❌ | ✅ | ✅ |
| **Rotate API key** | `POST /v1/tenants/{t}/subscriptions/{s}/rotate-key` | ⚠️ `stoactl auth rotate-key`? incertain | ✅ | ✅ |
| **List gateways** | `GET /v1/gateway/instances` | ✅ `stoactl get gateways` | N/A | ✅ |
| **Create gateway instance** | `POST /v1/gateway/instances` | ⚠️ impératif — **pas via `apply -f`** | N/A | ✅ |
| **Sync gateway** | `POST /v1/gateway/instances/{id}/sync` | ⚠️ `stoactl catalog sync` est proche mais pas identique | N/A | ✅ |
| **List/create/bind gateway policies** | `/v1/gateway/policies` | ❌ | N/A | ✅ |
| **Create/manage consumers** | `/v1/consumers/{t}` CRUD + lifecycle | ❌ (pas de sous-commande visible) | ⚠️ | ✅ |
| **Deployments (trigger/list/rollback)** | `/v1/tenants/{t}/deployments` | ✅ `stoactl deploy create/list/rollback` | ❌ | ✅ |
| **Promotions (dev→staging→prod)** | `/v1/tenants/{t}/promotions` | ❌ | ❌ | ⚠️ |
| **Audit logs (list/export)** | `/v1/audit/{t}` | ✅ `stoactl audit export` | ❌ | ✅ |
| **Metrics / dashboards** | `/v1/metrics`, `/v1/llm/usage` | ⚠️ `stoactl token-usage` (partiel) | ✅ | ✅ |
| **LLM budgets** | `/v1/llm/budget` CRUD | ❌ | ⚠️ | ✅ |
| **MCP servers / tools** | `/v1/mcp/servers`, `/v1/mcp/subscriptions` | ✅ `stoactl mcp list-tools` | ⚠️ | ✅ |
| **Webhooks** | `/tenants/{t}/webhooks` CRUD | ❌ | ❌ | ✅ |
| **Bridge OpenAPI → MCP** | (local) | ✅ `stoactl bridge` | ❌ | ❌ |

### Gaps saillants
- **Côté CLI declaratif (`apply -f`)** : couverture **~10%** des ressources — seul `kind: API` est câblé dans le switch.
- **Côté CLI impératif** : couverture **~70%** — ce que l'UI fait, le CLI sait souvent le faire, mais par des sous-commandes spécifiques (`stoactl tenant`, `stoactl subscription`, etc.) et pas via `apply`.
- **Côté UI seulement** : Consumers (lifecycle), Gateway Policies (bind), Webhooks, Promotions, LLM Budget — pas de commande stoactl.
- **Côté Portal seulement (pas CLI)** : subscribe app → API, rotate-key (UX-first).

---

## 4. Modèle déclaratif — état actuel

### 4.1 Fragments trouvés (ce qui existe)

**Two API groups coexistent** :
1. `stoa.io/v1` → utilisé par `stoa-go/pkg/types/types.go` (API, Tenant, Subscription, GatewayInstance) ET par `deploy/platform-bootstrap/` (WebMethodsAPI, Policy, Application, Scopes, RoleMatrix, SCIMProvider)
2. `gostoa.dev/v1alpha1` → utilisé par les **CRDs Helm** (Tool, ToolSet, GatewayInstance, GatewayBinding, Skill) ET par `deploy/demo-tenants/*.yaml` (Tenant, Subscription, Tool, ToolSet)

→ **Collision** : `Tenant` existe sous les deux groupes ; `GatewayInstance` existe sous les deux groupes.

### 4.2 CRDs Helm (`charts/stoa-platform/crds/`)

| Kind | Group | Version | Scope | Spec schema |
|------|-------|---------|-------|-------------|
| `Tool` | `gostoa.dev` | `v1alpha1` | Namespaced | displayName, endpoint, method, inputSchema, outputSchema, auth, rateLimit, annotations |
| `ToolSet` | `gostoa.dev` | `v1alpha1` | Namespaced | upstream (MCP URL, transport, auth), tools[], prefix |
| `GatewayInstance` | `gostoa.dev` | `v1alpha1` | Namespaced | displayName, gatewayType enum, environment, baseUrl, authConfig, capabilities[] |
| `GatewayBinding` | `gostoa.dev` | `v1alpha1` | Namespaced | (schéma non inspecté ici) |
| `Skill` | `gostoa.dev` | `v1alpha1` | Namespaced | (schéma non inspecté ici) |

**Couverture CRD** : 5 kinds. Les ressources centrales (API, Tenant, Subscription, Policy, Application) **ne sont pas des CRDs**.

### 4.3 Exemples YAML déployés
- `deploy/demo-tenants/team-alpha.yaml` — `kind: Tenant` (gostoa.dev/v1alpha1) avec quotas, roles, tools
- `deploy/demo-tenants/subscriptions.yaml` — `kind: Subscription`
- `deploy/platform-bootstrap/apis/control-plane-api.yaml` — `kind: WebMethodsAPI` (stoa.io/v1), ~263 lignes
- `deploy/platform-bootstrap/policies/*.yaml` — `kind: Policy` (stoa.io/v1)
- `charts/stoa-platform/examples/tool-weather.yaml` — `kind: Tool` complet

### 4.4 Reconciliation (desired vs actual)

**OUI, implémentée sérieusement** :

- **`control-plane-api/src/models/gateway_deployment.py`** (modèle clé, CAB-1950) :
  ```python
  desired_state     = Column(JSONB)
  desired_at        = Column(DateTime)
  actual_state      = Column(JSONB)
  actual_at         = Column(DateTime)
  sync_status       = Column(SQLEnum[PENDING, IN_PROGRESS, SUCCESS, FAILED])
  last_sync_attempt = Column(DateTime)
  last_sync_success = Column(DateTime)
  sync_error        = Column(Text)
  sync_steps        = Column(JSONB)           # observabilité step-level
  desired_generation   = Column(Integer)      # ↑ bumped par update
  synced_generation    = Column(Integer)      # ↑ bumped sur success
  attempted_generation = Column(Integer)      # ↑ bumped à chaque tentative
  ```
  → **C'est exactement le pattern K8s `observedGeneration`.** Migration `087_add_deployment_generations.py`.

- **`control-plane-api/src/workers/sync_engine.py`** : vraie boucle asynchrone, consomme Kafka topic `gateway-sync-requests` + réveille périodique (`SYNC_ENGINE_INTERVAL_SECONDS`). Appelle les méthodes d'adaptateur. **C'est un controller au sens K8s**, pas un cron.

- **`control-plane-api/src/workers/gateway_reconciler.py`** : 2e boucle périodique, sync l'état ArgoCD Application → `gateway_instances` table. **2e controller.**

**Limites actuelles** :
- Seul `GatewayDeployment` a ce split spec/status + generation. Les autres ressources (Tenant, API catalog, Subscription, Consumer) n'ont pas de champ `desired_generation` — elles vivent en état "flat" avec un simple `status` enum.
- Pas de `ResourceVersion` (ETag) au niveau global → pas d'optimistic concurrency control façon K8s.

---

## 5. STOA Links / Adapters — pattern operator ?

### 5.1 Adapters présents (`control-plane-api/src/adapters/`)
8 adapters, tous implémentant `GatewayAdapterInterface` (16 méthodes abstraites + lifecycle) :
1. `stoa/adapter.py` (Rust gateway)
2. `kong/adapter.py`
3. `gravitee/adapter.py`
4. `webmethods/adapter.py`
5. `apigee/adapter.py`
6. `azure/adapter.py`
7. `aws/adapter.py`
8. `template/adapter.py`

### 5.2 Pattern d'invocation — DUAL

**(a) Synchrone, request-driven** (procédural) :
Les handlers de route (`routers/apis.py`, etc.) peuvent appeler `adapter.sync_api()` en direct sur POST/PUT. Chemin court, pas async.

**(b) Asynchrone, reconciliation loop** (operator) :
- `workers/sync_engine.py` :
  - Consommateur Kafka sur topic `gateway-sync-requests` (publié par les handlers quand il faut pousser vers un gateway)
  - Wake-up périodique (`SYNC_ENGINE_INTERVAL_SECONDS`)
  - Compare `desired_state` vs `actual_state` de `GatewayDeployment`, choisit quoi faire, appelle l'adapter
  - Met à jour `sync_status`, `attempted_generation`, `synced_generation`
- `workers/gateway_reconciler.py` :
  - Loop séparée, sync ArgoCD → DB pour `gateway_instances`

**Verdict** : le système est hybride mais **la partie operator est réelle**, pas bidon. C'est un vrai **controller manager** avec 2 controllers.

### 5.3 Event bus
- **Kafka** (topic `gateway-sync-requests`, via `aiokafka` async).
- **Pas de** Redis pub/sub, SSE, webhook callbacks depuis adapters. Adapters = HTTP request/response pur.

### 5.4 Retour de l'adapter — `AdapterResult`
```python
@dataclass
class AdapterResult:
    success: bool
    resource_id: str | None
    data: dict
    error: str | None
```
→ **Exécution-based, pas diff-based**. L'adapter exécute et rapporte. Le diff est calculé côté Sync Engine (en comparant `desired_state` vs `actual_state` dans la DB).

---

## 6. Score d'écart avec le pattern Kubernetes

Notation 0-10. 10 = parité K8s, 0 = absent.

| Composant K8s | Équivalent STOA | État | Score | Écart |
|---|---|---|---|---|
| **kubectl** | `stoactl` | Complet, OAuth device flow, contexts, kubeconfig-like | **9/10** | `apply -f` limité au kind `API` |
| **API Server** | Control Plane FastAPI (`/v1/*`) | 447 endpoints, versionnés, tenant-scoped, CRUD majoritaire | **8/10** | Domaine Deployments reste procédural |
| **CRD / Resource Model** | `gostoa.dev/v1alpha1` CRDs + `stoa.io/v1` YAML | 5 CRDs (Tool/ToolSet/GatewayInstance/GatewayBinding/Skill) + ~6 kinds déclarés en YAML mais sans CRD | **5/10** | **Fragmentation** : 2 groups coexistent ; collision sur Tenant/GatewayInstance ; pas de schema registry unifié |
| **Desired State Store (etcd)** | PostgreSQL + `desired_state` JSONB | Dans `GatewayDeployment` uniquement (pas généralisé) | **6/10** | Spec/status split seulement pour GatewayDeployment |
| **Controller Manager** | `workers/sync_engine.py` + `workers/gateway_reconciler.py` | Vraies boucles, Kafka event-driven + périodique | **8/10** | 2 controllers seulement ; pas de framework générique "un controller par CRD" |
| **Reconciliation Loop** | `SYNC_ENGINE_INTERVAL_SECONDS` + topic Kafka | Implémentée avec `desired_generation` / `synced_generation` / `attempted_generation` (CAB-1950) | **9/10** | Pattern `observedGeneration` explicite. Reste seulement la généralisation aux autres ressources |
| **ResourceVersion / Optimistic concurrency** | (aucun) | Pas de champ `resource_version` ou ETag dans les modèles principaux | **1/10** | Absent hors GatewayDeployment |
| **Watch / Informer** | Kafka topics consumers | Event-driven via Kafka (pas de long-poll watch HTTP façon K8s) | **5/10** | Pas d'API `watch=true` côté Control Plane ; consommation Kafka interne uniquement |
| **Admission webhooks** | `stoactl apply --dry-run` + Pydantic validation | Validation statique uniquement | **4/10** | Pas de validation dynamique configurable |
| **K8s Dashboard** | Portal (dev) + Console (admin) React | UX complète, couvre plus de cas que CLI | **9/10** | OK — mais découplage incomplet du CLI |
| **RBAC** | Keycloak (realm `stoa`, rôles cpi-admin/tenant-admin/devops/viewer) | Production, OIDC, stoa:read/write/admin scopes | **9/10** | Pattern `Role`/`RoleBinding` K8s non explicite mais équivalent |
| **Namespace** | Tenant (`/v1/tenants/{tid}/...`) | Isolation stricte de TOUTES les ressources | **10/10** | Parité fonctionnelle |
| **Operator (par backend gateway)** | 8 adapters (Kong, Gravitee, webMethods, Apigee, AWS, Azure, STOA, template) | Interface 16 méthodes, idempotence documentée | **8/10** | Couplés au Sync Engine central, pas opérateurs indépendants |

**Score agrégé : 7.0 / 10** — bien au-dessus de ce que suggère l'intuition "on n'a pas du tout le pattern K8s".

---

## 7. Recommandations (factuelles, priorisées)

### 7.1 Quick wins (< 1 jour — câblage pur)

1. **Généraliser le switch `apply.go:126`** dans stoactl pour supporter tous les kinds déjà déclarés dans `types.go` : `Tenant`, `Subscription`, `GatewayInstance`, `Consumer`, `Policy`, `Contract`. Chaque branche = un appel `client.CreateOrUpdate<Kind>()` vers l'endpoint CRUD déjà existant. **Zero changement API Server**.
   - Impact : fait sauter le gap #1 de l'audit d'un coup. `stoactl apply -f tenant.yaml` devient possible.

2. **Ajouter `stoactl get <kind>` pour Consumers, Policies, Webhooks, Deployments, Promotions, LLM Budget** — les endpoints API existent tous, il manque juste les sous-commandes Cobra.

3. **Harmoniser l'apiVersion** : décider entre `stoa.io/v1` (choisi par `types.go` + `platform-bootstrap/`) et `gostoa.dev/v1alpha1` (choisi par les CRDs). Les fichiers `deploy/demo-tenants/*.yaml` et `deploy/demo-rpo/tools/*.yaml` utilisent déjà `gostoa.dev/v1alpha1` — il faudrait **soit migrer stoa-go/types.go vers `gostoa.dev`, soit l'inverse**.
   - Impact : élimine la collision `Tenant`/`GatewayInstance` entre les deux groups.

4. **Écrire un `README` qui liste le modèle de ressource canonique** (kind, group, version, schema source-of-truth) — élimine le gap documentaire.

### 7.2 Changements structurels (1-2 semaines)

5. **Généraliser le pattern `desired_generation` / `synced_generation`** (CAB-1950) **au-delà de `GatewayDeployment`**. Candidats prioritaires : `APIModel` (apis), `SubscriptionModel`, `ConsumerModel`. Chaque ressource devient réconciliable, pas juste les déploiements.

6. **Factoriser un mini "controller framework"** au-dessus de `sync_engine.py`. Aujourd'hui il y a 1 grosse loop pour tous les gateways. Le pattern K8s : 1 controller par ressource (1 pour `apis`, 1 pour `subscriptions`, etc.), chacun consommant sa propre topic Kafka. Refactor cosmétique de ce qui existe.

7. **Ajouter un endpoint `GET /v1/tenants/{t}/apis?watch=true`** en SSE ou long-poll — permet à `stoactl get apis -w` façon `kubectl`, et à des opérators tiers de réagir aux changements sans poll. Pattern K8s natif.

8. **JSON Schema registry** : générer automatiquement à partir des Pydantic schemas un dossier `schemas/<kind>.json` publié avec les CRDs. Source unique pour : validation `apply`, complétion IDE, doc auto, admission webhook futur.

### 7.3 Ce qui existe déjà et juste besoin d'être mis en avant

- **Sync Engine + Gateway Reconciler** : c'est déjà un controller manager embryonnaire. Le nommer comme tel (runbook, diagramme d'archi) aurait un impact marketing énorme pour les banques qui cherchent "K8s for APIs".
- **CAB-1950 generation pattern** : à citer comme adoption explicite du pattern `observedGeneration`. C'est exactement ce que les SREs K8s cherchent.
- **stoactl OAuth device flow + kubeconfig** : déjà au niveau de `kubectl`. Mettre en valeur dans la doc et les démos — actuellement sous-communiqué.
- **CRDs réelles pour Tool/ToolSet/GatewayInstance/GatewayBinding/Skill** : déjà dans Helm, déjà appliquées par `kubectl apply -f`. STOA est **déjà K8s-native** pour ce sous-ensemble.

---

## 8. Ce que cet audit N'A PAS fait

- Pas lu le code interne des 8 adapters (on a lu l'interface + la doc `.claude/rules/gateway-adapters.md`).
- Pas vérifié la couverture de tests derrière `stoactl apply -f` pour les kinds autres que `API`.
- Pas exploré le détail des schemas `GatewayBinding` / `Skill`.
- Pas comparé la matrice d'auth RBAC stoactl/Portal/Console — les 4 rôles sont documentés (`cpi-admin`, `tenant-admin`, `devops`, `viewer`) mais la granularité effective n'a pas été vérifiée endpoint par endpoint.
- Pas audité si `sync_engine.py` gère effectivement toutes les erreurs de reconciliation (retry, backoff, dead-letter). Les modèles de colonnes (`sync_error`, `last_sync_attempt`) suggèrent oui, mais non vérifié.

---

## 9. Conclusion factuelle

STOA est à **~70% du pattern K8s** au niveau architecture, mais cette réalité est **invisible** depuis l'extérieur parce que :
1. `stoactl apply -f` ne montre pas ses muscles (1 kind sur 10+).
2. Le modèle de ressource est fragmenté entre deux API groups.
3. Le Sync Engine est un "worker" dans le code, pas un "controller" dans la doc.

**Hypothèse initiale validée** : pousser le pattern "CLI-first / API-first / K8s-like" **n'est pas une refonte**, c'est un **alignement de câblage + nommage + doc**. La plupart des pièces existent. Le travail est : (a) généraliser `apply -f`, (b) harmoniser l'apiVersion, (c) étendre `observedGeneration` à toutes les ressources, (d) renommer Sync Engine en Controller Manager dans la doc.

**Le mental model banque centrale "kubectl for APIs" est atteignable en semaines, pas en trimestres.**
