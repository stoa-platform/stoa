// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * API Card Component
 *
 * Displays an API in the catalog grid view.
 * Optimized with React.memo to prevent unnecessary re-renders in grid.
 */

import { memo, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Tag, Clock } from 'lucide-react';
import type { API } from '../../types';

interface APICardProps {
  api: API;
}

// Move static objects outside component to prevent recreation on each render
const statusColors = {
  published: 'bg-green-100 text-green-800',
  deprecated: 'bg-amber-100 text-amber-800',
  draft: 'bg-gray-100 text-gray-800',
} as const;

// Date formatting options - created once
const dateFormatOptions: Intl.DateTimeFormatOptions = {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
};

export const APICard = memo(function APICard({ api }: APICardProps) {
  // Memoize the formatted date to avoid recalculating on each render
  const formattedDate = useMemo(() => {
    return new Date(api.updatedAt).toLocaleDateString('en-US', dateFormatOptions);
  }, [api.updatedAt]);

  return (
    <Link
      to={`/apis/${api.id}`}
      className="group bg-white rounded-lg border border-gray-200 p-6 hover:border-primary-300 hover:shadow-md transition-all"
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-gray-900 group-hover:text-primary-700 transition-colors truncate">
            {api.name}
          </h3>
          <p className="text-sm text-gray-500">v{api.version}</p>
        </div>
        <span className={`px-2 py-1 text-xs font-medium rounded-full ${statusColors[api.status]}`}>
          {api.status}
        </span>
      </div>

      <p className="text-sm text-gray-600 line-clamp-2 mb-4 min-h-[40px]">
        {api.description || 'No description available'}
      </p>

      <div className="flex flex-wrap gap-2 mb-4">
        {api.category && (
          <span className="inline-flex items-center gap-1 px-2 py-1 bg-primary-50 text-primary-700 text-xs rounded-full">
            <Tag className="h-3 w-3" />
            {api.category}
          </span>
        )}
        {api.tags?.slice(0, 2).map((tag) => (
          <span
            key={tag}
            className="px-2 py-1 bg-gray-100 text-gray-600 text-xs rounded-full"
          >
            {tag}
          </span>
        ))}
        {api.tags && api.tags.length > 2 && (
          <span className="px-2 py-1 bg-gray-100 text-gray-500 text-xs rounded-full">
            +{api.tags.length - 2}
          </span>
        )}
      </div>

      <div className="flex items-center justify-between pt-3 border-t border-gray-100">
        <div className="flex items-center text-xs text-gray-500">
          <Clock className="h-3 w-3 mr-1" />
          {formattedDate}
        </div>
        <span className="inline-flex items-center text-sm font-medium text-primary-600 group-hover:text-primary-700">
          View Details
          <ArrowRight className="h-4 w-4 ml-1 group-hover:translate-x-1 transition-transform" />
        </span>
      </div>
    </Link>
  );
});

export default APICard;
