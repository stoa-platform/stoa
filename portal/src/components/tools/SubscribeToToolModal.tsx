/**
 * Subscribe to Tool Modal Component
 *
 * Modal form for subscribing to an MCP Tool.
 */

import { useState, useEffect } from 'react';
import { X, Loader2, AlertCircle, Check, Zap, Crown } from 'lucide-react';
import type { MCPTool } from '../../types';

type ToolSubscriptionPlan = 'free' | 'basic' | 'premium';

interface SubscribeToToolModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: { toolId: string; plan: ToolSubscriptionPlan }) => Promise<void>;
  tool: MCPTool;
  isLoading?: boolean;
  error?: string | null;
}

interface PlanInfo {
  name: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
  features: string[];
  color: string;
  bgColor: string;
  borderColor: string;
}

const plans: Record<ToolSubscriptionPlan, PlanInfo> = {
  free: {
    name: 'Free',
    description: 'For testing and evaluation',
    icon: Check,
    features: ['100 calls/day', 'Basic rate limits', 'Community support'],
    color: 'text-gray-700',
    bgColor: 'bg-gray-50',
    borderColor: 'border-gray-200',
  },
  basic: {
    name: 'Basic',
    description: 'For development projects',
    icon: Zap,
    features: ['10,000 calls/day', 'Priority rate limits', 'Email support'],
    color: 'text-blue-700',
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-200',
  },
  premium: {
    name: 'Premium',
    description: 'For production workloads',
    icon: Crown,
    features: ['100,000 calls/day', 'Highest rate limits', 'Priority support'],
    color: 'text-purple-700',
    bgColor: 'bg-purple-50',
    borderColor: 'border-purple-200',
  },
};

export function SubscribeToToolModal({
  isOpen,
  onClose,
  onSubmit,
  tool,
  isLoading = false,
  error = null,
}: SubscribeToToolModalProps) {
  const [selectedPlan, setSelectedPlan] = useState<ToolSubscriptionPlan>('free');

  // Reset form when modal opens
  useEffect(() => {
    if (isOpen) {
      setSelectedPlan('free');
    }
  }, [isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    await onSubmit({
      toolId: tool.name || tool.id || '', // MCP tools use name as identifier
      plan: selectedPlan,
    });
  };

  const handleClose = () => {
    if (!isLoading) {
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
        <div className="relative bg-white rounded-xl shadow-xl max-w-lg w-full max-h-[90vh] overflow-y-auto">
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-gray-200">
            <div>
              <h2 className="text-xl font-semibold text-gray-900">
                Subscribe to Tool
              </h2>
              <p className="text-sm text-gray-500 mt-1">
                {tool.displayName || tool.name}{tool.version ? ` v${tool.version}` : ''}
              </p>
            </div>
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
            <div className="p-6 space-y-6">
              {/* Error message */}
              {error && (
                <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg">
                  <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
                  <p className="text-sm text-red-700">{error}</p>
                </div>
              )}

              {/* Tool Info */}
              <div className="bg-gray-50 rounded-lg p-4">
                <h4 className="font-medium text-gray-900">{tool.displayName || tool.name}</h4>
                <p className="text-sm text-gray-500 mt-1">{tool.description}</p>
                {(tool.category || (tool.tags && tool.tags.length > 0)) && (
                  <span className="inline-block mt-2 px-2 py-1 text-xs font-medium bg-gray-200 text-gray-700 rounded">
                    {tool.category || tool.tags?.[0]}
                  </span>
                )}
              </div>

              {/* Select Plan */}
              <div role="radiogroup" aria-labelledby="tool-plan-label">
                <span id="tool-plan-label" className="block text-sm font-medium text-gray-700 mb-3">
                  Select Plan <span className="text-red-500" aria-hidden="true">*</span>
                  <span className="sr-only">(required)</span>
                </span>
                <div className="space-y-3">
                  {(Object.keys(plans) as ToolSubscriptionPlan[]).map((planKey) => {
                    const plan = plans[planKey];
                    const Icon = plan.icon;
                    const isSelected = selectedPlan === planKey;

                    return (
                      <button
                        key={planKey}
                        type="button"
                        onClick={() => setSelectedPlan(planKey)}
                        disabled={isLoading}
                        className={`relative w-full p-4 rounded-lg border-2 text-left transition-all ${
                          isSelected
                            ? `${plan.borderColor} ${plan.bgColor} ring-2 ring-offset-1 ring-primary-500`
                            : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                        } disabled:opacity-50 disabled:cursor-not-allowed`}
                      >
                        <div className="flex items-start gap-3">
                          <div className={`p-2 rounded-lg ${plan.bgColor}`}>
                            <Icon className={`h-5 w-5 ${plan.color}`} />
                          </div>
                          <div className="flex-1">
                            <h4 className={`font-semibold ${isSelected ? plan.color : 'text-gray-900'}`}>
                              {plan.name}
                            </h4>
                            <p className="text-xs text-gray-500 mt-0.5">
                              {plan.description}
                            </p>
                            <ul className="mt-2 space-y-1">
                              {plan.features.map((feature, idx) => (
                                <li key={idx} className="flex items-center gap-1.5 text-xs text-gray-600">
                                  <Check className="h-3 w-3 text-green-500" />
                                  {feature}
                                </li>
                              ))}
                            </ul>
                          </div>
                        </div>
                        {isSelected && (
                          <div className="absolute top-2 right-2">
                            <div className="p-1 bg-primary-600 rounded-full">
                              <Check className="h-3 w-3 text-white" />
                            </div>
                          </div>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Info box */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <p className="text-sm text-blue-700">
                  After subscribing, you'll receive access credentials for this tool.
                  You can use these credentials with MCP-compatible clients to invoke the tool.
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
                disabled={isLoading}
                className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Subscribing...
                  </>
                ) : (
                  'Subscribe'
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export default SubscribeToToolModal;
