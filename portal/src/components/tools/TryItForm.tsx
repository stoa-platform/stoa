/**
 * Try It Form Component
 *
 * Dynamic form generator based on JSON Schema that allows testing tools.
 * Features:
 * - Auto-generates form fields from schema
 * - Validates input based on schema constraints
 * - Shows request/response
 * - Supports nested objects and arrays
 */

import { useState, useCallback, type ReactNode } from 'react';
import {
  Play,
  Loader2,
  Copy,
  Check,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  Plus,
  Trash2,
  Info,
} from 'lucide-react';
import type { MCPInputSchema, MCPPropertySchema } from '../../types';

interface TryItFormProps {
  schema: MCPInputSchema | null | undefined;
  toolName: string;
  onInvoke?: (args: Record<string, unknown>) => Promise<unknown>;
  isLoading?: boolean;
  className?: string;
}

interface FormFieldProps {
  name: string;
  property: MCPPropertySchema;
  value: unknown;
  onChange: (value: unknown) => void;
  isRequired: boolean;
  error?: string;
}

function FormField({ name, property, value, onChange, isRequired, error }: FormFieldProps) {
  const [showDescription, setShowDescription] = useState(false);
  const [jsonError, setJsonError] = useState<string | null>(null);

  const handleChange = useCallback((newValue: unknown) => {
    onChange(newValue);
  }, [onChange]);

  // String input
  if (property.type === 'string') {
    // Enum - render as select
    if (property.enum) {
      return (
        <div className="space-y-1">
          <label className="block text-sm font-medium text-gray-700">
            {name}
            {isRequired && <span className="text-red-500 ml-1">*</span>}
          </label>
          <select
            value={(value as string) || ''}
            onChange={(e) => handleChange(e.target.value)}
            className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 ${
              error ? 'border-red-300' : 'border-gray-300'
            }`}
          >
            <option value="">Select {name}...</option>
            {property.enum.map((opt) => (
              <option key={opt} value={opt}>{opt}</option>
            ))}
          </select>
          {property.description && (
            <p className="text-xs text-gray-500">{property.description}</p>
          )}
          {error && <p className="text-xs text-red-600">{error}</p>}
        </div>
      );
    }

    // Textarea for long text
    if (property.maxLength && property.maxLength > 200) {
      return (
        <div className="space-y-1">
          <label className="block text-sm font-medium text-gray-700">
            {name}
            {isRequired && <span className="text-red-500 ml-1">*</span>}
          </label>
          <textarea
            value={(value as string) || ''}
            onChange={(e) => handleChange(e.target.value)}
            placeholder={property.description || `Enter ${name}...`}
            rows={3}
            className={`w-full px-3 py-2 border rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary-500 ${
              error ? 'border-red-300' : 'border-gray-300'
            }`}
          />
          {property.description && (
            <p className="text-xs text-gray-500">{property.description}</p>
          )}
          {error && <p className="text-xs text-red-600">{error}</p>}
        </div>
      );
    }

    // Regular text input
    return (
      <div className="space-y-1">
        <label className="block text-sm font-medium text-gray-700">
          {name}
          {isRequired && <span className="text-red-500 ml-1">*</span>}
          {property.description && (
            <button
              type="button"
              onClick={() => setShowDescription(!showDescription)}
              className="ml-1 text-gray-400 hover:text-gray-600"
            >
              <Info className="h-3 w-3 inline" />
            </button>
          )}
        </label>
        <input
          type={property.format === 'email' ? 'email' : property.format === 'uri' ? 'url' : 'text'}
          value={(value as string) || ''}
          onChange={(e) => handleChange(e.target.value)}
          placeholder={property.default?.toString() || `Enter ${name}...`}
          className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 ${
            error ? 'border-red-300' : 'border-gray-300'
          }`}
        />
        {showDescription && property.description && (
          <p className="text-xs text-gray-500 bg-gray-50 p-2 rounded">{property.description}</p>
        )}
        {error && <p className="text-xs text-red-600">{error}</p>}
      </div>
    );
  }

  // Number input
  if (property.type === 'number' || property.type === 'integer') {
    return (
      <div className="space-y-1">
        <label className="block text-sm font-medium text-gray-700">
          {name}
          {isRequired && <span className="text-red-500 ml-1">*</span>}
        </label>
        <input
          type="number"
          value={value !== undefined ? (value as number) : ''}
          onChange={(e) => handleChange(e.target.value ? Number(e.target.value) : undefined)}
          placeholder={property.default?.toString() || `Enter ${name}...`}
          min={property.minimum}
          max={property.maximum}
          step={property.type === 'integer' ? 1 : 'any'}
          className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 ${
            error ? 'border-red-300' : 'border-gray-300'
          }`}
        />
        {property.description && (
          <p className="text-xs text-gray-500">{property.description}</p>
        )}
        {(property.minimum !== undefined || property.maximum !== undefined) && (
          <p className="text-xs text-gray-400">
            {property.minimum !== undefined && `Min: ${property.minimum}`}
            {property.minimum !== undefined && property.maximum !== undefined && ' • '}
            {property.maximum !== undefined && `Max: ${property.maximum}`}
          </p>
        )}
        {error && <p className="text-xs text-red-600">{error}</p>}
      </div>
    );
  }

  // Boolean input
  if (property.type === 'boolean') {
    return (
      <div className="space-y-1">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={!!value}
            onChange={(e) => handleChange(e.target.checked)}
            className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
          />
          <span className="text-sm font-medium text-gray-700">
            {name}
            {isRequired && <span className="text-red-500 ml-1">*</span>}
          </span>
        </label>
        {property.description && (
          <p className="text-xs text-gray-500 ml-6">{property.description}</p>
        )}
        {error && <p className="text-xs text-red-600 ml-6">{error}</p>}
      </div>
    );
  }

  // Array input (simple string array)
  if (property.type === 'array') {
    const arrayValue = (value as string[]) || [];

    return (
      <div className="space-y-2">
        <label className="block text-sm font-medium text-gray-700">
          {name}
          {isRequired && <span className="text-red-500 ml-1">*</span>}
        </label>
        <div className="space-y-2">
          {arrayValue.map((item, idx) => (
            <div key={idx} className="flex items-center gap-2">
              <input
                type="text"
                value={item}
                onChange={(e) => {
                  const newArray = [...arrayValue];
                  newArray[idx] = e.target.value;
                  handleChange(newArray);
                }}
                className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
              <button
                type="button"
                onClick={() => {
                  const newArray = arrayValue.filter((_, i) => i !== idx);
                  handleChange(newArray);
                }}
                className="p-2 text-gray-400 hover:text-red-600 transition-colors"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() => handleChange([...arrayValue, ''])}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-sm text-primary-600 hover:text-primary-700 hover:bg-primary-50 rounded-lg transition-colors"
          >
            <Plus className="h-4 w-4" />
            Add item
          </button>
        </div>
        {property.description && (
          <p className="text-xs text-gray-500">{property.description}</p>
        )}
        {error && <p className="text-xs text-red-600">{error}</p>}
      </div>
    );
  }

  // Object - render as JSON textarea
  if (property.type === 'object') {
    const jsonValue = value ? JSON.stringify(value, null, 2) : '';

    return (
      <div className="space-y-1">
        <label className="block text-sm font-medium text-gray-700">
          {name}
          {isRequired && <span className="text-red-500 ml-1">*</span>}
          <span className="text-xs text-gray-400 ml-2">(JSON)</span>
        </label>
        <textarea
          value={jsonValue}
          onChange={(e) => {
            try {
              const parsed = e.target.value ? JSON.parse(e.target.value) : undefined;
              setJsonError(null);
              handleChange(parsed);
            } catch {
              setJsonError('Invalid JSON');
            }
          }}
          placeholder={`{\n  "key": "value"\n}`}
          rows={4}
          className={`w-full px-3 py-2 border rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary-500 ${
            jsonError || error ? 'border-red-300' : 'border-gray-300'
          }`}
        />
        {property.description && (
          <p className="text-xs text-gray-500">{property.description}</p>
        )}
        {(jsonError || error) && (
          <p className="text-xs text-red-600">{jsonError || error}</p>
        )}
      </div>
    );
  }

  // Default fallback - text input
  return (
    <div className="space-y-1">
      <label className="block text-sm font-medium text-gray-700">
        {name}
        {isRequired && <span className="text-red-500 ml-1">*</span>}
      </label>
      <input
        type="text"
        value={(value as string) || ''}
        onChange={(e) => handleChange(e.target.value)}
        placeholder={`Enter ${name}...`}
        className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 ${
          error ? 'border-red-300' : 'border-gray-300'
        }`}
      />
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}

export function TryItForm({ schema, toolName, onInvoke, isLoading = false, className = '' }: TryItFormProps) {
  const [formData, setFormData] = useState<Record<string, unknown>>({});
  const [response, setResponse] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const [showResponse, setShowResponse] = useState(true);
  const [copied, setCopied] = useState(false);

  const properties: Record<string, MCPPropertySchema> = schema?.properties || {};
  const requiredFields = schema?.required || [];

  // Render form fields
  const renderFormFields = (): ReactNode => {
    return Object.entries(properties).map(([name, property]) => (
      <FormField
        key={name}
        name={name}
        property={property}
        value={formData[name]}
        onChange={(value) => handleFieldChange(name, value)}
        isRequired={requiredFields.includes(name)}
      />
    ));
  };

  const handleFieldChange = useCallback((fieldName: string, value: unknown) => {
    setFormData(prev => ({
      ...prev,
      [fieldName]: value,
    }));
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setResponse(null);

    // Validate required fields
    const missingRequired = requiredFields.filter(
      field => formData[field] === undefined || formData[field] === ''
    );
    if (missingRequired.length > 0) {
      setError(`Missing required fields: ${missingRequired.join(', ')}`);
      return;
    }

    // Filter out empty values
    const cleanedData = Object.fromEntries(
      Object.entries(formData).filter(([, v]) => v !== undefined && v !== '')
    );

    if (onInvoke) {
      try {
        const result = await onInvoke(cleanedData);
        setResponse(result);
      } catch (err) {
        setError((err as Error).message || 'Failed to invoke tool');
      }
    } else {
      // Demo mode - just show the request
      setResponse({
        _demo: true,
        message: 'Tool invocation not available in demo mode',
        request: {
          tool: toolName,
          arguments: cleanedData,
        },
      });
    }
  };

  const handleCopyResponse = async () => {
    if (!response) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(response, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const handleReset = () => {
    setFormData({});
    setResponse(null);
    setError(null);
  };

  if (!schema || Object.keys(properties).length === 0) {
    return (
      <div className={`bg-white border border-gray-200 rounded-lg p-6 ${className}`}>
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Try It</h2>
        <div className="text-center py-8">
          <AlertCircle className="h-12 w-12 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-500 text-sm">No input schema available</p>
          <p className="text-gray-400 text-xs mt-1">
            This tool doesn't define input parameters
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className={`bg-white border border-gray-200 rounded-lg overflow-hidden ${className}`}>
      {/* Header */}
      <div className="px-6 py-4 bg-gray-50 border-b border-gray-200">
        <h2 className="text-lg font-semibold text-gray-900">Try It</h2>
        <p className="text-sm text-gray-500 mt-1">
          Test this tool with your own parameters
        </p>
      </div>

      <form onSubmit={handleSubmit} className="p-6 space-y-4">
        {renderFormFields()}

        {/* Error Display */}
        {error && (
          <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg">
            <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-red-700">{error}</p>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-3 pt-2">
          <button
            type="submit"
            disabled={isLoading}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium"
          >
            {isLoading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Invoking...
              </>
            ) : (
              <>
                <Play className="h-4 w-4" />
                Invoke Tool
              </>
            )}
          </button>
          <button
            type="button"
            onClick={handleReset}
            className="px-4 py-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors font-medium"
          >
            Reset
          </button>
        </div>
      </form>

      {/* Response Section */}
      {response !== null && (
        <div className="border-t border-gray-200">
          <button
            onClick={() => setShowResponse(!showResponse)}
            className="w-full px-6 py-3 flex items-center justify-between bg-gray-50 hover:bg-gray-100 transition-colors"
          >
            <span className="text-sm font-medium text-gray-700">Response</span>
            {showResponse ? (
              <ChevronUp className="h-4 w-4 text-gray-500" />
            ) : (
              <ChevronDown className="h-4 w-4 text-gray-500" />
            )}
          </button>
          {showResponse && (
            <div className="relative">
              <pre className="p-4 bg-gray-900 text-gray-100 text-sm font-mono overflow-x-auto max-h-96">
                {JSON.stringify(response, null, 2)}
              </pre>
              <button
                onClick={handleCopyResponse}
                className="absolute top-2 right-2 p-2 text-gray-400 hover:text-white bg-gray-800 rounded-lg transition-colors"
              >
                {copied ? (
                  <Check className="h-4 w-4 text-green-400" />
                ) : (
                  <Copy className="h-4 w-4" />
                )}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default TryItForm;
