/**
 * JSON Schema Viewer Component
 *
 * Displays JSON Schema in a formatted, interactive way with:
 * - Required vs optional field indicators
 * - Type badges and constraints
 * - Expandable nested objects
 * - Copy functionality
 */

import { useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Copy,
  Check,
  AlertCircle,
  Hash,
  Type,
  List,
  ToggleLeft,
  Calendar,
  FileText,
  Code,
} from 'lucide-react';
import type { MCPInputSchema, MCPPropertySchema } from '../../types';

interface SchemaViewerProps {
  schema: MCPInputSchema | null | undefined;
  title?: string;
  className?: string;
}

interface PropertyRowProps {
  name: string;
  property: MCPPropertySchema;
  isRequired: boolean;
  depth?: number;
}

// Type icon mapping
const typeIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  string: Type,
  number: Hash,
  integer: Hash,
  boolean: ToggleLeft,
  array: List,
  object: FileText,
};

// Type badge colors
const typeColors: Record<string, string> = {
  string: 'bg-green-100 text-green-700',
  number: 'bg-blue-100 text-blue-700',
  integer: 'bg-blue-100 text-blue-700',
  boolean: 'bg-purple-100 text-purple-700',
  array: 'bg-amber-100 text-amber-700',
  object: 'bg-gray-100 text-gray-700',
};

function PropertyRow({ name, property, isRequired, depth = 0 }: PropertyRowProps) {
  const [isExpanded, setIsExpanded] = useState(depth < 2);
  const hasChildren = property.type === 'object' && property.properties;
  const hasArrayItems = property.type === 'array' && property.items;

  const TypeIcon = typeIcons[property.type] || Code;
  const typeColor = typeColors[property.type] || 'bg-gray-100 text-gray-700';

  const constraints: string[] = [];
  if (property.minimum !== undefined) constraints.push(`min: ${property.minimum}`);
  if (property.maximum !== undefined) constraints.push(`max: ${property.maximum}`);
  if (property.minLength !== undefined) constraints.push(`minLen: ${property.minLength}`);
  if (property.maxLength !== undefined) constraints.push(`maxLen: ${property.maxLength}`);
  if (property.pattern) constraints.push(`pattern: ${property.pattern}`);
  if (property.format) constraints.push(`format: ${property.format}`);

  return (
    <div className="border-l-2 border-gray-200 hover:border-primary-300 transition-colors">
      <div
        className={`flex items-start gap-3 py-2 px-3 hover:bg-gray-50 cursor-pointer ${
          depth > 0 ? 'ml-4' : ''
        }`}
        onClick={() => (hasChildren || hasArrayItems) && setIsExpanded(!isExpanded)}
        onKeyDown={(e) => e.key === 'Enter' && (hasChildren || hasArrayItems) && setIsExpanded(!isExpanded)}
        role={hasChildren || hasArrayItems ? 'button' : undefined}
        tabIndex={hasChildren || hasArrayItems ? 0 : undefined}
        aria-expanded={hasChildren || hasArrayItems ? isExpanded : undefined}
      >
        {/* Expand/Collapse Icon */}
        <div className="w-4 h-4 mt-0.5 flex-shrink-0">
          {(hasChildren || hasArrayItems) ? (
            isExpanded ? (
              <ChevronDown className="h-4 w-4 text-gray-400" />
            ) : (
              <ChevronRight className="h-4 w-4 text-gray-400" />
            )
          ) : (
            <span className="block w-1 h-1 bg-gray-300 rounded-full mt-1.5 ml-1.5" />
          )}
        </div>

        {/* Property Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            {/* Property Name */}
            <code className="font-mono text-sm font-medium text-gray-900">{name}</code>

            {/* Required Badge */}
            {isRequired ? (
              <span className="px-1.5 py-0.5 text-xs font-medium bg-red-100 text-red-700 rounded">
                required
              </span>
            ) : (
              <span className="px-1.5 py-0.5 text-xs font-medium bg-gray-100 text-gray-500 rounded">
                optional
              </span>
            )}

            {/* Type Badge */}
            <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 text-xs font-medium rounded ${typeColor}`}>
              <TypeIcon className="h-3 w-3" />
              {property.type}
              {property.type === 'array' && property.items?.type && (
                <span className="opacity-75">[{property.items.type}]</span>
              )}
            </span>

            {/* Enum Values */}
            {property.enum && (
              <span className="px-1.5 py-0.5 text-xs font-medium bg-indigo-100 text-indigo-700 rounded">
                enum
              </span>
            )}

            {/* Format Badge */}
            {property.format && (
              <span className="px-1.5 py-0.5 text-xs bg-cyan-100 text-cyan-700 rounded flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                {property.format}
              </span>
            )}
          </div>

          {/* Description */}
          {property.description && (
            <p className="text-sm text-gray-600 mt-1">{property.description}</p>
          )}

          {/* Constraints */}
          {constraints.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-1">
              {constraints.map((constraint, idx) => (
                <span key={idx} className="text-xs text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">
                  {constraint}
                </span>
              ))}
            </div>
          )}

          {/* Enum Values List */}
          {property.enum && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {property.enum.map((value, idx) => (
                <code key={idx} className="px-2 py-0.5 text-xs bg-indigo-50 text-indigo-700 rounded border border-indigo-200">
                  "{value}"
                </code>
              ))}
            </div>
          )}

          {/* Default Value */}
          {property.default !== undefined && (
            <p className="text-xs text-gray-500 mt-1">
              Default: <code className="bg-gray-100 px-1 rounded">{JSON.stringify(property.default)}</code>
            </p>
          )}
        </div>
      </div>

      {/* Nested Properties (Object) */}
      {hasChildren && isExpanded && property.properties && (
        <div className="ml-4">
          {Object.entries(property.properties).map(([childName, childProp]) => (
            <PropertyRow
              key={childName}
              name={childName}
              property={childProp as MCPPropertySchema}
              isRequired={false}
              depth={depth + 1}
            />
          ))}
        </div>
      )}

      {/* Array Items Schema */}
      {hasArrayItems && isExpanded && property.items && (
        <div className="ml-4 py-2 px-3">
          <div className="text-xs text-gray-500 mb-2">Array items:</div>
          {property.items.type === 'object' && property.items.properties ? (
            Object.entries(property.items.properties).map(([childName, childProp]) => (
              <PropertyRow
                key={childName}
                name={childName}
                property={childProp as MCPPropertySchema}
                isRequired={false}
                depth={depth + 1}
              />
            ))
          ) : (
            <div className="flex items-center gap-2 text-sm text-gray-600">
              <span className={`px-1.5 py-0.5 text-xs font-medium rounded ${typeColors[property.items.type] || 'bg-gray-100 text-gray-700'}`}>
                {property.items.type}
              </span>
              {property.items.description && <span>{property.items.description}</span>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function SchemaViewer({ schema, title = 'Input Schema', className = '' }: SchemaViewerProps) {
  const [viewMode, setViewMode] = useState<'formatted' | 'raw'>('formatted');
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!schema) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(schema, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy schema:', err);
    }
  };

  if (!schema) {
    return (
      <div className={`bg-gray-50 border border-gray-200 rounded-lg p-4 ${className}`}>
        <div className="flex items-center gap-2 text-gray-500">
          <AlertCircle className="h-4 w-4" />
          <span className="text-sm">No schema defined</span>
        </div>
      </div>
    );
  }

  const requiredFields = schema.required || [];
  const properties = schema.properties || {};
  const propertyCount = Object.keys(properties).length;
  const requiredCount = requiredFields.length;

  return (
    <div className={`bg-white border border-gray-200 rounded-lg overflow-hidden ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-200">
        <div className="flex items-center gap-3">
          <h3 className="font-medium text-gray-900">{title}</h3>
          <span className="text-xs text-gray-500">
            {propertyCount} {propertyCount === 1 ? 'property' : 'properties'}
            {requiredCount > 0 && ` • ${requiredCount} required`}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* View Mode Toggle */}
          <div className="flex items-center bg-gray-200 rounded-lg p-0.5">
            <button
              onClick={() => setViewMode('formatted')}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                viewMode === 'formatted'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              Formatted
            </button>
            <button
              onClick={() => setViewMode('raw')}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                viewMode === 'raw'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              Raw JSON
            </button>
          </div>

          {/* Copy Button */}
          <button
            onClick={handleCopy}
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
          >
            {copied ? (
              <>
                <Check className="h-3.5 w-3.5 text-green-600" />
                <span className="text-green-600">Copied!</span>
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5" />
                Copy
              </>
            )}
          </button>
        </div>
      </div>

      {/* Content */}
      {viewMode === 'formatted' ? (
        <div className="divide-y divide-gray-100">
          {propertyCount === 0 ? (
            <div className="px-4 py-6 text-center text-gray-500 text-sm">
              No properties defined in schema
            </div>
          ) : (
            Object.entries(properties).map(([name, property]) => (
              <PropertyRow
                key={name}
                name={name}
                property={property}
                isRequired={requiredFields.includes(name)}
              />
            ))
          )}

          {/* Additional Properties Note */}
          {schema.additionalProperties === false && (
            <div className="px-4 py-2 bg-amber-50 text-amber-700 text-xs">
              <AlertCircle className="h-3.5 w-3.5 inline mr-1" />
              Additional properties not allowed
            </div>
          )}
        </div>
      ) : (
        <pre className="p-4 bg-gray-900 text-gray-100 text-sm font-mono overflow-x-auto max-h-96">
          {JSON.stringify(schema, null, 2)}
        </pre>
      )}
    </div>
  );
}

export default SchemaViewer;
