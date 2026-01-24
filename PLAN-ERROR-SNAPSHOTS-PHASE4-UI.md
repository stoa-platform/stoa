# Plan: Error Snapshots Phase 4 - Console UI

## Objectif

Créer une interface UI dans la Console (control-plane-ui) pour visualiser et analyser les MCP Error Snapshots capturés par le MCP Gateway. Cette interface doit permettre le **time-travel debugging** avec une expérience utilisateur optimale.

---

## Réponses aux Questions Préliminaires

| Question | Réponse |
|----------|---------|
| Framework UI actuel | **Tailwind CSS** (pas de component library) |
| Pattern list/detail établi | **Oui** - Monitoring.tsx avec expandable rows est le pattern idéal |
| OpenSearch queryable | **Non** - À ajouter via control-plane-api (ou directement MCP Gateway) |
| Gestion multi-tenant | **Oui** - Via `tenant_id` dans le contexte auth (pattern existant) |

---

## Architecture Cible

```
┌─────────────────────────────────────────────────────────────────┐
│                    Control-Plane-UI                             │
│                                                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                  ErrorSnapshots.tsx                        │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │ │
│  │  │ Stats Cards │  │ Filter Bar  │  │ Snapshot List       │ │ │
│  │  │ - Total     │  │ - Error Type│  │ ┌─────────────────┐ │ │ │
│  │  │ - Cost USD  │  │ - Status    │  │ │ SnapshotRow     │ │ │ │
│  │  │ - Wasted    │  │ - Server    │  │ │ (expandable)    │ │ │ │
│  │  │ - Success%  │  │ - Date Range│  │ │ - Summary       │ │ │ │
│  │  └─────────────┘  └─────────────┘  │ │ - Details       │ │ │ │
│  │                                    │ │ - Timeline      │ │ │ │
│  │                                    │ │ - Replay Cmd    │ │ │ │
│  │                                    │ └─────────────────┘ │ │ │
│  │                                    └─────────────────────┘ │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              │                                  │
│                              ▼                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │               errorSnapshotsApi.ts                         │ │
│  │  GET  /mcp/v1/errors/snapshots                             │ │
│  │  GET  /mcp/v1/errors/snapshots/{id}                        │ │
│  │  GET  /mcp/v1/errors/snapshots/stats                       │ │
│  │  POST /mcp/v1/errors/snapshots/{id}/replay                 │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      MCP Gateway API                            │
│                  /mcp/v1/errors/snapshots/*                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Structure des Fichiers

```
control-plane-ui/src/
├── pages/
│   └── ErrorSnapshots.tsx        # Page principale (nouvelle)
├── components/
│   └── snapshots/                # Nouveau dossier
│       ├── SnapshotRow.tsx       # Ligne expandable
│       ├── SnapshotTimeline.tsx  # Timeline des étapes
│       ├── ContextViewer.tsx     # JSON viewer pour contextes
│       ├── CostBadge.tsx         # Badge coût LLM
│       └── ReplayCommand.tsx     # Commande cURL
├── services/
│   └── errorSnapshotsApi.ts      # Service API (nouveau)
└── types/
    └── index.ts                  # Types à ajouter
```

---

## Phase 4.1: Types TypeScript

### Ajouts à `types/index.ts`

```typescript
// MCP Error Snapshot types
export type MCPErrorType =
  | 'server_timeout'
  | 'server_rate_limited'
  | 'server_auth_failure'
  | 'server_unavailable'
  | 'server_internal_error'
  | 'tool_not_found'
  | 'tool_execution_error'
  | 'tool_validation_error'
  | 'tool_timeout'
  | 'llm_context_exceeded'
  | 'llm_quota_exceeded'
  | 'llm_invalid_response'
  | 'policy_denied'
  | 'unknown';

export type SnapshotResolutionStatus = 'unresolved' | 'investigating' | 'resolved' | 'ignored';

export interface MCPServerContext {
  name: string;
  url?: string;
  version?: string;
  tools_available: string[];
  health_at_error?: string;
  latency_p99_ms?: number;
  error_rate_percent?: number;
}

export interface ToolInvocation {
  tool_name: string;
  input_params?: Record<string, unknown>;
  input_params_masked?: Record<string, unknown>;
  masked_keys?: string[];
  output_preview?: string;
  duration_ms?: number;
  error_type?: string;
  error_message?: string;
  error_retryable?: boolean;
  backend_status_code?: number;
  backend_response_time_ms?: number;
}

export interface LLMContext {
  provider?: string;
  model?: string;
  tokens_input?: number;
  tokens_output?: number;
  tokens_context_limit?: number;
  latency_ms?: number;
  prompt_hash?: string;
  prompt_preview?: string;
  cost_usd?: number;
}

export interface RetryContext {
  attempts: number;
  max_attempts: number;
  delays_ms?: number[];
  strategy?: string;
  fallback_attempted?: boolean;
  fallback_server?: string;
}

export interface RequestContext {
  method: string;
  path: string;
  query_params?: Record<string, string>;
  headers?: Record<string, string>;
  body_preview?: string;
}

export interface UserContext {
  user_id?: string;
  tenant_id?: string;
  session_id?: string;
  roles?: string[];
  client_ip?: string;
}

export interface MCPErrorSnapshot {
  id: string;
  timestamp: string;
  error_type: MCPErrorType;
  error_message: string;
  error_code?: string;
  response_status: number;
  request: RequestContext;
  user?: UserContext;
  mcp_server?: MCPServerContext;
  tool_invocation?: ToolInvocation;
  llm_context?: LLMContext;
  retry_context?: RetryContext;
  total_cost_usd: number;
  tokens_wasted: number;
  trace_id?: string;
  resolution_status?: SnapshotResolutionStatus;
  resolution_notes?: string;
}

export interface MCPErrorSnapshotSummary {
  id: string;
  timestamp: string;
  error_type: MCPErrorType;
  error_message: string;
  response_status: number;
  mcp_server_name?: string;
  tool_name?: string;
  total_cost_usd: number;
  tokens_wasted: number;
  resolution_status?: SnapshotResolutionStatus;
}

export interface MCPErrorSnapshotStats {
  total: number;
  by_error_type: Record<MCPErrorType, number>;
  by_status: Record<number, number>;
  by_server: Record<string, number>;
  total_cost_usd: number;
  total_tokens_wasted: number;
  avg_cost_usd: number;
  resolution_stats: {
    unresolved: number;
    investigating: number;
    resolved: number;
    ignored: number;
  };
}

export interface MCPErrorSnapshotFilters {
  error_types?: MCPErrorType[];
  status_codes?: number[];
  server_names?: string[];
  tool_names?: string[];
  resolution_status?: SnapshotResolutionStatus[];
  start_date?: string;
  end_date?: string;
  min_cost_usd?: number;
  search?: string;
}

export interface MCPErrorSnapshotListResponse {
  snapshots: MCPErrorSnapshotSummary[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}
```

---

## Phase 4.2: Service API

### Nouveau fichier: `services/errorSnapshotsApi.ts`

```typescript
import { apiService } from './api';
import type {
  MCPErrorSnapshot,
  MCPErrorSnapshotSummary,
  MCPErrorSnapshotStats,
  MCPErrorSnapshotFilters,
  MCPErrorSnapshotListResponse,
  SnapshotResolutionStatus,
} from '../types';

const MCP_GATEWAY_URL = import.meta.env.VITE_MCP_GATEWAY_URL || 'https://mcp.gostoa.dev';

class ErrorSnapshotsService {
  private baseUrl = `${MCP_GATEWAY_URL}/mcp/v1/errors/snapshots`;

  async getSnapshots(
    filters?: MCPErrorSnapshotFilters,
    page: number = 1,
    pageSize: number = 20
  ): Promise<MCPErrorSnapshotListResponse> {
    const params = new URLSearchParams();
    params.set('page', String(page));
    params.set('page_size', String(pageSize));

    if (filters) {
      if (filters.error_types?.length) {
        filters.error_types.forEach(t => params.append('error_type', t));
      }
      if (filters.status_codes?.length) {
        filters.status_codes.forEach(c => params.append('status_code', String(c)));
      }
      if (filters.server_names?.length) {
        filters.server_names.forEach(s => params.append('server_name', s));
      }
      if (filters.resolution_status?.length) {
        filters.resolution_status.forEach(s => params.append('resolution_status', s));
      }
      if (filters.start_date) params.set('start_date', filters.start_date);
      if (filters.end_date) params.set('end_date', filters.end_date);
      if (filters.min_cost_usd) params.set('min_cost_usd', String(filters.min_cost_usd));
      if (filters.search) params.set('search', filters.search);
    }

    const { data } = await apiService.get<MCPErrorSnapshotListResponse>(
      `${this.baseUrl}?${params.toString()}`
    );
    return data;
  }

  async getSnapshot(snapshotId: string): Promise<MCPErrorSnapshot> {
    const { data } = await apiService.get<MCPErrorSnapshot>(
      `${this.baseUrl}/${snapshotId}`
    );
    return data;
  }

  async getStats(filters?: MCPErrorSnapshotFilters): Promise<MCPErrorSnapshotStats> {
    const params = new URLSearchParams();
    if (filters?.start_date) params.set('start_date', filters.start_date);
    if (filters?.end_date) params.set('end_date', filters.end_date);

    const { data } = await apiService.get<MCPErrorSnapshotStats>(
      `${this.baseUrl}/stats?${params.toString()}`
    );
    return data;
  }

  async updateResolutionStatus(
    snapshotId: string,
    status: SnapshotResolutionStatus,
    notes?: string
  ): Promise<MCPErrorSnapshot> {
    const { data } = await apiService.patch<MCPErrorSnapshot>(
      `${this.baseUrl}/${snapshotId}`,
      { resolution_status: status, resolution_notes: notes }
    );
    return data;
  }

  async generateReplayCommand(snapshotId: string): Promise<{ curl_command: string }> {
    const { data } = await apiService.post<{ curl_command: string }>(
      `${this.baseUrl}/${snapshotId}/replay`
    );
    return data;
  }
}

export const errorSnapshotsService = new ErrorSnapshotsService();
```

---

## Phase 4.3: Composants UI

### 4.3.1: Page principale `pages/ErrorSnapshots.tsx`

Structure basée sur `Monitoring.tsx`:

```typescript
// Key features:
// - Stats cards: Total errors, Cost USD, Tokens wasted, Resolution rate
// - Filter bar: Error type, Status code, Server, Date range, Search
// - Expandable rows with lazy-loaded details
// - Auto-refresh toggle (5s)
// - Resolution status update inline

// Status colors mapping
const errorTypeColors: Record<MCPErrorType, { color: string; bg: string }> = {
  server_timeout: { color: 'text-orange-600', bg: 'bg-orange-100' },
  server_rate_limited: { color: 'text-yellow-600', bg: 'bg-yellow-100' },
  tool_execution_error: { color: 'text-red-600', bg: 'bg-red-100' },
  llm_context_exceeded: { color: 'text-purple-600', bg: 'bg-purple-100' },
  // ... autres types
};

const resolutionColors: Record<SnapshotResolutionStatus, string> = {
  unresolved: 'bg-red-100 text-red-800',
  investigating: 'bg-yellow-100 text-yellow-800',
  resolved: 'bg-green-100 text-green-800',
  ignored: 'bg-gray-100 text-gray-800',
};
```

### 4.3.2: Composant `components/snapshots/SnapshotRow.tsx`

Row expandable avec:
- **Header condensé**: Timestamp, Error type badge, Server, Tool, Cost, Status
- **Détails expandés**:
  - Grid 3 colonnes: Request | Tool/Server Context | LLM Context
  - Timeline des retries si applicable
  - Error message complet
  - Bouton "Generate cURL"

### 4.3.3: Composant `components/snapshots/SnapshotTimeline.tsx`

Réutilisation du pattern `StepTimeline` de Monitoring.tsx:
- Affiche les étapes de retry
- Délais entre tentatives
- Fallback server si utilisé

### 4.3.4: Composant `components/snapshots/ContextViewer.tsx`

JSON viewer collapsible pour:
- Request headers (masqués)
- Tool input params (masqués)
- LLM context
- Backend response

### 4.3.5: Composant `components/snapshots/CostBadge.tsx`

Badge stylisé pour le coût:
```typescript
// Couleurs selon seuil
$0.00 - $0.01: green
$0.01 - $0.10: yellow
$0.10+: red

// Format: "$0.0234" ou "~$0.02"
```

### 4.3.6: Composant `components/snapshots/ReplayCommand.tsx`

Affiche la commande cURL avec:
- Bouton "Copy to clipboard"
- Toggle pour afficher/masquer les tokens sensibles
- Warning si des données ont été masquées

---

## Phase 4.4: Backend Endpoints (MCP Gateway)

Endpoints à ajouter dans `mcp-gateway/src/handlers/`:

### `GET /mcp/v1/errors/snapshots`
```python
@router.get("/errors/snapshots")
async def list_snapshots(
    page: int = 1,
    page_size: int = 20,
    error_type: list[str] = Query(default=[]),
    status_code: list[int] = Query(default=[]),
    server_name: list[str] = Query(default=[]),
    resolution_status: list[str] = Query(default=[]),
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    search: str | None = None,
) -> MCPErrorSnapshotListResponse:
    """List error snapshots with filters and pagination."""
```

### `GET /mcp/v1/errors/snapshots/{snapshot_id}`
```python
@router.get("/errors/snapshots/{snapshot_id}")
async def get_snapshot(snapshot_id: str) -> MCPErrorSnapshot:
    """Get full error snapshot details."""
```

### `GET /mcp/v1/errors/snapshots/stats`
```python
@router.get("/errors/snapshots/stats")
async def get_stats(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> MCPErrorSnapshotStats:
    """Get aggregated error statistics."""
```

### `PATCH /mcp/v1/errors/snapshots/{snapshot_id}`
```python
@router.patch("/errors/snapshots/{snapshot_id}")
async def update_snapshot(
    snapshot_id: str,
    update: SnapshotUpdate,
) -> MCPErrorSnapshot:
    """Update snapshot resolution status."""
```

### `POST /mcp/v1/errors/snapshots/{snapshot_id}/replay`
```python
@router.post("/errors/snapshots/{snapshot_id}/replay")
async def generate_replay(snapshot_id: str) -> ReplayResponse:
    """Generate cURL command to replay the request."""
```

---

## Phase 4.5: Routing

### Ajout dans `App.tsx`

```typescript
import { ErrorSnapshots } from './pages/ErrorSnapshots';

// Dans ProtectedRoutes
<Route path="/mcp/errors" element={<ErrorSnapshots />} />
```

### Ajout dans `Layout.tsx` (navigation)

```typescript
// Dans le menu latéral, section "MCP Gateway"
{
  name: 'Error Snapshots',
  href: '/mcp/errors',
  icon: AlertTriangle,
  badge: stats?.unresolved > 0 ? stats.unresolved : undefined,
}
```

---

## Phase 4.6: Storage Backend

### Option A: Kafka + OpenSearch (Recommandé pour production)

```
MCP Gateway → Kafka (stoa.errors.mcp-snapshots) → OpenSearch
                                                      ↓
                                              MCP Gateway API
                                                      ↓
                                              Console UI
```

### Option B: PostgreSQL (Plus simple pour le MVP)

```
MCP Gateway → PostgreSQL (mcp_error_snapshots table)
                                    ↓
                            MCP Gateway API
                                    ↓
                            Console UI
```

**Recommandation**: Commencer avec PostgreSQL pour le MVP, migrer vers OpenSearch ultérieurement si le volume le justifie.

### Table PostgreSQL

```sql
CREATE TABLE mcp_error_snapshots (
    id VARCHAR(50) PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    error_type VARCHAR(50) NOT NULL,
    error_message TEXT NOT NULL,
    error_code VARCHAR(50),
    response_status INTEGER NOT NULL,

    -- Request context
    request_method VARCHAR(10),
    request_path TEXT,
    request_headers JSONB,

    -- User context
    user_id VARCHAR(100),
    tenant_id VARCHAR(100),

    -- MCP context
    mcp_server_name VARCHAR(100),
    mcp_server_url TEXT,
    tool_name VARCHAR(100),
    tool_input_params JSONB,
    tool_duration_ms INTEGER,

    -- LLM context
    llm_provider VARCHAR(50),
    llm_model VARCHAR(100),
    llm_tokens_input INTEGER,
    llm_tokens_output INTEGER,

    -- Cost tracking
    total_cost_usd DECIMAL(10, 6) DEFAULT 0,
    tokens_wasted INTEGER DEFAULT 0,

    -- Retry context
    retry_attempts INTEGER DEFAULT 1,
    retry_max_attempts INTEGER DEFAULT 3,

    -- Resolution
    resolution_status VARCHAR(20) DEFAULT 'unresolved',
    resolution_notes TEXT,
    resolved_at TIMESTAMPTZ,
    resolved_by VARCHAR(100),

    -- Full snapshot JSON for details
    snapshot_data JSONB NOT NULL,

    -- Indexes
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX idx_snapshots_timestamp ON mcp_error_snapshots(timestamp DESC);
CREATE INDEX idx_snapshots_error_type ON mcp_error_snapshots(error_type);
CREATE INDEX idx_snapshots_tenant ON mcp_error_snapshots(tenant_id);
CREATE INDEX idx_snapshots_server ON mcp_error_snapshots(mcp_server_name);
CREATE INDEX idx_snapshots_tool ON mcp_error_snapshots(tool_name);
CREATE INDEX idx_snapshots_status ON mcp_error_snapshots(resolution_status);
```

---

## Ordre d'Implémentation

### Sprint 1: Backend API (2-3 jours)

1. **Alembic migration** pour table `mcp_error_snapshots`
2. **Repository** `src/features/error_snapshots/repository.py`
3. **Router** `src/features/error_snapshots/router.py` avec 5 endpoints
4. **Intégration** avec le publisher existant pour persister en DB
5. **Tests unitaires** des endpoints

### Sprint 2: UI Types & Service (1 jour)

1. **Types** dans `types/index.ts`
2. **Service** `errorSnapshotsApi.ts`
3. **Config** URL MCP Gateway dans `.env`

### Sprint 3: UI Components (2-3 jours)

1. **Page principale** `ErrorSnapshots.tsx` (stats + liste)
2. **SnapshotRow** avec expand/collapse
3. **SnapshotTimeline** pour les retries
4. **ContextViewer** pour JSON
5. **ReplayCommand** avec copy

### Sprint 4: Navigation & Polish (1 jour)

1. **Routing** dans App.tsx
2. **Menu** dans Layout.tsx avec badge
3. **Tests E2E** basiques
4. **Documentation** usage

---

## Métriques de Succès

| Métrique | Cible |
|----------|-------|
| Temps de chargement liste | < 500ms |
| Temps de chargement détail | < 200ms |
| Couverture tests backend | > 80% |
| Erreurs UI console | 0 |

---

## Dépendances

### Backend (MCP Gateway)
- `asyncpg` (déjà installé)
- `sqlalchemy[asyncio]` (déjà installé)

### Frontend (Control-Plane-UI)
- Aucune nouvelle dépendance (Tailwind + Lucide suffisent)

---

## Fichiers à Créer

| Fichier | Type | Description |
|---------|------|-------------|
| `mcp-gateway/src/features/error_snapshots/repository.py` | Backend | CRUD PostgreSQL |
| `mcp-gateway/src/features/error_snapshots/router.py` | Backend | API endpoints |
| `mcp-gateway/alembic/versions/xxx_create_snapshots_table.py` | Backend | Migration |
| `control-plane-ui/src/services/errorSnapshotsApi.ts` | Frontend | Service API |
| `control-plane-ui/src/pages/ErrorSnapshots.tsx` | Frontend | Page principale |
| `control-plane-ui/src/components/snapshots/SnapshotRow.tsx` | Frontend | Composant row |
| `control-plane-ui/src/components/snapshots/SnapshotTimeline.tsx` | Frontend | Timeline |
| `control-plane-ui/src/components/snapshots/ContextViewer.tsx` | Frontend | JSON viewer |
| `control-plane-ui/src/components/snapshots/CostBadge.tsx` | Frontend | Badge coût |
| `control-plane-ui/src/components/snapshots/ReplayCommand.tsx` | Frontend | cURL generator |

## Fichiers à Modifier

| Fichier | Modifications |
|---------|---------------|
| `control-plane-ui/src/types/index.ts` | Ajouter types MCP Error Snapshot |
| `control-plane-ui/src/App.tsx` | Ajouter route `/mcp/errors` |
| `control-plane-ui/src/components/Layout.tsx` | Ajouter lien navigation |
| `mcp-gateway/src/features/error_snapshots/__init__.py` | Exporter router |
| `mcp-gateway/src/main.py` | Inclure router snapshots |
| `mcp-gateway/src/features/error_snapshots/publisher.py` | Persister en DB |

---

## Prêt pour Implémentation

Ce plan fournit une roadmap complète pour implémenter la Phase 4 Error Snapshots UI. La structure s'aligne avec les patterns existants de la Console (Monitoring.tsx) tout en ajoutant les fonctionnalités spécifiques au debugging MCP:

- **Cost tracking** visible
- **Token waste** quantifié
- **Replay capability** intégrée
- **Resolution workflow** pour le suivi
