// STOA Design System — Canonical Environment Constants
// Single source of truth for environment colors, labels, and normalization.
// Used by Console, Portal, and shared components.

export type CanonicalEnvironment = 'development' | 'staging' | 'production';

/**
 * Page-level scope declaration for environment-aware behavior.
 * - 'environment': Data is filtered by active environment — read-only guards apply (APIs, Deployments)
 * - 'global': Data is platform-wide, cross-environment — no read-only guards (Gateways, Tenants, Settings)
 * - 'tenant': Data is tenant-scoped, env filtering may or may not be available
 */
export type PageScope = 'environment' | 'global' | 'tenant';

export interface EnvironmentColorSet {
  dot: string;
  bg: string;
  bgDark: string;
  text: string;
  textDark: string;
  border: string;
  borderDark: string;
  chrome: string;
  chromeText: string;
}

export const ENV_ORDER: CanonicalEnvironment[] = ['production', 'staging', 'development'];

export const ENV_LABELS: Record<CanonicalEnvironment, string> = {
  production: 'Production',
  staging: 'Staging',
  development: 'Development',
};

export const ENV_LABELS_PORTAL: Record<CanonicalEnvironment, string> = {
  production: 'Production',
  staging: 'Staging',
  development: 'Sandbox',
};

export const ENV_COLORS: Record<CanonicalEnvironment, EnvironmentColorSet> = {
  development: {
    dot: 'bg-green-500',
    bg: 'bg-green-50',
    bgDark: 'dark:bg-green-950/30',
    text: 'text-green-700',
    textDark: 'dark:text-green-400',
    border: 'border-green-200',
    borderDark: 'dark:border-green-800',
    chrome: 'bg-green-600',
    chromeText: 'text-white',
  },
  staging: {
    dot: 'bg-amber-500',
    bg: 'bg-amber-50',
    bgDark: 'dark:bg-amber-950/30',
    text: 'text-amber-700',
    textDark: 'dark:text-amber-400',
    border: 'border-amber-200',
    borderDark: 'dark:border-amber-800',
    chrome: 'bg-amber-500',
    chromeText: 'text-white',
  },
  production: {
    dot: 'bg-red-500',
    bg: 'bg-red-50',
    bgDark: 'dark:bg-red-950/30',
    text: 'text-red-700',
    textDark: 'dark:text-red-400',
    border: 'border-red-200',
    borderDark: 'dark:border-red-800',
    chrome: 'bg-red-600',
    chromeText: 'text-white',
  },
};

const ENV_ALIASES: Record<string, CanonicalEnvironment> = {
  dev: 'development',
  development: 'development',
  sandbox: 'development',
  stg: 'staging',
  staging: 'staging',
  prod: 'production',
  production: 'production',
};

export function normalizeEnvironment(env: string): CanonicalEnvironment {
  return ENV_ALIASES[env.toLowerCase()] ?? 'development';
}

export function getEnvColors(env: string): EnvironmentColorSet {
  return ENV_COLORS[normalizeEnvironment(env)];
}

export function getEnvLabel(env: string, portal = false): string {
  const canonical = normalizeEnvironment(env);
  return portal ? ENV_LABELS_PORTAL[canonical] : ENV_LABELS[canonical];
}
