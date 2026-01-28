// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * Unauthorized page - Shown when user lacks permission to access a resource
 */
import { Link } from 'react-router-dom';
import { ShieldX, Home, ArrowLeft } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

export function UnauthorizedPage() {
  const { user } = useAuth();

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-4">
      <div className="text-center max-w-md">
        {/* Icon */}
        <div className="flex justify-center mb-6">
          <div className="w-20 h-20 bg-red-100 rounded-full flex items-center justify-center">
            <ShieldX className="w-10 h-10 text-red-600" />
          </div>
        </div>

        {/* Title */}
        <h1 className="text-2xl font-bold text-gray-900 mb-2">
          Access Denied
        </h1>

        {/* Description */}
        <p className="text-gray-600 mb-6">
          You don't have permission to access this page.
          Please contact your administrator if you believe this is an error.
        </p>

        {/* User info for debugging */}
        {user && (
          <div className="bg-gray-50 rounded-lg p-4 mb-6 text-left">
            <p className="text-sm text-gray-500 mb-2">Current user information:</p>
            <div className="space-y-1 text-sm">
              <p>
                <span className="text-gray-500">Email:</span>{' '}
                <span className="font-medium text-gray-700">{user.email}</span>
              </p>
              <p>
                <span className="text-gray-500">Roles:</span>{' '}
                <span className="font-mono text-xs bg-gray-100 px-2 py-0.5 rounded">
                  {user.roles.length > 0 ? user.roles.join(', ') : 'none'}
                </span>
              </p>
              {user.tenant_id && (
                <p>
                  <span className="text-gray-500">Tenant:</span>{' '}
                  <span className="font-medium text-gray-700">{user.tenant_id}</span>
                </p>
              )}
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            to="/"
            className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
          >
            <Home className="w-4 h-4" />
            Go to Dashboard
          </Link>
          <button
            onClick={() => window.history.back()}
            className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Go Back
          </button>
        </div>
      </div>
    </div>
  );
}

export default UnauthorizedPage;
