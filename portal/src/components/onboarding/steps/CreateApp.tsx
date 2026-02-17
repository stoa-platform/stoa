/**
 * Step 2: Create Application (CAB-1306)
 */

import { useState } from 'react';
import { AlertCircle, Loader2 } from 'lucide-react';
import { useCreateApplication } from '../../../hooks/useApplications';
import type { Application } from '../../../types';

interface CreateAppProps {
  onCreated: (app: Application) => void;
  onBack: () => void;
}

export function CreateApp({ onCreated, onBack }: CreateAppProps) {
  const [name, setName] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [description, setDescription] = useState('');
  const createApp = useCreateApplication();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const result = await createApp.mutateAsync({
      name: name.toLowerCase().replace(/[^a-z0-9-]/g, '-'),
      description,
      callbackUrls: [],
    });
    onCreated(result);
  };

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <div className="text-center">
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
          Create your application
        </h2>
        <p className="mt-2 text-gray-500 dark:text-neutral-400">
          This registers an OAuth client that your integration will use to authenticate.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label
            htmlFor="displayName"
            className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1"
          >
            Application Name *
          </label>
          <input
            id="displayName"
            type="text"
            required
            value={displayName}
            onChange={(e) => {
              setDisplayName(e.target.value);
              if (!name) {
                setName(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-'));
              }
            }}
            placeholder="My Integration"
            className="w-full px-3 py-2 border border-gray-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-neutral-500 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none"
          />
        </div>

        <div>
          <label
            htmlFor="slug"
            className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1"
          >
            Slug
          </label>
          <input
            id="slug"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-'))}
            placeholder="my-integration"
            className="w-full px-3 py-2 border border-gray-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-neutral-500 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none font-mono text-sm"
          />
        </div>

        <div>
          <label
            htmlFor="description"
            className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1"
          >
            Description
          </label>
          <textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Brief description of what this application does..."
            rows={3}
            className="w-full px-3 py-2 border border-gray-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-800 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-neutral-500 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none resize-none"
          />
        </div>

        {createApp.error && (
          <div className="flex items-center gap-2 text-red-600 dark:text-red-400 text-sm">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            <span>{createApp.error.message}</span>
          </div>
        )}

        <div className="flex justify-between pt-4">
          <button
            type="button"
            onClick={onBack}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-neutral-300 hover:text-gray-900 dark:hover:text-white transition-colors"
          >
            Back
          </button>
          <button
            type="submit"
            disabled={!displayName || createApp.isPending}
            className="px-6 py-2 bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            {createApp.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Create Application
          </button>
        </div>
      </form>
    </div>
  );
}
