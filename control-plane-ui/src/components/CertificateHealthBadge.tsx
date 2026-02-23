import type { CertificateStatus } from '../types';

interface Props {
  status?: CertificateStatus;
  notAfter?: string;
  className?: string;
}

function getDaysUntilExpiry(notAfter: string): number {
  const now = new Date();
  const expiry = new Date(notAfter);
  return Math.floor((expiry.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
}

type HealthLevel = 'valid' | 'expiring-soon' | 'expiring' | 'critical' | 'expired' | 'revoked';

function getHealthLevel(status?: CertificateStatus, notAfter?: string): HealthLevel {
  if (status === 'revoked') return 'revoked';
  if (status === 'expired') return 'expired';

  if (!notAfter) return 'valid';

  const days = getDaysUntilExpiry(notAfter);
  if (days <= 0) return 'expired';
  if (days <= 7) return 'critical';
  if (days <= 30) return 'expiring';
  if (days <= 90) return 'expiring-soon';
  return 'valid';
}

const healthStyles: Record<HealthLevel, { bg: string; text: string; label: string }> = {
  valid: {
    bg: 'bg-green-100 dark:bg-green-900/30',
    text: 'text-green-800 dark:text-green-400',
    label: 'Valid',
  },
  'expiring-soon': {
    bg: 'bg-yellow-100 dark:bg-yellow-900/30',
    text: 'text-yellow-800 dark:text-yellow-400',
    label: 'Expiring Soon',
  },
  expiring: {
    bg: 'bg-orange-100 dark:bg-orange-900/30',
    text: 'text-orange-800 dark:text-orange-400',
    label: 'Expiring',
  },
  critical: {
    bg: 'bg-red-100 dark:bg-red-900/30',
    text: 'text-red-800 dark:text-red-400',
    label: 'Critical',
  },
  expired: {
    bg: 'bg-neutral-100 dark:bg-neutral-700',
    text: 'text-neutral-800 dark:text-neutral-400',
    label: 'Expired',
  },
  revoked: {
    bg: 'bg-red-100 dark:bg-red-900/30',
    text: 'text-red-800 dark:text-red-400',
    label: 'Revoked',
  },
};

export function CertificateHealthBadge({ status, notAfter, className = '' }: Props) {
  const level = getHealthLevel(status, notAfter);
  const style = healthStyles[level];

  const days = notAfter ? getDaysUntilExpiry(notAfter) : null;
  const tooltip =
    days !== null
      ? days > 0
        ? `Expires in ${days} day${days === 1 ? '' : 's'} (${new Date(notAfter!).toLocaleDateString()})`
        : `Expired ${Math.abs(days)} day${Math.abs(days) === 1 ? '' : 's'} ago`
      : undefined;

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${style.bg} ${style.text} ${className}`}
      title={tooltip}
    >
      {style.label}
      {days !== null && level !== 'revoked' && level !== 'expired' && days > 0 && (
        <span className="opacity-75">({days}d)</span>
      )}
    </span>
  );
}
