import { Activity, GitBranch, Globe, Server, Shield, Zap, type LucideIcon } from 'lucide-react';
import type { GatewayInstance, GatewayMode } from '../../types';

export const TYPE_DISPLAY: Record<string, { label: string; icon: LucideIcon }> = {
  stoa: { label: 'STOA', icon: Zap },
  stoa_edge_mcp: { label: 'STOA Edge MCP', icon: Zap },
  stoa_sidecar: { label: 'STOA Link', icon: Shield },
  stoa_proxy: { label: 'STOA Proxy', icon: Globe },
  stoa_shadow: { label: 'STOA Shadow', icon: Activity },
  webmethods: { label: 'webMethods', icon: Server },
  kong: { label: 'Kong', icon: Server },
  apigee: { label: 'Apigee', icon: Server },
  aws_apigateway: { label: 'AWS API GW', icon: Server },
  azure_apim: { label: 'Azure APIM', icon: Server },
  gravitee: { label: 'Gravitee', icon: Server },
  stoa_connect: { label: 'STOA Connect', icon: GitBranch },
};

export const MODE_LABELS: Record<GatewayMode, string> = {
  'edge-mcp': 'Edge MCP',
  sidecar: 'STOA Link',
  proxy: 'Proxy',
  shadow: 'Shadow',
  connect: 'Connect',
};

const TARGET_LABELS: Record<string, string> = {
  stoa: 'STOA',
  kong: 'Kong',
  webmethods: 'webMethods',
  gravitee: 'Gravitee',
  agentgateway: 'Agent Gateway',
};

const TOPOLOGY_LABELS: Record<string, string> = {
  'native-edge': 'Native edge',
  'remote-agent': 'Remote link',
  'same-pod': 'Same-pod sidecar',
};

const ENDPOINT_ALIASES: Record<string, string[]> = {
  public_url: ['public_url', 'publicUrl', 'public', 'runtime_url', 'runtimeUrl', 'external_url'],
  ui_url: ['ui_url', 'uiUrl', 'console_url', 'consoleUrl', 'web_ui_url', 'webUiUrl'],
  target_gateway_url: ['target_gateway_url', 'targetGatewayUrl', 'target_url', 'targetUrl'],
  admin_url: ['admin_url', 'adminUrl', 'admin', 'base_url', 'baseUrl'],
  internal_url: ['internal_url', 'internalUrl', 'internal'],
};

export type GatewayUrls = {
  publicUrl: string | null;
  uiUrl: string | null;
  targetUrl: string | null;
  baseUrl: string | null;
  primaryUrl: string | null;
};

export type GatewayExternalLink = {
  label: string;
  href: string;
  icon: LucideIcon;
};

function cleanUrl(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function endpointValue(gw: GatewayInstance, canonicalKey: string): string | null {
  const endpoints = gw.endpoints ?? {};
  for (const key of ENDPOINT_ALIASES[canonicalKey] ?? [canonicalKey]) {
    const value = cleanUrl(endpoints[key]);
    if (value) return value;
  }
  return null;
}

function isInternalUrl(value: string): boolean {
  if (!/^https?:\/\//i.test(value)) return true;
  try {
    const host = new URL(value).hostname.toLowerCase();
    return (
      host === 'localhost' ||
      host === '127.0.0.1' ||
      host === '0.0.0.0' ||
      host.endsWith('.svc') ||
      host.includes('.svc.cluster.local') ||
      host.endsWith('.cluster.local')
    );
  } catch {
    return true;
  }
}

export function externalUrl(value: unknown): string | null {
  const url = cleanUrl(value);
  return url && !isInternalUrl(url) ? url : null;
}

function hostname(value: string | null): string {
  if (!value) return '';
  try {
    return new URL(value).hostname.toLowerCase();
  } catch {
    return value.toLowerCase();
  }
}

export function displayUrl(value: string | null): string {
  return value?.replace(/^https?:\/\//, '') ?? '--';
}

export function gatewayUrls(gw: GatewayInstance): GatewayUrls {
  const publicUrl = externalUrl(gw.public_url) ?? externalUrl(endpointValue(gw, 'public_url'));
  const uiUrl = externalUrl(gw.ui_url) ?? externalUrl(endpointValue(gw, 'ui_url'));
  const targetUrl =
    externalUrl(gw.target_gateway_url) ?? externalUrl(endpointValue(gw, 'target_gateway_url'));
  const baseUrl = cleanUrl(gw.base_url) ?? endpointValue(gw, 'admin_url');
  const externalBaseUrl = baseUrl ? externalUrl(baseUrl) : null;

  return {
    publicUrl,
    uiUrl,
    targetUrl,
    baseUrl,
    primaryUrl: publicUrl ?? targetUrl ?? uiUrl ?? externalBaseUrl ?? baseUrl,
  };
}

function isLinkRuntime(gw: GatewayInstance, urls: GatewayUrls): boolean {
  return (
    gw.mode === 'sidecar' ||
    gw.gateway_type === 'stoa_sidecar' ||
    hostname(urls.publicUrl).includes('-link.') ||
    (gw.tags ?? []).includes('remote-agent')
  );
}

export function deploymentLabel(gw: GatewayInstance): string | null {
  const urls = gatewayUrls(gw);
  if (gw.deployment_mode === 'edge') return 'Edge';
  if (gw.deployment_mode === 'sidecar') return 'Sidecar';
  if (gw.deployment_mode === 'connect') {
    if (isLinkRuntime(gw, urls)) {
      const publicHost = hostname(urls.publicUrl);
      if (publicHost.includes('-k3s.')) return 'Link K8s';
      if (publicHost.includes('-link.')) return 'Link VPS';
      return 'STOA Link';
    }
    return 'Connect VPS';
  }
  return gw.mode ? (MODE_LABELS[gw.mode] ?? gw.mode) : null;
}

export function targetLabel(gw: GatewayInstance, fallback: string): string {
  if (gw.target_gateway_type) {
    return TARGET_LABELS[gw.target_gateway_type] ?? gw.target_gateway_type;
  }
  return fallback;
}

export function topologyLabel(gw: GatewayInstance): string | null {
  if (!gw.topology) return null;
  return TOPOLOGY_LABELS[gw.topology] ?? gw.topology;
}

export function gatewayExternalLinks(urls: GatewayUrls): GatewayExternalLink[] {
  const seen = new Set<string>();
  return [
    { label: 'Runtime', href: urls.publicUrl, icon: Zap },
    { label: 'Third-party UI', href: urls.uiUrl, icon: Globe },
    { label: 'Target', href: urls.targetUrl, icon: Server },
  ].flatMap((link) => {
    if (!link.href || seen.has(link.href)) return [];
    seen.add(link.href);
    return [{ ...link, href: link.href }];
  });
}
