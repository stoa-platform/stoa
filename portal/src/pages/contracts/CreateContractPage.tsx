// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * CreateContractPage
 *
 * Page for creating a new Universal API Contract (UAC).
 * After successful creation, shows the PublishSuccessModal
 * with all auto-generated bindings (REST, MCP, GraphQL, etc.)
 *
 * Reference: CAB-560 - Universal API Contracts
 */

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePublishContract } from '../../hooks/useContracts';
import { PublishSuccessModal } from '../../components/contracts/PublishSuccessModal';
import { PublishContractResponse, ContractCreate } from '../../types';
import { ArrowLeft, FileCode, Loader2 } from 'lucide-react';

export const CreateContractPage: React.FC = () => {
  const navigate = useNavigate();
  const [showSuccessModal, setShowSuccessModal] = useState(false);
  const [publishedContract, setPublishedContract] = useState<PublishContractResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [formData, setFormData] = useState<ContractCreate>({
    name: '',
    display_name: '',
    description: '',
    version: '1.0.0',
    openapi_spec_url: '',
  });

  const publishContract = usePublishContract({
    onSuccess: (data) => {
      setPublishedContract(data);
      setShowSuccessModal(true);
      setError(null);
    },
    onError: (err) => {
      setError(err.message || 'Failed to create contract');
    },
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    publishContract.mutate(formData);
  };

  const handleInputChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleViewContract = (id: string) => {
    setShowSuccessModal(false);
    navigate(`/contracts/${id}`);
  };

  const handleTestPlayground = (url: string) => {
    window.open(url, '_blank');
  };

  const handleCloseModal = () => {
    setShowSuccessModal(false);
    navigate('/contracts');
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate('/contracts')}
              className="text-gray-500 hover:text-gray-700 transition-colors"
            >
              <ArrowLeft className="h-5 w-5" />
            </button>
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-blue-100 flex items-center justify-center">
                <FileCode className="h-5 w-5 text-blue-600" />
              </div>
              <div>
                <h1 className="text-xl font-semibold text-gray-900">
                  Create Contract
                </h1>
                <p className="text-sm text-gray-500">
                  Define once, expose via REST, MCP, GraphQL & more
                </p>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Form */}
      <main className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Error message */}
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <p className="text-sm text-red-700">{error}</p>
            </div>
          )}

          {/* Contract Name */}
          <div>
            <label
              htmlFor="name"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Contract Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              id="name"
              name="name"
              required
              value={formData.name}
              onChange={handleInputChange}
              placeholder="e.g., customer-api"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
            <p className="mt-1 text-xs text-gray-500">
              Lowercase, hyphens allowed. Used in endpoints.
            </p>
          </div>

          {/* Display Name */}
          <div>
            <label
              htmlFor="display_name"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Display Name
            </label>
            <input
              type="text"
              id="display_name"
              name="display_name"
              value={formData.display_name || ''}
              onChange={handleInputChange}
              placeholder="e.g., Customer API"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          {/* Description */}
          <div>
            <label
              htmlFor="description"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Description
            </label>
            <textarea
              id="description"
              name="description"
              rows={3}
              value={formData.description || ''}
              onChange={handleInputChange}
              placeholder="What does this API do?"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          {/* Version */}
          <div>
            <label
              htmlFor="version"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Version
            </label>
            <input
              type="text"
              id="version"
              name="version"
              value={formData.version || ''}
              onChange={handleInputChange}
              placeholder="1.0.0"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          {/* OpenAPI Spec URL */}
          <div>
            <label
              htmlFor="openapi_spec_url"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              OpenAPI Spec URL
            </label>
            <input
              type="url"
              id="openapi_spec_url"
              name="openapi_spec_url"
              value={formData.openapi_spec_url || ''}
              onChange={handleInputChange}
              placeholder="https://example.com/openapi.yaml"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
            <p className="mt-1 text-xs text-gray-500">
              Optional. Link to your OpenAPI/Swagger specification.
            </p>
          </div>

          {/* Info box */}
          <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <span className="text-2xl">🤖</span>
              <div>
                <p className="text-sm font-medium text-purple-800">
                  MCP binding auto-generated
                </p>
                <p className="text-sm text-purple-700 mt-1">
                  When you publish this contract, STOA will automatically create
                  an MCP tool that AI agents can use. No extra configuration needed!
                </p>
              </div>
            </div>
          </div>

          {/* Submit button */}
          <div className="flex justify-end gap-3 pt-4 border-t border-gray-200">
            <button
              type="button"
              onClick={() => navigate('/contracts')}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={publishContract.isPending || !formData.name}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {publishContract.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Publishing...
                </>
              ) : (
                'Publish Contract'
              )}
            </button>
          </div>
        </form>
      </main>

      {/* Success Modal */}
      <PublishSuccessModal
        isOpen={showSuccessModal}
        onClose={handleCloseModal}
        data={publishedContract}
        onViewContract={handleViewContract}
        onTestPlayground={handleTestPlayground}
      />
    </div>
  );
};

export default CreateContractPage;
