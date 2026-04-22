# REWRITE-PLAN — UI-2 : casser `services/api.ts` en core transport + clients par domaine

> **Status** : validé avec amendements 2026-04-22. Phase 2 exécutable.
> Amendements appliqués : suppression `api/index.ts` (collision `api.ts` / dossier `api/`), `http/index.ts` unique point d'export runtime (interceptors installés), passthroughs via wrappers typés (pas `bind`), `satisfies LegacyApiSurface` au lieu de `Object.keys.length`, retrait bundle-size de la DoD, comptage interfaces re-corrigé (27, pas 18).

## A. Inventaire par domaine

Source : `src/services/api.ts` (1732 LOC, classe `ApiService` avec 170 méthodes + 5 passthroughs génériques + 18 interfaces inline en bas de fichier).

### A.0 Transport / plomberie (extrait du monolithe → `http/`)

| Élément | Lignes | Rôle | Callers |
|---|---|---|---|
| `axios.create` + baseURL | 75-81 | config instance | — (interne) |
| `interceptors.request.use` (auth header) | 84-92 | bearer token | — |
| `interceptors.response.use` (401 refresh + friendly error) | 95-147 | refresh queue, error map | — |
| `setTokenRefresher`, `setAuthToken`, `getAuthToken`, `clearAuthToken` | 150-167 | state auth | `AuthContext.tsx`, `Layout.tsx`, tests |
| `get/post/put/patch/delete<T>` génériques | 171-189 | passthrough HTTP | **58 appels** dans callers + **11 services siblings** |
| `createEventSource` (SSE) | 590-594 | stream events | `useEvents.ts`, `useDeployEvents.ts` |

### A.1 Domaines métier (tableau condensé)

| # | Domaine | Méthodes | LOC estimé client | Callers uniques | Types UI-1 dispo |
|---|---|---|---|---|---|
| 1 | **session** (`/v1/me`, `/v1/environments`) | 2 | ~30 | 3 | partiel |
| 2 | **tenants** (`/v1/tenants/{id}` CRUD + CA + CSR) | 11 | ~110 | 7 | partiel |
| 3 | **apis** (`/v1/tenants/{id}/apis` + admin catalog + audience + sync) | 10 | ~90 | 9 | partiel (APIVersionEntry) |
| 4 | **applications** (`/v1/tenants/{id}/applications`) | 5 | ~50 | 2 | non (types/index) |
| 5 | **consumers** (`/v1/consumers/` + certs) | 10 | ~120 | 3 | partiel (Bulk/Expiry) |
| 6 | **deployments** (tenants deploy + logs + deploy-api + env-status) | 12 | ~180 | 6 | non |
| 7 | **promotions** (`/v1/tenants/{id}/promotions`) | 8 | ~100 | 2 | oui (Promotion*) |
| 8 | **gateways** (admin instances + observability + policies) | 18 | ~220 | 10 | non |
| 9 | **gatewayDeployments** (`/v1/admin/deployments`) | 7 | ~90 | 3 | non |
| 10 | **traces** (`/v1/traces` + AI sessions + live) | 6 | ~80 | 4 | non |
| 11 | **monitoring** (`/v1/monitoring/transactions`) | 3 | ~50 | 2 | non |
| 12 | **platform** (`/v1/platform/*` + `/v1/operations` + `/v1/business`) | 10 | ~110 | 4 | partiel (ApplicationDiff) |
| 13 | **admin** (users + settings + roles + prospects + access-requests) | 9 | ~100 | 6 | partiel |
| 14 | **workflows** (`/v1/tenants/{id}/workflows`) | 9 | ~110 | 1 | non |
| 15 | **toolPermissions** (`/v1/tenants/{id}/tool-permissions`) | 3 | ~40 | 1 | oui (TenantToolPermissionCreate) |
| 16 | **chat** (settings + metering + usage + conversations) | 9 | ~100 | 3 | non |
| 17 | **llm** (usage + budget + timeseries + provider breakdown) | 5 | ~70 | 1 | non |
| 18 | **subscriptions** (`/v1/subscriptions`) | 6 | ~80 | 2 | oui (BulkSubscriptionAction) |
| 19 | **webhooks** (`/v1/tenants/{id}/webhooks` + deliveries) | 7 | ~90 | 1 | oui (Webhook*) |
| 20 | **credentialMappings** (`/v1/tenants/{id}/credential-mappings`) | 4 | ~60 | 1 | oui (CredentialMapping*) |
| 21 | **contracts** (`/v1/tenants/{id}/contracts` + bindings) | 9 | ~110 | 1 | oui (ContractUpdate) |
| 22 | **git** (`/v1/tenants/{id}/git/*`) | 2 | ~25 | 1 | non |

**Total : 22 clients de domaine** (de `~25` à `~220` LOC chacun, tous sous la cible < 300 LOC).

### A.2 Zombies détectés (déclarés mais 0 caller externe)

40 méthodes sur 170 (~24 %) : `createTenant`, `updateTenant`, `deleteTenant`, `getTenant`, `getApplication`, `getConsumer`, `blockConsumer`, `getDeployment`, `getPromotion`, `getTrace`, `getTraceTimeline`, `getLiveTraces`, `getMergeRequests`, `getCommits`, `getOperationsMetrics`, `getGatewayInstance`, `getGatewayDeployment`, `getGatewayInstanceMetrics`, `getGatewayPolicies`, `createGatewayPolicy`, `updateGatewayPolicy`, `deleteGatewayPolicy`, `createPolicyBinding`, `deletePolicyBinding`, `deployApiToGateways`, `getApiGatewayAssignments`, `createApiGatewayAssignment`, `deleteApiGatewayAssignment`, `getDeployableEnvironments`, `getEnvironmentStatus`, `getEnvironments`, `getCatalogEntries`, `getExpiringCertificates`, `revokeTenantCA`, `getContractBindings`, `getChatUsageStats`, `getWebhook`, `getPendingSubscriptions`, `getLlmBudget`, `updateLlmBudget`, `getTransactionStats`, `updateWorkflowTemplate`, `seedWorkflowTemplates`, `startWorkflow`, `getTenantCA` partial.

**Action** : **préserver dans leurs clients respectifs** (rewrite ≠ cleanup). Candidats suppression UI-3/audit ultérieur. Noter dans `REWRITE-BUGS.md`.

### A.3 Types inline en bas de `api.ts` (lignes 1487-1719)

**27 interfaces exportées** (comptage `grep -cE "^export interface" src/services/api.ts`) :

| # | Interface | Ligne | Domaine cible |
|---|---|---|---|
| 1 | `OperationsMetrics` | 1487 | platform |
| 2 | `BusinessMetrics` | 1496 | platform |
| 3 | `TopAPI` | 1505 | platform |
| 4 | `TenantChatSettings` | 1512 | chat |
| 5 | `ChatSourceEntry` | 1519 | chat |
| 6 | `ChatUsageBySource` | 1525 | chat |
| 7 | `TokenBudgetStatus` | 1533 | chat |
| 8 | `TokenUsageStats` | 1542 | chat |
| 9 | `ChatConversationMetrics` | 1555 | chat |
| 10 | `ModelDistributionEntry` | 1563 | chat |
| 11 | `ChatModelDistribution` | 1568 | chat |
| 12 | `ComponentStatus` | 1574 | platform |
| 13 | `GitOpsStatus` | 1584 | platform |
| 14 | `PlatformEvent` | 1590 | platform |
| 15 | `ExternalLinks` | 1601 | platform |
| 16 | `PlatformStatusResponse` | 1608 | platform |
| 17 | `ApplicationDiffResource` | 1615 | platform |
| 18 | `ApplicationDiffResponse` | 1625 | platform |
| 19 | `LlmUsageResponse` | 1633 | llm |
| 20 | `LlmTimeseriesPoint` | 1643 | llm |
| 21 | `LlmTimeseriesResponse` | 1648 | llm |
| 22 | `LlmProviderCostEntry` | 1654 | llm |
| 23 | `LlmProviderBreakdownResponse` | 1660 | llm |
| 24 | `LlmBudgetResponse` | 1665 | llm |
| 25 | `MonitoringTransaction` | 1678 | monitoring |
| 26 | `MonitoringTransactionDetail` | 1701 | monitoring |
| 27 | `MonitoringStats` | 1719 | monitoring |

**Action** : co-localiser dans le client de domaine concerné + **ré-exporter depuis la façade avec chemin explicite** :
```ts
// api.ts façade
export type { OperationsMetrics, BusinessMetrics, TopAPI, ComponentStatus, /* ... */ } from './api/platform';
export type { TenantChatSettings, TokenBudgetStatus, /* ... */ } from './api/chat';
export type { LlmUsageResponse, LlmBudgetResponse, /* ... */ } from './api/llm';
export type { MonitoringTransaction, MonitoringStats, /* ... */ } from './api/monitoring';
```
Pas de `api/index.ts` — chaque ré-export passe par un **sous-chemin explicite** (voir amendement résolution § C).

### A.4 Callers externes

- **76 fichiers** importent `apiService` depuis `../services/api` (44 pages, 13 hooks, 4 composants, 1 contexte, 1 mock, 13 tests).
- **56 fichiers de tests** font `vi.mock('../services/api', () => ({ apiService: { getX: vi.fn() } }))`.
- **11 services siblings** (`gatewayApi.ts`, `mcpGatewayApi.ts`, `federationApi.ts`, `backendApisApi.ts`, `skillsApi.ts`, `externalMcpServersApi.ts`, `errorSnapshotsApi.ts`, `discoveryApi.ts`, `diagnosticService.ts`, `mcpConnectorsApi.ts`, `proxyBackendService.ts`) consomment `apiService.get/post/put/delete` génériques.
- **Zéro `import axios`** hors `services/api.ts` (vérifié repo-wide).

---

## B. Core transport proposé

Extrait des lignes 1-189 de `api.ts` vers `src/services/http/` :

```
src/services/http/
├── index.ts           (~40 LOC) — UNIQUE point d'export runtime. Crée l'instance, installe les interceptors, puis exporte httpClient + helpers auth + SSE.
├── client.ts          (~40 LOC) — axios.create({ baseURL, headers }) — instance brute non exportée directement
├── auth.ts            (~50 LOC) — authToken state + setAuthToken/getAuthToken/clearAuthToken + TokenRefresher type + setTokenRefresher
├── interceptors.ts    (~30 LOC) — request interceptor (auth header)
├── refresh.ts         (~90 LOC) — response interceptor : 401 → refresh → retry + queue (isRefreshing + refreshQueue)
├── errors.ts          (~20 LOC) — hook getFriendlyErrorMessage dans le response interceptor
└── sse.ts             (~15 LOC) — createEventSource helper (lit API_BASE_URL depuis config)
```

**Règle d'import invariant (amendement)** :
- **Les clients de domaine (`api/*.ts`) importent uniquement `'../http'`** — jamais `'../http/client'`.
- **La façade `api.ts` importe uniquement `'./http'`** — jamais `'./http/client'`.
- `client.ts` n'est consommé que par `http/index.ts`, qui orchestre la composition (create → install interceptors → export).

Raison : l'instance `axios` doit être **déjà décorée** avec ses interceptors au moment où le premier consommateur l'utilise. Importer `./client` ailleurs contournerait l'installation des interceptors (effet de bord dans `index.ts`) et provoquerait des appels sans auth header ni refresh — classe de bug silencieuse difficile à tracker ([Axios docs : interceptors attachés à l'instance ; retry doit repasser par la même instance](https://axios-http.com/docs/interceptors)).

**Surface exportée par `http/index.ts`** :
```ts
// http/index.ts
import axios from 'axios';
import { config } from '@/config';
import { installRequestInterceptor } from './interceptors';
import { installRefreshInterceptor } from './refresh';

const instance = axios.create({
  baseURL: config.api.baseUrl,
  headers: { 'Content-Type': 'application/json' },
});

installRequestInterceptor(instance);
installRefreshInterceptor(instance);

export const httpClient = instance;
export { setAuthToken, getAuthToken, clearAuthToken, setTokenRefresher, type TokenRefresher } from './auth';
export { createEventSource } from './sse';
```

**Total core** : ~285 LOC, chaque fichier < 100 LOC. Les 11 services siblings continuent de consommer `apiService.get/post/…` via la façade.

**Comportement préservé à l'identique** :
- `this.client.interceptors.request.use` ordre et contenu inchangé (auth header).
- Response interceptor 401 flow : `_retry` flag, queue de requêtes parallèles, `isRefreshing` mutex, `setAuthToken` sur success, `clearAuthToken` implicite sur null (logic identique à CAB-1122).
- `getFriendlyErrorMessage` appliqué sur toutes les erreurs post-refresh (CAB-1629).
- Les tests d'auth (`AuthContext.test.tsx`, 7 autres) qui mockent `setTokenRefresher` / `setAuthToken` **continuent de fonctionner sans modification** (signatures identiques exposées depuis la façade).

---

## C. Structure cible

**Amendement résolution modules** : **pas de `src/services/api/index.ts`**. Depuis `src/services/api.ts`, le chemin `'./api'` entre en collision avec le fichier lui-même (self-import circulaire), et depuis un sous-fichier `api/tenants.ts`, `'../api'` est ambigu entre `api.ts` (fichier façade) et `api/index.ts` (dossier). L'algorithme node-like essaie d'abord `.ts`/`.tsx`/`.d.ts`, puis `index.ts` du dossier → collision potentielle. On supprime `api/index.ts` et **chaque import/ré-export utilise un sous-chemin explicite** (`'./api/tenants'`, `'./api/platform'`, …). Alternative envisagée puis écartée : renommer le dossier en `clients/` ou `domains/` (plus invasif, même bénéfice).

```
src/services/
├── api.ts                    (FAÇADE — agrégation pure, plus aucune logique métier)
├── http/
│   ├── index.ts              (UNIQUE export runtime — crée l'instance + installe interceptors)
│   ├── client.ts             (axios.create factory — interne)
│   ├── auth.ts
│   ├── interceptors.ts
│   ├── refresh.ts
│   ├── errors.ts
│   └── sse.ts
├── api/                      (PAS de index.ts — imports par sous-chemin explicite)
│   ├── session.ts            (/v1/me + /v1/environments)
│   ├── tenants.ts            (tenants CRUD + CA + CSR)
│   ├── apis.ts               (APIs CRUD + catalog + audience + versions)
│   ├── applications.ts
│   ├── consumers.ts          (consumers + mTLS certs)
│   ├── deployments.ts        (lifecycle + logs + deploy + env-status)
│   ├── promotions.ts
│   ├── gateways.ts           (admin gateways + observability + policies)
│   ├── gatewayDeployments.ts (admin deployments + catalog-entries + test/sync)
│   ├── traces.ts             (pipeline traces + AI sessions)
│   ├── monitoring.ts         (call flow transactions)
│   ├── platform.ts           (platform status + operations + business)
│   ├── admin.ts              (users + settings + roles + prospects + access-requests)
│   ├── workflows.ts
│   ├── toolPermissions.ts
│   ├── chat.ts               (settings + metering + conversations)
│   ├── llm.ts                (usage + budget)
│   ├── subscriptions.ts
│   ├── webhooks.ts           (+ deliveries)
│   ├── credentialMappings.ts
│   ├── contracts.ts          (+ bindings)
│   └── git.ts                (commits + MRs)
│
├── (existants, intouchés)
├── backendApisApi.ts
├── diagnosticService.ts
├── discoveryApi.ts
├── errorSnapshotsApi.ts
├── externalMcpServersApi.ts
├── federationApi.ts
├── gatewayApi.ts
├── mcpConnectorsApi.ts
├── mcpGatewayApi.ts
├── proxyBackendService.ts
└── skillsApi.ts
```

### C.1 Pattern d'export dans chaque client

Functional namespace (cohérent avec `gatewayApi.ts` et `diagnosticService.ts`, deux siblings existants) :

```ts
// src/services/api/tenants.ts
import type { Schemas } from '@stoa/shared/api-types';
import type { Tenant, TenantCreate, TenantCAInfo, IssuedCertificateListResponse } from '@/types';
import { httpClient } from '../http'; // via http/index.ts, interceptors déjà installés

export const tenantsClient = {
  async list(): Promise<Tenant[]> {
    const { data } = await httpClient.get<Tenant[]>('/v1/tenants');
    return data;
  },
  async get(tenantId: string): Promise<Tenant> { /* ... */ },
  async create(tenant: TenantCreate): Promise<Tenant> { /* ... */ },
  async update(tenantId: string, patch: Partial<TenantCreate>): Promise<Tenant> { /* ... */ },
  async remove(tenantId: string): Promise<void> { /* ... */ },
  async getCA(tenantId: string): Promise<TenantCAInfo> { /* ... */ },
  async generateCA(tenantId: string): Promise<TenantCAInfo> { /* ... */ },
  async signCSR(tenantId: string, csrPem: string, validityDays?: number): Promise<Schemas['CSRSignResponse']> { /* ... */ },
  async revokeCA(tenantId: string): Promise<void> { /* ... */ },
  async listIssuedCertificates(tenantId: string, status?: string): Promise<IssuedCertificateListResponse> { /* ... */ },
  async revokeIssuedCertificate(tenantId: string, certId: string): Promise<void> { /* ... */ },
};
```

- **Noms raccourcis** (`list`, `get`, `create`, `update`, `remove`) dans chaque client → cohérent REST, évite la répétition du domaine dans chaque nom.
- Au niveau **façade**, on conserve les noms longs actuels (`getTenants`, `createTenant`, …) pour zéro changement caller/test.
- `delete` est un mot réservé d'où `remove`.

### C.2 Façade `api.ts` — critère = **zéro logique métier** (pas de LOC cap arbitraire)

**Amendement** : critère DoD = "`api.ts` ne contient plus que des imports, des wrappers typés triviaux, un objet d'agrégation `satisfies LegacyApiSurface`, et des ré-exports de types". **Pas de plafond LOC** (~170 mappings × 1 ligne chacun = 170-250 LOC attendus, purement déclaratif).

```ts
// src/services/api.ts (façade)
import { httpClient, setAuthToken, setTokenRefresher, getAuthToken, clearAuthToken, createEventSource } from './http';
import { tenantsClient } from './api/tenants';
import { apisClient } from './api/apis';
import { applicationsClient } from './api/applications';
// ... ~22 imports de clients de domaine (sous-chemins explicites, pas de barrel)

// Wrappers typés pour le passthrough générique (préservés pour 58 callers + 11 siblings)
// Amendement : PAS de `.bind(httpClient)` — wrappers fins avec types préservés.
async function get<T = unknown>(
  url: string,
  config?: { params?: Record<string, unknown> }
): Promise<{ data: T }> {
  return httpClient.get<T>(url, config);
}
async function post<T = unknown>(url: string, data?: unknown): Promise<{ data: T }> {
  return httpClient.post<T>(url, data);
}
async function put<T = unknown>(url: string, data?: unknown): Promise<{ data: T }> {
  return httpClient.put<T>(url, data);
}
async function patch<T = unknown>(url: string, data?: unknown): Promise<{ data: T }> {
  return httpClient.patch<T>(url, data);
}
async function del<T = unknown>(url: string): Promise<{ data: T }> {
  return httpClient.delete<T>(url);
}

// Contrat de surface legacy — le code casse à la compilation si la façade ne
// correspond pas exactement à ce que les callers + tests consomment.
export interface LegacyApiSurface {
  // Plumbing
  setTokenRefresher: typeof setTokenRefresher;
  setAuthToken: typeof setAuthToken;
  getAuthToken: typeof getAuthToken;
  clearAuthToken: typeof clearAuthToken;
  createEventSource: typeof createEventSource;

  // Generic passthroughs (signature identique à l'ApiService historique)
  get: typeof get;
  post: typeof post;
  put: typeof put;
  patch: typeof patch;
  delete: typeof del;

  // Méthodes métier (noms longs historiques) — ~170 signatures reprises 1:1
  getMe: typeof sessionClient.getMe;
  getTenants: typeof tenantsClient.list;
  getTenant: typeof tenantsClient.get;
  createTenant: typeof tenantsClient.create;
  updateTenant: typeof tenantsClient.update;
  deleteTenant: typeof tenantsClient.remove;
  // ... 164 autres
}

export const apiService = {
  setTokenRefresher,
  setAuthToken,
  getAuthToken,
  clearAuthToken,
  createEventSource,

  get, post, put, patch, delete: del,

  getMe: sessionClient.getMe,
  getTenants: tenantsClient.list,
  getTenant: tenantsClient.get,
  createTenant: tenantsClient.create,
  updateTenant: tenantsClient.update,
  deleteTenant: tenantsClient.remove,
  // ... 164 autres mappings
} satisfies LegacyApiSurface;

// Ré-exports de types — chemins explicites, pas de barrel (§ C collision note)
export type {
  OperationsMetrics,
  BusinessMetrics,
  TopAPI,
  ComponentStatus,
  GitOpsStatus,
  PlatformEvent,
  ExternalLinks,
  PlatformStatusResponse,
  ApplicationDiffResource,
  ApplicationDiffResponse,
} from './api/platform';
export type {
  TenantChatSettings,
  ChatSourceEntry,
  ChatUsageBySource,
  TokenBudgetStatus,
  TokenUsageStats,
  ChatConversationMetrics,
  ModelDistributionEntry,
  ChatModelDistribution,
} from './api/chat';
export type {
  LlmUsageResponse,
  LlmTimeseriesPoint,
  LlmTimeseriesResponse,
  LlmProviderCostEntry,
  LlmProviderBreakdownResponse,
  LlmBudgetResponse,
} from './api/llm';
export type {
  MonitoringTransaction,
  MonitoringTransactionDetail,
  MonitoringStats,
} from './api/monitoring';
```

La façade est **purement déclarative + un contrat `satisfies`** — `tsc` échoue si un mapping est manquant ou mal typé (remplace le smoke test `Object.keys(...).length` de la v1, qui n'indiquait pas **quelle** méthode manquait).

---

## D. Stratégie de migration des callers — **Option A (façade + agrégation)**

### Recommandation : **Option A** (pas Option B).

**Contexte facteur décisif** : **56 fichiers de tests** utilisent `vi.mock('../services/api', () => ({ apiService: {...} }))`. Si on rewrite les imports des callers pour pointer sur `@/services/api/tenants`, il faut ÉGALEMENT rewriter les vi.mock de ces 56 tests (chacun avec sa surface de méthodes propre). Risque élevé de régression silencieuse sur tests unitaires.

**Différence vs UI-1** : UI-1 rewritait des imports de types (effet compile-time uniquement). Ici on touche du code runtime mocké par 56 tests → codemod B x ~5 en complexité.

### Option A retenue — pour, contre, dette

| | Option A (façade) | Option B (codemod massif) |
|---|---|---|
| Callers production (76 fichiers) | Inchangés | Tous réécrits |
| Tests `vi.mock` (56 fichiers) | **Inchangés** | Tous réécrits |
| Risque régression | **Faible** | Moyen-élevé |
| Propreté cible | Moyenne (façade résiduelle ~200 LOC) | Haute |
| Durée ingé | ~6h | ~12h+ |
| Reversibilité partielle | Oui (juste supprimer façade) | Non (codemod one-shot) |

**Dette résiduelle assumée** :
1. Façade `api.ts` ~200 LOC d'agrégation pur (pas de logique, juste re-routing).
2. Callers peuvent continuer d'utiliser `apiService.getX(...)` — pas de force de migration.
3. Ticket UI-3 possible : codemod incrémental par domaine + suppression finale de la façade quand 0 usage `apiService.*`. Hors scope UI-2.

### Gain immédiat malgré façade

- Core transport isolé et testable séparément.
- Tout nouveau code peut importer `{ tenantsClient } from '@/services/api/tenants'` directement.
- Fichier 1732 LOC → 22 fichiers < 220 LOC + core < 100 LOC chacun.
- Types UI-1 (Schemas) utilisés systématiquement dans les nouveaux clients, fin du drift avec `types/index.ts`.

### Codemod léger optionnel (bonus, arbitrable)

Un codemod **jetable** (`scripts/migrate-apiservice.ts` ts-morph) peut migrer `apiService.getTenant(id)` → `tenantsClient.get(id)` dans une sélection ciblée (par ex. seulement `src/pages/Tenants.tsx`) **sans** toucher les tests. À exécuter après le rewrite, PR par PR, selon l'appétit. Pas inclus dans la DoD Phase 2.

---

## E. Plan d'exécution Phase 2

**Ordre** — core d'abord, puis domaines par dépendance décroissante :

| # | Étape | Fichiers créés / modifiés | Tests à vérifier | Commit |
|---|---|---|---|---|
| 1 | Core HTTP : extrait la classe `ApiService` → `http/client.ts` + `http/auth.ts` + `http/interceptors.ts` + `http/refresh.ts` + `http/errors.ts` + `http/sse.ts`. `api.ts` devient temporairement un wrapper qui appelle `httpClient` mais **expose la même API publique** (classe `ApiService` ou aggregate objet). Tous les callers inchangés. | `services/http/*` ; `api.ts` réduit | `AuthContext.test.tsx`, `Layout.test.tsx`, hooks/*.test.ts (refresh flow) | `refactor(ui): extract axios core to services/http (UI-2 S1)` |
| 2 | **Domaines à faible churn d'abord** (éviter conflits MR) : `git`, `toolPermissions`, `admin`, `llm`, `workflows`, `subscriptions`, `webhooks`, `credentialMappings`, `contracts`, `monitoring`, `traces`, `chat`, `promotions`, `session`, `applications`, `platform`. (SSE est déjà dans `http/sse.ts` — pas un domaine métier.) | `services/api/<dom>.ts` + façade re-route | tests du domaine concerné | 1 commit par groupe de 3-4 domaines |
| 3 | **Domaines à forte volumétrie** : `tenants`, `apis`, `consumers`, `deployments`, `gateways`, `gatewayDeployments`. | idem | idem | 1 commit par domaine |
| 4 | Déplacement des 18 interfaces inline (bas d'`api.ts`) vers leurs clients respectifs + re-export depuis la façade | `api/platform.ts`, `api/chat.ts`, `api/llm.ts`, `api/monitoring.ts` | tests qui importent ces types | `refactor(ui): relocate inline response types to domain clients (UI-2 S3)` |
| 5 | `api.ts` réduit à la façade agrégée (<200 LOC) | final | suite complète | `refactor(ui): collapse api.ts to aggregator facade (UI-2 S4)` |
| 6 | **Bonus** (optionnel, hors DoD) : rule ESLint `no-restricted-imports` qui interdit `import axios` en dehors de `src/services/http/**` | `.eslintrc.cjs` | lint | `chore(ui): ban axios imports outside services/http (UI-2 bonus)` |

**Point de commit après chaque domaine extrait** : oui, un squash-friendly step-by-step. Tests lancés entre chaque (`npm run test -- --run`) + `tsc --noEmit`.

**Branche de travail** : `refactor/ui-2-split-api-client`. Une ou plusieurs PRs selon l'arbitrage. Recommandation : **1 PR pour la Phase 2 complète**, découpée en commits lisibles (revue plus facile qu'une PR par domaine vu la répétition mécanique).

---

## F. Risques identifiés

### F.1 Test mock contamination (MOYEN)
**56 tests** font `vi.mock('../services/api', () => ({ apiService: {...} }))`. La façade préserve cette surface → tests inchangés. Mais si la façade casse l'agrégation (ex : oublier une méthode), les mocks deviennent silencieusement no-op en test, et les callers réels explosent en runtime. **Mitigation (amendement)** : contrat **`export interface LegacyApiSurface`** + `export const apiService = { ... } satisfies LegacyApiSurface`. `tsc --noEmit` échoue à la compilation si une méthode manque ou est mal typée, avec un message précis indiquant quelle clé pose problème. Bien plus robuste que le smoke test `Object.keys().length` (cardinalité sans diagnostic). Par ailleurs Vitest lève explicitement une erreur dès qu'une méthode consommée par le code n'est pas présente dans la factory `vi.mock`.

### F.2 Refresh token state partagée (ÉLEVÉ)
`authToken`, `tokenRefresher`, `isRefreshing`, `refreshQueue` sont couplés. La tentation de disperser cet état entre modules doit être évitée. **Mitigation** : tout cet état vit dans `http/auth.ts` + `http/refresh.ts`, un unique module-scope closure. Les domain clients ne voient que `httpClient` exposé par `http/index.ts` — **déjà décoré avec les interceptors**. Invariant : personne n'importe `http/client.ts` directement.

### F.3 Re-export des 18 types inline (MOYEN)
Certains callers font `import { BusinessMetrics } from '../services/api'`. Si on déplace ces types sans re-export, le build casse. **Mitigation** : Phase 2 étape 4 — re-exports explicites depuis la façade pour chaque type. Valider par `grep -rn "from '.*services/api'" src/ | grep -v "apiService"` avant de toucher.

### F.4 Circulaires (FAIBLE)
`AuthContext` appelle `apiService.setTokenRefresher(refresh)`. La closure `refresh` peut elle-même appeler des endpoints via `apiService`. **Mitigation** : inchangé — on garde la même injection par setter, pas de dépendance directe `http/ → auth/context`.

### F.5 Services siblings dépendent du passthrough générique (ÉLEVÉ)
**11 fichiers** utilisent `apiService.get<T>(url)` / `apiService.post(...)` en direct (pattern préexistant). Si on supprime les passthroughs, tous cassent. **Mitigation** : passthroughs `get/post/put/patch/delete` préservés sur la façade (déjà dans le plan). Possibilité future : offrir `import { httpClient } from '@/services/http'` et migrer progressivement les siblings — hors scope UI-2.

### F.6 Zombies (~40 méthodes) (FAIBLE)
Préservés dans les clients de domaine. Risque = 0 (code mort existant, pas de régression possible). Flaggés dans `REWRITE-BUGS.md` pour cleanup UI-3.

### F.7 `any` omniprésent sur le domaine gateway/deployment (FAIBLE, out of scope)
Méthodes `getGatewayInstance(id): Promise<any>`, `getGatewayDeployments(): Promise<{ items: any[]; ... }>` etc. — typage faible préexistant. **Décision** : documenter dans `REWRITE-BUGS.md`, typer avec `Schemas['X']` QUAND disponible dans UI-1, sinon conserver `any` (pas de redéclaration manuelle de type — ticket UI-4 potentiel).

### F.8 Build / bundle size (INFORMATIF — retiré de la DoD)
**Amendement** : **retiré de la DoD**. Rollup tree-shake bien les exports nommés ESM, mais tant que la majorité du code continue d'importer un gros objet `apiService` et que la façade ré-agrège tous les clients, l'effet réaliste est **neutre**, pas un gain garanti. On mesurera à titre informatif (`du -sh dist/assets/*.js` avant/après) mais **aucun seuil ±5 % n'est imposé** comme critère de succès UI-2.

### F.9 Renommage méthodes `list/get/create/update/remove` au niveau client (FAIBLE)
Les callers continuent d'utiliser les noms longs via façade. Au niveau client, les noms courts réduisent le bruit. **Risque** si un autre sprint bypass la façade et importe le client directement avant UI-3 — documenter le pattern dans `CLAUDE.md`.

---

## Arbitrages validés 2026-04-22

| # | Question | Arbitrage |
|---|---|---|
| 1 | Option A vs B | **A** (façade) — facteur 56-tests-mocks |
| 2 | Pattern d'export | **`const <domain>Client = { ... }`** — pas de classe, cohérent avec siblings fonctionnels |
| 3 | PR unique ou par domaine | **1 PR** avec commits lisibles |
| 4 | Bonus ESLint `no-restricted-imports axios` | **Dernier commit non-bloquant** ou ticket séparé |
| 5 | Arbitrage `any` | **Conserver par défaut**. Remplacer uniquement quand `Schemas[...]` existe ET colle exactement au payload (pas de typage inventé) |

### Amendements bloquants appliqués dans ce plan

1. ✅ Suppression de `src/services/api/index.ts` — collision résolution `api.ts` / dossier `api/`. Imports par sous-chemin explicite uniquement.
2. ✅ `src/services/http/index.ts` = UNIQUE point d'export runtime — crée l'instance, installe les interceptors, puis exporte `httpClient` + helpers. Invariant : personne n'importe `http/client.ts`.
3. ✅ Passthroughs `get/post/put/patch/delete` via **wrappers typés fins** — pas de `.bind(httpClient)`.
4. ✅ Contrat de surface legacy via `export interface LegacyApiSurface` + `satisfies` — remplace le smoke `Object.keys().length`.
5. ✅ Critère DoD `api.ts` = "plus aucune logique métier" — pas de plafond LOC arbitraire.
6. ✅ Ré-exports de types depuis sous-chemins explicites (`from './api/platform'`, etc.).
7. ✅ Bundle size retiré de la DoD.
8. ✅ A.3 recomptée : **27 interfaces** (pas 18) avec tableau ligne par ligne.
9. ✅ Étape 2 ne mentionne plus `events` — SSE vit déjà dans `http/sse.ts`.

**Phase 2 peut démarrer.**
