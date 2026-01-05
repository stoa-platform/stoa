import { CreditCard, Wrench, TrendingUp, AlertCircle } from 'lucide-react';

// Mock data
const mockSubscriptions = [
  {
    id: '1',
    toolName: 'Text Analyzer',
    status: 'active',
    plan: 'premium',
    usage: { callsToday: 45, dailyLimit: 1000 },
    expiresAt: '2026-02-15',
  },
  {
    id: '2',
    toolName: 'Code Assistant',
    status: 'active',
    plan: 'basic',
    usage: { callsToday: 120, dailyLimit: 500 },
    expiresAt: '2026-01-20',
  },
];

export function MySubscriptions() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">My Subscriptions</h1>
        <p className="text-gray-500 mt-1">
          Manage your tool subscriptions and monitor usage
        </p>
      </div>

      {/* Stats Overview */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary-50 rounded-lg">
              <CreditCard className="h-5 w-5 text-primary-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900">{mockSubscriptions.length}</p>
              <p className="text-sm text-gray-500">Active Subscriptions</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-green-50 rounded-lg">
              <TrendingUp className="h-5 w-5 text-green-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900">165</p>
              <p className="text-sm text-gray-500">Calls Today</p>
            </div>
          </div>
        </div>
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-amber-50 rounded-lg">
              <AlertCircle className="h-5 w-5 text-amber-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900">1</p>
              <p className="text-sm text-gray-500">Expiring Soon</p>
            </div>
          </div>
        </div>
      </div>

      {/* Subscriptions List */}
      <div className="bg-white rounded-lg border border-gray-200">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="font-semibold text-gray-900">Active Subscriptions</h2>
        </div>
        <div className="divide-y divide-gray-200">
          {mockSubscriptions.map(sub => (
            <div key={sub.id} className="px-6 py-4 hover:bg-gray-50">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="p-2 bg-primary-50 rounded-lg">
                    <Wrench className="h-5 w-5 text-primary-600" />
                  </div>
                  <div>
                    <h3 className="font-medium text-gray-900">{sub.toolName}</h3>
                    <p className="text-sm text-gray-500">
                      {sub.plan.charAt(0).toUpperCase() + sub.plan.slice(1)} Plan
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-sm font-medium text-gray-900">
                    {sub.usage.callsToday} / {sub.usage.dailyLimit} calls
                  </p>
                  <p className="text-xs text-gray-500">
                    Expires: {new Date(sub.expiresAt).toLocaleDateString()}
                  </p>
                </div>
              </div>
              {/* Usage bar */}
              <div className="mt-3">
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary-500 rounded-full"
                    style={{ width: `${(sub.usage.callsToday / sub.usage.dailyLimit) * 100}%` }}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {mockSubscriptions.length === 0 && (
        <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
          <CreditCard className="h-12 w-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500">You don't have any subscriptions yet</p>
          <button className="mt-4 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700">
            Browse Tools
          </button>
        </div>
      )}
    </div>
  );
}
