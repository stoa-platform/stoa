/**
 * Client Certificate Types (CAB-870)
 *
 * Matches backend schemas from control-plane-api/src/schemas/client.py
 */

export interface Client {
  id: string;
  tenant_id: string;
  name: string;
  certificate_cn: string;
  certificate_serial: string | null;
  certificate_fingerprint: string | null;
  certificate_pem: string | null;
  certificate_not_before: string | null;
  certificate_not_after: string | null;
  status: 'active' | 'revoked' | 'expired';
  created_at: string;
  updated_at: string;
  // Rotation fields (CAB-869)
  certificate_fingerprint_previous: string | null;
  previous_cert_expires_at: string | null;
  is_in_grace_period: boolean;
  last_rotated_at: string | null;
  rotation_count: number;
}

export interface ClientWithCertificate extends Client {
  private_key_pem: string;
  grace_period_ends?: string | null;
}

export interface ClientCreate {
  name: string;
}

export interface RotateRequest {
  reason?: string;
  grace_period_hours?: number;
}

export interface ClientStats {
  total: number;
  active: number;
  expiring_soon: number;
  critical: number;
  expired: number;
  revoked: number;
  in_grace_period: number;
}

export type CertificateHealthStatus =
  | 'active'
  | 'expiring_soon'
  | 'critical'
  | 'expired'
  | 'revoked'
  | 'grace_period';

export function getCertificateHealth(client: Client): CertificateHealthStatus {
  if (client.status === 'revoked') return 'revoked';
  if (client.is_in_grace_period) return 'grace_period';
  if (!client.certificate_not_after) return 'active';

  const now = new Date();
  const expiresAt = new Date(client.certificate_not_after);
  const daysRemaining = (expiresAt.getTime() - now.getTime()) / (1000 * 60 * 60 * 24);

  if (daysRemaining <= 0) return 'expired';
  if (daysRemaining < 7) return 'critical';
  if (daysRemaining < 30) return 'expiring_soon';
  return 'active';
}

export function getDaysRemaining(certificateNotAfter: string | null): number | null {
  if (!certificateNotAfter) return null;
  const now = new Date();
  const expiresAt = new Date(certificateNotAfter);
  return Math.max(0, Math.ceil((expiresAt.getTime() - now.getTime()) / (1000 * 60 * 60 * 24)));
}

export function computeClientStats(clients: Client[]): ClientStats {
  const stats: ClientStats = {
    total: clients.length,
    active: 0,
    expiring_soon: 0,
    critical: 0,
    expired: 0,
    revoked: 0,
    in_grace_period: 0,
  };

  for (const client of clients) {
    const health = getCertificateHealth(client);
    switch (health) {
      case 'active': stats.active++; break;
      case 'expiring_soon': stats.expiring_soon++; break;
      case 'critical': stats.critical++; break;
      case 'expired': stats.expired++; break;
      case 'revoked': stats.revoked++; break;
      case 'grace_period': stats.in_grace_period++; break;
    }
  }

  return stats;
}

export const healthColors: Record<CertificateHealthStatus, string> = {
  active: 'bg-green-100 text-green-800',
  expiring_soon: 'bg-yellow-100 text-yellow-800',
  critical: 'bg-orange-100 text-orange-800',
  expired: 'bg-red-100 text-red-800',
  revoked: 'bg-gray-100 text-gray-800',
  grace_period: 'bg-blue-100 text-blue-800',
};

export const healthLabels: Record<CertificateHealthStatus, string> = {
  active: 'Active',
  expiring_soon: 'Expiring Soon',
  critical: 'Critical',
  expired: 'Expired',
  revoked: 'Revoked',
  grace_period: 'Grace Period',
};
