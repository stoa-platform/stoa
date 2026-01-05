# STOA Portal API Integration Fix Plan

> **Project**: STOA Developer Portal
> **Issue**: Portal calling wrong API endpoints - 404 errors
> **Priority**: CRITICAL - Portal is non-functional
> **Date**: 2026-01-05

---

## Executive Summary

The STOA Developer Portal serves **two distinct purposes**:

1. **API Manager** (for Human Users) - Browse APIs, subscribe, test, manage applications
2. **MCP Interface** (for AI Agents) - Discover tools, invoke them, manage the STOA platform

Currently, the portal is broken due to endpoint mismatches. This plan addresses both the immediate fixes AND the architectural changes needed to fulfill both purposes.

---

## Problem Summary

The STOA Developer Portal is experiencing multiple 404 errors because:

1. **Tools Service** calls `/v1/tools` on Control-Plane API, but this endpoint **doesn't exist** there. Tools are served by the **MCP Gateway**.

2. **API Catalog Service** calls `/v1/apis` but Control-Plane API uses **tenant-scoped** endpoints like `/v1/tenants/{tenant_id}/apis`.

3. **Subscriptions Service** calls `/v1/subscriptions` but this endpoint doesn't exist in the current Control-Plane API structure.

4. **Applications Service** calls `/v1/applications` but should use tenant-scoped endpoints.

---

## Architecture Overview

### Two API Clients Required

```
Portal Application
├── apiClient (Control-Plane API)
│   ├── APIs, Applications, Subscriptions (human management)
│   └── Base: https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0
│
└── mcpClient (MCP Gateway)
    ├── MCP Tools (for AI agents)
    └── Base: https://mcp.stoa.cab-i.com
```

### MCP Gateway Purpose

The MCP Gateway is **not** for human tool browsing - it's for **AI agents to manage the STOA platform**:

- AI agents discover platform capabilities via `/mcp/v1/tools`
- AI agents invoke operations via `/mcp/v1/tools/{name}/invoke`
- The tools themselves represent Control-Plane API operations (create tenant, deploy API, etc.)

---

## Current vs Expected Endpoint Mapping

### 1. MCP Tools (WRONG TARGET)

| Portal Service | Current Call | Target API | Status |
|----------------|--------------|------------|--------|
| `tools.ts` | `GET /v1/tools` | Control-Plane API | **WRONG** |
| `tools.ts` | `GET /v1/tools/{id}` | Control-Plane API | **WRONG** |
| `tools.ts` | `GET /v1/tools/categories` | Control-Plane API | **WRONG** |
| `tools.ts` | `POST /v1/tools/subscriptions` | Control-Plane API | **WRONG** |

**Should call MCP Gateway (`mcp.stoa.cab-i.com`):**

| MCP Gateway Endpoint | Description |
|----------------------|-------------|
| `GET /mcp/v1/tools` | List all tools (supports `?tag=`, `?tenant_id=`, pagination) |
| `GET /mcp/v1/tools/{tool_name}` | Get tool details |
| `GET /mcp/v1/tools/tags` | Get all available tags (categories) |
| `POST /mcp/v1/tools/{tool_name}/invoke` | Invoke a tool (requires auth) |

### 2. API Catalog (WRONG STRUCTURE)

| Portal Service | Current Call | Correct Endpoint |
|----------------|--------------|------------------|
| `apiCatalog.ts` | `GET /v1/apis` | `GET /v1/gateway/apis` OR `GET /v1/tenants/{id}/apis` |
| `apiCatalog.ts` | `GET /v1/apis/{id}` | `GET /v1/tenants/{tenant_id}/apis/{id}` |
| `apiCatalog.ts` | `GET /v1/apis/categories` | Not implemented in Control-Plane API |

### 3. Subscriptions (WRONG STRUCTURE)

| Portal Service | Current Call | Correct Endpoint |
|----------------|--------------|------------------|
| `subscriptions.ts` | `GET /v1/subscriptions` | Not directly available |
| `subscriptions.ts` | `POST /v1/subscriptions` | `POST /v1/tenants/{tenant_id}/applications/{app_id}/subscribe/{api_id}` |

### 4. Applications (WRONG STRUCTURE)

| Portal Service | Current Call | Correct Endpoint |
|----------------|--------------|------------------|
| `applications.ts` | `GET /v1/applications` | `GET /v1/tenants/{tenant_id}/applications` |
| `applications.ts` | `POST /v1/applications` | `POST /v1/tenants/{tenant_id}/applications` |

---

## Recommended Solution

### Phase 1: Create MCP Client (Immediate)

The MCP Tools feature should call **MCP Gateway**, not Control-Plane API.

**Files to create:**

#### 1. `portal/src/services/mcpClient.ts` (NEW FILE)

```typescript
/**
 * STOA Developer Portal - MCP Gateway Client
 *
 * Axios instance for MCP Gateway API calls.
 * Used for AI agent tool discovery and invocation.
 */

import axios, { AxiosInstance, AxiosError } from 'axios';
import { config } from '../config';
import { getAccessToken } from './api';

// Create axios instance for MCP Gateway
export const mcpClient: AxiosInstance = axios.create({
  baseURL: config.mcp.baseUrl,
  timeout: config.mcp.timeout,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor - adds Authorization header
mcpClient.interceptors.request.use(
  (reqConfig) => {
    const token = getAccessToken();
    if (token) {
      reqConfig.headers.Authorization = `Bearer ${token}`;
    }
    return reqConfig;
  },
  (error) => Promise.reject(error)
);

// Response interceptor - handle errors
mcpClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response) {
      switch (error.response.status) {
        case 401:
          console.warn('MCP: Unauthorized - authentication required for tool invocation');
          break;
        case 403:
          console.warn('MCP: Forbidden - insufficient permissions');
          break;
        case 404:
          console.warn('MCP: Tool not found');
          break;
        default:
          console.error('MCP: Request failed', error.response.status);
      }
    }
    return Promise.reject(error);
  }
);

export default mcpClient;
```

#### 2. Rewrite `portal/src/services/tools.ts`

```typescript
/**
 * STOA Developer Portal - MCP Tools Service
 *
 * Service for MCP Tool discovery and invocation via MCP Gateway.
 * This enables AI agents to discover and use platform capabilities.
 */

import { mcpClient } from './mcpClient';
import type { MCPTool, MCPToolInvocation, PaginatedResponse } from '../types';

export interface ListToolsParams {
  tag?: string;
  tenant_id?: string;
  cursor?: string;
  limit?: number;
}

export interface InvokeToolParams {
  arguments: Record<string, unknown>;
}

/**
 * MCP Tools service - calls MCP Gateway
 */
export const toolsService = {
  /**
   * List all available MCP tools
   * GET /mcp/v1/tools
   */
  async listTools(params?: ListToolsParams): Promise<{ tools: MCPTool[]; cursor?: string }> {
    const response = await mcpClient.get('/mcp/v1/tools', { params });
    return response.data;
  },

  /**
   * Get a single tool by name
   * GET /mcp/v1/tools/{name}
   */
  async getTool(name: string): Promise<MCPTool> {
    const response = await mcpClient.get(`/mcp/v1/tools/${encodeURIComponent(name)}`);
    return response.data;
  },

  /**
   * Get all available tags (categories)
   * GET /mcp/v1/tools/tags
   */
  async getTags(): Promise<string[]> {
    const response = await mcpClient.get('/mcp/v1/tools/tags');
    return response.data.tags;
  },

  /**
   * Invoke a tool (requires authentication)
   * POST /mcp/v1/tools/{name}/invoke
   */
  async invokeTool(name: string, args: Record<string, unknown>): Promise<MCPToolInvocation> {
    const response = await mcpClient.post(`/mcp/v1/tools/${encodeURIComponent(name)}/invoke`, {
      arguments: args,
    });
    return response.data;
  },

  /**
   * Get MCP server info
   * GET /mcp/v1/
   */
  async getServerInfo(): Promise<{ name: string; version: string }> {
    const response = await mcpClient.get('/mcp/v1/');
    return response.data;
  },
};

export default toolsService;
```

### Phase 2: Add Portal Endpoints to Control-Plane API

Add new endpoints specifically for portal consumers (human users):

**File to create:** `control-plane-api/src/routers/portal.py`

```python
"""
Portal Router - Endpoints for Developer Portal

These endpoints are designed for API consumers (not tenant admins).
They provide cross-tenant views and simplified operations.
"""

from fastapi import APIRouter, Depends, Query
from typing import Optional
from ..auth import get_current_user
from ..schemas.portal import (
    PortalAPIResponse,
    PortalApplicationResponse,
    PortalSubscriptionResponse,
)

router = APIRouter(prefix="/v1/portal", tags=["portal"])


@router.get("/apis")
async def list_published_apis(
    search: Optional[str] = Query(None, description="Search term"),
    category: Optional[str] = Query(None, description="Filter by category"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PortalAPIResponse:
    """
    List all published APIs for the portal catalog.
    No tenant context needed - shows all public APIs.
    """
    # Implementation: Query all APIs with status='published'
    ...


@router.get("/apis/{api_id}")
async def get_api_details(api_id: str):
    """
    Get API details including OpenAPI spec.
    """
    ...


@router.get("/applications")
async def list_user_applications(
    user = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    List applications belonging to the current user.
    Aggregates across all tenants where user has access.
    """
    ...


@router.post("/applications")
async def create_application(
    data: dict,
    user = Depends(get_current_user),
):
    """
    Create a new consumer application.
    Returns client_id and client_secret (secret shown only once).
    """
    ...


@router.get("/subscriptions")
async def list_user_subscriptions(
    user = Depends(get_current_user),
    application_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    List subscriptions for the current user's applications.
    """
    ...


@router.post("/subscriptions")
async def subscribe_to_api(
    data: dict,
    user = Depends(get_current_user),
):
    """
    Subscribe an application to an API.
    """
    ...
```

### Phase 3: Update Portal Services

After Control-Plane API changes:

#### Update `portal/src/services/apiCatalog.ts`

```typescript
/**
 * STOA Developer Portal - API Catalog Service
 *
 * Service for browsing and discovering published APIs.
 */

import { apiClient } from './api';
import type { API, PaginatedResponse } from '../types';

const BASE_PATH = '/v1/portal';

export interface ListAPIsParams {
  page?: number;
  pageSize?: number;
  search?: string;
  category?: string;
}

export const apiCatalogService = {
  /**
   * List all published APIs (marketplace view)
   */
  listAPIs: async (params?: ListAPIsParams): Promise<PaginatedResponse<API>> => {
    const response = await apiClient.get<PaginatedResponse<API>>(`${BASE_PATH}/apis`, {
      params: {
        page: params?.page || 1,
        page_size: params?.pageSize || 20,
        search: params?.search,
        category: params?.category,
      },
    });
    return response.data;
  },

  /**
   * Get a single API by ID
   */
  getAPI: async (id: string): Promise<API> => {
    const response = await apiClient.get<API>(`${BASE_PATH}/apis/${id}`);
    return response.data;
  },

  /**
   * Get OpenAPI specification for an API
   */
  getOpenAPISpec: async (id: string): Promise<object> => {
    const response = await apiClient.get<object>(`${BASE_PATH}/apis/${id}/openapi`);
    return response.data;
  },
};
```

#### Update `portal/src/services/applications.ts`

```typescript
import { apiClient } from './api';
import type { Application, ApplicationCreateRequest, PaginatedResponse } from '../types';

const BASE_PATH = '/v1/portal';

export const applicationsService = {
  listApplications: async (params?: { page?: number; pageSize?: number }) => {
    const response = await apiClient.get<PaginatedResponse<Application>>(`${BASE_PATH}/applications`, {
      params: { page: params?.page || 1, page_size: params?.pageSize || 20 },
    });
    return response.data;
  },

  getApplication: async (id: string): Promise<Application> => {
    const response = await apiClient.get<Application>(`${BASE_PATH}/applications/${id}`);
    return response.data;
  },

  createApplication: async (data: ApplicationCreateRequest): Promise<Application> => {
    const response = await apiClient.post<Application>(`${BASE_PATH}/applications`, data);
    return response.data;
  },

  // ... other methods
};
```

#### Update `portal/src/services/subscriptions.ts`

```typescript
import { apiClient } from './api';
import type { APISubscription, PaginatedResponse } from '../types';

const BASE_PATH = '/v1/portal';

export const subscriptionsService = {
  listSubscriptions: async (params?: { applicationId?: string; page?: number }) => {
    const response = await apiClient.get<PaginatedResponse<APISubscription>>(`${BASE_PATH}/subscriptions`, {
      params: { application_id: params?.applicationId, page: params?.page || 1 },
    });
    return response.data;
  },

  subscribe: async (data: { applicationId: string; apiId: string; plan: string }) => {
    const response = await apiClient.post<APISubscription>(`${BASE_PATH}/subscriptions`, data);
    return response.data;
  },

  // ... other methods
};
```

---

## Immediate Workaround (If Control-Plane API Changes Are Delayed)

### For MCP Tools
Update `tools.ts` to use MCP Gateway immediately (no backend changes needed).

### For API Catalog
Use `/v1/gateway/apis` endpoint (already exists):

```typescript
// Temporary fix in apiCatalog.ts
listAPIs: async (params) => apiClient.get('/v1/gateway/apis', { params }),
```

### For Applications/Subscriptions
These features may need to be disabled until Control-Plane API adds portal endpoints.

---

## Files to Modify

### Immediate (Phase 1)

| File | Action | Priority |
|------|--------|----------|
| `portal/src/services/mcpClient.ts` | CREATE | High |
| `portal/src/services/tools.ts` | REWRITE | High |
| `portal/src/services/index.ts` | UPDATE (export mcpClient) | High |
| `portal/src/types/mcp.ts` | UPDATE (MCP types) | High |

### Backend (Phase 2)

| File | Action | Priority |
|------|--------|----------|
| `control-plane-api/src/routers/portal.py` | CREATE | High |
| `control-plane-api/src/main.py` | ADD router | High |
| `control-plane-api/src/schemas/portal.py` | CREATE | High |

### Portal Services (Phase 3)

| File | Action | Priority |
|------|--------|----------|
| `portal/src/services/apiCatalog.ts` | UPDATE | Medium |
| `portal/src/services/applications.ts` | UPDATE | Medium |
| `portal/src/services/subscriptions.ts` | UPDATE | Medium |

---

## MCP Gateway Endpoint Reference

For `portal/src/services/tools.ts` implementation:

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/mcp/v1/tools` | Optional | List tools (`?tag=`, `?tenant_id=`, `?cursor=`, `?limit=`) |
| GET | `/mcp/v1/tools/{name}` | Optional | Get tool details |
| GET | `/mcp/v1/tools/tags` | Optional | List all tags (for filters) |
| POST | `/mcp/v1/tools/{name}/invoke` | **Required** | Invoke tool |
| GET | `/mcp/v1/` | None | MCP server info |
| GET | `/health` | None | Health check |

---

## Control-Plane API Endpoint Reference

Existing endpoints (for reference):

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/tenants` | List tenants |
| GET | `/v1/tenants/{id}/apis` | List APIs for tenant |
| GET | `/v1/tenants/{id}/applications` | List applications for tenant |
| POST | `/v1/tenants/{id}/applications/{app}/subscribe/{api}` | Subscribe |
| GET | `/v1/gateway/apis` | List all gateway APIs (useful for catalog) |
| GET | `/v1/health` | Health check |

---

## Testing Plan

1. **MCP Tools** (after Phase 1):
   - [ ] Tools Catalog loads tools from MCP Gateway
   - [ ] Tool Detail page shows tool information and input schema
   - [ ] Tool invocation works (with auth)
   - [ ] Tags filter works
   - [ ] AI agent can discover tools via MCP

2. **API Catalog** (after Phase 2/3):
   - [ ] API Catalog shows published APIs
   - [ ] API Detail page loads
   - [ ] OpenAPI spec viewer works

3. **Applications** (after Phase 2/3):
   - [ ] Create application works
   - [ ] List user's applications
   - [ ] Credentials displayed correctly

4. **Subscriptions** (after Phase 2/3):
   - [ ] Subscribe to API works
   - [ ] List subscriptions
   - [ ] Cancel subscription

---

## Conclusion

The portal's API integration issues stem from a design mismatch:
- **MCP Tools** should use MCP Gateway (not Control-Plane API) - for AI agents
- **API/App/Subscription** services assume flat endpoints, but Control-Plane API uses tenant-scoped structure

The recommended approach is:
1. **Immediately** fix MCP Tools to use MCP Gateway
2. **Add** portal-specific endpoints to Control-Plane API
3. **Update** portal services to use new endpoints

This provides clean separation between:
- **Console** (admin/devops) - Tenant-scoped operations
- **Portal** (API consumers) - User-centric operations
- **MCP Gateway** (AI agents) - Platform management via tools
