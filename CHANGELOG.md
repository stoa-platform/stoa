# Changelog

Toutes les modifications notables de ce projet sont documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/).

---

## [Unreleased]

### Modifié (2026-01-04) - CAB-237 Rename devops → console subdomain

- **Renommage sous-domaine Control Plane UI**
  - `devops.stoa.cab-i.com` → `console.stoa.cab-i.com`
  - Reflète l'unification UI: DevOps + Developers (AI Tools Portal)

- **Fichiers de configuration mis à jour**:
  - `deploy/config/dev.env` - CORS_ORIGINS, DOMAIN_UI
  - `deploy/config/staging.env` - CORS_ORIGINS, DOMAIN_UI
  - `deploy/config/prod.env` - CORS_ORIGINS, DOMAIN_UI
  - `control-plane-api/src/config.py` - CORS_ORIGINS default
  - `control-plane-api/Dockerfile` - ENV CORS_ORIGINS
  - `gitops-templates/_defaults.yaml` - CONTROL_PLANE_UI_URL

- **Scripts et playbooks**:
  - `ansible/playbooks/bootstrap-platform.yaml` - URL dans message final
  - `scripts/init-gitlab-gitops.sh` - URL dans affichage

- **Documentation**:
  - `CLAUDE.md` - Key URLs section
  - `README.md` - Architecture diagram, URLs, exemples
  - `docs/ibm/webmethods-gateway-api.md` - URLs exemple
  - `docs/runbooks/README.md` - URLs services
  - `docs/runbooks/high/certificate-expiration.md` - Check script domains
  - `docs/runbooks/medium/api-rollback.md` - URLs vérification

- **Scripts de migration**:
  - `scripts/update-keycloak-console-redirect.sh` - Met à jour redirectURIs Keycloak
  - `scripts/verify-console-dns.sh` - Vérifie/crée DNS Route53

- **Déploiement effectué**:
  - Ingress `control-plane-ui` mis à jour vers `console.stoa.cab-i.com`
  - Certificat TLS `stoa-console-tls` émis par Let's Encrypt
  - Client Keycloak `control-plane-ui` redirectURIs mis à jour

- **Accès Console UI**:
  - URL: https://console.stoa.cab-i.com
  - Users: `admin@cab-i.com`, `demo@apim.local` (password: `demo`)

### Ajouté (2026-01-04) - CAB-124 Portal Integration - Tool Catalog

- **Control Plane UI - Section AI Tools**
  - `src/pages/AITools/ToolCatalog.tsx` - Catalogue des tools MCP:
    - Grille de cards avec filtres (recherche, tag, tenant)
    - Pagination et compteur de résultats
    - Bouton Subscribe/Unsubscribe inline
    - Navigation vers détail tool

  - `src/pages/AITools/ToolDetail.tsx` - Page détail d'un tool:
    - Header avec nom, méthode, version, tags
    - Onglets: Overview, Schema, Quick Start, Usage
    - Bouton Subscribe/Unsubscribe
    - Affichage statistiques d'usage

  - `src/pages/AITools/MySubscriptions.tsx` - Gestion des souscriptions:
    - Tableau des tools souscrits
    - Statut, usage count, date de souscription
    - Actions: voir détail, unsubscribe

  - `src/pages/AITools/UsageDashboard.tsx` - Dashboard métriques:
    - Stats cards: Total Calls, Success Rate, Avg Latency, Cost
    - Graphiques temporels (UsageChart)
    - Tableau breakdown par tool
    - Sélecteur de période (day, week, month)

  - `src/components/tools/ToolCard.tsx` - Card tool pour le catalogue:
    - Affichage: nom, description, méthode, tags, params count
    - Indicateur API-backed, tenant info
    - Bouton Subscribe

  - `src/components/tools/ToolSchemaViewer.tsx` - Visualisation JSON Schema:
    - Affichage hiérarchique des propriétés
    - Types colorés, badges required
    - Enum, default values
    - Mode expandable pour objets/arrays

  - `src/components/tools/QuickStartGuide.tsx` - Guide d'intégration:
    - Onglets: Claude Desktop, Python SDK, cURL
    - Code snippets avec bouton Copy
    - Génération automatique des exemples d'arguments

  - `src/components/tools/UsageChart.tsx` - Graphiques d'usage:
    - Bar chart simple avec hover tooltips
    - Indicateur de tendance
    - UsageStatsCard pour métriques clés

  - `src/services/mcpGatewayApi.ts` - Client API MCP Gateway:
    - Méthodes: getTools, getTool, getToolTags
    - Subscriptions: getMySubscriptions, subscribeTool, unsubscribeTool
    - Usage: getMyUsage, getToolUsage, getUsageHistory
    - Server info et health check

  - `src/types/index.ts` - Types TypeScript ajoutés:
    - MCPTool, ToolInputSchema, ToolPropertySchema
    - ListToolsResponse, ToolUsageStats, ToolUsageSummary
    - ToolSubscription, ToolSubscriptionCreate

  - **Navigation et routes** (`src/App.tsx`, `src/components/Layout.tsx`):
    - Menu "AI Tools" avec icône Wrench
    - Routes: /ai-tools, /ai-tools/:toolName, /ai-tools/subscriptions, /ai-tools/usage
    - QuickActionCard sur Dashboard

  - **Configuration** (`src/config.ts`):
    - `services.mcpGateway.url` (VITE_MCP_GATEWAY_URL)
    - `features.enableAITools` (VITE_ENABLE_AI_TOOLS)

  - **Tests** (vitest + @testing-library/react):
    - `src/components/tools/ToolCard.test.tsx` - 12 tests
    - `src/components/tools/ToolSchemaViewer.test.tsx` - 10 tests
    - `src/services/mcpGatewayApi.test.ts` - 15 tests
    - Setup: vitest.config.ts, test/setup.ts, test/mocks.ts

  - **Dépendances dev ajoutées**:
    - vitest, @testing-library/react, @testing-library/jest-dom
    - @testing-library/user-event, jsdom

### Ajouté (2026-01-04) - CAB-121 Tool Registry CRDs Kubernetes

- **STOA MCP Gateway - Kubernetes CRDs pour Tool Registry**
  - `charts/stoa-platform/crds/tool-crd.yaml` - CRD Tool:
    - Kind: `Tool`, API Group: `stoa.cab-i.com/v1alpha1`
    - Spec: displayName, description, endpoint, method, inputSchema, tags
    - Authentication: type (none/apiKey/bearer/oauth2), secretRef
    - Status subresource: phase, invocationCount, errorCount, conditions
    - Printer columns pour `kubectl get tools`

  - `charts/stoa-platform/crds/toolset-crd.yaml` - CRD ToolSet:
    - Kind: `ToolSet`, génère plusieurs tools depuis OpenAPI spec
    - Sources: url, configMapRef, secretRef, inline
    - Selector: filtrage par tags, operationIds, methods
    - toolDefaults: valeurs par défaut pour tous les tools générés

  - `src/k8s/models.py` - Modèles Pydantic pour les CRDs:
    - `ToolCR`, `ToolCRSpec`, `ToolCRStatus`, `ToolCRAuthentication`
    - `ToolSetCR`, `ToolSetCRSpec`, `OpenAPISource`, `ToolSelector`
    - Validation complète des specs

  - `src/k8s/watcher.py` - Kubernetes Watcher async:
    - `ToolWatcher`: watch des CRDs Tool et ToolSet
    - Callbacks: on_added, on_removed, on_modified
    - Conversion CRD → Tool interne
    - Support multi-namespace ou namespace unique
    - Graceful degradation si kubernetes-asyncio non installé
    - Watch restart automatique avec backoff

  - `charts/stoa-platform/templates/mcp-gateway-rbac.yaml`:
    - ServiceAccount, ClusterRole, RoleBinding
    - Permissions: get, list, watch sur tools, toolsets
    - Permissions: patch, update sur status subresource

  - `charts/stoa-platform/templates/mcp-gateway-deployment.yaml`:
    - Deployment Helm complet pour MCP Gateway
    - Toutes les variables d'environnement configurables
    - Liveness/readiness probes

  - `charts/stoa-platform/values/mcp-gateway.yaml`:
    - Configuration par défaut MCP Gateway
    - Exemples CRDs commentés

  - `tests/test_k8s.py` - 24 tests:
    - Tests models: ToolCR, ToolCRSpec, ToolSetCR
    - Tests watcher: callbacks, tool name generation, event handling
    - Tests singleton pattern
    - Tests intégration OpenAPI converter

  - **Configuration ajoutée** (`src/config/settings.py`):
    - `k8s_watcher_enabled`: bool (default: False)
    - `k8s_watch_namespace`: str | None (default: None = all namespaces)
    - `kubeconfig_path`: str | None (default: None = in-cluster config)

  - **Dépendance optionnelle**: `kubernetes-asyncio>=29.0.0`, `pyyaml>=6.0`
    - Installation: `pip install stoa-mcp-gateway[k8s]`

  - **Métriques**: 196 tests, 79% coverage global
    - k8s/models.py: 100% coverage
    - k8s/watcher.py: 45% coverage (code async difficile à tester)

### Ajouté (2026-01-04) - CAB-123 Metering Pipeline (Kafka)

- **STOA MCP Gateway - Metering Pipeline**
  - `src/metering/models.py` - Schéma d'événements de metering:
    - `MeteringEvent`: tenant, project, consumer, user_id, tool, latency_ms, status, cost_units
    - `MeteringStatus`: success, error, timeout, rate_limited, unauthorized
    - `MeteringEventBatch`: Lot d'événements pour traitement bulk
    - Méthodes: `to_kafka_message()`, `from_tool_invocation()`, `_compute_cost()`
    - Pricing model: base cost + latency cost + premium tools

  - `src/metering/producer.py` - Producer Kafka async:
    - `MeteringProducer`: Client aiokafka avec buffering
    - Double mode: emit (buffered) vs emit_immediate (direct)
    - Flush périodique (5s) et flush on buffer full (100 events)
    - Graceful degradation si Kafka indisponible
    - Compression gzip, idempotence, partition par tenant

  - **Intégration dans handlers MCP** (`src/handlers/mcp.py`):
    - Metering automatique sur chaque invocation de tool
    - Capture: latency_ms, status, consumer (header X-Consumer-ID)
    - Emission même pour les erreurs (403, timeout, etc.)
    - Fire-and-forget (ne bloque pas la requête)

  - `tests/test_metering.py` - 23 tests:
    - Tests MeteringEvent: création, serialization, cost computation
    - Tests MeteringProducer: buffering, flush, graceful failure
    - Tests singleton pattern
    - Tests intégration avec Kafka mocké

  - **Configuration ajoutée** (`src/config/settings.py`):
    - `metering_enabled`: bool (default: True)
    - `kafka_bootstrap_servers`: str (default: localhost:9092)
    - `metering_topic`: str (default: stoa.metering.events)
    - `metering_buffer_size`: int (default: 100)
    - `metering_flush_interval`: float (default: 5.0s)

  - **Dépendance**: aiokafka>=0.10.0 ajouté à pyproject.toml

  - **Métriques**: 172 tests, 85% coverage global
    - metering/models.py: 100% coverage
    - metering/producer.py: 69% coverage

- **Renommage**: `stoa-mcp-gateway/` → `mcp-gateway/`

### Ajouté (2026-01-04) - CAB-122 OPA Policy Engine Integration

- **STOA MCP Gateway - OPA Policy Engine**
  - `src/policy/opa_client.py` - Client OPA avec double mode:
    - Mode embedded (MVP): Évaluation Python des règles (pas de sidecar)
    - Mode sidecar (production): Requêtes HTTP vers OPA
    - Fail-open pour haute disponibilité

  - `src/policy/policies/authz.rego` - Règles d'autorisation Rego:
    - Classification des tools: read_only, write, admin
    - Mapping rôles → scopes (cpi-admin, tenant-admin, devops, viewer)
    - Isolation multi-tenant
    - Gestion des tools dynamiques

  - `src/policy/policies/tools.rego` - Règles spécifiques aux tools:
    - Rate limiting par rôle
    - Restrictions environnement production
    - Confirmation pour actions destructives

  - `tests/test_opa_policy.py` - 31 tests pour le policy engine:
    - Tests EmbeddedEvaluator: scopes, authz, tenant isolation, dynamic tools
    - Tests OPAClient: embedded, sidecar, fail-open
    - Tests singleton pattern

  - **Intégration dans handlers MCP**:
    - Policy check avant invocation de tool
    - Construction user_claims depuis TokenClaims
    - Erreur 403 si policy denied

  - **Docker Compose**: OPA sidecar ajouté (openpolicyagent/opa:0.60.0)

  - **Métriques**: 149 tests, 86% coverage global
    - opa_client.py: 93% coverage

### Ajouté (2026-01-04) - CAB-199 MCP Gateway Tests & Tools Implementation

- **STOA MCP Gateway - Tests complets et outils additionnels**
  - `tests/test_tool_registry.py` - 46 tests pour le registre de tools
    - Tests basic: register, unregister, get, overwrite
    - Tests list: filter by tenant, by tag, pagination
    - Tests lifecycle: startup, shutdown, HTTP client
    - Tests invocation: builtin tools, API-backed tools, error handling
    - Tests HTTP methods: GET, POST, PUT, DELETE, PATCH
    - Tests singleton pattern
    - Tests nouveaux outils built-in

  - `tests/test_openapi_converter.py` - 30 tests pour la conversion OpenAPI
    - Tests basic: empty spec, single/multiple operations
    - Tests conversion: operationId, name generation, description
    - Tests parameters: query, path, enum, required
    - Tests request body: properties extraction
    - Tests base URL: OpenAPI 3.x, Swagger 2.0, override
    - Tests metadata: api_id, tenant_id, version
    - Tests edge cases: $ref, missing schema, non-dict paths

  - `tests/test_mcp.py` - 25 tests pour les handlers MCP
    - Tests server info, tools, resources, prompts endpoints
    - Tests pagination et filtres
    - Tests authentication avec dependency override
    - Tests response format (camelCase aliases)

  - `src/services/openapi_converter.py` - Convertisseur OpenAPI → MCP Tools
    - Support OpenAPI 3.0.x, 3.1.x et Swagger 2.0
    - Extraction des paramètres (path, query, header)
    - Extraction du request body (JSON)
    - Génération automatique du nom si pas d'operationId
    - Sanitization des noms pour compatibilité MCP
    - Métadonnées STOA (api_id, tenant_id, base_url)

  - **Nouveaux outils built-in** ajoutés au registre:
    - `stoa_health_check` - Vérification santé des services (api, gateway, auth)
    - `stoa_list_tools` - Liste des outils disponibles avec filtrage par tag
    - `stoa_get_tool_schema` - Récupération du schema d'un outil
    - `stoa_search_apis` - Recherche d'APIs par mot-clé (placeholder)

  - **Améliorations tool_registry.py**:
    - Support méthode HTTP PATCH
    - 7 outils built-in au total
    - Méthodes helper: `_check_health()`, `_get_tools_info()`, `_get_tool_schema()`

  - **Métriques**: 118 tests, 85% coverage global
    - tool_registry.py: 96% coverage
    - openapi_converter.py: 91% coverage
    - mcp.py (handlers): 98% coverage
    - models/mcp.py: 100% coverage

### Ajouté (2026-01-03) - CAB-120 MCP Gateway Auth + MCP Base

- **STOA MCP Gateway - Phase 2** - Auth + MCP Base
  - `stoa-mcp-gateway/src/middleware/auth.py` - Middleware OIDC Keycloak complet
    - Validation JWT avec cache JWKS (TTL 5 min)
    - Modèle `TokenClaims` avec helpers `has_role()`, `has_scope()`
    - Dependencies FastAPI: `get_current_user`, `get_optional_user`
    - Factories: `require_role()`, `require_scope()` pour contrôle d'accès
    - Support Bearer token + API Key (M2M)

  - `stoa-mcp-gateway/src/handlers/mcp.py` - Handlers MCP Protocol
    - `GET /mcp/v1/` - Server info et capabilities
    - `GET /mcp/v1/tools` - Liste des tools avec pagination
    - `GET /mcp/v1/tools/{name}` - Détails d'un tool
    - `POST /mcp/v1/tools/{name}/invoke` - Invocation (auth requise)
    - `GET /mcp/v1/resources` - Liste des resources
    - `GET /mcp/v1/prompts` - Liste des prompts

  - `stoa-mcp-gateway/src/models/mcp.py` - Modèles Pydantic MCP spec
    - `Tool`, `ToolInvocation`, `ToolResult` avec extensions STOA
    - `Resource`, `ResourceReference`, `ResourceContentRead`
    - `Prompt`, `PromptArgument`, `PromptMessage`
    - Responses: `ListToolsResponse`, `InvokeToolResponse`, etc.

  - `stoa-mcp-gateway/src/services/tool_registry.py` - Registre des tools
    - Enregistrement dynamique de tools
    - Tools built-in: `stoa_platform_info`, `stoa_list_apis`, `stoa_get_api_details`
    - Invocation avec passage de token utilisateur
    - Support backends HTTP (GET/POST/PUT/DELETE)

  - `stoa-mcp-gateway/src/middleware/metrics.py` - Métriques Prometheus
    - HTTP: requests total, duration, in-progress
    - MCP: tool invocations, duration par tool
    - Auth: attempts, token validation duration
    - Backend: requests par backend/method/status

  - `stoa-mcp-gateway/docker-compose.yml` - Stack développement local
    - MCP Gateway avec hot-reload (Dockerfile.dev)
    - Keycloak avec realm `stoa` pré-configuré
    - Prometheus (port 9090)
    - Grafana (port 3000, admin/admin)

  - `stoa-mcp-gateway/dev/keycloak/stoa-realm.json` - Realm Keycloak
    - Rôles: `cpi-admin`, `tenant-admin`, `devops`, `viewer`
    - Clients: `stoa-mcp-gateway`, `stoa-test-client`
    - Users de test: admin, tenant-admin, devops, viewer

  - **Tests**: 25 tests, 71% coverage
    - `tests/test_auth.py` - TokenClaims, OIDCAuthenticator
    - `tests/test_mcp.py` - Endpoints MCP
    - `tests/test_health.py` - Health checks

### Modifié (2025-01-03) - Rebranding APIM → STOA

- **Renommage complet du projet** - APIM Platform devient STOA Platform
  - Repository GitHub: `apim-aws` → `stoa`
  - Repository GitLab: `apim-gitops` → `stoa-gitops` (cab6961310/stoa-gitops)
  - Domaine: `apim.cab-i.com` → `stoa.cab-i.com`
  - Namespace Kubernetes: `apim-system` → `stoa-system`
  - Keycloak realm: `apim` → `stoa`
  - Helm chart: `apim-platform` → `stoa-platform`
  - Vault paths: `secret/apim/*` → `secret/stoa/*`
  - AWS resources: `apim-*` → `stoa-*`

- **72 fichiers modifiés** pour le rebranding:
  - Documentation (README, CHANGELOG, docs/*)
  - Configuration (deploy/config/*.env)
  - Python API (control-plane-api/)
  - React UI (control-plane-ui/)
  - Ansible playbooks et vars
  - GitOps templates
  - Helm charts et K8s manifests
  - Scripts
  - Terraform modules

- **Repo GitLab stoa-gitops initialisé**
  - Structure: environments/{dev,staging,prod}, tenants/, argocd/
  - ArgoCD ApplicationSets configurés
  - URL: https://gitlab.com/cab6961310/stoa-gitops

- **Migration infrastructure AWS complète**
  - DNS: `*.stoa.cab-i.com` configuré (Hostpapa CNAME)
  - Certificats TLS Let's Encrypt générés pour tous les sous-domaines
  - Ingresses Kubernetes mis à jour (api, devops, auth, gateway, awx)
  - Keycloak: hostname corrigé dans les args du deployment
  - AWX: CRD mis à jour avec nouveau hostname
  - Control-Plane UI: rebuildée avec nouvelles URLs

- **Suppression du hardcoding des URLs**
  - Ansible playbooks: utilisation de `{{ base_domain | default('stoa.cab-i.com') }}`
  - Scripts: utilisation de variables d'environnement avec fallback
  - Configuration centralisée dans `ansible/vars/platform-config.yaml`

- **Architecture de configuration centralisée**
  - `BASE_DOMAIN` comme source unique de vérité pour le domaine
  - Fichiers .env avec variables dérivées: `${BASE_DOMAIN}` → sous-domaines
  - Permet déploiement chez un client en changeant une seule variable
  - Structure:
    - `deploy/config/{dev,staging,prod}.env` - Configuration par environnement
    - `control-plane-api/src/config.py` - Config Python avec fallback BASE_DOMAIN
    - `control-plane-ui/src/config.ts` - Config TypeScript avec Vite env vars
    - `ansible/vars/platform-config.yaml` - Config Ansible centralisée
    - `gitops-templates/_defaults.yaml` - Defaults GitOps avec interpolation

### Supprimé (2024-12-23) - Retrait webMethods Developer Portal

- **webMethods Developer Portal** - Supprimé de l'architecture
  - Licence trial IBM demandée uniquement pour Gateway (sans Portal)
  - Developer Portal custom React prévu en Phase 8
  - Playbook `promote-portal.yaml` supprimé
  - Références au portal retirées de la documentation
  - Handler `_handle_promote_request` supprimé du deployment_worker

### Ajouté (2025-12-23) - Phase 3: Secrets & Gateway Alias - COMPLÉTÉ ✅

- **HashiCorp Vault** - Déployé sur EKS pour gestion centralisée des secrets
  - Helm chart `hashicorp/vault` v0.31.0 (Vault 1.20.4)
  - Namespace: `vault`
  - Storage: 5GB PVC (gp2)
  - UI accessible: https://vault.stoa.cab-i.com
  - Clés unseal sauvegardées dans AWS Secrets Manager (`stoa/vault/keys`)

- **Vault Secrets Engine** - KV v2 pour secrets APIM
  - Path: `secret/stoa/{env}/{type}`
  - Structure:
    - `secret/stoa/dev/gateway-admin` - Credentials Gateway admin
    - `secret/stoa/dev/keycloak-admin` - Credentials Keycloak admin
    - `secret/stoa/dev/awx-automation` - Client credentials AWX
    - `secret/stoa/dev/aliases/*` - Backend aliases avec credentials

- **Vault Kubernetes Auth** - Authentification native K8s
  - Roles: `stoa-apps` (lecture), `awx-admin` (lecture/écriture)
  - Service accounts: `control-plane-api`, `awx-web`, `awx-task`
  - Policies: `stoa-read`, `stoa-admin`

- **Playbook sync-alias.yaml** - Synchronisation aliases Vault → Gateway
  - Lecture des aliases depuis Vault
  - Création/mise à jour dans webMethods Gateway
  - Support authentification: Basic Auth, API Key, OAuth2
  - Mode dry-run pour preview

- **Playbook rotate-credentials.yaml** - Rotation automatique des credentials
  - Types supportés: password, api_key, oauth_client
  - Mise à jour Vault + Gateway Alias en une opération
  - Rotation client secret Keycloak pour OAuth
  - Callback de notification vers Control-Plane API

- **AWX Job Templates** - Nouveaux templates Phase 3
  - `Sync Gateway Aliases` (ID: 15) - sync-alias.yaml
  - `Rotate Credentials` (ID: 16) - rotate-credentials.yaml

### Corrigé (2024-12-23) - OpenAPI 3.1.0 → 3.0.0 Conversion

- **OpenAPI Version Compatibility** - webMethods Gateway 10.15 ne supporte pas OpenAPI 3.1.0
  - `deploy-api.yaml`: Détection automatique de la version OpenAPI
  - Conversion 3.1.x → 3.0.0 avant import dans Gateway
  - Support swagger 2.0 et OpenAPI 3.0.x natifs
  - Détection type API (`swagger` vs `openapi`) dans le playbook

- **Gateway Proxy Response Format** - Gestion des deux formats de réponse
  - Proxy Control-Plane API retourne `{"api_id": "..."}`
  - Gateway direct retourne `{"apiResponse": {"api": {"id": "..."}}}`
  - Variable `imported_api_id` extraite pour compatibilité
  - Variable `final_api_id` pour affichage unifié

- **POST /v1/gateway/apis** - Nouvel endpoint pour import API via proxy
  - `control-plane-api/src/routers/gateway.py`: Route POST /apis
  - `control-plane-api/src/services/gateway_service.py`: Méthode `import_api()`
  - Support `apiDefinition` comme objet JSON (pas string)
  - Support paramètre `type` (openapi, swagger, raml, wsdl)

- **AWX Job Template Deploy API** - Flux E2E validé
  - Import API avec spec OpenAPI 3.1.0 (convertie en 3.0.0)
  - Activation automatique de l'API après import
  - Notification vers Control-Plane API
  - Test validé: Control-Plane-API-E2E v2.2 (ID: 4b4045ba-23f3-4a45-ad38-680419d79880)

### Corrigé (2024-12-22) - Pipeline E2E Kafka → AWX

- **AWX Token** - Configuration et persistence
  - Token API créé et sauvegardé dans AWS Secrets Manager (`stoa/awx-token`)
  - Variable `AWX_TOKEN` configurée sur deployment control-plane-api

- **Noms Job Templates AWX** - Alignement code/AWX
  - `awx_service.py`: `deploy-api` → `Deploy API`, `rollback-api` → `Rollback API`
  - `deployment_worker.py`: `promote-portal` → `Promote Portal`, `sync-gateway` → `Sync Gateway`

- **Playbooks manquants GitLab** - Push vers stoa-gitops
  - `deploy-api.yaml` - Déploiement API dans Gateway
  - `rollback.yaml` - Rollback/désactivation API
  - `sync-gateway.yaml` - Synchronisation Gateway
  - `promote-portal.yaml` - Publication API sur Gateway

- **Kafka Snappy Compression** - Support codec snappy
  - Ajout `python-snappy==0.7.3` dans requirements.txt
  - Ajout `libsnappy-dev` dans Dockerfile

- **GitLab Atomic Commits** - Fix race condition
  - `git_service.py`: Utilisation `commits.create()` API pour commits atomiques
  - Évite erreur `reference does not point to expected object`

- **AWX Project Sync** - Job templates mis à jour
  - Tous templates (Deploy API, Rollback API, Sync Gateway, Promote Portal)
    pointent vers projet 7 "APIM Playbooks" avec playbooks corrects

- **Pipeline Deploy API** - Flux Kafka → AWX → Gateway fonctionnel
  - `deploy-api.yaml`: Fix variables récursives Ansible (`_gateway_url` vs `gw_url`)
  - `deploy-api.yaml`: Ajout credentials par défaut (évite `vars_files` manquants dans AWX)
  - `awx_service.py`: Ajout paramètre `openapi_spec` dans `deploy_api()`
  - `deployment_worker.py`: Transmission `openapi_spec` vers AWX extra_vars
  - `events.py`: Endpoint `POST /v1/events/deployment-result` pour callbacks AWX
  - Test validé: PetstoreAPI v3.0.0 déployé et activé via pipeline

- **Playbooks OIDC** - Migration vers authentification OIDC via proxy Gateway-Admin-API
  - Tous playbooks supportent 2 modes: OIDC (recommandé) et Basic Auth (fallback)
  - URLs HTTPS externes: `https://auth.stoa.cab-i.com`, `https://api.stoa.cab-i.com/v1/gateway`
  - Client service account `awx-automation` pour AWX
  - Playbooks mis à jour: `deploy-api.yaml`, `rollback.yaml`, `sync-gateway.yaml`, `promote-portal.yaml`
  - `bootstrap-platform.yaml`: Création automatique du client Keycloak `awx-automation`

### Ajouté (Phase 2.5) - Validation E2E - COMPLÉTÉ ✅

- **Gateway OIDC Configuration** - Sécurisation APIs via Keycloak
  - External Authorization Server `KeycloakOIDC` configuré dans Gateway
  - OAuth2 Strategies par application avec JWT validation
  - Scope mappings standardisés: `{AuthServer}:{Tenant}:{Api}:{Version}:{Scope}`
  - APIs sécurisées:
    - Control-Plane-API (ID: `7ba67c90-814d-4d2f-a5da-36e9cda77afe`)
    - Gateway-Admin-API (ID: `8f9c7b6c-1bc6-4438-88be-a10e2352bae2`) - Proxy admin

- **Gateway Admin Service** - Proxy OIDC pour administration Gateway
  - `control-plane-api/src/services/gateway_service.py` - Service dual-mode auth
  - `control-plane-api/src/routers/gateway.py` - Router `/v1/gateway/*`
  - Token forwarding: JWT utilisateur transmis à Gateway (audit trail)
  - Fallback Basic Auth pour compatibilité legacy
  - Config: `GATEWAY_USE_OIDC_PROXY=True` (défaut)

- **Sécurisation des Secrets** - AWS Secrets Manager + K8s
  - `ansible/vars/secrets.yaml` - Configuration centralisée (zéro hardcoding)
  - `terraform/modules/secrets/main.tf` - Module AWS Secrets Manager
  - Stratégie documentée:
    - **AWS Secrets Manager**: Secrets bootstrap (gateway-admin, keycloak-admin, rds-master, etc.)
    - **K8s Secrets / Vault**: Secrets runtime (OAuth clients, tokens tenants)
  - Chemins AWS SM: `stoa/{env}/gateway-admin`, `stoa/{env}/keycloak-admin`, etc.
  - Tous playbooks Ansible mis à jour avec `vars_files: ../vars/secrets.yaml`

- **Tenant STOA Platform** - Tenant administrateur avec accès cross-tenant
  - Fichier: `tenants/stoa/` dans GitLab stoa-gitops
  - User: `stoaadmin@cab-i.com` (role: cpi-admin)
  - API: Control-Plane configurée pour Gateway OIDC

- **Playbooks Ansible** - Automation complète
  - `bootstrap-platform.yaml` - **Initialisation plateforme** (KeycloakOIDC + APIs bootstrap)
  - `provision-tenant.yaml` - Crée groupes Keycloak, users, namespaces K8s
  - `register-api-gateway.yaml` - Import OpenAPI, OIDC, rate limiting, activation
  - `configure-gateway-oidc.yaml` - Configuration OIDC complète
  - `configure-gateway-oidc-tasks.yaml` - Tâches réutilisables avec scope naming
  - `tasks/create-keycloak-user.yaml` - Création user avec roles
  - Playbooks existants sécurisés: `deploy-api`, `sync-gateway`, `promote-portal`, `rollback`

- **Gateway-Admin API** - Spec OpenAPI pour proxy admin
  - `apis/gateway-admin-api/openapi.json` - Spec OpenAPI 3.0.3
  - Endpoints: `/apis`, `/applications`, `/scopes`, `/alias`, `/configure-oidc`, `/health`
  - Sécurisé via JWT Keycloak (BearerAuth)
  - Backend: proxy vers `apigateway:5555/rest/apigateway`

- **AWX Job Templates** - Nouveaux templates
  - `Provision Tenant` (ID: 12) - Provisioning tenant complet
  - `Register API Gateway` (ID: 13) - Enregistrement API dans Gateway

- **Control-Plane API** - Nouveaux handlers et services
  - Router `/v1/gateway/*` - Administration Gateway via OIDC proxy
  - Endpoints: `GET /apis`, `PUT /apis/{id}/activate`, `POST /configure-oidc`, etc.
  - Event `tenant-provisioning` → AWX Provision Tenant
  - Event `api-registration` → AWX Register API Gateway
  - `gateway_service`: `list_apis()`, `activate_api()`, `configure_api_oidc()`, etc.
  - `awx_service`: `provision_tenant()`, `register_api_gateway()`

- **Architecture clarifiée**
  - GitHub (stoa): Code source, développement, CI/CD
  - GitLab (stoa-gitops): Runtime data, tenants, playbooks AWX

### Ajouté (Phase 2) - COMPLÉTÉ
- **GitOps Templates** (`gitops-templates/`) - Modèles pour initialiser GitLab
  - `_defaults.yaml` - Variables globales par défaut
  - `environments/{dev,staging,prod}/config.yaml` - Config par environnement
  - `templates/` - Templates API, Application, Tenant
  - **Note**: Les données tenants sont sur GitLab, pas ici

- **Variable Resolver Service** - Résolution de placeholders `${VAR}` et `${VAR:default}`
  - Support des références Vault: `vault:secret/path#key`
  - Merge de configs: global → env → tenant → inline defaults
  - Validation des variables requises

- **IAM Sync Service** - Synchronisation GitOps ↔ Keycloak
  - Sync groupes/utilisateurs par tenant
  - Création clients OAuth2 pour applications
  - Réconciliation et détection de drift
  - Rotation des secrets clients

- **Routers GitOps-Enabled**
  - APIs router: CRUD via GitLab + events Kafka
  - Tenants router: Multi-tenant avec RBAC

- **ArgoCD** - GitOps Continuous Delivery
  - Chart Helm avec SSO Keycloak
  - ApplicationSets pour multi-tenant auto-discovery
  - AppProjects avec RBAC par tenant
  - Scripts d'installation: `scripts/install-argocd.sh`
  - URL: https://argocd.stoa.cab-i.com

- **Script Init GitLab** - `scripts/init-gitlab-gitops.sh`
  - Initialise le repo GitLab stoa-gitops
  - Copie les templates et configurations

- **GitLab stoa-gitops** - Repository configuré
  - URL: https://gitlab.com/cab6961310/stoa-gitops
  - Structure: `_defaults.yaml`, `environments/`, `tenants/`
  - Connecté à ArgoCD pour GitOps

---

## [2.0.0] - 2024-12-21

### Phase 1: Event-Driven Architecture - COMPLÉTÉ

#### Ajouté
- **Redpanda (Kafka)** - Event streaming compatible Kafka
  - 1 broker sur EKS avec Redpanda Console
  - Storage: 10GB persistant (EBS gp2)
  - Topics: `api-created`, `api-updated`, `api-deleted`, `deploy-requests`, `deploy-results`, `audit-log`, `notifications`

- **AWX (Ansible Tower)** - Automation
  - AWX 24.6.1 via AWX Operator 2.19.1
  - URL: https://awx.stoa.cab-i.com
  - Job Templates: Deploy API, Sync Gateway, Promote Portal, Rollback API

- **Control-Plane UI** - Interface React
  - Authentification Keycloak avec PKCE (Keycloak 25+)
  - Pages: Dashboard, Tenants, APIs, Applications, Deployments, Monitoring
  - URL: https://console.stoa.cab-i.com

- **Control-Plane API** - Backend FastAPI
  - Kafka Producer intégré (events sur CRUD)
  - Deployment Worker (consumer `deploy-requests`)
  - Webhook GitLab (Push, MR, Tag Push)
  - Pipeline Traces (in-memory store)
  - URL: https://api.stoa.cab-i.com

- **Configuration Variabilisée**
  - UI: Variables `VITE_*` pour build-time config
  - API: Variables d'environnement via pydantic-settings
  - Dockerfiles avec build args pour personnalisation

#### Modifié
- Infrastructure: 3x t3.large (2 CPU / 8GB RAM) pour supporter Redpanda + AWX
- Keycloak: Realm `stoa`, clients `control-plane-ui` et `control-plane-api`

#### Corrigé
- Authentification PKCE - `response_type: 'code'` + `pkce_method: 'S256'`
- URLs Keycloak - `auth.stoa.cab-i.com` au lieu de `keycloak.dev.stoa.cab-i.com`
- OpenAPI Tags - Harmonisation casse (`Traces` au lieu de `traces`)

---

## [1.0.0] - 2024-12-XX

### Infrastructure initiale

#### Ajouté
- **AWS Infrastructure** (Terraform)
  - VPC avec subnets publics/privés
  - EKS Cluster `stoa-dev-cluster`
  - RDS PostgreSQL (db.t3.micro)
  - ECR Repositories

- **Kubernetes**
  - Nginx Ingress Controller
  - Cert-Manager (Let's Encrypt)
  - EBS CSI Driver

- **webMethods**
  - API Gateway (lean trial 10.15)
  - Elasticsearch 8.11 (pour Gateway)

- **Keycloak** - Identity Provider
  - URL: https://auth.stoa.cab-i.com
  - Realm: `stoa`

---

## Roadmap

### Phase 2: GitOps + ArgoCD (Priorité Haute) - COMPLÉTÉ ✅
- [x] Structure GitOps par tenant (`gitops-templates/`)
- [x] Variable Resolver (templates avec placeholders `${VAR}`)
- [x] IAM Sync Service (Git → Keycloak)
- [x] Routers API/Tenants avec intégration GitLab
- [x] ArgoCD Helm chart avec SSO Keycloak
- [x] ApplicationSets multi-tenant
- [x] Installation ArgoCD sur EKS
- [x] Repository GitLab `stoa-gitops` configuré

### Phase 2.5: Validation E2E - COMPLÉTÉ ✅
- [x] Playbook provision-tenant.yaml (Keycloak + K8s namespaces)
- [x] Playbook register-api-gateway.yaml (Gateway OIDC)
- [x] AWX Job Templates (Provision Tenant, Register API Gateway)
- [x] Tenant stoa dans GitLab avec STOAAdmin
- [x] Control-Plane API handlers (tenant-provisioning, api-registration)
- [x] User stoaadmin@cab-i.com créé avec rôle cpi-admin
- [x] Architecture GitHub/GitLab documentée

### Phase 3: Secrets & Gateway Alias - COMPLÉTÉ ✅
- [x] HashiCorp Vault déployé sur EKS
- [x] Vault KV v2 avec structure secrets APIM
- [x] Kubernetes auth configuré (roles, policies)
- [x] Playbook sync-alias.yaml pour Gateway Alias
- [x] Playbook rotate-credentials.yaml pour rotation secrets
- [x] Jobs AWX: Sync Gateway Aliases, Rotate Credentials
- [ ] Intégration External Secrets Operator (optionnel - future)
- [ ] Auto-unseal avec AWS KMS (optionnel - future)

### Phase 2.6: Cilium Network Foundation (Priorité Moyenne)
- [ ] Installer Cilium sur EKS (remplace AWS VPC CNI + kube-proxy)
- [ ] Gateway API CRDs + GatewayClass Cilium
- [ ] Migrer Nginx Ingress → Gateway API (*.stoa.cab-i.com)
- [ ] CiliumNetworkPolicy - Default deny + tenant isolation
- [ ] Hubble - Observabilité réseau
- [ ] Documentation migration Cilium & runbooks

### Phase 4: Observabilité (Priorité Moyenne)
- [ ] Amazon OpenSearch
- [ ] FluentBit (log shipping)
- [ ] Prometheus + Grafana
- [ ] OpenSearch Dashboards

### Phase 5: Multi-Environment (Priorité Basse)
- [ ] Environnement STAGING
- [ ] Promotion DEV → STAGING → PROD

### Phase 6: Beta Testing (Priorité Basse)
- [ ] Tenant démo
- [ ] Documentation utilisateur (MkDocs)

### Phase 7: Sécurité Opérationnelle (Priorité Basse)
- [ ] Job 1: Certificate Checker (expiration TLS, Vault PKI, endpoints)
- [ ] Job 2: Secret Rotation (API Keys, OAuth, DB passwords via Vault)
- [ ] Job 3: Usage Reporting (métriques par tenant, PDF, email)
- [ ] Job 4: GitLab Security Scan (Gitleaks, Semgrep, Trivy)
- [ ] NotificationService (Email, Slack, PagerDuty)
- [ ] CronJobs Kubernetes (Helm chart)
- [ ] Intégration GitLab CI/CD (security-scan stage)
- [ ] Monitoring Jobs (Prometheus, Kafka, OpenSearch, Grafana Dashboard)
- [ ] Alertes (job failed, job not running, critical findings)

### Phase 8: Developer Portal Custom (Priorité Basse)
- [ ] Frontend React + TypeScript + Vite + TailwindCSS
- [ ] Keycloak SSO (client `developer-portal`)
- [ ] Catalogue APIs avec recherche/filtres
- [ ] Détail API + Swagger-UI
- [ ] Gestion Applications (CRUD, credentials, rotation API Key)
- [ ] Gestion Souscriptions
- [ ] Try-It Console (Monaco Editor, proxy backend)
- [ ] Code Samples (curl, Python, JavaScript)
- [ ] Endpoints `/portal/*` dans Control-Plane API
- [ ] Events Kafka (application-created, subscription-created)
- [ ] Déploiement Kubernetes
- [ ] Plan détaillé: [docs/DEVELOPER-PORTAL-PLAN.md](docs/DEVELOPER-PORTAL-PLAN.md)

### Phase 9: Ticketing - Demandes de Production (Priorité Basse)
- [ ] Modèle PromotionRequest (YAML dans Git)
- [ ] Workflow: PENDING → APPROVED → DEPLOYING → DEPLOYED
- [ ] RBAC: DevOps crée, CPI approuve
- [ ] Règle anti-self-approval
- [ ] Endpoints CRUD `/v1/requests/prod`
- [ ] Trigger AWX automatique sur approbation
- [ ] Webhook callback AWX → update status
- [ ] UI: Liste demandes, formulaire, détail, timeline
- [ ] Events Kafka (request-created, approved, rejected, deployed, failed)
- [ ] Notifications Email + Slack
- [ ] Plan détaillé: [docs/TICKETING-SYSTEM-PLAN.md](docs/TICKETING-SYSTEM-PLAN.md)

### Phase 4.5: Jenkins Orchestration Layer (Priorité Haute - Enterprise)
- [ ] Jenkins déployé sur EKS (Helm jenkins/jenkins)
- [ ] Configuration JCasC (Jenkins Configuration as Code)
- [ ] Intégration Keycloak SSO (OIDC)
- [ ] Service Kafka Consumer → Jenkins Trigger
- [ ] Jenkinsfile `deploy-api` avec approval gates
- [ ] Jenkinsfile `rollback-api` avec emergency bypass
- [ ] Jenkinsfile `promote-api` pour promotion entre envs
- [ ] Jenkinsfile `delete-api` avec confirmation
- [ ] Shared Library (kafkaPublish, awxLaunch, notifyDeployment)
- [ ] Blue Ocean UI accessible
- [ ] Slack notifications configurées
- [ ] Dashboard métriques Jenkins
- [ ] Credentials AWX/Kafka/Keycloak dans Jenkins Credentials Store
- [ ] Backup Jenkins config (PVC + S3)

### Phase 9.5: Production Readiness (Priorité Haute - Critique)
- [ ] Script backup AWX database (PostgreSQL) → S3
- [ ] Script backup Vault snapshot → S3 + KMS
- [ ] CronJob Kubernetes pour backups quotidiens (AWX + Vault)
- [ ] Procédures de restore documentées et testées
- [ ] Pipeline Load Testing (K6 ou Gatling)
- [ ] Seuils de performance définis (p95 < 500ms, p99 < 1s)
- [ ] Runbooks opérationnels (docs/runbooks/)
  - Incident: API Gateway down
  - Incident: AWX job failure
  - Incident: Vault sealed
  - Incident: Kafka lag élevé
  - Procédure: Rollback d'urgence
  - Procédure: Scaling horizontal
  - Procédure: Rotation des secrets
- [ ] Scan OWASP ZAP sur Control Plane API et UI
- [ ] Remédiation vulnérabilités critiques
- [ ] Chaos Testing (Litmus/Chaos Mesh)
  - Pod kill (API, AWX, Vault)
  - Network latency injection
  - CPU/Memory stress
- [ ] Validation auto-healing Kubernetes
- [ ] SLO/SLA documentés
  - Availability: 99.9%
  - API Latency p95: < 500ms
  - Deployment Success Rate: > 99%
  - MTTR: < 1h pour P1
- [ ] Dashboard SLO dans Grafana
- [ ] Alertes configurées sur SLO breach

### Phase 10: Resource Lifecycle Management (Priorité Moyenne)
- [ ] Module Terraform `common_tags` avec validations
- [ ] Tags obligatoires: environment, owner, project, cost-center, ttl, created_at, auto-teardown, data-class
- [ ] Lambda `resource-cleanup` avec EventBridge schedule (cron 2h UTC)
- [ ] Notifications owner (48h → 24h → delete)
- [ ] OPA Gatekeeper policies pour Kubernetes admission control
- [ ] GitHub Actions workflow `tag-governance.yaml`
- [ ] Dashboard Grafana "Resource Lifecycle"
- [ ] Events Kafka (resource-created, resource-expiring, resource-deleted, tag-violation)
- [ ] Guardrails: TTL max 30d, exclusion prod, exclusion data-class=restricted
- [ ] Documentation tagging policy
- [ ] Alternative n8n workflow pour multi-cloud (optionnel)

### Phase 11: Resource Lifecycle Advanced (Priorité Basse)
- [ ] Système de quotas par projet (Terraform + AWS Service Quotas)
- [ ] Whitelist configuration (ARN patterns, tags critical=true)
- [ ] Destruction ordonnée (dépendances AWS: IAM → ASG → EC2 → ELB → S3 → RDS)
- [ ] API self-service TTL extension (`PATCH /v1/resources/{id}/ttl`)
- [ ] Boutons Snooze dans emails (7j, 14j)
- [ ] Limite 2 extensions max (60j total)
- [ ] Calcul coût évité (pricing AWS par instance_type)
- [ ] Dashboard Grafana "Cost Savings" (coût évité par projet)
- [ ] Métriques Prometheus (resources_deleted, cost_avoided_usd)
- [ ] n8n workflow complet avec Notion board "Resources to Delete"
- [ ] Cron horaire (au lieu de quotidien) pour pré-alertes
- [ ] Event Kafka `resource-ttl-extended`

### Phase 12: STOA MCP Gateway (Priorité Haute) - COMPLÈTE ✅
- [x] Gateway Core + Auth Keycloak (CAB-120)
  - FastAPI + OIDC middleware avec JWKS caching
  - Modèles Pydantic MCP Protocol spec
  - Tool Registry avec built-in tools
  - Prometheus metrics middleware
  - Docker Compose dev stack (Keycloak, Prometheus, Grafana)
- [x] Gateway Tests & Tools Implementation (CAB-199)
  - 118 tests, 85% coverage global
  - OpenAPI → MCP Tools converter (OpenAPI 3.x, Swagger 2.0)
  - 7 built-in tools (platform_info, list_apis, get_api_details, health_check, list_tools, get_tool_schema, search_apis)
  - Support HTTP PATCH method
- [x] OPA Policy Engine Integration (CAB-122)
  - Mode embedded (Python) + sidecar (Rego)
  - Policies: authz, tenant isolation, rate limiting
  - 31 tests, 93% coverage opa_client.py
- [x] Metering Pipeline Kafka (CAB-123)
  - MeteringEvent schema, MeteringProducer async
  - Intégration handlers MCP (fire-and-forget)
  - 23 tests, 100% coverage models
- [x] Tool Registry CRDs Kubernetes (CAB-121)
  - CRDs: Tool, ToolSet (OpenAPI → MCP tools)
  - Kubernetes watcher async avec callbacks
  - Helm templates: RBAC, Deployment
  - 24 tests, 100% coverage models
- [x] Portal Integration - Tool Catalog (CAB-124)
  - Section AI Tools dans Control Plane UI
  - Pages: ToolCatalog, ToolDetail, MySubscriptions, UsageDashboard
  - Composants: ToolCard, ToolSchemaViewer, QuickStartGuide, UsageChart
  - Service mcpGatewayApi.ts, tests vitest

### Phase 13: B2B Protocol Binders (Priorité Basse)
- [ ] EDI X12/EDIFACT support
- [ ] SWIFT messaging integration
- [ ] AS2/AS4 protocol handlers
- [ ] B2B message transformation
- [ ] Partner onboarding automation

### Phase 14: Community & Go-to-Market (Priorité Moyenne)
- [ ] GTM-01: Stratégie Open Core documentée (CAB-201)
- [ ] GTM-02: Licensing choice Apache 2.0 vs dual (CAB-202)
- [ ] GTM-03: Repository structure mono vs multi-repo (CAB-203)
- [ ] GTM-04: Documentation publique Docusaurus (CAB-204)
- [ ] GTM-05: Landing page STOA (CAB-205)
- [ ] GTM-06: Community channels Discord/GitHub (CAB-206)
- [ ] GTM-07: Roadmap publique (CAB-207)
- [ ] GTM-08: IBM Partnership positioning (CAB-208)
- [ ] GTM-09: Pricing tiers definition (CAB-209)
- [ ] GTM-10: Beta program structure (CAB-210)

---

## URLs

| Service | URL | Notes |
|---------|-----|-------|
| Control Plane UI | https://console.stoa.cab-i.com | React + Keycloak |
| Control Plane API | https://api.stoa.cab-i.com | FastAPI |
| Keycloak | https://auth.stoa.cab-i.com | Realm: stoa |
| AWX | https://awx.stoa.cab-i.com | admin/demo |
| API Gateway | https://gateway.stoa.cab-i.com | Administrator/manage |
| ArgoCD | https://argocd.stoa.cab-i.com | GitOps CD |
| Vault | https://vault.stoa.cab-i.com | Secrets Management |
