// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * Response Viewer Component
 *
 * Displays API response with status, headers, body, and timing information.
 */

import { useState } from 'react';
import {
  CheckCircle,
  XCircle,
  Clock,
  Copy,
  Check,
  ChevronDown,
  ChevronRight,
  FileJson,
  AlertTriangle,
} from 'lucide-react';

export interface ResponseData {
  status: number;
  statusText: string;
  headers: Record<string, string>;
  body: unknown;
  timing: {
    total: number;
    dns?: number;
    tcp?: number;
    ttfb?: number;
  };
  error?: string;
}

interface ResponseViewerProps {
  response: ResponseData | null;
  isLoading?: boolean;
}

const STATUS_COLORS: Record<string, { bg: string; text: string; icon: typeof CheckCircle }> = {
  '2xx': { bg: 'bg-green-100', text: 'text-green-700', icon: CheckCircle },
  '3xx': { bg: 'bg-blue-100', text: 'text-blue-700', icon: CheckCircle },
  '4xx': { bg: 'bg-amber-100', text: 'text-amber-700', icon: AlertTriangle },
  '5xx': { bg: 'bg-red-100', text: 'text-red-700', icon: XCircle },
  default: { bg: 'bg-gray-100', text: 'text-gray-700', icon: AlertTriangle },
};

function getStatusColor(status: number) {
  if (status >= 200 && status < 300) return STATUS_COLORS['2xx'];
  if (status >= 300 && status < 400) return STATUS_COLORS['3xx'];
  if (status >= 400 && status < 500) return STATUS_COLORS['4xx'];
  if (status >= 500) return STATUS_COLORS['5xx'];
  return STATUS_COLORS['default'];
}

function formatTiming(ms: number): string {
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

export function ResponseViewer({ response, isLoading }: ResponseViewerProps) {
  const [activeTab, setActiveTab] = useState<'body' | 'headers'>('body');
  const [showRawBody, setShowRawBody] = useState(false);
  const [copied, setCopied] = useState(false);
  const [headersExpanded, setHeadersExpanded] = useState(true);

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-8">
        <div className="flex flex-col items-center justify-center">
          <div className="w-8 h-8 border-2 border-primary-600 border-t-transparent rounded-full animate-spin mb-4" />
          <p className="text-gray-500">Sending request...</p>
        </div>
      </div>
    );
  }

  if (!response) {
    return (
      <div className="bg-gray-50 rounded-lg border border-gray-200 border-dashed p-8">
        <div className="flex flex-col items-center justify-center text-center">
          <FileJson className="h-12 w-12 text-gray-300 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-1">No Response Yet</h3>
          <p className="text-sm text-gray-500">
            Configure your request above and click Send to see the response
          </p>
        </div>
      </div>
    );
  }

  const statusColor = getStatusColor(response.status);
  const StatusIcon = statusColor.icon;

  const bodyString = typeof response.body === 'string'
    ? response.body
    : JSON.stringify(response.body, null, 2);

  const bodySize = new Blob([bodyString]).size;

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(bodyString);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers
      const textarea = document.createElement('textarea');
      textarea.value = bodyString;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      {/* Status Bar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-gray-50">
        <div className="flex items-center gap-4">
          {/* Status */}
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg ${statusColor.bg}`}>
            <StatusIcon className={`h-4 w-4 ${statusColor.text}`} />
            <span className={`font-semibold ${statusColor.text}`}>
              {response.status}
            </span>
            <span className={`text-sm ${statusColor.text}`}>
              {response.statusText}
            </span>
          </div>

          {/* Timing */}
          <div className="flex items-center gap-1.5 text-gray-500">
            <Clock className="h-4 w-4" />
            <span className="text-sm font-medium">
              {formatTiming(response.timing.total)}
            </span>
          </div>

          {/* Size */}
          <div className="text-sm text-gray-500">
            {formatBytes(bodySize)}
          </div>
        </div>

        {/* Copy Button */}
        <button
          onClick={copyToClipboard}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
        >
          {copied ? (
            <>
              <Check className="h-4 w-4 text-green-500" />
              Copied!
            </>
          ) : (
            <>
              <Copy className="h-4 w-4" />
              Copy
            </>
          )}
        </button>
      </div>

      {/* Error Message */}
      {response.error && (
        <div className="px-4 py-3 bg-red-50 border-b border-red-100">
          <div className="flex items-start gap-2">
            <XCircle className="h-5 w-5 text-red-500 mt-0.5 flex-shrink-0" />
            <div>
              <p className="font-medium text-red-800">Request Failed</p>
              <p className="text-sm text-red-600 mt-1">{response.error}</p>
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-4 px-4">
          <button
            onClick={() => setActiveTab('body')}
            className={`
              py-3 px-1 border-b-2 text-sm font-medium transition-colors
              ${activeTab === 'body'
                ? 'border-primary-600 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
              }
            `}
          >
            Body
          </button>
          <button
            onClick={() => setActiveTab('headers')}
            className={`
              py-3 px-1 border-b-2 text-sm font-medium transition-colors
              ${activeTab === 'headers'
                ? 'border-primary-600 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
              }
            `}
          >
            Headers
            <span className="ml-1.5 px-1.5 py-0.5 text-xs bg-gray-100 rounded-full">
              {Object.keys(response.headers).length}
            </span>
          </button>
        </nav>
      </div>

      {/* Tab Content */}
      <div className="max-h-[500px] overflow-auto">
        {/* Body Tab */}
        {activeTab === 'body' && (
          <div className="relative">
            {/* View Toggle */}
            <div className="absolute top-2 right-2 z-10">
              <button
                onClick={() => setShowRawBody(!showRawBody)}
                className="px-2 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded transition-colors"
              >
                {showRawBody ? 'Pretty' : 'Raw'}
              </button>
            </div>

            {showRawBody ? (
              <pre className="p-4 text-sm font-mono text-gray-800 whitespace-pre-wrap break-all">
                {bodyString}
              </pre>
            ) : (
              <pre className="p-4 text-sm font-mono overflow-x-auto">
                <code className="language-json">{bodyString}</code>
              </pre>
            )}
          </div>
        )}

        {/* Headers Tab */}
        {activeTab === 'headers' && (
          <div className="p-4">
            <button
              onClick={() => setHeadersExpanded(!headersExpanded)}
              className="flex items-center gap-2 text-sm font-medium text-gray-700 hover:text-gray-900 mb-3"
            >
              {headersExpanded ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
              Response Headers ({Object.keys(response.headers).length})
            </button>

            {headersExpanded && (
              <div className="space-y-1">
                {Object.entries(response.headers).map(([key, value]) => (
                  <div
                    key={key}
                    className="flex items-start py-1.5 px-2 hover:bg-gray-50 rounded text-sm"
                  >
                    <span className="font-medium text-gray-700 w-48 flex-shrink-0">
                      {key}:
                    </span>
                    <span className="text-gray-600 font-mono break-all">
                      {value}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Timing Details */}
      {response.timing && (response.timing.dns || response.timing.tcp || response.timing.ttfb) && (
        <div className="px-4 py-3 border-t border-gray-200 bg-gray-50">
          <div className="flex items-center gap-6 text-xs text-gray-500">
            <span className="font-medium text-gray-700">Timing:</span>
            {response.timing.dns !== undefined && (
              <span>DNS: {formatTiming(response.timing.dns)}</span>
            )}
            {response.timing.tcp !== undefined && (
              <span>TCP: {formatTiming(response.timing.tcp)}</span>
            )}
            {response.timing.ttfb !== undefined && (
              <span>TTFB: {formatTiming(response.timing.ttfb)}</span>
            )}
            <span className="font-medium">Total: {formatTiming(response.timing.total)}</span>
          </div>
        </div>
      )}
    </div>
  );
}

export default ResponseViewer;
