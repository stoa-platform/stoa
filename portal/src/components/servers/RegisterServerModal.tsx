/**
 * Register Server Modal (CAB-1319)
 *
 * Form for registering a new tenant-scoped external MCP server.
 * Conditional credential fields based on auth_type selection.
 */

import { useState } from 'react';
import { X, Loader2, AlertCircle } from 'lucide-react';
import type { TenantMCPServerCreatePayload } from '../../services/tenantMcpServers';

type TransportType = 'sse' | 'http' | 'websocket';
type AuthType = 'none' | 'api_key' | 'bearer_token' | 'oauth2';

interface RegisterServerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: TenantMCPServerCreatePayload) => Promise<void>;
  isLoading?: boolean;
  error?: string | null;
}

export function RegisterServerModal({
  isOpen,
  onClose,
  onSubmit,
  isLoading = false,
  error = null,
}: RegisterServerModalProps) {
  const [displayName, setDisplayName] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [description, setDescription] = useState('');
  const [transport, setTransport] = useState<TransportType>('sse');
  const [authType, setAuthType] = useState<AuthType>('none');
  const [toolPrefix, setToolPrefix] = useState('');
  // Credential fields
  const [apiKey, setApiKey] = useState('');
  const [bearerToken, setBearerToken] = useState('');
  const [oauth2ClientId, setOauth2ClientId] = useState('');
  const [oauth2ClientSecret, setOauth2ClientSecret] = useState('');
  const [oauth2TokenUrl, setOauth2TokenUrl] = useState('');
  const [oauth2Scope, setOauth2Scope] = useState('');

  const resetForm = () => {
    setDisplayName('');
    setBaseUrl('');
    setDescription('');
    setTransport('sse');
    setAuthType('none');
    setToolPrefix('');
    setApiKey('');
    setBearerToken('');
    setOauth2ClientId('');
    setOauth2ClientSecret('');
    setOauth2TokenUrl('');
    setOauth2Scope('');
  };

  const handleClose = () => {
    if (!isLoading) {
      resetForm();
      onClose();
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const payload: TenantMCPServerCreatePayload = {
      display_name: displayName.trim(),
      base_url: baseUrl.trim(),
      description: description.trim() || undefined,
      transport,
      auth_type: authType,
      tool_prefix: toolPrefix.trim() || undefined,
    };

    // Add credentials based on auth type
    if (authType === 'api_key' && apiKey.trim()) {
      payload.credentials = { api_key: apiKey.trim() };
    } else if (authType === 'bearer_token' && bearerToken.trim()) {
      payload.credentials = { bearer_token: bearerToken.trim() };
    } else if (authType === 'oauth2' && oauth2ClientId.trim() && oauth2TokenUrl.trim()) {
      payload.credentials = {
        oauth2: {
          client_id: oauth2ClientId.trim(),
          client_secret: oauth2ClientSecret.trim(),
          token_url: oauth2TokenUrl.trim(),
          scope: oauth2Scope.trim() || undefined,
        },
      };
    }

    await onSubmit(payload);
  };

  const isFormValid =
    displayName.trim() !== '' &&
    baseUrl.trim() !== '' &&
    (authType === 'none' ||
      (authType === 'api_key' && apiKey.trim() !== '') ||
      (authType === 'bearer_token' && bearerToken.trim() !== '') ||
      (authType === 'oauth2' &&
        oauth2ClientId.trim() !== '' &&
        oauth2ClientSecret.trim() !== '' &&
        oauth2TokenUrl.trim() !== ''));

  if (!isOpen) return null;

  const inputClass =
    'w-full px-4 py-2 border border-neutral-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 dark:text-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:bg-neutral-100 dark:disabled:bg-neutral-700 disabled:cursor-not-allowed';
  const labelClass = 'block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1';

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
        <div className="relative bg-white dark:bg-neutral-800 rounded-xl shadow-xl max-w-lg w-full max-h-[90vh] overflow-y-auto">
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-neutral-200 dark:border-neutral-700 sticky top-0 bg-white dark:bg-neutral-800 z-10">
            <h2 className="text-xl font-semibold text-neutral-900 dark:text-white">
              Register MCP Server
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
              {/* Error */}
              {error && (
                <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                  <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
                  <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
                </div>
              )}

              {/* Display Name */}
              <div>
                <label htmlFor="server-display-name" className={labelClass}>
                  Display Name <span className="text-red-500">*</span>
                </label>
                <input
                  id="server-display-name"
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="My Linear Integration"
                  required
                  disabled={isLoading}
                  className={inputClass}
                />
              </div>

              {/* Base URL */}
              <div>
                <label htmlFor="server-base-url" className={labelClass}>
                  Base URL <span className="text-red-500">*</span>
                </label>
                <input
                  id="server-base-url"
                  type="url"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder="https://mcp.linear.app/sse"
                  required
                  disabled={isLoading}
                  className={inputClass}
                />
              </div>

              {/* Transport */}
              <div>
                <label htmlFor="server-transport" className={labelClass}>
                  Transport Protocol
                </label>
                <select
                  id="server-transport"
                  value={transport}
                  onChange={(e) => setTransport(e.target.value as TransportType)}
                  disabled={isLoading}
                  className={inputClass}
                >
                  <option value="sse">SSE (Server-Sent Events)</option>
                  <option value="http">HTTP (Streamable HTTP)</option>
                  <option value="websocket">WebSocket</option>
                </select>
              </div>

              {/* Auth Type */}
              <div>
                <label htmlFor="server-auth-type" className={labelClass}>
                  Authentication
                </label>
                <select
                  id="server-auth-type"
                  value={authType}
                  onChange={(e) => setAuthType(e.target.value as AuthType)}
                  disabled={isLoading}
                  className={inputClass}
                >
                  <option value="none">None</option>
                  <option value="api_key">API Key</option>
                  <option value="bearer_token">Bearer Token</option>
                  <option value="oauth2">OAuth2</option>
                </select>
              </div>

              {/* Conditional Credential Fields */}
              {authType === 'api_key' && (
                <div>
                  <label htmlFor="server-api-key" className={labelClass}>
                    API Key <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="server-api-key"
                    type="password"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="Enter API key"
                    required
                    disabled={isLoading}
                    className={inputClass}
                  />
                </div>
              )}

              {authType === 'bearer_token' && (
                <div>
                  <label htmlFor="server-bearer-token" className={labelClass}>
                    Bearer Token <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="server-bearer-token"
                    type="password"
                    value={bearerToken}
                    onChange={(e) => setBearerToken(e.target.value)}
                    placeholder="Enter bearer token"
                    required
                    disabled={isLoading}
                    className={inputClass}
                  />
                </div>
              )}

              {authType === 'oauth2' && (
                <div className="space-y-3 p-4 bg-neutral-50 dark:bg-neutral-750 rounded-lg border border-neutral-200 dark:border-neutral-700">
                  <h4 className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                    OAuth2 Configuration
                  </h4>
                  <div>
                    <label htmlFor="server-oauth2-client-id" className={labelClass}>
                      Client ID <span className="text-red-500">*</span>
                    </label>
                    <input
                      id="server-oauth2-client-id"
                      type="text"
                      value={oauth2ClientId}
                      onChange={(e) => setOauth2ClientId(e.target.value)}
                      placeholder="OAuth2 client ID"
                      required
                      disabled={isLoading}
                      className={inputClass}
                    />
                  </div>
                  <div>
                    <label htmlFor="server-oauth2-client-secret" className={labelClass}>
                      Client Secret <span className="text-red-500">*</span>
                    </label>
                    <input
                      id="server-oauth2-client-secret"
                      type="password"
                      value={oauth2ClientSecret}
                      onChange={(e) => setOauth2ClientSecret(e.target.value)}
                      placeholder="OAuth2 client secret"
                      required
                      disabled={isLoading}
                      className={inputClass}
                    />
                  </div>
                  <div>
                    <label htmlFor="server-oauth2-token-url" className={labelClass}>
                      Token URL <span className="text-red-500">*</span>
                    </label>
                    <input
                      id="server-oauth2-token-url"
                      type="url"
                      value={oauth2TokenUrl}
                      onChange={(e) => setOauth2TokenUrl(e.target.value)}
                      placeholder="https://auth.example.com/oauth/token"
                      required
                      disabled={isLoading}
                      className={inputClass}
                    />
                  </div>
                  <div>
                    <label htmlFor="server-oauth2-scope" className={labelClass}>
                      Scope
                    </label>
                    <input
                      id="server-oauth2-scope"
                      type="text"
                      value={oauth2Scope}
                      onChange={(e) => setOauth2Scope(e.target.value)}
                      placeholder="read write (space-separated)"
                      disabled={isLoading}
                      className={inputClass}
                    />
                  </div>
                </div>
              )}

              {/* Tool Prefix */}
              <div>
                <label htmlFor="server-tool-prefix" className={labelClass}>
                  Tool Prefix
                </label>
                <input
                  id="server-tool-prefix"
                  type="text"
                  value={toolPrefix}
                  onChange={(e) => setToolPrefix(e.target.value)}
                  placeholder="linear"
                  disabled={isLoading}
                  className={inputClass}
                />
                <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                  Prefix for namespaced tool names (e.g., linear__create_issue)
                </p>
              </div>

              {/* Description */}
              <div>
                <label htmlFor="server-description" className={labelClass}>
                  Description
                </label>
                <textarea
                  id="server-description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Brief description of this MCP server..."
                  rows={2}
                  disabled={isLoading}
                  className={`${inputClass} resize-none`}
                />
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-3 p-6 border-t border-neutral-200 dark:border-neutral-700 sticky bottom-0 bg-white dark:bg-neutral-800">
              <button
                type="button"
                onClick={handleClose}
                disabled={isLoading}
                className="px-4 py-2 text-sm font-medium text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isLoading || !isFormValid}
                className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Registering...
                  </>
                ) : (
                  'Register Server'
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export default RegisterServerModal;
