import { useState, useRef, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { apiService } from '../services/api';
import { useEnvironmentMode } from '../hooks/useEnvironmentMode';
import { useToastActions } from '@stoa/shared/components/Toast';
import { useConfirm } from '@stoa/shared/components/ConfirmDialog';
import type { Consumer, CertificateStatus } from '../types';

const certStatusStyles: Record<CertificateStatus, string> = {
  active: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  rotating: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  revoked: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  expired: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-400',
};

interface Props {
  consumer: Consumer;
  tenantId: string;
  onClose: () => void;
}

export function ConsumerDetailModal({ consumer, tenantId, onClose }: Props) {
  const { canEdit } = useEnvironmentMode();
  const toast = useToastActions();
  const queryClient = useQueryClient();
  const [confirm, ConfirmDialog] = useConfirm();
  const [showRotateForm, setShowRotateForm] = useState(false);
  const [pemValue, setPemValue] = useState('');
  const [gracePeriod, setGracePeriod] = useState(24);
  const [rotating, setRotating] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const invalidate = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['consumers', tenantId] });
  }, [queryClient, tenantId]);

  const handleRevoke = useCallback(async () => {
    const ok = await confirm({
      title: 'Revoke Certificate',
      message: `Revoke the certificate for "${consumer.name}"? This will disable their API access immediately.`,
      confirmLabel: 'Revoke',
      cancelLabel: 'Cancel',
      variant: 'danger',
    });
    if (!ok) return;
    try {
      await apiService.revokeCertificate(tenantId, consumer.id);
      toast.success('Certificate revoked', `Certificate for ${consumer.name} has been revoked`);
      invalidate();
      onClose();
    } catch (err: unknown) {
      toast.error(
        'Revoke failed',
        err instanceof Error ? err.message : 'Failed to revoke certificate'
      );
    }
  }, [tenantId, consumer, confirm, toast, invalidate, onClose]);

  const handleFileUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      setPemValue((ev.target?.result as string) || '');
    };
    reader.readAsText(file);
  }, []);

  const handleRotate = useCallback(async () => {
    if (!pemValue.trim()) {
      toast.error('Missing certificate', 'Please paste or upload a PEM certificate');
      return;
    }
    setRotating(true);
    try {
      await apiService.rotateCertificate(tenantId, consumer.id, pemValue.trim(), gracePeriod);
      toast.success(
        'Certificate rotated',
        `New certificate active for ${consumer.name}. Grace period: ${gracePeriod}h`
      );
      invalidate();
      onClose();
    } catch (err: unknown) {
      toast.error(
        'Rotation failed',
        err instanceof Error ? err.message : 'Failed to rotate certificate'
      );
    } finally {
      setRotating(false);
    }
  }, [tenantId, consumer, pemValue, gracePeriod, toast, invalidate, onClose]);

  const hasCert = !!consumer.certificate_fingerprint;
  const certStatus = consumer.certificate_status as CertificateStatus | undefined;

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-40 bg-black/50" onClick={onClose} />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          className="bg-white dark:bg-neutral-800 rounded-lg shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex justify-between items-start p-6 border-b border-gray-200 dark:border-neutral-700">
            <div>
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                {consumer.name}
              </h2>
              <p className="text-sm text-gray-500 dark:text-neutral-400 font-mono">
                {consumer.external_id}
              </p>
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 dark:hover:text-neutral-300"
            >
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>

          {/* Body */}
          <div className="p-6 space-y-6">
            {/* Consumer Info */}
            <section className="space-y-2">
              <h3 className="text-sm font-medium text-gray-500 dark:text-neutral-400 uppercase tracking-wider">
                Consumer
              </h3>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                <dt className="text-gray-500 dark:text-neutral-400">Email</dt>
                <dd className="text-gray-900 dark:text-white">{consumer.email}</dd>
                <dt className="text-gray-500 dark:text-neutral-400">Company</dt>
                <dd className="text-gray-900 dark:text-white">{consumer.company || '—'}</dd>
                <dt className="text-gray-500 dark:text-neutral-400">Status</dt>
                <dd className="text-gray-900 dark:text-white capitalize">{consumer.status}</dd>
                <dt className="text-gray-500 dark:text-neutral-400">Created</dt>
                <dd className="text-gray-900 dark:text-white">
                  {new Date(consumer.created_at).toLocaleDateString()}
                </dd>
              </dl>
            </section>

            {/* Certificate Info */}
            <section className="space-y-2">
              <h3 className="text-sm font-medium text-gray-500 dark:text-neutral-400 uppercase tracking-wider">
                Certificate
              </h3>
              {hasCert ? (
                <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                  <dt className="text-gray-500 dark:text-neutral-400">Status</dt>
                  <dd>
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${certStatus ? certStatusStyles[certStatus] : ''}`}
                    >
                      {certStatus || 'unknown'}
                    </span>
                  </dd>
                  <dt className="text-gray-500 dark:text-neutral-400">Fingerprint</dt>
                  <dd className="text-gray-900 dark:text-white font-mono text-xs break-all">
                    {consumer.certificate_fingerprint}
                  </dd>
                  {consumer.certificate_subject_dn && (
                    <>
                      <dt className="text-gray-500 dark:text-neutral-400">Subject</dt>
                      <dd className="text-gray-900 dark:text-white text-xs break-all">
                        {consumer.certificate_subject_dn}
                      </dd>
                    </>
                  )}
                  {consumer.certificate_not_before && (
                    <>
                      <dt className="text-gray-500 dark:text-neutral-400">Valid from</dt>
                      <dd className="text-gray-900 dark:text-white">
                        {new Date(consumer.certificate_not_before).toLocaleDateString()}
                      </dd>
                    </>
                  )}
                  {consumer.certificate_not_after && (
                    <>
                      <dt className="text-gray-500 dark:text-neutral-400">Valid until</dt>
                      <dd className="text-gray-900 dark:text-white">
                        {new Date(consumer.certificate_not_after).toLocaleDateString()}
                      </dd>
                    </>
                  )}
                  {(consumer.rotation_count ?? 0) > 0 && (
                    <>
                      <dt className="text-gray-500 dark:text-neutral-400">Rotations</dt>
                      <dd className="text-gray-900 dark:text-white">{consumer.rotation_count}</dd>
                    </>
                  )}
                  {consumer.last_rotated_at && (
                    <>
                      <dt className="text-gray-500 dark:text-neutral-400">Last rotated</dt>
                      <dd className="text-gray-900 dark:text-white">
                        {new Date(consumer.last_rotated_at).toLocaleDateString()}
                      </dd>
                    </>
                  )}
                </dl>
              ) : (
                <p className="text-sm text-gray-500 dark:text-neutral-400 italic">
                  No certificate bound to this consumer.
                </p>
              )}
            </section>

            {/* Rotate Form */}
            {showRotateForm && (
              <section className="space-y-3 border-t border-gray-200 dark:border-neutral-700 pt-4">
                <h3 className="text-sm font-medium text-gray-900 dark:text-white">
                  Rotate Certificate
                </h3>
                <div>
                  <label className="block text-sm text-gray-600 dark:text-neutral-400 mb-1">
                    New PEM Certificate
                  </label>
                  <textarea
                    value={pemValue}
                    onChange={(e) => setPemValue(e.target.value)}
                    placeholder="-----BEGIN CERTIFICATE-----&#10;...&#10;-----END CERTIFICATE-----"
                    rows={5}
                    className="w-full border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm font-mono bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500"
                  />
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".pem,.crt,.cer,.cert"
                    onChange={handleFileUpload}
                    className="hidden"
                  />
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="mt-1 text-sm text-blue-600 hover:text-blue-800 dark:text-blue-400"
                  >
                    Or upload a file (.pem, .crt, .cer)
                  </button>
                </div>
                <div>
                  <label className="block text-sm text-gray-600 dark:text-neutral-400 mb-1">
                    Grace period (hours)
                  </label>
                  <input
                    type="number"
                    value={gracePeriod}
                    onChange={(e) => setGracePeriod(Number(e.target.value))}
                    min={1}
                    max={720}
                    className="w-24 border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500"
                  />
                  <span className="ml-2 text-xs text-gray-500 dark:text-neutral-400">
                    Old cert stays valid during this period
                  </span>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={handleRotate}
                    disabled={rotating || !pemValue.trim()}
                    className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {rotating ? 'Rotating...' : 'Confirm Rotation'}
                  </button>
                  <button
                    onClick={() => {
                      setShowRotateForm(false);
                      setPemValue('');
                    }}
                    className="px-4 py-2 border border-gray-300 dark:border-neutral-600 text-sm rounded-lg hover:bg-gray-50 dark:hover:bg-neutral-700 dark:text-white"
                  >
                    Cancel
                  </button>
                </div>
              </section>
            )}
          </div>

          {/* Footer Actions */}
          {canEdit && hasCert && certStatus !== 'revoked' && !showRotateForm && (
            <div className="p-6 border-t border-gray-200 dark:border-neutral-700 flex gap-3">
              <button
                onClick={() => setShowRotateForm(true)}
                className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700"
              >
                Rotate Certificate
              </button>
              <button
                onClick={handleRevoke}
                className="px-4 py-2 border border-red-300 text-red-600 dark:border-red-700 dark:text-red-400 text-sm rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20"
              >
                Revoke Certificate
              </button>
            </div>
          )}
        </div>
      </div>

      {ConfirmDialog}
    </>
  );
}
