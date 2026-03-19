/**
 * CertificateGenerationWizard — 3-step client-side cert generation (CAB-1788).
 *
 * Step 1: Generate RSA-4096 keypair in browser (node-forge)
 * Step 2: Create CSR → sign via tenant CA API → get signed certificate
 * Step 3: One-time download (PEM or PKCS12)
 *
 * Private key NEVER leaves the browser — only the CSR (public key + subject) is sent to the API.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { apiService } from '../services/api';
import { useToastActions } from '@stoa/shared/components/Toast';
import { Button } from '@stoa/shared/components/Button';
import {
  generateKeyPair,
  createCSR,
  createPKCS12,
  downloadOnce,
  downloadPem,
  type GeneratedKeyPair,
} from '../lib/crypto';
import type { CSRSignResponse } from '../types';
import {
  KeyRound,
  FileSignature,
  Download,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Shield,
  X,
} from 'lucide-react';

interface Props {
  tenantId: string;
  tenantName: string;
  onClose: () => void;
  onComplete: () => void;
}

type Step = 'generate' | 'sign' | 'download';

export function CertificateGenerationWizard({ tenantId, tenantName, onClose, onComplete }: Props) {
  const toast = useToastActions();
  const [step, setStep] = useState<Step>('generate');
  const [generating, setGenerating] = useState(false);
  const [signing, setSigning] = useState(false);
  const [keyPair, setKeyPair] = useState<GeneratedKeyPair | null>(null);
  const [signedCert, setSignedCert] = useState<CSRSignResponse | null>(null);
  const [commonName, setCommonName] = useState('');
  const [validityDays, setValidityDays] = useState(365);
  const [downloaded, setDownloaded] = useState(false);
  const [p12Password, setP12Password] = useState('');
  const hasUnsavedKeyRef = useRef(false);

  // beforeunload warning when private key is in memory but not downloaded
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (hasUnsavedKeyRef.current) {
        e.preventDefault();
      }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, []);

  // Step 1: Generate keypair
  const handleGenerate = useCallback(async () => {
    if (!commonName.trim()) {
      toast.error('Common Name required', 'Enter a CN for the certificate subject');
      return;
    }
    setGenerating(true);
    try {
      // Run in setTimeout to avoid blocking the UI during RSA generation
      const kp = await new Promise<GeneratedKeyPair>((resolve) => {
        setTimeout(() => resolve(generateKeyPair()), 50);
      });
      setKeyPair(kp);
      hasUnsavedKeyRef.current = true;
      setStep('sign');
    } catch (err) {
      toast.error('Key generation failed', err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setGenerating(false);
    }
  }, [commonName, toast]);

  // Step 2: Ensure tenant CA exists, then create CSR and sign
  const handleSign = useCallback(async () => {
    if (!keyPair) return;
    setSigning(true);
    try {
      // Auto-generate tenant CA if none exists
      try {
        await apiService.getTenantCA(tenantId);
      } catch {
        // 404 means no CA — generate one automatically
        await apiService.generateTenantCA(tenantId);
      }

      const csrPem = createCSR(keyPair.privateKeyPem, {
        commonName: commonName.trim(),
        organization: 'STOA Platform',
        organizationalUnit: tenantName,
      });

      const result = await apiService.signCSR(tenantId, csrPem, validityDays);
      setSignedCert(result);
      setStep('download');
    } catch (err) {
      toast.error('Signing failed', err instanceof Error ? err.message : 'Failed to sign CSR');
    } finally {
      setSigning(false);
    }
  }, [keyPair, commonName, tenantId, tenantName, validityDays, toast]);

  // Step 3: Download handlers
  const handleDownloadPem = useCallback(() => {
    if (!keyPair || !signedCert) return;
    const bundle = [
      '# Private Key\n',
      keyPair.privateKeyPem,
      '\n# Signed Certificate\n',
      signedCert.signed_certificate_pem,
    ].join('');
    downloadPem(bundle, `${commonName.trim()}-certificate-bundle.pem`);
    setDownloaded(true);
    hasUnsavedKeyRef.current = false;
  }, [keyPair, signedCert, commonName]);

  const handleDownloadKeyOnly = useCallback(() => {
    if (!keyPair) return;
    downloadPem(keyPair.privateKeyPem, `${commonName.trim()}-private-key.pem`);
    setDownloaded(true);
    hasUnsavedKeyRef.current = false;
  }, [keyPair, commonName]);

  const handleDownloadCertOnly = useCallback(() => {
    if (!signedCert) return;
    downloadPem(signedCert.signed_certificate_pem, `${commonName.trim()}-certificate.pem`);
  }, [signedCert, commonName]);

  const handleDownloadPKCS12 = useCallback(() => {
    if (!keyPair || !signedCert || !p12Password) {
      toast.error('Password required', 'Enter a password to protect the PKCS12 bundle');
      return;
    }
    try {
      const blob = createPKCS12(
        keyPair.privateKeyPem,
        signedCert.signed_certificate_pem,
        p12Password
      );
      downloadOnce(blob, `${commonName.trim()}-certificate.p12`);
      setDownloaded(true);
      hasUnsavedKeyRef.current = false;
    } catch (err) {
      toast.error(
        'PKCS12 export failed',
        err instanceof Error ? err.message : 'Failed to create PKCS12'
      );
    }
  }, [keyPair, signedCert, p12Password, commonName, toast]);

  const handleClose = useCallback(() => {
    if (hasUnsavedKeyRef.current && !downloaded) {
      const confirmed = window.confirm(
        'Your private key has not been downloaded yet. If you close this wizard, the key will be lost forever. Continue?'
      );
      if (!confirmed) return;
    }
    hasUnsavedKeyRef.current = false;
    if (downloaded) onComplete();
    else onClose();
  }, [downloaded, onClose, onComplete]);

  const steps: { id: Step; label: string; icon: typeof KeyRound }[] = [
    { id: 'generate', label: 'Generate Keys', icon: KeyRound },
    { id: 'sign', label: 'Sign Certificate', icon: FileSignature },
    { id: 'download', label: 'Download', icon: Download },
  ];

  const stepIndex = steps.findIndex((s) => s.id === step);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-neutral-800 rounded-xl shadow-2xl max-w-lg w-full mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-200 dark:border-neutral-700">
          <div className="flex items-center gap-3">
            <Shield className="h-5 w-5 text-primary-600 dark:text-primary-400" />
            <h2 className="text-lg font-semibold text-neutral-900 dark:text-white">
              Generate Client Certificate
            </h2>
          </div>
          <button
            onClick={handleClose}
            className="text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Step indicator */}
        <div className="px-6 pt-4">
          <div className="flex items-center gap-2">
            {steps.map((s, i) => {
              const Icon = s.icon;
              const isActive = i === stepIndex;
              const isDone = i < stepIndex;
              return (
                <div key={s.id} className="flex items-center gap-2 flex-1">
                  <div
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                      isDone
                        ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
                        : isActive
                          ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-400'
                          : 'bg-neutral-100 dark:bg-neutral-700 text-neutral-400 dark:text-neutral-500'
                    }`}
                  >
                    {isDone ? (
                      <CheckCircle2 className="h-3.5 w-3.5" />
                    ) : (
                      <Icon className="h-3.5 w-3.5" />
                    )}
                    {s.label}
                  </div>
                  {i < steps.length - 1 && (
                    <div
                      className={`flex-1 h-px ${isDone ? 'bg-green-300 dark:bg-green-700' : 'bg-neutral-200 dark:bg-neutral-700'}`}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Content */}
        <div className="px-6 py-6 space-y-4 min-h-[280px]">
          {step === 'generate' && (
            <>
              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3 flex gap-2">
                <Shield className="h-4 w-4 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" />
                <p className="text-sm text-blue-700 dark:text-blue-300">
                  Your private key is generated in the browser and never sent to the server. Only
                  the Certificate Signing Request (public key) is transmitted.
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
                  Common Name (CN) <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={commonName}
                  onChange={(e) => setCommonName(e.target.value)}
                  placeholder="e.g. my-api-client"
                  className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                />
                <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                  Identifies this client certificate. Usually the application or service name.
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
                  Validity (days)
                </label>
                <select
                  value={validityDays}
                  onChange={(e) => setValidityDays(Number(e.target.value))}
                  className="w-full border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                >
                  <option value={90}>90 days</option>
                  <option value={180}>180 days</option>
                  <option value={365}>1 year</option>
                  <option value={730}>2 years</option>
                </select>
              </div>

              <Button
                onClick={handleGenerate}
                loading={generating}
                disabled={!commonName.trim()}
                className="w-full"
              >
                {generating ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Generating RSA-4096 keypair...
                  </span>
                ) : (
                  'Generate Keypair'
                )}
              </Button>
            </>
          )}

          {step === 'sign' && keyPair && (
            <>
              <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-3">
                <p className="text-sm font-medium text-green-700 dark:text-green-400">
                  RSA-4096 keypair generated
                </p>
                <p className="text-xs text-green-600 dark:text-green-500 mt-1 font-mono">
                  SHA-256: {keyPair.fingerprint.substring(0, 32)}...
                </p>
              </div>

              <div className="space-y-2">
                <p className="text-sm text-neutral-600 dark:text-neutral-400">
                  A Certificate Signing Request (CSR) will be created and signed by your
                  tenant&apos;s CA. The private key stays in your browser.
                </p>
                <div className="text-xs text-neutral-500 dark:text-neutral-400 space-y-1">
                  <p>
                    <strong>Subject:</strong> CN={commonName}, OU={tenantName}, O=STOA Platform
                  </p>
                  <p>
                    <strong>Validity:</strong> {validityDays} days
                  </p>
                  <p>
                    <strong>Key Algorithm:</strong> RSA-4096
                  </p>
                </div>
              </div>

              <Button onClick={handleSign} loading={signing} className="w-full">
                {signing ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Signing certificate...
                  </span>
                ) : (
                  'Sign Certificate'
                )}
              </Button>
            </>
          )}

          {step === 'download' && signedCert && (
            <>
              <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-3 flex gap-2">
                <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-amber-700 dark:text-amber-400">
                    Download your private key now
                  </p>
                  <p className="text-xs text-amber-600 dark:text-amber-500 mt-0.5">
                    This is the only time you can download the private key. It is not stored on the
                    server.
                  </p>
                </div>
              </div>

              <div className="text-xs text-neutral-500 dark:text-neutral-400 space-y-1 bg-neutral-50 dark:bg-neutral-900 rounded-lg p-3">
                <p>
                  <strong>Subject:</strong> {signedCert.subject_dn}
                </p>
                <p>
                  <strong>Issuer:</strong> {signedCert.issuer_dn}
                </p>
                <p>
                  <strong>Validity:</strong> {signedCert.validity_days} days
                </p>
              </div>

              {/* PEM downloads */}
              <div className="space-y-2">
                <Button onClick={handleDownloadPem} variant="primary" className="w-full">
                  <Download className="h-4 w-4 mr-2" />
                  Download Bundle (Key + Certificate PEM)
                </Button>

                <div className="flex gap-2">
                  <Button
                    onClick={handleDownloadKeyOnly}
                    variant="secondary"
                    size="sm"
                    className="flex-1"
                  >
                    Private Key Only
                  </Button>
                  <Button
                    onClick={handleDownloadCertOnly}
                    variant="secondary"
                    size="sm"
                    className="flex-1"
                  >
                    Certificate Only
                  </Button>
                </div>
              </div>

              {/* PKCS12 export */}
              <div className="border-t border-neutral-200 dark:border-neutral-700 pt-4">
                <p className="text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                  PKCS#12 Export (.p12)
                </p>
                <div className="flex gap-2">
                  <input
                    type="password"
                    value={p12Password}
                    onChange={(e) => setP12Password(e.target.value)}
                    placeholder="Bundle password"
                    className="flex-1 border border-neutral-300 dark:border-neutral-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                  />
                  <Button
                    onClick={handleDownloadPKCS12}
                    variant="secondary"
                    size="sm"
                    disabled={!p12Password}
                  >
                    Export .p12
                  </Button>
                </div>
              </div>

              {downloaded && (
                <div className="flex items-center gap-2 text-green-600 dark:text-green-400 text-sm">
                  <CheckCircle2 className="h-4 w-4" />
                  <span>Certificate downloaded successfully</span>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-neutral-200 dark:border-neutral-700 flex justify-end">
          <Button variant="ghost" onClick={handleClose}>
            {downloaded ? 'Done' : 'Cancel'}
          </Button>
        </div>
      </div>
    </div>
  );
}
