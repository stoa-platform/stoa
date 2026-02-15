import { useState } from 'react';
import { X } from 'lucide-react';
import { backendApisService } from '../../services/backendApisApi';
import { useToastActions } from '@stoa/shared/components/Toast';
import type { BackendApiAuthType, BackendApiCreate } from '../../types';

interface RegisterApiModalProps {
  tenantId: string;
  onClose: () => void;
  onCreated: () => void;
}

const authTypeOptions: { value: BackendApiAuthType; label: string }[] = [
  { value: 'none', label: 'None' },
  { value: 'api_key', label: 'API Key' },
  { value: 'bearer', label: 'Bearer Token' },
  { value: 'basic', label: 'Basic Auth' },
  { value: 'oauth2_cc', label: 'OAuth2 Client Credentials' },
];

export function RegisterApiModal({ tenantId, onClose, onCreated }: RegisterApiModalProps) {
  const toast = useToastActions();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [description, setDescription] = useState('');
  const [backendUrl, setBackendUrl] = useState('');
  const [openapiSpecUrl, setOpenapiSpecUrl] = useState('');
  const [authType, setAuthType] = useState<BackendApiAuthType>('none');

  // Auth config fields
  const [headerName, setHeaderName] = useState('X-API-Key');
  const [headerValue, setHeaderValue] = useState('');
  const [bearerToken, setBearerToken] = useState('');
  const [basicUsername, setBasicUsername] = useState('');
  const [basicPassword, setBasicPassword] = useState('');
  const [oauthClientId, setOauthClientId] = useState('');
  const [oauthClientSecret, setOauthClientSecret] = useState('');
  const [oauthTokenUrl, setOauthTokenUrl] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      let authConfig: Record<string, string> | undefined;

      if (authType === 'api_key' && headerValue) {
        authConfig = { header_name: headerName, header_value: headerValue };
      } else if (authType === 'bearer' && bearerToken) {
        authConfig = { token: bearerToken };
      } else if (authType === 'basic' && basicUsername) {
        authConfig = { username: basicUsername, password: basicPassword };
      } else if (authType === 'oauth2_cc' && oauthClientId) {
        authConfig = {
          client_id: oauthClientId,
          client_secret: oauthClientSecret,
          token_url: oauthTokenUrl,
        };
      }

      const payload: BackendApiCreate = {
        name,
        display_name: displayName || undefined,
        description: description || undefined,
        backend_url: backendUrl,
        openapi_spec_url: openapiSpecUrl || undefined,
        auth_type: authType,
        auth_config: authConfig,
      };

      await backendApisService.createBackendApi(tenantId, payload);
      toast.success('API registered', `${displayName || name} has been created as draft`);
      onCreated();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to register API';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-neutral-800 rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex justify-between items-center px-6 py-4 border-b dark:border-neutral-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Register Backend API
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-neutral-300"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-5">
          {error && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg text-sm">
              {error}
            </div>
          )}

          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
              Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500"
              placeholder="petstore-api"
              required
              pattern="^[a-z][a-z0-9-_]*$"
              title="Lowercase letters, numbers, hyphens, and underscores."
            />
          </div>

          {/* Display Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
              Display Name
            </label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500"
              placeholder="Petstore API"
            />
          </div>

          {/* Backend URL */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
              Backend URL <span className="text-red-500">*</span>
            </label>
            <input
              type="url"
              value={backendUrl}
              onChange={(e) => setBackendUrl(e.target.value)}
              className="w-full border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500"
              placeholder="https://api.example.com/v1"
              required
            />
          </div>

          {/* OpenAPI Spec URL */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
              OpenAPI Spec URL
            </label>
            <input
              type="url"
              value={openapiSpecUrl}
              onChange={(e) => setOpenapiSpecUrl(e.target.value)}
              className="w-full border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500"
              placeholder="https://api.example.com/openapi.json"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500"
              rows={2}
              placeholder="A brief description of this API"
            />
          </div>

          {/* Auth Type */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
              Authentication
            </label>
            <select
              value={authType}
              onChange={(e) => setAuthType(e.target.value as BackendApiAuthType)}
              className="w-full border border-gray-300 dark:border-neutral-600 rounded-lg px-3 py-2 bg-white dark:bg-neutral-700 dark:text-white focus:ring-2 focus:ring-blue-500"
            >
              {authTypeOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Dynamic auth config fields */}
          {authType === 'api_key' && (
            <div className="space-y-3 p-4 bg-gray-50 dark:bg-neutral-700 rounded-lg">
              <h4 className="text-sm font-medium text-gray-700 dark:text-neutral-300">
                API Key Configuration
              </h4>
              <div>
                <label className="block text-xs text-gray-600 dark:text-neutral-400 mb-1">
                  Header Name
                </label>
                <input
                  type="text"
                  value={headerName}
                  onChange={(e) => setHeaderName(e.target.value)}
                  className="w-full border border-gray-300 dark:border-neutral-600 rounded px-3 py-2 text-sm bg-white dark:bg-neutral-600 dark:text-white"
                  placeholder="X-API-Key"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-600 dark:text-neutral-400 mb-1">
                  API Key Value
                </label>
                <input
                  type="password"
                  value={headerValue}
                  onChange={(e) => setHeaderValue(e.target.value)}
                  className="w-full border border-gray-300 dark:border-neutral-600 rounded px-3 py-2 text-sm bg-white dark:bg-neutral-600 dark:text-white"
                  placeholder="Enter API key"
                />
              </div>
            </div>
          )}

          {authType === 'bearer' && (
            <div className="p-4 bg-gray-50 dark:bg-neutral-700 rounded-lg">
              <label className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1">
                Bearer Token
              </label>
              <input
                type="password"
                value={bearerToken}
                onChange={(e) => setBearerToken(e.target.value)}
                className="w-full border border-gray-300 dark:border-neutral-600 rounded px-3 py-2 text-sm bg-white dark:bg-neutral-600 dark:text-white"
                placeholder="Enter bearer token"
              />
            </div>
          )}

          {authType === 'basic' && (
            <div className="space-y-3 p-4 bg-gray-50 dark:bg-neutral-700 rounded-lg">
              <h4 className="text-sm font-medium text-gray-700 dark:text-neutral-300">
                Basic Auth Credentials
              </h4>
              <div>
                <label className="block text-xs text-gray-600 dark:text-neutral-400 mb-1">
                  Username
                </label>
                <input
                  type="text"
                  value={basicUsername}
                  onChange={(e) => setBasicUsername(e.target.value)}
                  className="w-full border border-gray-300 dark:border-neutral-600 rounded px-3 py-2 text-sm bg-white dark:bg-neutral-600 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-600 dark:text-neutral-400 mb-1">
                  Password
                </label>
                <input
                  type="password"
                  value={basicPassword}
                  onChange={(e) => setBasicPassword(e.target.value)}
                  className="w-full border border-gray-300 dark:border-neutral-600 rounded px-3 py-2 text-sm bg-white dark:bg-neutral-600 dark:text-white"
                />
              </div>
            </div>
          )}

          {authType === 'oauth2_cc' && (
            <div className="space-y-3 p-4 bg-gray-50 dark:bg-neutral-700 rounded-lg">
              <h4 className="text-sm font-medium text-gray-700 dark:text-neutral-300">
                OAuth2 Client Credentials
              </h4>
              <div>
                <label className="block text-xs text-gray-600 dark:text-neutral-400 mb-1">
                  Client ID
                </label>
                <input
                  type="text"
                  value={oauthClientId}
                  onChange={(e) => setOauthClientId(e.target.value)}
                  className="w-full border border-gray-300 dark:border-neutral-600 rounded px-3 py-2 text-sm bg-white dark:bg-neutral-600 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-600 dark:text-neutral-400 mb-1">
                  Client Secret
                </label>
                <input
                  type="password"
                  value={oauthClientSecret}
                  onChange={(e) => setOauthClientSecret(e.target.value)}
                  className="w-full border border-gray-300 dark:border-neutral-600 rounded px-3 py-2 text-sm bg-white dark:bg-neutral-600 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-600 dark:text-neutral-400 mb-1">
                  Token URL
                </label>
                <input
                  type="url"
                  value={oauthTokenUrl}
                  onChange={(e) => setOauthTokenUrl(e.target.value)}
                  className="w-full border border-gray-300 dark:border-neutral-600 rounded px-3 py-2 text-sm bg-white dark:bg-neutral-600 dark:text-white"
                  placeholder="https://auth.example.com/oauth/token"
                />
              </div>
            </div>
          )}
        </form>

        {/* Footer */}
        <div className="flex justify-end gap-3 px-6 py-4 border-t dark:border-neutral-700 bg-gray-50 dark:bg-neutral-800">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 border border-gray-300 dark:border-neutral-600 rounded-lg hover:bg-white dark:hover:bg-neutral-700 dark:text-neutral-300"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={loading}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? 'Registering...' : 'Register API'}
          </button>
        </div>
      </div>
    </div>
  );
}
