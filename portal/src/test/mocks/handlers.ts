/**
 * MSW request handlers for Portal integration tests (CAB-1951).
 */

import { http, HttpResponse } from 'msw';
import { mockApis, mockTools, mockSubscriptions, mockDashboardStats } from './data';

const API_BASE = 'https://api.gostoa.dev';

export const handlers = [
  // API Catalog
  http.get(`${API_BASE}/v1/portal/apis`, () => {
    return HttpResponse.json(mockApis);
  }),
  http.get(`${API_BASE}/v1/portal/apis/:apiId`, ({ params }) => {
    const api = mockApis.find((a) => a.id === params.apiId);
    return api ? HttpResponse.json(api) : new HttpResponse(null, { status: 404 });
  }),

  // Tools
  http.get(`${API_BASE}/v1/portal/tools`, () => {
    return HttpResponse.json(mockTools);
  }),

  // Subscriptions
  http.get(`${API_BASE}/v1/portal/subscriptions`, () => {
    return HttpResponse.json(mockSubscriptions);
  }),
  http.post(`${API_BASE}/v1/portal/subscriptions`, async ({ request }) => {
    const body = (await request.json()) as Record<string, string>;
    return HttpResponse.json({ id: 'sub-new', ...body, status: 'active' }, { status: 201 });
  }),

  // Dashboard
  http.get(`${API_BASE}/v1/portal/dashboard`, () => {
    return HttpResponse.json(mockDashboardStats);
  }),

  // User profile
  http.get(`${API_BASE}/v1/me`, () => {
    return HttpResponse.json({
      id: 'user-001',
      email: 'dev@oasis.gg',
      name: 'Wade Watts',
      tenant_id: 'oasis-gunters',
      roles: ['tenant-admin'],
    });
  }),
];
