/**
 * Create Application Modal Component
 *
 * Modal form for creating a new consumer application.
 */

import { useState } from 'react';
import { X, Plus, Trash2, AlertCircle, Shield } from 'lucide-react';
import { Button } from '@stoa/shared/components/Button';
import type { ApplicationCreateRequest, SecurityProfile } from '../../types';

const SECURITY_PROFILES: { value: SecurityProfile; label: string; description: string }[] = [
  {
    value: 'oauth2_public',
    label: 'OAuth2 Public (PKCE)',
    description: 'Browser/mobile apps — no client secret, uses PKCE',
  },
  {
    value: 'oauth2_confidential',
    label: 'OAuth2 Confidential',
    description: 'Server-side apps — client secret required',
  },
  {
    value: 'api_key',
    label: 'API Key',
    description: 'Simple key auth — no OAuth, key shown once',
  },
  {
    value: 'fapi_baseline',
    label: 'FAPI Baseline',
    description: 'Financial-grade — private_key_jwt + PKCE (requires JWKS URI)',
  },
  {
    value: 'fapi_advanced',
    label: 'FAPI Advanced',
    description: 'Financial-grade — private_key_jwt + PKCE + DPoP (requires JWKS URI)',
  },
];

interface CreateAppModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: ApplicationCreateRequest) => Promise<void>;
  isLoading?: boolean;
  error?: string | null;
}

export function CreateAppModal({
  isOpen,
  onClose,
  onSubmit,
  isLoading = false,
  error = null,
}: CreateAppModalProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [securityProfile, setSecurityProfile] = useState<SecurityProfile>('oauth2_public');
  const [jwksUri, setJwksUri] = useState('');
  const [callbackUrls, setCallbackUrls] = useState<string[]>(['']);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const filteredCallbackUrls = callbackUrls.filter((url) => url.trim() !== '');

    const isFapi = securityProfile === 'fapi_baseline' || securityProfile === 'fapi_advanced';

    await onSubmit({
      name: name.trim(),
      display_name: name.trim(),
      description: description.trim() || undefined,
      redirect_uris: filteredCallbackUrls,
      security_profile: securityProfile,
      jwks_uri: isFapi && jwksUri.trim() ? jwksUri.trim() : undefined,
    });
  };

  const handleAddCallbackUrl = () => {
    setCallbackUrls([...callbackUrls, '']);
  };

  const handleRemoveCallbackUrl = (index: number) => {
    setCallbackUrls(callbackUrls.filter((_, i) => i !== index));
  };

  const handleCallbackUrlChange = (index: number, value: string) => {
    const updated = [...callbackUrls];
    updated[index] = value;
    setCallbackUrls(updated);
  };

  const resetForm = () => {
    setName('');
    setDescription('');
    setSecurityProfile('oauth2_public');
    setJwksUri('');
    setCallbackUrls(['']);
  };

  const handleClose = () => {
    if (!isLoading) {
      resetForm();
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 transition-opacity"
        onClick={handleClose}
        onKeyDown={(e) => e.key === 'Escape' && handleClose()}
        role="button"
        aria-label="Close modal"
        tabIndex={0}
      />

      {/* Modal */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative bg-white dark:bg-neutral-800 rounded-xl shadow-xl max-w-lg w-full">
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-neutral-200 dark:border-neutral-700">
            <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">
              Create New Application
            </h2>
            <button
              onClick={handleClose}
              disabled={isLoading}
              className="p-2 text-neutral-400 dark:text-neutral-500 hover:text-neutral-600 dark:hover:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg transition-colors disabled:opacity-50"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit}>
            <div className="p-6 space-y-4">
              {/* Error message */}
              {error && (
                <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                  <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
                  <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
                </div>
              )}

              {/* Name */}
              <div>
                <label
                  htmlFor="app-name"
                  className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
                >
                  Application Name <span className="text-red-500">*</span>
                </label>
                <input
                  id="app-name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="My API Consumer App"
                  required
                  disabled={isLoading}
                  className="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 dark:text-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:bg-neutral-100 dark:disabled:bg-neutral-700 disabled:cursor-not-allowed"
                />
              </div>

              {/* Description */}
              <div>
                <label
                  htmlFor="app-description"
                  className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
                >
                  Description
                </label>
                <textarea
                  id="app-description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Brief description of what this application does..."
                  rows={3}
                  disabled={isLoading}
                  className="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 dark:text-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:bg-neutral-100 dark:disabled:bg-neutral-700 disabled:cursor-not-allowed resize-none"
                />
              </div>

              {/* Security Profile */}
              <div>
                <label
                  htmlFor="security-profile"
                  className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
                >
                  <span className="inline-flex items-center gap-1.5">
                    <Shield className="h-4 w-4" />
                    Security Profile
                  </span>
                </label>
                <select
                  id="security-profile"
                  value={securityProfile}
                  onChange={(e) => setSecurityProfile(e.target.value as SecurityProfile)}
                  disabled={isLoading}
                  className="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 dark:text-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:bg-neutral-100 dark:disabled:bg-neutral-700 disabled:cursor-not-allowed appearance-none cursor-pointer"
                >
                  {SECURITY_PROFILES.map((profile) => (
                    <option key={profile.value} value={profile.value}>
                      {profile.label}
                    </option>
                  ))}
                </select>
                <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
                  {SECURITY_PROFILES.find((p) => p.value === securityProfile)?.description}
                </p>
              </div>

              {/* JWKS URI (only for FAPI profiles) */}
              {(securityProfile === 'fapi_baseline' || securityProfile === 'fapi_advanced') && (
                <div>
                  <label
                    htmlFor="jwks-uri"
                    className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
                  >
                    JWKS URI <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="jwks-uri"
                    type="url"
                    value={jwksUri}
                    onChange={(e) => setJwksUri(e.target.value)}
                    placeholder="https://your-app.com/.well-known/jwks.json"
                    required
                    disabled={isLoading}
                    className="w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 dark:text-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:bg-neutral-100 dark:disabled:bg-neutral-700 disabled:cursor-not-allowed"
                  />
                  <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
                    Public endpoint serving your JSON Web Key Set for private_key_jwt
                    authentication.
                  </p>
                </div>
              )}

              {/* Callback URLs */}
              <div>
                <label
                  htmlFor="callback-url-0"
                  className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1"
                >
                  Callback URLs (OAuth Redirect URIs)
                </label>
                <div className="space-y-2">
                  {callbackUrls.map((url, index) => (
                    <div key={index} className="flex gap-2">
                      <input
                        id={`callback-url-${index}`}
                        type="url"
                        value={url}
                        onChange={(e) => handleCallbackUrlChange(index, e.target.value)}
                        placeholder="https://your-app.com/callback"
                        disabled={isLoading}
                        className="flex-1 px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 dark:text-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:bg-neutral-100 dark:disabled:bg-neutral-700 disabled:cursor-not-allowed"
                      />
                      {callbackUrls.length > 1 && (
                        <button
                          type="button"
                          onClick={() => handleRemoveCallbackUrl(index)}
                          disabled={isLoading}
                          className="p-2 text-neutral-400 dark:text-neutral-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors disabled:opacity-50"
                        >
                          <Trash2 className="h-5 w-5" />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
                <Button
                  variant="link"
                  size="sm"
                  icon={<Plus className="h-4 w-4" />}
                  onClick={handleAddCallbackUrl}
                  disabled={isLoading}
                  className="mt-2"
                >
                  Add another URL
                </Button>
              </div>

              {/* Info box */}
              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                <p className="text-sm text-blue-700 dark:text-blue-400">
                  {securityProfile === 'api_key' ? (
                    <>
                      After creating the application, you'll receive an <strong>API Key</strong>.
                      The key will only be shown once, so make sure to copy it immediately.
                    </>
                  ) : securityProfile === 'oauth2_public' ? (
                    <>
                      After creating the application, you'll receive a <strong>Client ID</strong>.
                      Public clients use PKCE — no client secret is needed.
                    </>
                  ) : (
                    <>
                      After creating the application, you'll receive a <strong>Client ID</strong>{' '}
                      and <strong>Client Secret</strong>. The secret will only be shown once, so
                      make sure to copy it immediately.
                    </>
                  )}
                </p>
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-3 p-6 border-t border-neutral-200 dark:border-neutral-700">
              <Button variant="secondary" onClick={handleClose} disabled={isLoading}>
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={
                  !name.trim() ||
                  ((securityProfile === 'fapi_baseline' || securityProfile === 'fapi_advanced') &&
                    !jwksUri.trim())
                }
                loading={isLoading}
              >
                {isLoading ? 'Creating...' : 'Create Application'}
              </Button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export default CreateAppModal;
