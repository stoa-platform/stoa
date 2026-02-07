import { http, HttpResponse } from 'msw';
import { mockTenants, mockApis, mockApplications, mockGateways, mockDeployments, mockPlatformStatus, mockProspectsResponse, mockProspectsMetrics, mockAggregatedMetrics, mockBusinessMetrics } from './data';

const API_BASE = 'https://api.gostoa.dev';

export const handlers = [
  // Tenants
  http.get(`${API_BASE}/v1/tenants`, () => {
    return HttpResponse.json(mockTenants);
  }),
  http.get(`${API_BASE}/v1/tenants/:tenantId`, ({ params }) => {
    const tenant = mockTenants.find(t => t.id === params.tenantId);
    return tenant ? HttpResponse.json(tenant) : new HttpResponse(null, { status: 404 });
  }),
  http.post(`${API_BASE}/v1/tenants`, async ({ request }) => {
    const body = await request.json() as Record<string, string>;
    return HttpResponse.json({ id: 'new-tenant', ...body, status: 'active', created_at: new Date().toISOString(), updated_at: new Date().toISOString() }, { status: 201 });
  }),
  http.delete(`${API_BASE}/v1/tenants/:tenantId`, () => {
    return new HttpResponse(null, { status: 204 });
  }),

  // APIs
  http.get(`${API_BASE}/v1/tenants/:tenantId/apis`, () => {
    return HttpResponse.json({ items: mockApis });
  }),
  http.post(`${API_BASE}/v1/tenants/:tenantId/apis`, async ({ request }) => {
    const body = await request.json() as Record<string, unknown>;
    return HttpResponse.json({ id: 'new-api', ...body, status: 'draft', deployed_dev: false, deployed_staging: false, created_at: new Date().toISOString(), updated_at: new Date().toISOString() }, { status: 201 });
  }),
  http.put(`${API_BASE}/v1/tenants/:tenantId/apis/:apiId`, async ({ request }) => {
    const body = await request.json() as Record<string, unknown>;
    return HttpResponse.json({ id: 'api-1', ...body });
  }),
  http.delete(`${API_BASE}/v1/tenants/:tenantId/apis/:apiId`, () => {
    return new HttpResponse(null, { status: 204 });
  }),

  // Applications
  http.get(`${API_BASE}/v1/tenants/:tenantId/applications`, () => {
    return HttpResponse.json({ items: mockApplications });
  }),
  http.post(`${API_BASE}/v1/tenants/:tenantId/applications`, async ({ request }) => {
    const body = await request.json() as Record<string, unknown>;
    return HttpResponse.json({ id: 'new-app', ...body, status: 'pending', client_id: 'client-new', created_at: new Date().toISOString(), updated_at: new Date().toISOString() }, { status: 201 });
  }),
  http.delete(`${API_BASE}/v1/tenants/:tenantId/applications/:appId`, () => {
    return new HttpResponse(null, { status: 204 });
  }),

  // Deployments
  http.get(`${API_BASE}/v1/tenants/:tenantId/deployments`, () => {
    return HttpResponse.json(mockDeployments);
  }),
  http.post(`${API_BASE}/v1/tenants/:tenantId/deployments`, async ({ request }) => {
    const body = await request.json() as Record<string, unknown>;
    return HttpResponse.json({ id: 'dep-new', ...body, status: 'pending', started_at: new Date().toISOString() }, { status: 201 });
  }),

  // Platform Status
  http.get(`${API_BASE}/v1/platform/status`, () => {
    return HttpResponse.json(mockPlatformStatus);
  }),

  // Gateway Instances
  http.get(`${API_BASE}/v1/admin/gateways`, () => {
    return HttpResponse.json({ items: mockGateways, total: mockGateways.length, page: 1, page_size: 20 });
  }),
  http.post(`${API_BASE}/v1/admin/gateways/:id/health`, () => {
    return HttpResponse.json({ status: 'healthy', details: {}, gateway_name: 'test', gateway_type: 'stoa' });
  }),
  http.delete(`${API_BASE}/v1/admin/gateways/:id`, () => {
    return new HttpResponse(null, { status: 204 });
  }),

  // Gateway Observability
  http.get(`${API_BASE}/v1/admin/gateways/metrics`, () => {
    return HttpResponse.json(mockAggregatedMetrics);
  }),

  // Admin Prospects
  http.get(`${API_BASE}/v1/admin/prospects`, () => {
    return HttpResponse.json(mockProspectsResponse);
  }),
  http.get(`${API_BASE}/v1/admin/prospects/metrics`, () => {
    return HttpResponse.json(mockProspectsMetrics);
  }),
  http.get(`${API_BASE}/v1/admin/prospects/export`, () => {
    return new HttpResponse(new Blob(['csv data'], { type: 'text/csv' }));
  }),

  // Business Metrics
  http.get(`${API_BASE}/v1/business/metrics`, () => {
    return HttpResponse.json(mockBusinessMetrics);
  }),

  // Monitoring (fallback — component uses demo data internally)
  http.get(`${API_BASE}/v1/monitoring/transactions`, () => {
    return HttpResponse.json([]);
  }),
  http.get(`${API_BASE}/v1/monitoring/transactions/stats`, () => {
    return HttpResponse.json({ total_requests: 0, success_count: 0, error_count: 0 });
  }),
];
