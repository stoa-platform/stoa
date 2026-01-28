// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
import { ChevronDown, ChevronRight, Circle, AlertCircle } from 'lucide-react';
import { useState } from 'react';
import type { ToolInputSchema, ToolPropertySchema } from '../../types';

interface ToolSchemaViewerProps {
  schema: ToolInputSchema;
  title?: string;
}

export function ToolSchemaViewer({ schema, title = 'Input Schema' }: ToolSchemaViewerProps) {
  const properties = schema.properties || {};
  const required = schema.required || [];

  if (Object.keys(properties).length === 0) {
    return (
      <div className="text-sm text-gray-500 italic">
        This tool has no input parameters.
      </div>
    );
  }

  return (
    <div className="bg-gray-50 rounded-lg border border-gray-200">
      <div className="px-4 py-3 border-b border-gray-200">
        <h4 className="text-sm font-medium text-gray-700">{title}</h4>
      </div>
      <div className="p-4 space-y-2">
        {Object.entries(properties).map(([name, prop]) => (
          <PropertyRow
            key={name}
            name={name}
            property={prop}
            isRequired={required.includes(name)}
          />
        ))}
      </div>
    </div>
  );
}

interface PropertyRowProps {
  name: string;
  property: ToolPropertySchema;
  isRequired: boolean;
  depth?: number;
}

function PropertyRow({ name, property, isRequired, depth = 0 }: PropertyRowProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const hasNestedProperties = property.type === 'object' && property.properties;
  const hasItems = property.type === 'array' && property.items;

  const typeColors: Record<string, string> = {
    string: 'text-green-600',
    number: 'text-blue-600',
    integer: 'text-blue-600',
    boolean: 'text-purple-600',
    array: 'text-orange-600',
    object: 'text-pink-600',
  };

  const formatType = (prop: ToolPropertySchema): string => {
    if (prop.type === 'array' && prop.items) {
      return `${prop.items.type}[]`;
    }
    return prop.type;
  };

  return (
    <div className="text-sm" style={{ marginLeft: depth * 16 }}>
      <div
        className={`flex items-start gap-2 py-1.5 ${hasNestedProperties || hasItems ? 'cursor-pointer hover:bg-gray-100 rounded' : ''}`}
        onClick={() => (hasNestedProperties || hasItems) && setIsExpanded(!isExpanded)}
      >
        {/* Expand/Collapse Icon */}
        {hasNestedProperties || hasItems ? (
          isExpanded ? (
            <ChevronDown className="h-4 w-4 text-gray-400 mt-0.5 flex-shrink-0" />
          ) : (
            <ChevronRight className="h-4 w-4 text-gray-400 mt-0.5 flex-shrink-0" />
          )
        ) : (
          <Circle className="h-2 w-2 text-gray-300 mt-1.5 ml-1 mr-1 flex-shrink-0" />
        )}

        {/* Property Name */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-mono font-medium text-gray-900">{name}</span>
            <span className={`font-mono text-xs ${typeColors[property.type] || 'text-gray-500'}`}>
              {formatType(property)}
            </span>
            {isRequired && (
              <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 bg-red-50 text-red-600 text-xs rounded">
                <AlertCircle className="h-3 w-3" />
                required
              </span>
            )}
            {property.enum && (
              <span className="text-xs text-gray-400">
                enum: [{property.enum.join(', ')}]
              </span>
            )}
            {property.default !== undefined && (
              <span className="text-xs text-gray-400">
                default: {JSON.stringify(property.default)}
              </span>
            )}
          </div>
          {property.description && (
            <p className="text-gray-500 text-xs mt-0.5">{property.description}</p>
          )}
        </div>
      </div>

      {/* Nested Properties */}
      {isExpanded && hasNestedProperties && (
        <div className="mt-1 pl-2 border-l border-gray-200 ml-2">
          {Object.entries(property.properties!).map(([nestedName, nestedProp]) => (
            <PropertyRow
              key={nestedName}
              name={nestedName}
              property={nestedProp}
              isRequired={false}
              depth={depth + 1}
            />
          ))}
        </div>
      )}

      {/* Array Items */}
      {isExpanded && hasItems && property.items?.properties && (
        <div className="mt-1 pl-2 border-l border-gray-200 ml-2">
          <div className="text-xs text-gray-400 mb-1">Array items:</div>
          {Object.entries(property.items.properties).map(([itemName, itemProp]) => (
            <PropertyRow
              key={itemName}
              name={itemName}
              property={itemProp}
              isRequired={false}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface SchemaJsonViewerProps {
  schema: ToolInputSchema;
}

export function SchemaJsonViewer({ schema }: SchemaJsonViewerProps) {
  return (
    <pre className="bg-gray-900 text-gray-100 rounded-lg p-4 overflow-x-auto text-xs">
      <code>{JSON.stringify(schema, null, 2)}</code>
    </pre>
  );
}
