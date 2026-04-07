/**
 * ToolPermissionsMatrix — per-tenant tool allow/deny matrix.
 *
 * Displays MCP servers and their tools in a matrix layout.
 * Tenant admins can toggle allowed/denied per tool and bulk-toggle per server.
 * Default-allow: tools without an explicit permission row are allowed.
 *
 * CAB-1982
 */
import { useState, useCallback, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Shield,
  ShieldCheck,
  ShieldX,
  Server,
  Wrench,
  Save,
  RotateCcw,
  CheckCircle2,
  XCircle,
  Loader2,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { apiService } from '../services/api';
import { externalMcpServersService } from '../services/externalMcpServersApi';
import type { TenantToolPermission, ExternalMCPServer } from '../types';

const ACTIVE_TENANT_KEY = 'stoa-active-tenant';

/** Local state: tool_name → allowed */
type PermissionDraft = Map<string, boolean>;

/** Keyed by server_id */
type ServerPermissions = Map<string, PermissionDraft>;

interface ServerWithTools {
  server: ExternalMCPServer;
  tools: { name: string; description?: string }[];
}

export function ToolPermissionsMatrix() {
  const { user, hasPermission, hasRole } = useAuth();
  const queryClient = useQueryClient();
  const tenantId = localStorage.getItem(ACTIVE_TENANT_KEY) || user?.tenant_id || '';

  const canEdit = hasRole('cpi-admin') || hasRole('tenant-admin');

  // Track unsaved changes: server_id → (tool_name → allowed)
  const [draft, setDraft] = useState<ServerPermissions>(new Map());
  const [expandedServers, setExpandedServers] = useState<Set<string>>(new Set());
  const [saveSuccess, setSaveSuccess] = useState(false);

  // ---- Data fetching ----

  const {
    data: serversResponse,
    isLoading: serversLoading,
    error: serversError,
  } = useQuery({
    queryKey: ['external-mcp-servers', tenantId],
    queryFn: () => externalMcpServersService.listServers({ page_size: 100 }),
    enabled: !!tenantId,
  });

  const servers = useMemo(() => serversResponse?.servers ?? [], [serversResponse]);

  // Fetch tools for each server
  const serverIds = useMemo(() => servers.map((s) => s.id), [servers]);
  const { data: serverDetails, isLoading: detailsLoading } = useQuery({
    queryKey: ['external-mcp-server-details', serverIds],
    queryFn: async () => {
      const details = await Promise.all(
        servers.map((s) => externalMcpServersService.getServer(s.id))
      );
      return details;
    },
    enabled: servers.length > 0,
  });

  const { data: permissionsResponse, isLoading: permissionsLoading } = useQuery({
    queryKey: ['tool-permissions', tenantId],
    queryFn: () => apiService.listToolPermissions(tenantId, { page_size: 100 }),
    enabled: !!tenantId,
  });

  // Build a lookup: `${server_id}:${tool_name}` → permission
  const permissionMap = useMemo(() => {
    const items = permissionsResponse?.items ?? [];
    const map = new Map<string, TenantToolPermission>();
    for (const p of items) {
      map.set(`${p.mcp_server_id}:${p.tool_name}`, p);
    }
    return map;
  }, [permissionsResponse]);

  // Build server+tools list — platform servers first
  const serversWithTools: ServerWithTools[] = useMemo(() => {
    if (!serverDetails) return [];
    return serverDetails
      .filter((d) => d.tools.length > 0)
      .map((d) => ({
        server: servers.find((s) => s.id === d.id) ?? d,
        tools: d.tools.map((t) => ({ name: t.name, description: t.description })),
      }))
      .sort((a, b) => (b.server.is_platform ? 1 : 0) - (a.server.is_platform ? 1 : 0));
  }, [serverDetails, servers]);

  // ---- Permission state resolution ----

  const getToolAllowed = useCallback(
    (serverId: string, toolName: string): boolean => {
      // Draft takes precedence
      const serverDraft = draft.get(serverId);
      if (serverDraft?.has(toolName)) {
        return serverDraft.get(toolName)!;
      }
      // Check existing permissions (default-allow if no row)
      const existing = permissionMap.get(`${serverId}:${toolName}`);
      return existing?.allowed ?? true;
    },
    [draft, permissionMap]
  );

  const hasChanges = draft.size > 0 && Array.from(draft.values()).some((m) => m.size > 0);

  // ---- Draft mutations ----

  const toggleTool = useCallback(
    (serverId: string, toolName: string) => {
      if (!canEdit) return;
      const current = getToolAllowed(serverId, toolName);
      setDraft((prev) => {
        const next = new Map(prev);
        const serverDraft = new Map(next.get(serverId) ?? new Map());
        serverDraft.set(toolName, !current);
        next.set(serverId, serverDraft);
        return next;
      });
    },
    [canEdit, getToolAllowed]
  );

  const toggleServer = useCallback(
    (serverId: string, tools: { name: string }[], allowed: boolean) => {
      if (!canEdit) return;
      setDraft((prev) => {
        const next = new Map(prev);
        const serverDraft = new Map<string, boolean>();
        for (const tool of tools) {
          serverDraft.set(tool.name, allowed);
        }
        next.set(serverId, serverDraft);
        return next;
      });
    },
    [canEdit]
  );

  const resetDraft = useCallback(() => {
    setDraft(new Map());
  }, []);

  // ---- Save mutations ----

  const saveMutation = useMutation({
    mutationFn: async () => {
      const operations: Promise<unknown>[] = [];
      for (const [serverId, toolDraft] of draft.entries()) {
        for (const [toolName, allowed] of toolDraft.entries()) {
          operations.push(
            apiService.upsertToolPermission(tenantId, {
              mcp_server_id: serverId,
              tool_name: toolName,
              allowed,
            })
          );
        }
      }
      await Promise.all(operations);
    },
    onSuccess: () => {
      setDraft(new Map());
      queryClient.invalidateQueries({ queryKey: ['tool-permissions', tenantId] });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    },
  });

  const toggleServerExpanded = useCallback((serverId: string) => {
    setExpandedServers((prev) => {
      const next = new Set(prev);
      if (next.has(serverId)) {
        next.delete(serverId);
      } else {
        next.add(serverId);
      }
      return next;
    });
  }, []);

  // ---- Permission check ----

  if (!hasPermission('apis:read')) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-zinc-400">You do not have permission to view this page.</p>
      </div>
    );
  }

  if (!tenantId) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-zinc-400">No tenant selected. Please select a tenant first.</p>
      </div>
    );
  }

  const isLoading = serversLoading || detailsLoading || permissionsLoading;

  // ---- Server stats ----

  const getServerStats = (swt: ServerWithTools) => {
    const total = swt.tools.length;
    let allowed = 0;
    for (const tool of swt.tools) {
      if (getToolAllowed(swt.server.id, tool.name)) {
        allowed++;
      }
    }
    return { total, allowed, denied: total - allowed };
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zinc-100 flex items-center gap-2">
            <Shield className="h-6 w-6 text-emerald-400" />
            Tool Permissions
          </h1>
          <p className="mt-1 text-sm text-zinc-400">
            Control which MCP tools are available for this tenant. Tools are allowed by default.
          </p>
        </div>
        {canEdit && (
          <div className="flex items-center gap-2">
            {saveSuccess && (
              <span className="flex items-center gap-1 text-sm text-emerald-400">
                <CheckCircle2 className="h-4 w-4" />
                Saved
              </span>
            )}
            {saveMutation.isError && (
              <span className="flex items-center gap-1 text-sm text-red-400">
                <XCircle className="h-4 w-4" />
                Save failed
              </span>
            )}
            <button
              onClick={resetDraft}
              disabled={!hasChanges}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-zinc-700 text-zinc-300 hover:bg-zinc-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Reset
            </button>
            <button
              onClick={() => saveMutation.mutate()}
              disabled={!hasChanges || saveMutation.isPending}
              className="flex items-center gap-1.5 px-4 py-1.5 text-sm rounded-lg bg-emerald-600 text-white hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {saveMutation.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Save className="h-3.5 w-3.5" />
              )}
              Save Changes
            </button>
          </div>
        )}
      </div>

      {/* Unsaved changes banner */}
      {hasChanges && (
        <div className="flex items-center gap-2 px-4 py-2 bg-amber-900/30 border border-amber-700/50 rounded-lg text-sm text-amber-300">
          <Shield className="h-4 w-4 flex-shrink-0" />
          You have unsaved changes. Click &quot;Save Changes&quot; to apply.
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center h-48">
          <Loader2 className="h-8 w-8 animate-spin text-zinc-500" />
        </div>
      )}

      {/* Error */}
      {serversError && (
        <div className="p-4 bg-red-900/20 border border-red-800/50 rounded-lg text-red-300">
          Failed to load MCP servers. Please try again.
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !serversError && serversWithTools.length === 0 && (
        <div className="flex flex-col items-center justify-center h-48 text-zinc-400">
          <Server className="h-10 w-10 mb-2 opacity-50" />
          <p>No MCP servers with tools found.</p>
          <p className="text-sm mt-1">Add external MCP servers to manage tool permissions.</p>
        </div>
      )}

      {/* Server list */}
      {!isLoading &&
        serversWithTools.map((swt) => {
          const isExpanded = expandedServers.has(swt.server.id);
          const stats = getServerStats(swt);
          const allAllowed = stats.denied === 0;
          const allDenied = stats.allowed === 0;

          return (
            <div
              key={swt.server.id}
              className="border border-zinc-800 rounded-lg bg-zinc-900/50 overflow-hidden"
            >
              {/* Server header */}
              <div className="flex items-center justify-between px-4 py-3 bg-zinc-900/80">
                <button
                  onClick={() => toggleServerExpanded(swt.server.id)}
                  className="flex items-center gap-2 text-left flex-1 min-w-0"
                >
                  {isExpanded ? (
                    <ChevronDown className="h-4 w-4 text-zinc-400 flex-shrink-0" />
                  ) : (
                    <ChevronRight className="h-4 w-4 text-zinc-400 flex-shrink-0" />
                  )}
                  <Server className="h-4 w-4 text-zinc-400 flex-shrink-0" />
                  <span className="font-medium text-zinc-200 truncate">
                    {swt.server.display_name || swt.server.name}
                  </span>
                  {swt.server.is_platform && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-800/40 text-blue-400 flex-shrink-0">
                      Platform
                    </span>
                  )}
                  <span className="text-xs text-zinc-500 flex-shrink-0">
                    {stats.total} tool{stats.total !== 1 ? 's' : ''}
                  </span>
                </button>
                <div className="flex items-center gap-3 ml-4">
                  {/* Stats badges */}
                  <span className="flex items-center gap-1 text-xs">
                    <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
                    <span className="text-emerald-400">{stats.allowed}</span>
                  </span>
                  {stats.denied > 0 && (
                    <span className="flex items-center gap-1 text-xs">
                      <ShieldX className="h-3.5 w-3.5 text-red-400" />
                      <span className="text-red-400">{stats.denied}</span>
                    </span>
                  )}
                  {/* Bulk actions */}
                  {canEdit && (
                    <div className="flex items-center gap-1 ml-2">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleServer(swt.server.id, swt.tools, true);
                        }}
                        disabled={allAllowed}
                        className="px-2 py-0.5 text-xs rounded border border-emerald-700/50 text-emerald-400 hover:bg-emerald-900/30 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                        title="Allow all tools on this server"
                      >
                        Allow all
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleServer(swt.server.id, swt.tools, false);
                        }}
                        disabled={allDenied}
                        className="px-2 py-0.5 text-xs rounded border border-red-700/50 text-red-400 hover:bg-red-900/30 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                        title="Deny all tools on this server"
                      >
                        Deny all
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {/* Tools list */}
              {isExpanded && (
                <div className="divide-y divide-zinc-800/50">
                  {swt.tools.map((tool) => {
                    const allowed = getToolAllowed(swt.server.id, tool.name);
                    const isDrafted = draft.get(swt.server.id)?.has(tool.name) ?? false;

                    return (
                      <div
                        key={tool.name}
                        className={`flex items-center justify-between px-4 py-2.5 pl-10 ${
                          isDrafted ? 'bg-amber-900/10' : ''
                        }`}
                      >
                        <div className="flex items-center gap-2 min-w-0 flex-1">
                          <Wrench className="h-3.5 w-3.5 text-zinc-500 flex-shrink-0" />
                          <span className="text-sm text-zinc-300 truncate">{tool.name}</span>
                          {tool.description && (
                            <span className="text-xs text-zinc-500 truncate hidden sm:inline">
                              — {tool.description}
                            </span>
                          )}
                          {isDrafted && (
                            <span className="text-[10px] px-1 py-0.5 rounded bg-amber-800/40 text-amber-400 flex-shrink-0">
                              modified
                            </span>
                          )}
                        </div>
                        <button
                          onClick={() => toggleTool(swt.server.id, tool.name)}
                          disabled={!canEdit}
                          className={`flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-full font-medium transition-colors ${
                            allowed
                              ? 'bg-emerald-900/40 text-emerald-400 border border-emerald-700/50 hover:bg-emerald-900/60'
                              : 'bg-red-900/40 text-red-400 border border-red-700/50 hover:bg-red-900/60'
                          } ${!canEdit ? 'cursor-not-allowed opacity-60' : ''}`}
                          title={allowed ? 'Click to deny' : 'Click to allow'}
                        >
                          {allowed ? (
                            <>
                              <ShieldCheck className="h-3 w-3" />
                              Allowed
                            </>
                          ) : (
                            <>
                              <ShieldX className="h-3 w-3" />
                              Denied
                            </>
                          )}
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
    </div>
  );
}
