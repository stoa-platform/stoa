/**
 * Request Builder Component
 *
 * Form for building API requests with method, path, headers, and body.
 */

import { useState } from 'react';
import { Plus, Trash2, Send, Loader2 } from 'lucide-react';

export interface Header {
  key: string;
  value: string;
  enabled: boolean;
}

export interface RequestConfig {
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  path: string;
  headers: Header[];
  body: string;
  queryParams: Header[];
}

interface RequestBuilderProps {
  baseUrl: string;
  initialPath?: string;
  initialMethod?: RequestConfig['method'];
  onSubmit: (request: RequestConfig) => void;
  isLoading?: boolean;
  disabled?: boolean;
}

const HTTP_METHODS: RequestConfig['method'][] = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'];

const METHOD_COLORS: Record<RequestConfig['method'], string> = {
  GET: 'bg-green-100 text-green-700 border-green-300',
  POST: 'bg-blue-100 text-blue-700 border-blue-300',
  PUT: 'bg-amber-100 text-amber-700 border-amber-300',
  DELETE: 'bg-red-100 text-red-700 border-red-300',
  PATCH: 'bg-purple-100 text-purple-700 border-purple-300',
};

export function RequestBuilder({
  baseUrl,
  initialPath = '/',
  initialMethod = 'GET',
  onSubmit,
  isLoading = false,
  disabled = false,
}: RequestBuilderProps) {
  const [method, setMethod] = useState<RequestConfig['method']>(initialMethod);
  const [path, setPath] = useState(initialPath);
  const [headers, setHeaders] = useState<Header[]>([
    { key: 'Content-Type', value: 'application/json', enabled: true },
    { key: 'Accept', value: 'application/json', enabled: true },
  ]);
  const [queryParams, setQueryParams] = useState<Header[]>([]);
  const [body, setBody] = useState('');
  const [activeTab, setActiveTab] = useState<'params' | 'headers' | 'body'>('params');

  const addHeader = () => {
    setHeaders([...headers, { key: '', value: '', enabled: true }]);
  };

  const updateHeader = (index: number, field: keyof Header, value: string | boolean) => {
    const newHeaders = [...headers];
    newHeaders[index] = { ...newHeaders[index], [field]: value };
    setHeaders(newHeaders);
  };

  const removeHeader = (index: number) => {
    setHeaders(headers.filter((_, i) => i !== index));
  };

  const addQueryParam = () => {
    setQueryParams([...queryParams, { key: '', value: '', enabled: true }]);
  };

  const updateQueryParam = (index: number, field: keyof Header, value: string | boolean) => {
    const newParams = [...queryParams];
    newParams[index] = { ...newParams[index], [field]: value };
    setQueryParams(newParams);
  };

  const removeQueryParam = (index: number) => {
    setQueryParams(queryParams.filter((_, i) => i !== index));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      method,
      path,
      headers: headers.filter((h) => h.enabled && h.key),
      queryParams: queryParams.filter((p) => p.enabled && p.key),
      body,
    });
  };

  const buildFullUrl = () => {
    let url = `${baseUrl}${path}`;
    const enabledParams = queryParams.filter((p) => p.enabled && p.key);
    if (enabledParams.length > 0) {
      const params = new URLSearchParams();
      enabledParams.forEach((p) => params.append(p.key, p.value));
      url += `?${params.toString()}`;
    }
    return url;
  };

  const showBodyTab = ['POST', 'PUT', 'PATCH'].includes(method);

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* URL Bar */}
      <div className="flex gap-2">
        <select
          value={method}
          onChange={(e) => setMethod(e.target.value as RequestConfig['method'])}
          disabled={disabled}
          className={`
            px-3 py-2.5 border rounded-lg font-medium text-sm
            focus:ring-2 focus:ring-primary-500 focus:border-primary-500
            disabled:opacity-50 disabled:cursor-not-allowed
            ${METHOD_COLORS[method]}
          `}
        >
          {HTTP_METHODS.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>

        <div className="flex-1 relative">
          <input
            type="text"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="/api/v1/resource"
            disabled={disabled}
            className="w-full px-3 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:bg-gray-100 disabled:cursor-not-allowed font-mono text-sm"
          />
        </div>

        <button
          type="submit"
          disabled={disabled || isLoading}
          className="inline-flex items-center gap-2 px-4 py-2.5 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium"
        >
          {isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
          Send
        </button>
      </div>

      {/* Full URL Preview */}
      <div className="text-xs text-gray-500">
        <span className="font-medium">Full URL:</span>{' '}
        <code className="bg-gray-100 px-2 py-0.5 rounded break-all">{buildFullUrl()}</code>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-4">
          <button
            type="button"
            onClick={() => setActiveTab('params')}
            className={`
              py-2 px-1 border-b-2 text-sm font-medium transition-colors
              ${activeTab === 'params'
                ? 'border-primary-600 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
              }
            `}
          >
            Query Params
            {queryParams.filter((p) => p.enabled && p.key).length > 0 && (
              <span className="ml-1.5 px-1.5 py-0.5 text-xs bg-gray-100 rounded-full">
                {queryParams.filter((p) => p.enabled && p.key).length}
              </span>
            )}
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('headers')}
            className={`
              py-2 px-1 border-b-2 text-sm font-medium transition-colors
              ${activeTab === 'headers'
                ? 'border-primary-600 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
              }
            `}
          >
            Headers
            {headers.filter((h) => h.enabled && h.key).length > 0 && (
              <span className="ml-1.5 px-1.5 py-0.5 text-xs bg-gray-100 rounded-full">
                {headers.filter((h) => h.enabled && h.key).length}
              </span>
            )}
          </button>
          {showBodyTab && (
            <button
              type="button"
              onClick={() => setActiveTab('body')}
              className={`
                py-2 px-1 border-b-2 text-sm font-medium transition-colors
                ${activeTab === 'body'
                  ? 'border-primary-600 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
                }
              `}
            >
              Body
              {body && (
                <span className="ml-1.5 px-1.5 py-0.5 text-xs bg-green-100 text-green-700 rounded-full">
                  Set
                </span>
              )}
            </button>
          )}
        </nav>
      </div>

      {/* Tab Content */}
      <div className="min-h-[200px]">
        {/* Query Params Tab */}
        {activeTab === 'params' && (
          <div className="space-y-2">
            {queryParams.map((param, index) => (
              <div key={index} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={param.enabled}
                  onChange={(e) => updateQueryParam(index, 'enabled', e.target.checked)}
                  disabled={disabled}
                  className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <input
                  type="text"
                  value={param.key}
                  onChange={(e) => updateQueryParam(index, 'key', e.target.value)}
                  placeholder="Key"
                  disabled={disabled}
                  className="flex-1 px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:bg-gray-100"
                />
                <input
                  type="text"
                  value={param.value}
                  onChange={(e) => updateQueryParam(index, 'value', e.target.value)}
                  placeholder="Value"
                  disabled={disabled}
                  className="flex-1 px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:bg-gray-100"
                />
                <button
                  type="button"
                  onClick={() => removeQueryParam(index)}
                  disabled={disabled}
                  className="p-1.5 text-gray-400 hover:text-red-500 transition-colors disabled:opacity-50"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
            <button
              type="button"
              onClick={addQueryParam}
              disabled={disabled}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50"
            >
              <Plus className="h-4 w-4" />
              Add Parameter
            </button>
          </div>
        )}

        {/* Headers Tab */}
        {activeTab === 'headers' && (
          <div className="space-y-2">
            {headers.map((header, index) => (
              <div key={index} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={header.enabled}
                  onChange={(e) => updateHeader(index, 'enabled', e.target.checked)}
                  disabled={disabled}
                  className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <input
                  type="text"
                  value={header.key}
                  onChange={(e) => updateHeader(index, 'key', e.target.value)}
                  placeholder="Header name"
                  disabled={disabled}
                  className="flex-1 px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:bg-gray-100"
                />
                <input
                  type="text"
                  value={header.value}
                  onChange={(e) => updateHeader(index, 'value', e.target.value)}
                  placeholder="Value"
                  disabled={disabled}
                  className="flex-1 px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:bg-gray-100"
                />
                <button
                  type="button"
                  onClick={() => removeHeader(index)}
                  disabled={disabled}
                  className="p-1.5 text-gray-400 hover:text-red-500 transition-colors disabled:opacity-50"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
            <button
              type="button"
              onClick={addHeader}
              disabled={disabled}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50"
            >
              <Plus className="h-4 w-4" />
              Add Header
            </button>
          </div>
        )}

        {/* Body Tab */}
        {activeTab === 'body' && showBodyTab && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-500">Request Body (JSON)</span>
              <button
                type="button"
                onClick={() => {
                  try {
                    const formatted = JSON.stringify(JSON.parse(body), null, 2);
                    setBody(formatted);
                  } catch {
                    // Invalid JSON, ignore
                  }
                }}
                disabled={disabled || !body}
                className="text-xs text-primary-600 hover:text-primary-700 disabled:opacity-50"
              >
                Format JSON
              </button>
            </div>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder='{\n  "key": "value"\n}'
              disabled={disabled}
              rows={8}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg font-mono text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:bg-gray-100 disabled:cursor-not-allowed resize-y"
            />
          </div>
        )}
      </div>
    </form>
  );
}

export default RequestBuilder;
