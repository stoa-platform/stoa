/**
 * SubNav tab group definitions (CAB-1785)
 *
 * Separated from SubNav.tsx to avoid react-refresh/only-export-components warnings.
 * Import the relevant group constant in each page alongside the SubNav component.
 */

import {
  Layers,
  FileText,
  ScrollText,
  Users,
  ShieldCheck,
  KeyRound,
  AppWindow,
  Webhook,
  Shield,
  Server,
  GitCompareArrows,
  Rocket,
  Gauge,
  Activity,
  BarChart3,
} from 'lucide-react';
import type { SubNavTab } from './SubNav';

export const apiCatalogTabs: SubNavTab[] = [
  { label: 'APIs', href: '/apis', icon: Layers },
  { label: 'Subscriptions', href: '/subscriptions', icon: FileText },
  { label: 'Contracts', href: '/contracts', icon: ScrollText },
];

export const consumersTabs: SubNavTab[] = [
  { label: 'Consumers', href: '/consumers', icon: Users },
  { label: 'Certificates', href: '/certificates', icon: ShieldCheck },
  { label: 'Credential Mappings', href: '/credential-mappings', icon: KeyRound },
];

export const applicationsTabs: SubNavTab[] = [
  { label: 'Applications', href: '/applications', icon: AppWindow },
  { label: 'Webhooks', href: '/webhooks', icon: Webhook },
  { label: 'Security Profiles', href: '/security-posture', icon: Shield },
];

export const apiDeploymentTabs: SubNavTab[] = [
  { label: 'Deployments', href: '/api-deployments', icon: Rocket },
];

export const gatewayTabs: SubNavTab[] = [
  { label: 'Overview', href: '/gateway', icon: Server },
  { label: 'Registry', href: '/gateways', icon: Server },
  { label: 'Config Sync', href: '/drift', icon: GitCompareArrows },
];

// AR-1: static security posture remains under Governance; runtime guardrail events stay here.
export const observabilityTabs: SubNavTab[] = [
  { label: 'Gateway Health', href: '/observability', icon: Gauge },
  { label: 'Live Calls', href: '/observability/live-calls', icon: Activity },
  { label: 'Security & Guardrails', href: '/observability/security', icon: ShieldCheck },
  { label: 'Expert Mode', href: '/observability/grafana', icon: BarChart3 },
];
