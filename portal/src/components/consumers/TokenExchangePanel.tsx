/**
 * Token Exchange Panel (RFC 8693)
 *
 * Allows consumers to exchange tokens visually. Paste a subject token,
 * optionally specify audience/scope, and get back an exchanged token
 * with decoded claims and a cURL snippet.
 *
 * Reference: CAB-1121 Session 3
 */

import { useState } from 'react';
import { ArrowRightLeft, Copy, Check, AlertCircle, Loader2, Terminal } from 'lucide-react';
import { consumersService } from '../../services/consumers';

interface TokenExchangePanelProps {
  tenantId: string;
  consumerId: string;
  consumerName: string;
}

interface DecodedClaims {
  [key: string]: unknown;
}

function decodeJwtPayload(token: string): DecodedClaims | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const payload = atob(parts[1].replace(/-/g, '+').replace(/_/g, '/'));
    return JSON.parse(payload);
  } catch {
    return null;
  }
}

export function TokenExchangePanel({ tenantId, consumerId }: TokenExchangePanelProps) {
  const [subjectToken, setSubjectToken] = useState('');
  const [audience, setAudience] = useState('');
  const [scope, setScope] = useState('');
  const [exchangedToken, setExchangedToken] = useState<string | null>(null);
  const [expiresIn, setExpiresIn] = useState<number | null>(null);
  const [decodedClaims, setDecodedClaims] = useState<DecodedClaims | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [copiedField, setCopiedField] = useState<string | null>(null);

  const copyToClipboard = async (value: string, field: string) => {
    await navigator.clipboard.writeText(value);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  };

  const handleExchange = async () => {
    if (!subjectToken.trim()) return;

    setLoading(true);
    setError(null);
    setExchangedToken(null);
    setDecodedClaims(null);

    try {
      const result = await consumersService.exchangeToken(tenantId, consumerId, {
        subject_token: subjectToken.trim(),
        audience: audience.trim() || undefined,
        scope: scope.trim() || undefined,
      });

      setExchangedToken(result.access_token);
      setExpiresIn(result.expires_in);
      setDecodedClaims(decodeJwtPayload(result.access_token));
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(axiosErr?.response?.data?.detail || 'Token exchange failed');
    } finally {
      setLoading(false);
    }
  };

  const curlSnippet = exchangedToken
    ? `curl -H "Authorization: Bearer ${exchangedToken}" \\
  \${STOA_GATEWAY_URL}/mcp/v1/tools`
    : '';

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm font-medium text-neutral-700 dark:text-neutral-300">
        <ArrowRightLeft className="h-4 w-4" />
        <span>Token Exchange (RFC 8693)</span>
      </div>

      {/* Subject Token Input */}
      <div>
        <label
          htmlFor="subject-token"
          className="block text-sm text-neutral-600 dark:text-neutral-400 mb-1"
        >
          Subject Token
        </label>
        <textarea
          id="subject-token"
          value={subjectToken}
          onChange={(e) => setSubjectToken(e.target.value)}
          placeholder="Paste your access token here..."
          rows={3}
          className="w-full px-3 py-2 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg text-sm font-mono text-neutral-700 dark:text-neutral-300 placeholder-neutral-400 dark:placeholder-neutral-500 focus:ring-2 focus:ring-primary-500 focus:border-transparent resize-none"
        />
      </div>

      {/* Optional Fields */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label
            htmlFor="audience"
            className="block text-sm text-neutral-600 dark:text-neutral-400 mb-1"
          >
            Audience <span className="text-neutral-400 dark:text-neutral-500">(optional)</span>
          </label>
          <input
            id="audience"
            type="text"
            value={audience}
            onChange={(e) => setAudience(e.target.value)}
            placeholder="e.g. stoa-api"
            className="w-full px-3 py-2 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg text-sm text-neutral-700 dark:text-neutral-300 placeholder-neutral-400 dark:placeholder-neutral-500 focus:ring-2 focus:ring-primary-500 focus:border-transparent"
          />
        </div>
        <div>
          <label
            htmlFor="scope"
            className="block text-sm text-neutral-600 dark:text-neutral-400 mb-1"
          >
            Scope <span className="text-neutral-400 dark:text-neutral-500">(optional)</span>
          </label>
          <input
            id="scope"
            type="text"
            value={scope}
            onChange={(e) => setScope(e.target.value)}
            placeholder="e.g. openid profile"
            className="w-full px-3 py-2 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg text-sm text-neutral-700 dark:text-neutral-300 placeholder-neutral-400 dark:placeholder-neutral-500 focus:ring-2 focus:ring-primary-500 focus:border-transparent"
          />
        </div>
      </div>

      {/* Exchange Button */}
      <button
        onClick={handleExchange}
        disabled={loading || !subjectToken.trim()}
        className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <ArrowRightLeft className="h-4 w-4" />
        )}
        {loading ? 'Exchanging...' : 'Exchange Token'}
      </button>

      {/* Error Display */}
      {error && (
        <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
          <AlertCircle className="h-4 w-4 text-red-500 mt-0.5 flex-shrink-0" />
          <span className="text-sm text-red-700 dark:text-red-300">{error}</span>
        </div>
      )}

      {/* Result */}
      {exchangedToken && (
        <div className="space-y-3 pt-2 border-t border-neutral-200 dark:border-neutral-700">
          {/* Exchanged Token */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                Exchanged Token
              </span>
              {expiresIn && (
                <span className="text-xs text-neutral-500 dark:text-neutral-400">
                  expires in {expiresIn}s
                </span>
              )}
            </div>
            <div className="flex items-start gap-2">
              <div className="flex-1 px-3 py-2 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg font-mono text-xs text-neutral-700 dark:text-neutral-300 break-all max-h-20 overflow-y-auto">
                {exchangedToken}
              </div>
              <button
                onClick={() => copyToClipboard(exchangedToken, 'token')}
                className="p-2 text-neutral-500 hover:text-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg transition-colors flex-shrink-0"
                title="Copy token"
              >
                {copiedField === 'token' ? (
                  <Check className="h-4 w-4 text-green-500" />
                ) : (
                  <Copy className="h-4 w-4" />
                )}
              </button>
            </div>
          </div>

          {/* Decoded Claims */}
          {decodedClaims && (
            <div>
              <span className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-1">
                Token Claims
              </span>
              <pre className="px-3 py-2 bg-neutral-50 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg text-xs text-neutral-600 dark:text-neutral-400 overflow-x-auto max-h-32 overflow-y-auto">
                {JSON.stringify(decodedClaims, null, 2)}
              </pre>
            </div>
          )}

          {/* cURL Snippet */}
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Terminal className="h-4 w-4 text-neutral-500 dark:text-neutral-400" />
              <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                Quick Test
              </span>
            </div>
            <div className="relative">
              <pre className="px-3 py-2 bg-neutral-900 dark:bg-neutral-950 text-green-400 text-xs rounded-lg overflow-x-auto">
                {curlSnippet}
              </pre>
              <button
                onClick={() => copyToClipboard(curlSnippet, 'curl')}
                className="absolute top-1.5 right-1.5 p-1 bg-neutral-700 hover:bg-neutral-600 rounded text-neutral-300 transition-colors"
                title="Copy cURL command"
              >
                {copiedField === 'curl' ? (
                  <Check className="h-3 w-3 text-green-400" />
                ) : (
                  <Copy className="h-3 w-3" />
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default TokenExchangePanel;
