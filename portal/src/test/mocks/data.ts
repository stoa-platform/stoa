/**
 * Mock data for Portal MSW handlers (CAB-1951).
 */

export const mockApis = [
  {
    id: 'api-weather',
    tenant_id: 'oasis-gunters',
    name: 'weather-api',
    display_name: 'Weather API',
    version: '2.0.0',
    description: 'Real-time weather data for AI agents',
    status: 'published',
    tags: ['weather', 'mcp'],
    created_at: '2026-01-15T10:00:00Z',
    updated_at: '2026-03-01T14:30:00Z',
  },
  {
    id: 'api-payment',
    tenant_id: 'oasis-gunters',
    name: 'payment-api',
    display_name: 'Payment API',
    version: '1.0.0',
    description: 'Process payments securely',
    status: 'published',
    tags: ['payments'],
    created_at: '2026-02-01T10:00:00Z',
    updated_at: '2026-03-10T12:00:00Z',
  },
];

export const mockTools = [
  {
    id: 'tool-weather',
    name: 'get-weather',
    display_name: 'Get Weather',
    description: 'Retrieve current weather for a location',
    version: '1.0',
    status: 'active',
  },
];

export const mockSubscriptions = [
  {
    id: 'sub-001',
    api_id: 'api-weather',
    application_id: 'app-mobile',
    plan: 'basic',
    status: 'active',
    created_at: '2026-02-15T10:00:00Z',
  },
];

export const mockDashboardStats = {
  total_apis: 12,
  total_subscriptions: 5,
  total_tools: 8,
  total_calls_30d: 15420,
};
