/**
 * Step 4: First Call — credentials + curl example (CAB-1306)
 */

import { Copy, Check, ExternalLink } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { config } from '../../../config';
import type { Application, API } from '../../../types';
import type { UseCase } from './ChooseUseCase';

interface FirstCallProps {
  app: Application | null;
  selectedApi: API | null;
  useCase: UseCase;
  onFinish: () => void;
}

export function FirstCall({ app, selectedApi, useCase, onFinish }: FirstCallProps) {
  const { t } = useTranslation('onboarding');
  const [copied, setCopied] = useState<string | null>(null);

  const apiBaseUrl = config.api.baseUrl;
  const mcpBaseUrl = config.mcp.baseUrl;

  const curlCommand = selectedApi
    ? `curl -X GET "${apiBaseUrl}/v1/portal/apis/${selectedApi.id}" \\
  -H "Authorization: Bearer $TOKEN" \\
  -H "Content-Type: application/json"`
    : `curl -X GET "${apiBaseUrl}/v1/portal/apis" \\
  -H "Authorization: Bearer $TOKEN"`;

  const mcpConfig = app
    ? `{
  "mcpServers": {
    "stoa": {
      "url": "${mcpBaseUrl}/mcp/sse",
      "transport": "sse"
    }
  }
}`
    : '';

  const handleCopy = async (text: string, id: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="text-center">
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white">{t('firstCall.title')}</h2>
        <p className="mt-2 text-gray-500 dark:text-neutral-400">{t('firstCall.subtitle')}</p>
      </div>

      {/* Credentials summary */}
      {app && (
        <div className="bg-gray-50 dark:bg-neutral-900 rounded-lg border border-gray-200 dark:border-neutral-700 p-4">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">
            {t('firstCall.credentials')}
          </h3>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-gray-500 dark:text-neutral-400">{t('firstCall.appName')}</dt>
              <dd className="font-mono text-gray-900 dark:text-white">{app.name}</dd>
            </div>
            {app.clientId && (
              <div className="flex justify-between">
                <dt className="text-gray-500 dark:text-neutral-400">{t('firstCall.clientId')}</dt>
                <dd className="font-mono text-gray-900 dark:text-white">{app.clientId}</dd>
              </div>
            )}
            {app.clientSecret && (
              <div className="flex justify-between items-center">
                <dt className="text-gray-500 dark:text-neutral-400">
                  {t('firstCall.clientSecret')}
                </dt>
                <dd className="flex items-center gap-2">
                  <code className="font-mono text-xs bg-yellow-50 dark:bg-yellow-900/20 text-yellow-800 dark:text-yellow-300 px-2 py-0.5 rounded">
                    {app.clientSecret}
                  </code>
                  <button
                    onClick={() => handleCopy(app.clientSecret!, 'secret')}
                    className="text-gray-400 hover:text-gray-600 dark:hover:text-neutral-300"
                    title={t('firstCall.copySecret')}
                  >
                    {copied === 'secret' ? (
                      <Check className="h-4 w-4 text-green-500" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </button>
                </dd>
              </div>
            )}
          </dl>
          {app.clientSecret && (
            <p className="mt-3 text-xs text-yellow-600 dark:text-yellow-400">
              {t('firstCall.secretWarning')}
            </p>
          )}
        </div>
      )}

      {/* curl example */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
            {useCase === 'mcp-agent' ? t('firstCall.mcpConfig') : t('firstCall.exampleCall')}
          </h3>
          <button
            onClick={() => handleCopy(useCase === 'mcp-agent' ? mcpConfig : curlCommand, 'example')}
            className="text-xs text-gray-500 dark:text-neutral-400 hover:text-gray-700 dark:hover:text-neutral-300 flex items-center gap-1"
          >
            {copied === 'example' ? (
              <>
                <Check className="h-3 w-3 text-green-500" /> {t('firstCall.copied')}
              </>
            ) : (
              <>
                <Copy className="h-3 w-3" /> {t('firstCall.copy')}
              </>
            )}
          </button>
        </div>
        <pre className="bg-gray-900 dark:bg-neutral-950 text-gray-100 rounded-lg p-4 text-sm overflow-x-auto">
          <code>{useCase === 'mcp-agent' ? mcpConfig : curlCommand}</code>
        </pre>
      </div>

      {/* Links */}
      <div className="flex flex-wrap gap-3">
        {selectedApi && (
          <a
            href={`/apis/${selectedApi.id}/test`}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-primary-600 dark:text-primary-400 bg-primary-50 dark:bg-primary-900/20 rounded-lg hover:bg-primary-100 dark:hover:bg-primary-900/30 transition-colors"
          >
            {t('firstCall.trySandbox')}
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        )}
        <a
          href={config.services.docs.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-gray-600 dark:text-neutral-400 bg-gray-50 dark:bg-neutral-900 rounded-lg hover:bg-gray-100 dark:hover:bg-neutral-800 transition-colors"
        >
          {t('firstCall.documentation')}
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      </div>

      {/* Finish */}
      <div className="flex justify-center pt-4">
        <button
          onClick={onFinish}
          className="px-8 py-3 bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-700 transition-colors"
        >
          {t('firstCall.goToDashboard')}
        </button>
      </div>
    </div>
  );
}
