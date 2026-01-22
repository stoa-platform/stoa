/**
 * STOA E2E Test Personas
 * Based on Ready Player One theme
 */

export interface Persona {
  name: string;
  username: string;
  password: string;
  tenant: string;
  role: 'cpi-admin' | 'tenant-admin' | 'devops' | 'viewer';
  scopes: string[];
  defaultApp: 'portal' | 'console';
}

export type PersonaKey = 'parzival' | 'art3mis' | 'aech' | 'sorrento' | 'i-r0k' | 'anorak';

/**
 * HIGH-FIVE Personas (Tenant: high-five)
 * The good guys - main characters
 */
const highFivePersonas = {
  parzival: {
    name: 'Parzival',
    username: process.env.PARZIVAL_USER || 'parzival@high-five.io',
    password: process.env.PARZIVAL_PASSWORD || '',
    tenant: 'high-five',
    role: 'tenant-admin' as const,
    scopes: ['stoa:catalog:read', 'stoa:catalog:write', 'stoa:subscriptions:read', 'stoa:subscriptions:write'],
    defaultApp: 'console' as const,
  },
  art3mis: {
    name: 'Art3mis',
    username: process.env.ART3MIS_USER || 'art3mis@high-five.io',
    password: process.env.ART3MIS_PASSWORD || '',
    tenant: 'high-five',
    role: 'devops' as const,
    scopes: ['stoa:catalog:read', 'stoa:catalog:write', 'stoa:subscriptions:read'],
    defaultApp: 'portal' as const,
  },
  aech: {
    name: 'Aech',
    username: process.env.AECH_USER || 'aech@high-five.io',
    password: process.env.AECH_PASSWORD || '',
    tenant: 'high-five',
    role: 'viewer' as const,
    scopes: ['stoa:catalog:read', 'stoa:subscriptions:read'],
    defaultApp: 'portal' as const,
  },
};

/**
 * IOI Personas (Tenant: ioi)
 * The competitors
 */
const ioiPersonas = {
  sorrento: {
    name: 'Sorrento',
    username: process.env.SORRENTO_USER || 'sorrento@ioi.corp',
    password: process.env.SORRENTO_PASSWORD || '',
    tenant: 'ioi',
    role: 'tenant-admin' as const,
    scopes: ['stoa:catalog:read', 'stoa:catalog:write', 'stoa:subscriptions:read', 'stoa:subscriptions:write'],
    defaultApp: 'console' as const,
  },
  'i-r0k': {
    name: 'i-R0k',
    username: process.env.I_R0K_USER || 'i-r0k@ioi.corp',
    password: process.env.I_R0K_PASSWORD || '',
    tenant: 'ioi',
    role: 'viewer' as const,
    scopes: ['stoa:catalog:read', 'stoa:subscriptions:read'],
    defaultApp: 'portal' as const,
  },
};

/**
 * Admin Persona (Platform-wide)
 */
const adminPersonas = {
  anorak: {
    name: 'Anorak',
    username: process.env.ANORAK_USER || 'anorak@stoa.cab-i.com',
    password: process.env.ANORAK_PASSWORD || '',
    tenant: '*', // Access to all tenants
    role: 'cpi-admin' as const,
    scopes: ['stoa:admin', 'stoa:platform:read', 'stoa:platform:write'],
    defaultApp: 'console' as const,
  },
};

/**
 * All personas combined
 */
export const PERSONAS: Record<PersonaKey, Persona> = {
  ...highFivePersonas,
  ...ioiPersonas,
  ...adminPersonas,
};

/**
 * Get persona by name
 */
export function getPersona(name: PersonaKey): Persona {
  const persona = PERSONAS[name];
  if (!persona) {
    throw new Error(`Unknown persona: ${name}. Available: ${Object.keys(PERSONAS).join(', ')}`);
  }
  return persona;
}

/**
 * Get all personas for a specific tenant
 */
export function getPersonasByTenant(tenant: string): Persona[] {
  return Object.values(PERSONAS).filter(p => p.tenant === tenant || p.tenant === '*');
}

/**
 * Get storage state path for a persona
 */
export function getAuthStatePath(personaKey: PersonaKey): string {
  return `fixtures/.auth/${personaKey}.json`;
}
