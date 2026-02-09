/**
 * Create Consumer Modal Component
 *
 * Modal form for creating a new external API consumer (CAB-1121).
 */

import { useState } from 'react';
import { X, Loader2, AlertCircle } from 'lucide-react';
import type { ConsumerCreateRequest } from '../../types';

interface CreateConsumerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: ConsumerCreateRequest) => Promise<void>;
  isLoading?: boolean;
  error?: string | null;
}

export function CreateConsumerModal({
  isOpen,
  onClose,
  onSubmit,
  isLoading = false,
  error = null,
}: CreateConsumerModalProps) {
  const [name, setName] = useState('');
  const [externalId, setExternalId] = useState('');
  const [email, setEmail] = useState('');
  const [company, setCompany] = useState('');
  const [description, setDescription] = useState('');
  const [emailError, setEmailError] = useState<string | null>(null);

  const validateEmail = (value: string): boolean => {
    if (!value.trim()) {
      setEmailError('Email is required');
      return false;
    }
    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailPattern.test(value)) {
      setEmailError('Please enter a valid email address');
      return false;
    }
    setEmailError(null);
    return true;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateEmail(email)) {
      return;
    }

    await onSubmit({
      name: name.trim(),
      external_id: externalId.trim(),
      email: email.trim(),
      company: company.trim() || undefined,
      description: description.trim() || undefined,
    });
  };

  const resetForm = () => {
    setName('');
    setExternalId('');
    setEmail('');
    setCompany('');
    setDescription('');
    setEmailError(null);
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
          <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-neutral-700">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
              Register New Consumer
            </h2>
            <button
              onClick={handleClose}
              disabled={isLoading}
              className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-neutral-200 hover:bg-gray-100 dark:hover:bg-neutral-700 rounded-lg transition-colors disabled:opacity-50"
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
                  <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
                </div>
              )}

              {/* Name */}
              <div>
                <label
                  htmlFor="consumer-name"
                  className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1"
                >
                  Consumer Name <span className="text-red-500">*</span>
                </label>
                <input
                  id="consumer-name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="ACME Corp"
                  required
                  disabled={isLoading}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:bg-gray-100 dark:disabled:bg-neutral-600 disabled:cursor-not-allowed"
                />
              </div>

              {/* External ID */}
              <div>
                <label
                  htmlFor="consumer-external-id"
                  className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1"
                >
                  External ID <span className="text-red-500">*</span>
                </label>
                <input
                  id="consumer-external-id"
                  type="text"
                  value={externalId}
                  onChange={(e) => setExternalId(e.target.value)}
                  placeholder="partner-acme-001"
                  required
                  disabled={isLoading}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-gray-900 dark:text-white font-mono text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:bg-gray-100 dark:disabled:bg-neutral-600 disabled:cursor-not-allowed"
                />
                <p className="mt-1 text-xs text-gray-500 dark:text-neutral-400">
                  Unique identifier for this consumer within your tenant
                </p>
              </div>

              {/* Email */}
              <div>
                <label
                  htmlFor="consumer-email"
                  className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1"
                >
                  Contact Email <span className="text-red-500">*</span>
                </label>
                <input
                  id="consumer-email"
                  type="email"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    if (emailError) validateEmail(e.target.value);
                  }}
                  onBlur={() => email && validateEmail(email)}
                  placeholder="api@acme.com"
                  required
                  disabled={isLoading}
                  className={`w-full px-4 py-2 border rounded-lg bg-white dark:bg-neutral-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:bg-gray-100 dark:disabled:bg-neutral-600 disabled:cursor-not-allowed ${
                    emailError
                      ? 'border-red-300 dark:border-red-600'
                      : 'border-gray-300 dark:border-neutral-600'
                  }`}
                />
                {emailError && (
                  <p className="mt-1 text-xs text-red-600 dark:text-red-400">{emailError}</p>
                )}
              </div>

              {/* Company */}
              <div>
                <label
                  htmlFor="consumer-company"
                  className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1"
                >
                  Company
                </label>
                <input
                  id="consumer-company"
                  type="text"
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                  placeholder="ACME Corporation"
                  disabled={isLoading}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:bg-gray-100 dark:disabled:bg-neutral-600 disabled:cursor-not-allowed"
                />
              </div>

              {/* Description */}
              <div>
                <label
                  htmlFor="consumer-description"
                  className="block text-sm font-medium text-gray-700 dark:text-neutral-300 mb-1"
                >
                  Description
                </label>
                <textarea
                  id="consumer-description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Brief description of this API consumer..."
                  rows={3}
                  disabled={isLoading}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-neutral-600 rounded-lg bg-white dark:bg-neutral-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500 disabled:bg-gray-100 dark:disabled:bg-neutral-600 disabled:cursor-not-allowed resize-none"
                />
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-3 p-6 border-t border-gray-200 dark:border-neutral-700">
              <button
                type="button"
                onClick={handleClose}
                disabled={isLoading}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-neutral-300 hover:bg-gray-100 dark:hover:bg-neutral-700 rounded-lg transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isLoading || !name.trim() || !externalId.trim() || !email.trim()}
                className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Creating...
                  </>
                ) : (
                  'Register Consumer'
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export default CreateConsumerModal;
