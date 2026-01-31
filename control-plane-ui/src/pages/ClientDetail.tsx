/**
 * Client Detail Page (CAB-870)
 *
 * Shows certificate info, grace period status, and rotate/revoke actions.
 */
import { useState, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, RotateCw, Trash2, Download, Clock, Copy, Check, AlertTriangle } from 'lucide-react';
import { useClient, useRotateClient, useRevokeClient } from '../hooks/useClients';
import { getCertificateHealth, getDaysRemaining, healthColors, healthLabels } from '../types/client';
import type { ClientWithCertificate, CertificateHealthStatus } from '../types/client';

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function InfoCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4">{title}</h3>
      <dl className="space-y-3">{children}</dl>
    </div>
  );
}

function InfoRow({ label, children, copyValue }: {
  label: string;
  children: React.ReactNode;
  copyValue?: string;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    if (!copyValue) return;
    await navigator.clipboard.writeText(copyValue);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [copyValue]);

  return (
    <div className="flex items-start justify-between">
      <dt className="text-sm text-gray-500 min-w-[140px]">{label}</dt>
      <dd className="text-sm text-gray-900 text-right flex items-center gap-1.5 max-w-[60%]">
        <span className="truncate">{children}</span>
        {copyValue && (
          <button
            onClick={handleCopy}
            className="text-gray-400 hover:text-gray-600 flex-shrink-0"
            title="Copy"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-green-500" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
        )}
      </dd>
    </div>
  );
}

function HealthBadge({ health }: { health: CertificateHealthStatus }) {
  return (
    <span className={`px-2 py-1 text-xs font-medium rounded-full ${healthColors[health]}`}>
      {healthLabels[health]}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    active: 'bg-green-100 text-green-800',
    revoked: 'bg-gray-100 text-gray-800',
    expired: 'bg-red-100 text-red-800',
  };
  return (
    <span className={`px-2 py-1 text-xs font-medium rounded-full ${colors[status] || 'bg-gray-100 text-gray-800'}`}>
      {status}
    </span>
  );
}

// Download certificate modal (shared with Clients.tsx pattern)
function DownloadCertificateModal({ client, onClose }: {
  client: ClientWithCertificate;
  onClose: () => void;
}) {
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  const copyToClipboard = useCallback(async (text: string, label: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(label);
    setTimeout(() => setCopied(null), 2000);
  }, []);

  const downloadFile = useCallback((content: string, filename: string) => {
    const blob = new Blob([content], { type: 'application/x-pem-file' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl p-6 max-h-[90vh] overflow-y-auto">
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-600 mt-0.5 flex-shrink-0" />
          <div>
            <h3 className="font-semibold text-amber-900">Private Key - Save Now</h3>
            <p className="text-amber-700 text-sm mt-1">
              The private key is shown ONE TIME only. Download or copy it before closing.
            </p>
          </div>
        </div>

        {client.grace_period_ends && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-4 flex items-center gap-2">
            <Clock className="w-4 h-4 text-blue-600" />
            <span className="text-sm text-blue-700">
              Grace period ends: {new Date(client.grace_period_ends).toLocaleString()}
            </span>
          </div>
        )}

        <div className="mb-4">
          <div className="flex justify-between items-center mb-1">
            <label className="text-sm font-medium text-gray-700">Certificate (PEM)</label>
            <div className="flex gap-2">
              <button onClick={() => copyToClipboard(client.certificate_pem || '', 'cert')} className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1">
                {copied === 'cert' ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />} {copied === 'cert' ? 'Copied' : 'Copy'}
              </button>
              <button onClick={() => downloadFile(client.certificate_pem || '', `${client.name}-cert.pem`)} className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1">
                <Download className="w-3 h-3" /> Download
              </button>
            </div>
          </div>
          <pre className="bg-gray-50 rounded border border-gray-200 p-3 text-xs overflow-x-auto max-h-32">{client.certificate_pem}</pre>
        </div>

        <div className="mb-4">
          <div className="flex justify-between items-center mb-1">
            <label className="text-sm font-medium text-red-700">Private Key (PEM)</label>
            <div className="flex gap-2">
              <button onClick={() => copyToClipboard(client.private_key_pem, 'key')} className="text-xs text-red-600 hover:text-red-800 flex items-center gap-1">
                {copied === 'key' ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />} {copied === 'key' ? 'Copied' : 'Copy'}
              </button>
              <button onClick={() => downloadFile(client.private_key_pem, `${client.name}-key.pem`)} className="text-xs text-red-600 hover:text-red-800 flex items-center gap-1">
                <Download className="w-3 h-3" /> Download
              </button>
            </div>
          </div>
          <pre className="bg-red-50 rounded border border-red-200 p-3 text-xs overflow-x-auto max-h-32">{client.private_key_pem}</pre>
        </div>

        <div className="border-t pt-4 mt-4">
          <label className="flex items-center gap-2 text-sm text-gray-700 mb-4 cursor-pointer">
            <input type="checkbox" checked={saved} onChange={e => setSaved(e.target.checked)} className="rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
            I have saved the private key securely
          </label>
          <button onClick={onClose} disabled={!saved} className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed">Close</button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Rotate Modal with grace period input
// ---------------------------------------------------------------------------

function RotateModal({ clientName, isLoading, onClose, onRotate }: {
  clientName: string;
  isLoading: boolean;
  onClose: () => void;
  onRotate: (gracePeriodHours?: number, reason?: string) => void;
}) {
  const [gracePeriodHours, setGracePeriodHours] = useState(24);
  const [reason, setReason] = useState('manual_rotation');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-semibold text-gray-900 mb-2">Rotate Certificate</h2>
        <p className="text-sm text-gray-600 mb-4">
          Rotate the certificate for "{clientName}". Both old and new certificates will be valid during the grace period.
        </p>

        <div className="space-y-4 mb-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Grace Period (hours)</label>
            <input
              type="number"
              value={gracePeriodHours}
              onChange={e => setGracePeriodHours(Number(e.target.value))}
              min={1}
              max={168}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500"
            />
            <p className="text-xs text-gray-500 mt-1">1-168 hours (default: 24h)</p>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Reason</label>
            <input
              type="text"
              value={reason}
              onChange={e => setReason(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>

        <div className="flex justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50">Cancel</button>
          <button
            onClick={() => onRotate(gracePeriodHours, reason)}
            disabled={isLoading}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {isLoading ? 'Rotating...' : 'Rotate Certificate'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Detail Page
// ---------------------------------------------------------------------------

export function ClientDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: client, isLoading, error } = useClient(id || null);
  const rotateMutation = useRotateClient();
  const revokeMutation = useRevokeClient();

  const [showRotateModal, setShowRotateModal] = useState(false);
  const [showRevokeConfirm, setShowRevokeConfirm] = useState(false);
  const [rotatedClient, setRotatedClient] = useState<ClientWithCertificate | null>(null);

  const handleRotate = useCallback(async (gracePeriodHours?: number, reason?: string) => {
    if (!client) return;
    try {
      const result = await rotateMutation.mutateAsync({
        clientId: client.id,
        body: { grace_period_hours: gracePeriodHours, reason },
      });
      setShowRotateModal(false);
      setRotatedClient(result);
    } catch (err: any) {
      alert(err.response?.data?.detail || err.message || 'Failed to rotate certificate');
    }
  }, [client, rotateMutation]);

  const handleRevoke = useCallback(async () => {
    if (!client) return;
    try {
      await revokeMutation.mutateAsync(client.id);
      navigate('/clients');
    } catch (err: any) {
      alert(err.response?.data?.detail || err.message || 'Failed to revoke client');
    }
  }, [client, revokeMutation, navigate]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (error || !client) {
    return (
      <div className="text-center py-16">
        <h3 className="text-lg font-medium text-gray-900 mb-2">Client not found</h3>
        <Link to="/clients" className="text-blue-600 hover:text-blue-800">Back to clients</Link>
      </div>
    );
  }

  const health = getCertificateHealth(client);
  const days = getDaysRemaining(client.certificate_not_after);

  const downloadPEM = (content: string | null, filename: string) => {
    if (!content) return;
    const blob = new Blob([content], { type: 'application/x-pem-file' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link to="/clients" className="text-gray-500 hover:text-gray-700">
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900">{client.name}</h1>
            <StatusBadge status={client.status} />
            <HealthBadge health={health} />
          </div>
          <p className="text-gray-500 mt-1">CN: {client.certificate_cn}</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowRotateModal(true)}
            disabled={client.status !== 'active'}
            className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 flex items-center gap-2"
          >
            <RotateCw className="w-4 h-4" />
            Rotate
          </button>
          <button
            onClick={() => setShowRevokeConfirm(true)}
            disabled={client.status === 'revoked'}
            className="px-4 py-2 border border-red-300 text-red-600 rounded-lg hover:bg-red-50 disabled:opacity-50 flex items-center gap-2"
          >
            <Trash2 className="w-4 h-4" />
            Revoke
          </button>
        </div>
      </div>

      {/* Grace Period Alert */}
      {client.is_in_grace_period && client.previous_cert_expires_at && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 flex items-start gap-3">
          <Clock className="w-5 h-5 text-blue-600 mt-0.5" />
          <div>
            <h3 className="font-semibold text-blue-900">Grace Period Active</h3>
            <p className="text-blue-700 text-sm mt-1">
              Both old and new certificates are valid until{' '}
              {new Date(client.previous_cert_expires_at).toLocaleString()}.
              Update your clients before this deadline.
            </p>
          </div>
        </div>
      )}

      {/* Info Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <InfoCard title="Certificate Status">
          <InfoRow label="Status"><StatusBadge status={client.status} /></InfoRow>
          <InfoRow label="Health"><HealthBadge health={health} /></InfoRow>
          <InfoRow label="Expires">
            {days !== null ? (
              <span className={days < 7 ? 'text-red-600 font-semibold' : ''}>
                {days} days ({new Date(client.certificate_not_after!).toLocaleDateString()})
              </span>
            ) : 'N/A'}
          </InfoRow>
          <InfoRow label="Issued">
            {client.certificate_not_before ? new Date(client.certificate_not_before).toLocaleDateString() : 'N/A'}
          </InfoRow>
        </InfoCard>

        <InfoCard title="Certificate Details">
          <InfoRow label="Serial" copyValue={client.certificate_serial || undefined}>
            <span className="font-mono text-xs">{client.certificate_serial || 'N/A'}</span>
          </InfoRow>
          <InfoRow label="Fingerprint" copyValue={client.certificate_fingerprint || undefined}>
            <span className="font-mono text-xs">{client.certificate_fingerprint ? `${client.certificate_fingerprint.slice(0, 24)}...` : 'N/A'}</span>
          </InfoRow>
          {client.certificate_fingerprint_previous && (
            <InfoRow label="Previous FP" copyValue={client.certificate_fingerprint_previous}>
              <span className="font-mono text-xs">{client.certificate_fingerprint_previous.slice(0, 24)}...</span>
            </InfoRow>
          )}
        </InfoCard>

        <InfoCard title="Rotation History">
          <InfoRow label="Total Rotations">{client.rotation_count}</InfoRow>
          <InfoRow label="Last Rotated">
            {client.last_rotated_at ? new Date(client.last_rotated_at).toLocaleString() : 'Never'}
          </InfoRow>
        </InfoCard>

        <InfoCard title="Metadata">
          <InfoRow label="Client ID" copyValue={client.id}>
            <span className="font-mono text-xs">{client.id.slice(0, 12)}...</span>
          </InfoRow>
          <InfoRow label="Tenant">{client.tenant_id}</InfoRow>
          <InfoRow label="Created">{new Date(client.created_at).toLocaleString()}</InfoRow>
          <InfoRow label="Updated">{new Date(client.updated_at).toLocaleString()}</InfoRow>
        </InfoCard>
      </div>

      {/* Certificate PEM */}
      {client.certificate_pem && (
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Certificate (PEM)</h3>
            <button
              onClick={() => downloadPEM(client.certificate_pem, `${client.name}-cert.pem`)}
              className="text-blue-600 hover:text-blue-800 flex items-center gap-2 text-sm"
            >
              <Download className="w-4 h-4" />
              Download
            </button>
          </div>
          <pre className="bg-gray-50 rounded border border-gray-200 p-4 text-xs overflow-x-auto">
            {client.certificate_pem}
          </pre>
        </div>
      )}

      {/* Modals */}
      {showRotateModal && (
        <RotateModal
          clientName={client.name}
          isLoading={rotateMutation.isPending}
          onClose={() => setShowRotateModal(false)}
          onRotate={handleRotate}
        />
      )}

      {showRevokeConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setShowRevokeConfirm(false)}>
          <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6" onClick={e => e.stopPropagation()}>
            <h2 className="text-lg font-semibold text-gray-900 mb-2">Revoke Client</h2>
            <p className="text-gray-600 text-sm mb-6">
              Permanently revoke "{client.name}"? This action cannot be undone. The client will no longer be able to authenticate.
            </p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setShowRevokeConfirm(false)} className="px-4 py-2 text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50">Cancel</button>
              <button
                onClick={handleRevoke}
                disabled={revokeMutation.isPending}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
              >
                {revokeMutation.isPending ? 'Revoking...' : 'Revoke'}
              </button>
            </div>
          </div>
        </div>
      )}

      {rotatedClient && (
        <DownloadCertificateModal
          client={rotatedClient}
          onClose={() => setRotatedClient(null)}
        />
      )}
    </div>
  );
}
