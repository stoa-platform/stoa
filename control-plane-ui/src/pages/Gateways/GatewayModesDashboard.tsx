import { useState, useEffect } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';
import { CardSkeleton } from '@stoa/shared/components/Skeleton';
import type { GatewayMode } from '../../types';

interface ModeConfig {
  id: GatewayMode;
  name: string;
  description: string;
  icon: string;
  color: string;
  bgColor: string;
  borderColor: string;
}

const modeConfigs: ModeConfig[] = [
  {
    id: 'edge-mcp',
    name: 'Edge MCP',
    description: 'MCP protocol with SSE transport for AI-native API access',
    icon: 'M13 10V3L4 14h7v7l9-11h-7z', // Lightning bolt
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-200',
  },
  {
    id: 'sidecar',
    name: 'Sidecar',
    description: 'Policy enforcement behind existing gateway (Kong, Envoy, Apigee)',
    icon: 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z', // Shield
    color: 'text-emerald-600',
    bgColor: 'bg-emerald-50',
    borderColor: 'border-emerald-200',
  },
  {
    id: 'proxy',
    name: 'Proxy',
    description: 'Inline request/response transformation with rate limiting',
    icon: 'M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4', // Arrows right-left
    color: 'text-purple-600',
    bgColor: 'bg-purple-50',
    borderColor: 'border-purple-200',
  },
  {
    id: 'shadow',
    name: 'Shadow',
    description: 'Passive traffic capture and UAC contract auto-generation',
    icon: 'M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z', // Eye
    color: 'text-orange-600',
    bgColor: 'bg-orange-50',
    borderColor: 'border-orange-200',
  },
];

interface ModeStats {
  mode: string;
  total: number;
  online: number;
  offline: number;
  degraded: number;
}

export function GatewayModesDashboard() {
  const { isReady } = useAuth();
  const [stats, setStats] = useState<{ modes: ModeStats[]; total_gateways: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isReady) {
      loadStats();
    }
  }, [isReady]);

  const loadStats = async () => {
    try {
      setLoading(true);
      const data = await apiService.getGatewayModeStats();
      setStats(data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load gateway mode stats');
    } finally {
      setLoading(false);
    }
  };

  const getModeStat = (modeId: string): ModeStats => {
    const found = stats?.modes.find((m) => m.mode === modeId);
    return found || { mode: modeId, total: 0, online: 0, offline: 0, degraded: 0 };
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-64 bg-gray-200 rounded animate-pulse" />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {[1, 2, 3, 4].map((i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Gateway Modes</h1>
        <p className="text-gray-500 mt-1">
          STOA Gateway deployment modes across your infrastructure (ADR-024)
        </p>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {/* Total Summary */}
      <div className="bg-gradient-to-r from-indigo-500 to-purple-600 rounded-xl p-6 text-white">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-indigo-100 text-sm font-medium">Total STOA Gateways</p>
            <p className="text-4xl font-bold mt-1">{stats?.total_gateways || 0}</p>
          </div>
          <div className="text-right">
            <p className="text-indigo-100 text-sm">Unified Architecture</p>
            <p className="text-lg font-medium mt-1">4 Deployment Modes</p>
          </div>
        </div>
      </div>

      {/* Mode Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {modeConfigs.map((mode) => {
          const stat = getModeStat(mode.id);
          return (
            <div
              key={mode.id}
              className={`${mode.bgColor} ${mode.borderColor} border-2 rounded-xl overflow-hidden hover:shadow-lg transition-shadow`}
            >
              <div className="p-6">
                {/* Icon + Name */}
                <div className="flex items-center gap-3 mb-4">
                  <div className={`p-2 rounded-lg bg-white shadow-sm ${mode.color}`}>
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d={mode.icon}
                      />
                    </svg>
                  </div>
                  <h3 className="text-lg font-semibold text-gray-900">{mode.name}</h3>
                </div>

                {/* Description */}
                <p className="text-sm text-gray-600 mb-4 min-h-[40px]">{mode.description}</p>

                {/* Stats */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-2xl font-bold text-gray-900">{stat.total}</span>
                    <span className="text-sm text-gray-500">instances</span>
                  </div>

                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div className="bg-white rounded-lg px-2 py-1.5 shadow-sm">
                      <div className="text-green-600 font-semibold">{stat.online}</div>
                      <div className="text-xs text-gray-500">online</div>
                    </div>
                    <div className="bg-white rounded-lg px-2 py-1.5 shadow-sm">
                      <div className="text-yellow-600 font-semibold">{stat.degraded}</div>
                      <div className="text-xs text-gray-500">degraded</div>
                    </div>
                    <div className="bg-white rounded-lg px-2 py-1.5 shadow-sm">
                      <div className="text-gray-600 font-semibold">{stat.offline}</div>
                      <div className="text-xs text-gray-500">offline</div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Footer */}
              <div className="px-6 py-3 bg-white/50 border-t border-white/20">
                <a
                  href={`/admin/gateways?mode=${mode.id}`}
                  className={`text-sm font-medium ${mode.color} hover:underline`}
                >
                  View {mode.name} gateways &rarr;
                </a>
              </div>
            </div>
          );
        })}
      </div>

      {/* Architecture Info */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          STOA Gateway Architecture (ADR-024)
        </h2>
        <div className="prose prose-sm text-gray-600">
          <p>
            The STOA Gateway uses a unified architecture with 4 deployment modes, all from a single
            Rust binary:
          </p>
          <ul className="mt-2 space-y-1">
            <li>
              <strong>Edge MCP:</strong> Native MCP protocol with SSE transport for AI agents
              (Claude, GPT, etc.)
            </li>
            <li>
              <strong>Sidecar:</strong> Policy enforcement deployed alongside existing gateways
            </li>
            <li>
              <strong>Proxy:</strong> Full inline proxy with request/response transformation
            </li>
            <li>
              <strong>Shadow:</strong> Passive traffic observation for auto-generating API contracts
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}
