/**
 * DataSeeder — API-first test data factory for E2E tests (CAB-1990)
 *
 * Creates deterministic, named entities via the Control Plane API.
 * Uses real backends from the gateway arena (echo-backend, fapi-echo, llm-mock).
 * Each run is idempotent: 409 (already exists) is treated as success.
 * cleanup() removes all entities created with the given runId.
 */

import { APIRequestContext } from '@playwright/test';

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const API_URL = process.env.STOA_API_URL || 'https://api.gostoa.dev';
const AUTH_URL = process.env.STOA_AUTH_URL || 'https://auth.gostoa.dev';
const KC_REALM = process.env.STOA_KC_REALM || 'stoa';
const KC_CLIENT_ID = process.env.STOA_KC_CLIENT_ID || 'control-plane-ui';
const ADMIN_USER = process.env.ANORAK_USER || 'anorak@gostoa.dev';
const ADMIN_PASSWORD = process.env.ANORAK_PASSWORD || '';

const DEFAULT_TENANT = 'high-five';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SeededAPI {
  id: string;
  name: string;
  display_name: string;
  backend_url: string;
  status: string;
}

export interface SeededMCPServer {
  id: string;
  name: string;
  display_name: string;
  tools_count: number;
}

export interface SeededSubscription {
  id: string;
  api_id: string;
  api_name: string;
  status: string;
}

export interface SeededState {
  runId: string;
  tenant: string;
  apis: SeededAPI[];
  mcpServers: SeededMCPServer[];
  subscriptions: SeededSubscription[];
}

// ---------------------------------------------------------------------------
// Arena backends — real services running in K8s / VPS
// ---------------------------------------------------------------------------

/**
 * Known backends from the gateway arena infrastructure.
 * These are actual echo/mock services used for benchmarks.
 * In local/CI without K8s, the seeder still creates the API records
 * (backends are not health-checked during creation).
 */
const ARENA_BACKENDS = {
  echoBackend: {
    name: 'Echo Backend',
    url: 'http://echo-backend.stoa-system.svc:8888',
    description: 'Lightweight nginx echo (static JSON, <1ms). L0 arena baseline.',
  },
  fapiEcho: {
    name: 'FAPI Echo',
    url: 'http://fapi-echo.stoa-system.svc:8889',
    description: 'Financial-grade API echo for FAPI/OpenBanking scenarios.',
  },
  llmMock: {
    name: 'LLM Mock',
    url: 'http://llm-mock-backend.stoa-system.svc:8889',
    description: 'Mock Anthropic + OpenAI-compatible responses. L1 enterprise benchmark.',
  },
} as const;

// ---------------------------------------------------------------------------
// DataSeeder class
// ---------------------------------------------------------------------------

export class DataSeeder {
  private request: APIRequestContext;
  private token: string | null = null;

  constructor(request: APIRequestContext) {
    this.request = request;
  }

  // -------------------------------------------------------------------------
  // Auth
  // -------------------------------------------------------------------------

  private async getToken(): Promise<string> {
    if (this.token) return this.token;

    const tokenUrl = `${AUTH_URL}/realms/${KC_REALM}/protocol/openid-connect/token`;
    const resp = await this.request.post(tokenUrl, {
      form: {
        grant_type: 'password',
        client_id: KC_CLIENT_ID,
        username: ADMIN_USER,
        password: ADMIN_PASSWORD,
      },
    });

    if (!resp.ok()) {
      throw new Error(`Auth failed (${resp.status()}): ${await resp.text()}`);
    }

    const data = await resp.json();
    this.token = data.access_token;
    return this.token!;
  }

  private async authHeaders(): Promise<Record<string, string>> {
    const token = await this.getToken();
    return {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    };
  }

  // -------------------------------------------------------------------------
  // Seed
  // -------------------------------------------------------------------------

  async seed(
    runId: string = `e2e-${Date.now()}`,
    tenant: string = DEFAULT_TENANT,
  ): Promise<SeededState> {
    const headers = await this.authHeaders();
    const state: SeededState = {
      runId,
      tenant,
      apis: [],
      mcpServers: [],
      subscriptions: [],
    };

    // --- APIs (3 real arena backends) ---
    const apiDefs = [
      {
        name: `echo-api-${runId}`,
        display_name: `${ARENA_BACKENDS.echoBackend.name} (${runId})`,
        backend_url: ARENA_BACKENDS.echoBackend.url,
        description: ARENA_BACKENDS.echoBackend.description,
        tags: ['arena', 'echo', 'benchmark'],
      },
      {
        name: `fapi-echo-${runId}`,
        display_name: `${ARENA_BACKENDS.fapiEcho.name} (${runId})`,
        backend_url: ARENA_BACKENDS.fapiEcho.url,
        description: ARENA_BACKENDS.fapiEcho.description,
        tags: ['arena', 'fapi', 'openbanking'],
      },
      {
        name: `llm-mock-${runId}`,
        display_name: `${ARENA_BACKENDS.llmMock.name} (${runId})`,
        backend_url: ARENA_BACKENDS.llmMock.url,
        description: ARENA_BACKENDS.llmMock.description,
        tags: ['arena', 'llm', 'ai'],
      },
    ];

    for (const apiDef of apiDefs) {
      const resp = await this.request.post(`${API_URL}/v1/tenants/${tenant}/apis`, {
        headers,
        data: { ...apiDef, version: '1.0.0' },
      });

      if (resp.ok()) {
        const api = await resp.json();
        state.apis.push({
          id: api.id,
          name: api.name,
          display_name: api.display_name,
          backend_url: api.backend_url,
          status: api.status,
        });
      } else if (resp.status() === 409) {
        // Already exists — idempotent
        state.apis.push({
          id: apiDef.name,
          name: apiDef.name,
          display_name: apiDef.display_name,
          backend_url: apiDef.backend_url,
          status: 'draft',
        });
      } else {
        console.warn(`Failed to create API ${apiDef.name}: ${resp.status()} ${await resp.text()}`);
      }
    }

    // --- MCP Servers (2 servers) ---
    const mcpDefs = [
      {
        name: `echo-mcp-${runId}`,
        display_name: `Echo MCP Server (${runId})`,
        description: 'Echo backend exposed as MCP server for testing',
        base_url: `${ARENA_BACKENDS.echoBackend.url}/mcp`,
        transport: 'http' as const,
        auth_type: 'none' as const,
        tool_prefix: `echo_${runId.replace(/-/g, '_')}`,
        environment: 'dev',
      },
      {
        name: `llm-mcp-${runId}`,
        display_name: `LLM Mock MCP Server (${runId})`,
        description: 'LLM mock backend exposed as MCP server',
        base_url: `${ARENA_BACKENDS.llmMock.url}/mcp`,
        transport: 'http' as const,
        auth_type: 'none' as const,
        tool_prefix: `llm_${runId.replace(/-/g, '_')}`,
        environment: 'dev',
      },
    ];

    for (const mcpDef of mcpDefs) {
      const resp = await this.request.post(`${API_URL}/v1/admin/external-mcp-servers`, {
        headers,
        data: mcpDef,
      });

      if (resp.ok()) {
        const server = await resp.json();
        state.mcpServers.push({
          id: server.id,
          name: server.name,
          display_name: server.display_name,
          tools_count: server.tools_count ?? 0,
        });
      } else if (resp.status() === 409) {
        state.mcpServers.push({
          id: mcpDef.name,
          name: mcpDef.name,
          display_name: mcpDef.display_name,
          tools_count: 0,
        });
      } else {
        console.warn(
          `Failed to create MCP server ${mcpDef.name}: ${resp.status()} ${await resp.text()}`,
        );
      }
    }

    // --- Subscriptions (3 ��� one per API) ---
    for (const api of state.apis) {
      const resp = await this.request.post(`${API_URL}/v1/subscriptions`, {
        headers,
        data: {
          application_id: `e2e-app-${runId}`,
          application_name: `E2E App (${runId})`,
          api_id: api.name,
          api_name: api.display_name,
          api_version: '1.0.0',
          tenant_id: tenant,
          plan_name: 'default',
        },
      });

      if (resp.ok()) {
        const sub = await resp.json();
        state.subscriptions.push({
          id: sub.id,
          api_id: api.name,
          api_name: api.display_name,
          status: sub.status,
        });
      } else if (resp.status() === 409) {
        state.subscriptions.push({
          id: `sub-${api.name}`,
          api_id: api.name,
          api_name: api.display_name,
          status: 'pending',
        });
      } else {
        console.warn(
          `Failed to create subscription for ${api.name}: ${resp.status()} ${await resp.text()}`,
        );
      }
    }

    return state;
  }

  // -------------------------------------------------------------------------
  // Cleanup
  // -------------------------------------------------------------------------

  async cleanup(state: SeededState): Promise<void> {
    const headers = await this.authHeaders();

    // Delete subscriptions first (depend on APIs)
    for (const sub of state.subscriptions) {
      try {
        await this.request.post(`${API_URL}/v1/subscriptions/${sub.id}/revoke`, { headers });
      } catch {
        // Best-effort cleanup
      }
    }

    // Delete MCP servers
    for (const server of state.mcpServers) {
      try {
        await this.request.delete(`${API_URL}/v1/admin/external-mcp-servers/${server.id}`, {
          headers,
        });
      } catch {
        // Best-effort cleanup
      }
    }

    // Delete APIs
    for (const api of state.apis) {
      try {
        await this.request.delete(`${API_URL}/v1/tenants/${state.tenant}/apis/${api.id}`, {
          headers,
        });
      } catch {
        // Best-effort cleanup
      }
    }
  }
}
