/**
 * FeaturedAPIs Component
 *
 * Shows a preview of available APIs on the homepage.
 */

import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { BookOpen, ArrowRight, Globe, Lock, Tag } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { config } from '../../config';

interface APIPreview {
  id: string;
  name: string;
  displayName: string;
  description: string;
  version: string;
  status: string;
  category: string;
  tags: string[];
  visibility?: 'public' | 'internal';
}

function APISkeleton() {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 animate-pulse">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 bg-gray-200 rounded-lg" />
        <div className="flex-1">
          <div className="h-4 w-32 bg-gray-200 rounded mb-2" />
          <div className="h-3 w-full bg-gray-200 rounded mb-1" />
          <div className="h-3 w-2/3 bg-gray-200 rounded" />
        </div>
      </div>
    </div>
  );
}

export function FeaturedAPIs() {
  const { accessToken } = useAuth();
  const [apis, setApis] = useState<APIPreview[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!accessToken) return;

    async function loadAPIs() {
      setIsLoading(true);
      try {
        const response = await fetch(`${config.api.baseUrl}/v1/portal/apis?limit=4`, {
          headers: {
            Authorization: `Bearer ${accessToken}`,
          },
        });
        if (response.ok) {
          const data = await response.json();
          setApis(data.apis || []);
        }
      } catch (error) {
        console.error('Failed to load APIs:', error);
      } finally {
        setIsLoading(false);
      }
    }

    loadAPIs();
  }, [accessToken]);

  if (!config.features.enableAPICatalog) {
    return null;
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200">
      <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BookOpen className="h-5 w-5 text-indigo-600" />
          <h2 className="font-semibold text-gray-900">API Catalog</h2>
        </div>
        <Link
          to="/apis"
          className="text-sm text-primary-600 hover:text-primary-700 font-medium flex items-center gap-1"
        >
          Browse all APIs
          <ArrowRight className="h-3 w-3" />
        </Link>
      </div>

      <div className="p-4">
        {isLoading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <APISkeleton />
            <APISkeleton />
            <APISkeleton />
            <APISkeleton />
          </div>
        ) : apis.length === 0 ? (
          <div className="py-8 text-center">
            <BookOpen className="h-8 w-8 text-gray-300 mx-auto mb-2" />
            <p className="text-gray-500 text-sm">No APIs available</p>
            <p className="text-gray-400 text-xs mt-1">
              APIs will appear here once published
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {apis.map((api) => (
              <Link
                key={api.id || api.name}
                to={`/apis/${api.name}`}
                className="group flex items-start gap-3 p-3 rounded-lg border border-gray-100 hover:border-primary-200 hover:bg-primary-50/50 transition-all"
              >
                <div className="p-2 bg-indigo-100 rounded-lg">
                  <BookOpen className="h-4 w-4 text-indigo-600" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-medium text-gray-900 group-hover:text-primary-700 truncate">
                      {api.displayName || api.name}
                    </h3>
                    {api.visibility === 'internal' ? (
                      <Lock className="h-3 w-3 text-gray-400" />
                    ) : (
                      <Globe className="h-3 w-3 text-gray-400" />
                    )}
                  </div>
                  <p className="text-xs text-gray-500 line-clamp-1 mt-0.5">
                    {api.description}
                  </p>
                  {api.tags && api.tags.length > 0 && (
                    <div className="flex items-center gap-1 mt-1.5">
                      <Tag className="h-3 w-3 text-gray-400" />
                      <span className="text-xs text-gray-400">
                        {api.tags.slice(0, 2).join(', ')}
                      </span>
                    </div>
                  )}
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default FeaturedAPIs;
