/**
 * Step 3: Subscribe to an API (CAB-1306)
 */

import { useState } from 'react';
import { Search, Check, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAPIs } from '../../../hooks/useAPIs';
import type { API } from '../../../types';

interface SubscribeAPIProps {
  onSelected: (api: API) => void;
  onBack: () => void;
  onSkip: () => void;
}

export function SubscribeAPI({ onSelected, onBack, onSkip }: SubscribeAPIProps) {
  const { t } = useTranslation('onboarding');
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data, isLoading } = useAPIs({ search, page: 1, pageSize: 6 });

  const apis = data?.items ?? [];
  const selected = apis.find((a) => a.id === selectedId);

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
          {t('subscribeApi.title')}
        </h2>
        <p className="mt-2 text-gray-500 dark:text-neutral-400">{t('subscribeApi.subtitle')}</p>
      </div>

      {/* Search */}
      <div className="relative max-w-md mx-auto">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t('subscribeApi.searchPlaceholder')}
          className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-neutral-500 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
        />
      </div>

      {/* API grid */}
      {isLoading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-primary-500" />
        </div>
      ) : apis.length === 0 ? (
        <p className="text-center text-gray-500 dark:text-neutral-400 py-8">
          {t('subscribeApi.noApis')}
        </p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {apis.map((api) => (
            <button
              key={api.id}
              onClick={() => setSelectedId(api.id)}
              className={`relative text-left p-4 rounded-lg border transition-all ${
                selectedId === api.id
                  ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20 ring-2 ring-primary-500'
                  : 'border-gray-200 dark:border-neutral-700 hover:border-gray-300 dark:hover:border-neutral-600'
              }`}
            >
              {selectedId === api.id && (
                <div className="absolute top-2 right-2 bg-primary-600 text-white rounded-full p-0.5">
                  <Check className="h-3 w-3" />
                </div>
              )}
              <h3 className="font-medium text-gray-900 dark:text-white text-sm">{api.name}</h3>
              <p className="text-xs text-gray-500 dark:text-neutral-400 mt-1 line-clamp-2">
                {api.description}
              </p>
              {api.version && (
                <span className="inline-block mt-2 text-xs px-2 py-0.5 bg-gray-100 dark:bg-neutral-800 rounded text-gray-600 dark:text-neutral-400">
                  v{api.version}
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      {/* Actions */}
      <div className="flex justify-between pt-4">
        <button
          type="button"
          onClick={onBack}
          className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-neutral-300 hover:text-gray-900 dark:hover:text-white transition-colors"
        >
          {t('subscribeApi.back')}
        </button>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={onSkip}
            className="px-4 py-2 text-sm font-medium text-gray-500 dark:text-neutral-400 hover:text-gray-700 dark:hover:text-neutral-300 transition-colors"
          >
            {t('subscribeApi.skip')}
          </button>
          <button
            type="button"
            onClick={() => selected && onSelected(selected)}
            disabled={!selected}
            className="px-6 py-2 bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {t('subscribeApi.continue')}
          </button>
        </div>
      </div>
    </div>
  );
}
