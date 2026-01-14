/**
 * Create Application Modal Component
 *
 * Modal form for creating a new consumer application.
 */

import { useState } from 'react';
import { X, Plus, Trash2, Loader2, AlertCircle } from 'lucide-react';
import type { ApplicationCreateRequest } from '../../types';

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
  const [callbackUrls, setCallbackUrls] = useState<string[]>(['']);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const filteredCallbackUrls = callbackUrls.filter((url) => url.trim() !== '');

    await onSubmit({
      name: name.trim(),
      description: description.trim() || undefined,
      callbackUrls: filteredCallbackUrls,
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
        <div className="relative bg-white rounded-xl shadow-xl max-w-lg w-full">
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-gray-200">
            <h2 className="text-xl font-semibold text-gray-900">
              Create New Application
            </h2>
            <button
              onClick={handleClose}
              disabled={isLoading}
              className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit}>
            <div className="p-6 space-y-4">
              {/* Error message */}
              {error && (
                <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg">
                  <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
                  <p className="text-sm text-red-700">{error}</p>
                </div>
              )}

              {/* Name */}
              <div>
                <label htmlFor="app-name" className="block text-sm font-medium text-gray-700 mb-1">
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
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
                />
              </div>

              {/* Description */}
              <div>
                <label htmlFor="app-description" className="block text-sm font-medium text-gray-700 mb-1">
                  Description
                </label>
                <textarea
                  id="app-description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Brief description of what this application does..."
                  rows={3}
                  disabled={isLoading}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:bg-gray-100 disabled:cursor-not-allowed resize-none"
                />
              </div>

              {/* Callback URLs */}
              <div>
                <label htmlFor="callback-url-0" className="block text-sm font-medium text-gray-700 mb-1">
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
                        className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
                      />
                      {callbackUrls.length > 1 && (
                        <button
                          type="button"
                          onClick={() => handleRemoveCallbackUrl(index)}
                          disabled={isLoading}
                          className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-50"
                        >
                          <Trash2 className="h-5 w-5" />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
                <button
                  type="button"
                  onClick={handleAddCallbackUrl}
                  disabled={isLoading}
                  className="mt-2 inline-flex items-center gap-1 text-sm text-primary-600 hover:text-primary-700 disabled:opacity-50"
                >
                  <Plus className="h-4 w-4" />
                  Add another URL
                </button>
              </div>

              {/* Info box */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <p className="text-sm text-blue-700">
                  After creating the application, you'll receive a <strong>Client ID</strong> and{' '}
                  <strong>Client Secret</strong>. The secret will only be shown once, so make sure
                  to copy it immediately.
                </p>
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-3 p-6 border-t border-gray-200">
              <button
                type="button"
                onClick={handleClose}
                disabled={isLoading}
                className="px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isLoading || !name.trim()}
                className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Creating...
                  </>
                ) : (
                  'Create Application'
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export default CreateAppModal;
