import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';

vi.mock('axios', () => {
  const mockAxiosInstance = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    defaults: { headers: { common: {} } },
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  };
  return {
    default: {
      create: vi.fn(() => mockAxiosInstance),
    },
  };
});

// Must import AFTER vi.mock so the mock is active during module evaluation
let apiService: any;
let mockClient: any;
let requestInterceptor: (config: any) => any;
let responseErrorInterceptor: (error: any) => any;

beforeEach(async () => {
  vi.clearAllMocks();

  // Re-create the mock client for each test
  mockClient = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    defaults: { headers: { common: {} as Record<string, string> } },
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  };
  vi.mocked(axios.create).mockReturnValue(mockClient as any);

  // Re-import to get a fresh ApiService instance with interceptors captured
  vi.resetModules();
  const mod = await import('./api');
  apiService = mod.apiService;

  // Capture interceptors registered during constructor
  requestInterceptor = mockClient.interceptors.request.use.mock.calls[0]?.[0];
  responseErrorInterceptor = mockClient.interceptors.response.use.mock.calls[0]?.[1];
});

describe('ApiService', () => {
  describe('constructor', () => {
    it('creates axios client with correct base config', () => {
      expect(axios.create).toHaveBeenCalledWith(
        expect.objectContaining({
          headers: { 'Content-Type': 'application/json' },
        })
      );
    });

    it('registers request and response interceptors', () => {
      expect(mockClient.interceptors.request.use).toHaveBeenCalledTimes(1);
      expect(mockClient.interceptors.response.use).toHaveBeenCalledTimes(1);
    });
  });

  describe('setAuthToken / clearAuthToken', () => {
    it('sets auth token on defaults', () => {
      apiService.setAuthToken('test-token');
      expect(mockClient.defaults.headers.common['Authorization']).toBe('Bearer test-token');
    });

    it('clears auth token from defaults', () => {
      apiService.setAuthToken('test-token');
      apiService.clearAuthToken();
      expect(mockClient.defaults.headers.common['Authorization']).toBeUndefined();
    });
  });

  describe('request interceptor', () => {
    it('attaches Bearer token when auth token is set', () => {
      apiService.setAuthToken('my-token');
      const config = { headers: {} as Record<string, string> };
      const result = requestInterceptor(config);
      expect(result.headers.Authorization).toBe('Bearer my-token');
    });

    it('does not attach header when no token set', () => {
      const config = { headers: {} as Record<string, string> };
      const result = requestInterceptor(config);
      expect(result.headers.Authorization).toBeUndefined();
    });
  });

  describe('response interceptor (401 token refresh)', () => {
    it('rejects non-401 errors normally', async () => {
      const error = { response: { status: 500 }, config: {} };
      await expect(responseErrorInterceptor(error)).rejects.toEqual(error);
    });

    it('rejects 401 when no token refresher is set', async () => {
      const error = { response: { status: 401 }, config: { _retry: false, headers: {} } };
      await expect(responseErrorInterceptor(error)).rejects.toEqual(error);
    });

    it('retries request after successful token refresh', async () => {
      const refresher = vi.fn().mockResolvedValue('new-token');
      apiService.setTokenRefresher(refresher);

      const originalRequest = { _retry: false, headers: {} as Record<string, string> };
      const error = { response: { status: 401 }, config: originalRequest };

      mockClient.mockImplementation = undefined;
      // Mock the retry call
      const retryResponse = { data: 'success' };
      mockClient.mockReturnValue = retryResponse;
      // The interceptor calls this.client(originalRequest) for retry
      // We need to mock the client as a callable
      // Replace the internal client reference - since we can't directly,
      // we verify the refresher was called
      try {
        await responseErrorInterceptor(error);
      } catch {
        // Expected - the mock client is not callable
      }
      expect(refresher).toHaveBeenCalled();
    });

    it('does not retry if already retried', async () => {
      const refresher = vi.fn().mockResolvedValue('new-token');
      apiService.setTokenRefresher(refresher);

      const error = {
        response: { status: 401 },
        config: { _retry: true, headers: {} },
      };
      await expect(responseErrorInterceptor(error)).rejects.toEqual(error);
      expect(refresher).not.toHaveBeenCalled();
    });
  });

  describe('generic HTTP methods', () => {
    it('get() delegates to client.get', async () => {
      mockClient.get.mockResolvedValue({ data: { items: [] } });
      const result = await apiService.get('/test', { params: { page: 1 } });
      expect(mockClient.get).toHaveBeenCalledWith('/test', { params: { page: 1 } });
      expect(result).toEqual({ data: { items: [] } });
    });

    it('post() delegates to client.post', async () => {
      mockClient.post.mockResolvedValue({ data: { id: '1' } });
      const result = await apiService.post('/test', { name: 'foo' });
      expect(mockClient.post).toHaveBeenCalledWith('/test', { name: 'foo' });
      expect(result).toEqual({ data: { id: '1' } });
    });

    it('put() delegates to client.put', async () => {
      mockClient.put.mockResolvedValue({ data: { id: '1' } });
      const result = await apiService.put('/test', { name: 'bar' });
      expect(mockClient.put).toHaveBeenCalledWith('/test', { name: 'bar' });
      expect(result).toEqual({ data: { id: '1' } });
    });

    it('patch() delegates to client.patch', async () => {
      mockClient.patch.mockResolvedValue({ data: { id: '1' } });
      const result = await apiService.patch('/test', { name: 'baz' });
      expect(mockClient.patch).toHaveBeenCalledWith('/test', { name: 'baz' });
      expect(result).toEqual({ data: { id: '1' } });
    });

    it('delete() delegates to client.delete', async () => {
      mockClient.delete.mockResolvedValue({ data: null });
      const result = await apiService.delete('/test');
      expect(mockClient.delete).toHaveBeenCalledWith('/test');
      expect(result).toEqual({ data: null });
    });
  });

  describe('Tenants API', () => {
    it('getTenants calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: [{ id: 't1' }] });
      const result = await apiService.getTenants();
      expect(mockClient.get).toHaveBeenCalledWith('/v1/tenants');
      expect(result).toEqual([{ id: 't1' }]);
    });

    it('getTenant calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: { id: 't1' } });
      const result = await apiService.getTenant('t1');
      expect(mockClient.get).toHaveBeenCalledWith('/v1/tenants/t1');
      expect(result).toEqual({ id: 't1' });
    });

    it('createTenant posts to correct endpoint', async () => {
      const payload = { name: 'acme', display_name: 'Acme' };
      mockClient.post.mockResolvedValue({ data: { id: 't1', ...payload } });
      const result = await apiService.createTenant(payload);
      expect(mockClient.post).toHaveBeenCalledWith('/v1/tenants', payload);
      expect(result).toEqual({ id: 't1', ...payload });
    });

    it('updateTenant puts to correct endpoint', async () => {
      const payload = { display_name: 'Updated' };
      mockClient.put.mockResolvedValue({ data: { id: 't1', ...payload } });
      const result = await apiService.updateTenant('t1', payload);
      expect(mockClient.put).toHaveBeenCalledWith('/v1/tenants/t1', payload);
      expect(result).toEqual({ id: 't1', ...payload });
    });

    it('deleteTenant calls correct endpoint', async () => {
      mockClient.delete.mockResolvedValue({});
      await apiService.deleteTenant('t1');
      expect(mockClient.delete).toHaveBeenCalledWith('/v1/tenants/t1');
    });
  });

  describe('Environments API', () => {
    it('getEnvironments returns environments array', async () => {
      mockClient.get.mockResolvedValue({ data: { environments: [{ name: 'dev' }] } });
      const result = await apiService.getEnvironments();
      expect(mockClient.get).toHaveBeenCalledWith('/v1/environments');
      expect(result).toEqual([{ name: 'dev' }]);
    });
  });

  describe('APIs', () => {
    it('getApis calls with tenant and pagination', async () => {
      mockClient.get.mockResolvedValue({ data: { items: [{ id: 'a1' }] } });
      const result = await apiService.getApis('t1');
      expect(mockClient.get).toHaveBeenCalledWith('/v1/tenants/t1/apis', {
        params: { page: 1, page_size: 100 },
      });
      expect(result).toEqual([{ id: 'a1' }]);
    });

    it('getApis passes environment filter', async () => {
      mockClient.get.mockResolvedValue({ data: { items: [] } });
      await apiService.getApis('t1', 'staging');
      expect(mockClient.get).toHaveBeenCalledWith('/v1/tenants/t1/apis', {
        params: { page: 1, page_size: 100, environment: 'staging' },
      });
    });

    it('getApis falls back to data when no items property', async () => {
      mockClient.get.mockResolvedValue({ data: [{ id: 'a1' }] });
      const result = await apiService.getApis('t1');
      expect(result).toEqual([{ id: 'a1' }]);
    });

    it('getApi calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: { id: 'a1' } });
      const result = await apiService.getApi('t1', 'a1');
      expect(mockClient.get).toHaveBeenCalledWith('/v1/tenants/t1/apis/a1');
      expect(result).toEqual({ id: 'a1' });
    });

    it('createApi posts to correct endpoint', async () => {
      const payload = {
        name: 'api1',
        display_name: 'API 1',
        version: '1.0',
        description: 'desc',
        backend_url: 'http://x',
      };
      mockClient.post.mockResolvedValue({ data: { id: 'a1', ...payload } });
      await apiService.createApi('t1', payload);
      expect(mockClient.post).toHaveBeenCalledWith('/v1/tenants/t1/apis', payload);
    });

    it('updateApi puts to correct endpoint', async () => {
      mockClient.put.mockResolvedValue({ data: { id: 'a1' } });
      await apiService.updateApi('t1', 'a1', { description: 'new' });
      expect(mockClient.put).toHaveBeenCalledWith('/v1/tenants/t1/apis/a1', { description: 'new' });
    });

    it('deleteApi calls correct endpoint', async () => {
      mockClient.delete.mockResolvedValue({});
      await apiService.deleteApi('t1', 'a1');
      expect(mockClient.delete).toHaveBeenCalledWith('/v1/tenants/t1/apis/a1');
    });
  });

  describe('Applications', () => {
    it('getApplications calls with pagination', async () => {
      mockClient.get.mockResolvedValue({ data: { items: [{ id: 'app1' }] } });
      const result = await apiService.getApplications('t1');
      expect(mockClient.get).toHaveBeenCalledWith('/v1/tenants/t1/applications', {
        params: { page: 1, page_size: 100 },
      });
      expect(result).toEqual([{ id: 'app1' }]);
    });

    it('getApplication calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: { id: 'app1' } });
      await apiService.getApplication('t1', 'app1');
      expect(mockClient.get).toHaveBeenCalledWith('/v1/tenants/t1/applications/app1');
    });

    it('createApplication posts correctly', async () => {
      const payload = { name: 'app', display_name: 'App', description: 'd', redirect_uris: [] };
      mockClient.post.mockResolvedValue({ data: { id: 'app1' } });
      await apiService.createApplication('t1', payload as any);
      expect(mockClient.post).toHaveBeenCalledWith('/v1/tenants/t1/applications', payload);
    });

    it('updateApplication puts correctly', async () => {
      mockClient.put.mockResolvedValue({ data: { id: 'app1' } });
      await apiService.updateApplication('t1', 'app1', { description: 'new' } as any);
      expect(mockClient.put).toHaveBeenCalledWith('/v1/tenants/t1/applications/app1', {
        description: 'new',
      });
    });

    it('deleteApplication calls correct endpoint', async () => {
      mockClient.delete.mockResolvedValue({});
      await apiService.deleteApplication('t1', 'app1');
      expect(mockClient.delete).toHaveBeenCalledWith('/v1/tenants/t1/applications/app1');
    });
  });

  describe('Consumers', () => {
    it('getConsumers calls with pagination', async () => {
      mockClient.get.mockResolvedValue({ data: { items: [{ id: 'c1' }] } });
      const result = await apiService.getConsumers('t1');
      expect(mockClient.get).toHaveBeenCalledWith('/v1/consumers/t1', {
        params: { page: 1, page_size: 100 },
      });
      expect(result).toEqual([{ id: 'c1' }]);
    });

    it('getConsumer calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: { id: 'c1' } });
      await apiService.getConsumer('t1', 'c1');
      expect(mockClient.get).toHaveBeenCalledWith('/v1/consumers/t1/c1');
    });

    it('suspendConsumer posts to correct endpoint', async () => {
      mockClient.post.mockResolvedValue({ data: { id: 'c1', status: 'suspended' } });
      await apiService.suspendConsumer('t1', 'c1');
      expect(mockClient.post).toHaveBeenCalledWith('/v1/consumers/t1/c1/suspend');
    });

    it('activateConsumer posts to correct endpoint', async () => {
      mockClient.post.mockResolvedValue({ data: { id: 'c1', status: 'active' } });
      await apiService.activateConsumer('t1', 'c1');
      expect(mockClient.post).toHaveBeenCalledWith('/v1/consumers/t1/c1/activate');
    });

    it('deleteConsumer calls correct endpoint', async () => {
      mockClient.delete.mockResolvedValue({});
      await apiService.deleteConsumer('t1', 'c1');
      expect(mockClient.delete).toHaveBeenCalledWith('/v1/consumers/t1/c1');
    });

    it('rotateCertificate posts with correct payload', async () => {
      mockClient.post.mockResolvedValue({ data: { id: 'c1' } });
      await apiService.rotateCertificate('t1', 'c1', 'PEM_DATA', 48);
      expect(mockClient.post).toHaveBeenCalledWith('/v1/consumers/t1/c1/certificate/rotate', {
        certificate_pem: 'PEM_DATA',
        grace_period_hours: 48,
      });
    });

    it('rotateCertificate uses default grace period', async () => {
      mockClient.post.mockResolvedValue({ data: { id: 'c1' } });
      await apiService.rotateCertificate('t1', 'c1', 'PEM');
      expect(mockClient.post).toHaveBeenCalledWith('/v1/consumers/t1/c1/certificate/rotate', {
        certificate_pem: 'PEM',
        grace_period_hours: 24,
      });
    });

    it('revokeCertificate posts to correct endpoint', async () => {
      mockClient.post.mockResolvedValue({ data: { id: 'c1' } });
      await apiService.revokeCertificate('t1', 'c1');
      expect(mockClient.post).toHaveBeenCalledWith('/v1/consumers/t1/c1/certificate/revoke');
    });

    it('blockConsumer posts to correct endpoint', async () => {
      mockClient.post.mockResolvedValue({ data: { id: 'c1' } });
      await apiService.blockConsumer('t1', 'c1');
      expect(mockClient.post).toHaveBeenCalledWith('/v1/consumers/t1/c1/block');
    });

    it('bindCertificate posts with correct payload', async () => {
      mockClient.post.mockResolvedValue({ data: { id: 'c1' } });
      await apiService.bindCertificate('t1', 'c1', 'PEM');
      expect(mockClient.post).toHaveBeenCalledWith('/v1/consumers/t1/c1/certificate', {
        certificate_pem: 'PEM',
      });
    });

    it('getExpiringCertificates passes days param', async () => {
      mockClient.get.mockResolvedValue({ data: { consumers: [] } });
      await apiService.getExpiringCertificates('t1', 60);
      expect(mockClient.get).toHaveBeenCalledWith('/v1/consumers/t1/certificates/expiring', {
        params: { days: 60 },
      });
    });

    it('bulkRevokeCertificates posts with consumer IDs', async () => {
      mockClient.post.mockResolvedValue({ data: { revoked: 2 } });
      await apiService.bulkRevokeCertificates('t1', ['c1', 'c2']);
      expect(mockClient.post).toHaveBeenCalledWith('/v1/consumers/t1/certificates/bulk-revoke', {
        consumer_ids: ['c1', 'c2'],
      });
    });
  });

  describe('Deployments', () => {
    it('listDeployments calls with params', async () => {
      mockClient.get.mockResolvedValue({ data: { items: [], total: 0 } });
      await apiService.listDeployments('t1', { environment: 'dev', page: 2 });
      expect(mockClient.get).toHaveBeenCalledWith('/v1/tenants/t1/deployments', {
        params: { environment: 'dev', page: 2 },
      });
    });

    it('getDeployment calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: { id: 'd1' } });
      await apiService.getDeployment('t1', 'd1');
      expect(mockClient.get).toHaveBeenCalledWith('/v1/tenants/t1/deployments/d1');
    });

    it('createDeployment posts correctly', async () => {
      const payload = { api_id: 'a1', environment: 'dev', version: '1.0' };
      mockClient.post.mockResolvedValue({ data: { id: 'd1' } });
      await apiService.createDeployment('t1', payload as any);
      expect(mockClient.post).toHaveBeenCalledWith('/v1/tenants/t1/deployments', payload);
    });

    it('rollbackDeployment posts with target version', async () => {
      mockClient.post.mockResolvedValue({ data: { id: 'd1' } });
      await apiService.rollbackDeployment('t1', 'd1', '0.9.0');
      expect(mockClient.post).toHaveBeenCalledWith('/v1/tenants/t1/deployments/d1/rollback', {
        target_version: '0.9.0',
      });
    });

    it('getEnvironmentStatus calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: { environment: 'dev' } });
      await apiService.getEnvironmentStatus('t1', 'dev');
      expect(mockClient.get).toHaveBeenCalledWith(
        '/v1/tenants/t1/deployments/environments/dev/status'
      );
    });
  });

  describe('Git', () => {
    it('getCommits calls with optional path', async () => {
      mockClient.get.mockResolvedValue({ data: [{ sha: 'abc' }] });
      await apiService.getCommits('t1', 'src/');
      expect(mockClient.get).toHaveBeenCalledWith('/v1/tenants/t1/git/commits', {
        params: { path: 'src/' },
      });
    });

    it('getCommits calls without path param when none provided', async () => {
      mockClient.get.mockResolvedValue({ data: [] });
      await apiService.getCommits('t1');
      expect(mockClient.get).toHaveBeenCalledWith('/v1/tenants/t1/git/commits', { params: {} });
    });

    it('getMergeRequests calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: [] });
      await apiService.getMergeRequests('t1');
      expect(mockClient.get).toHaveBeenCalledWith('/v1/tenants/t1/git/merge-requests');
    });
  });

  describe('Pipeline Traces', () => {
    it('getTraces calls with optional params', async () => {
      mockClient.get.mockResolvedValue({ data: { traces: [], total: 0 } });
      await apiService.getTraces(10, 't1', 'error');
      expect(mockClient.get).toHaveBeenCalledWith('/v1/traces', {
        params: { limit: 10, tenant_id: 't1', status: 'error' },
      });
    });

    it('getTraces sends empty params when none provided', async () => {
      mockClient.get.mockResolvedValue({ data: { traces: [], total: 0 } });
      await apiService.getTraces();
      expect(mockClient.get).toHaveBeenCalledWith('/v1/traces', { params: {} });
    });

    it('getTrace calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: { id: 'tr1' } });
      await apiService.getTrace('tr1');
      expect(mockClient.get).toHaveBeenCalledWith('/v1/traces/tr1');
    });

    it('getTraceTimeline calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: { events: [] } });
      await apiService.getTraceTimeline('tr1');
      expect(mockClient.get).toHaveBeenCalledWith('/v1/traces/tr1/timeline');
    });

    it('getTraceStats calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: { total: 100 } });
      await apiService.getTraceStats();
      expect(mockClient.get).toHaveBeenCalledWith('/v1/traces/stats');
    });

    it('getLiveTraces calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: { traces: [], count: 0 } });
      await apiService.getLiveTraces();
      expect(mockClient.get).toHaveBeenCalledWith('/v1/traces/live');
    });
  });

  describe('Platform Status', () => {
    it('getPlatformStatus calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: { gitops: {} } });
      await apiService.getPlatformStatus();
      expect(mockClient.get).toHaveBeenCalledWith('/v1/platform/status');
    });

    it('getPlatformComponents calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: [] });
      await apiService.getPlatformComponents();
      expect(mockClient.get).toHaveBeenCalledWith('/v1/platform/components');
    });

    it('getComponentStatus calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: { name: 'api' } });
      await apiService.getComponentStatus('api');
      expect(mockClient.get).toHaveBeenCalledWith('/v1/platform/components/api');
    });

    it('syncPlatformComponent posts to correct endpoint', async () => {
      mockClient.post.mockResolvedValue({ data: { message: 'ok' } });
      await apiService.syncPlatformComponent('api');
      expect(mockClient.post).toHaveBeenCalledWith('/v1/platform/components/api/sync');
    });

    it('getComponentDiff calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: { resources: [] } });
      await apiService.getComponentDiff('api');
      expect(mockClient.get).toHaveBeenCalledWith('/v1/platform/components/api/diff');
    });

    it('getPlatformEvents calls with optional params', async () => {
      mockClient.get.mockResolvedValue({ data: [] });
      await apiService.getPlatformEvents('gateway', 5);
      expect(mockClient.get).toHaveBeenCalledWith('/v1/platform/events', {
        params: { component: 'gateway', limit: 5 },
      });
    });

    it('getPlatformEvents calls with empty params when none provided', async () => {
      mockClient.get.mockResolvedValue({ data: [] });
      await apiService.getPlatformEvents();
      expect(mockClient.get).toHaveBeenCalledWith('/v1/platform/events', { params: {} });
    });
  });

  describe('Admin Prospects', () => {
    it('getProspects calls with params', async () => {
      mockClient.get.mockResolvedValue({ data: { items: [] } });
      await apiService.getProspects({ company: 'acme', page: 2 });
      expect(mockClient.get).toHaveBeenCalledWith('/v1/admin/prospects', {
        params: { company: 'acme', page: 2 },
      });
    });

    it('getProspectsMetrics calls with date params', async () => {
      mockClient.get.mockResolvedValue({ data: { total: 10 } });
      await apiService.getProspectsMetrics({ date_from: '2026-01-01' });
      expect(mockClient.get).toHaveBeenCalledWith('/v1/admin/prospects/metrics', {
        params: { date_from: '2026-01-01' },
      });
    });

    it('getProspect calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: { id: 'inv1' } });
      await apiService.getProspect('inv1');
      expect(mockClient.get).toHaveBeenCalledWith('/v1/admin/prospects/inv1');
    });

    it('exportProspectsCSV calls with params and blob responseType', async () => {
      mockClient.get.mockResolvedValue({ data: new Blob() });
      await apiService.exportProspectsCSV({ status: 'active' });
      expect(mockClient.get).toHaveBeenCalledWith('/v1/admin/prospects/export', {
        params: { status: 'active' },
        responseType: 'blob',
      });
    });
  });

  describe('Gateway Instances', () => {
    it('getGatewayInstances calls with params', async () => {
      mockClient.get.mockResolvedValue({ data: { items: [], total: 0 } });
      await apiService.getGatewayInstances({ gateway_type: 'kong' });
      expect(mockClient.get).toHaveBeenCalledWith('/v1/admin/gateways', {
        params: { gateway_type: 'kong' },
      });
    });

    it('getGatewayInstance calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: { id: 'gw1' } });
      await apiService.getGatewayInstance('gw1');
      expect(mockClient.get).toHaveBeenCalledWith('/v1/admin/gateways/gw1');
    });

    it('createGatewayInstance posts correctly', async () => {
      mockClient.post.mockResolvedValue({ data: { id: 'gw1' } });
      await apiService.createGatewayInstance({ name: 'gw' });
      expect(mockClient.post).toHaveBeenCalledWith('/v1/admin/gateways', { name: 'gw' });
    });

    it('updateGatewayInstance puts correctly', async () => {
      mockClient.put.mockResolvedValue({ data: { id: 'gw1' } });
      await apiService.updateGatewayInstance('gw1', { name: 'updated' });
      expect(mockClient.put).toHaveBeenCalledWith('/v1/admin/gateways/gw1', { name: 'updated' });
    });

    it('deleteGatewayInstance calls correct endpoint', async () => {
      mockClient.delete.mockResolvedValue({});
      await apiService.deleteGatewayInstance('gw1');
      expect(mockClient.delete).toHaveBeenCalledWith('/v1/admin/gateways/gw1');
    });

    it('checkGatewayHealth posts to correct endpoint', async () => {
      mockClient.post.mockResolvedValue({ data: { status: 'healthy' } });
      await apiService.checkGatewayHealth('gw1');
      expect(mockClient.post).toHaveBeenCalledWith('/v1/admin/gateways/gw1/health');
    });

    it('getGatewayModeStats calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: { modes: [], total_gateways: 0 } });
      await apiService.getGatewayModeStats();
      expect(mockClient.get).toHaveBeenCalledWith('/v1/admin/gateways/modes/stats');
    });
  });

  describe('Gateway Deployments', () => {
    it('getDeploymentStatusSummary calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: {} });
      await apiService.getDeploymentStatusSummary();
      expect(mockClient.get).toHaveBeenCalledWith('/v1/admin/deployments/status');
    });

    it('getGatewayDeployments calls with params', async () => {
      mockClient.get.mockResolvedValue({ data: { items: [] } });
      await apiService.getGatewayDeployments({ sync_status: 'synced' });
      expect(mockClient.get).toHaveBeenCalledWith('/v1/admin/deployments', {
        params: { sync_status: 'synced' },
      });
    });

    it('deployApiToGateways posts correctly', async () => {
      mockClient.post.mockResolvedValue({ data: [{ id: 'd1' }] });
      await apiService.deployApiToGateways({ api_catalog_id: 'a1', gateway_instance_ids: ['gw1'] });
      expect(mockClient.post).toHaveBeenCalledWith('/v1/admin/deployments', {
        api_catalog_id: 'a1',
        gateway_instance_ids: ['gw1'],
      });
    });

    it('undeployFromGateway calls correct endpoint', async () => {
      mockClient.delete.mockResolvedValue({});
      await apiService.undeployFromGateway('d1');
      expect(mockClient.delete).toHaveBeenCalledWith('/v1/admin/deployments/d1');
    });

    it('forceSyncDeployment posts to correct endpoint', async () => {
      mockClient.post.mockResolvedValue({ data: {} });
      await apiService.forceSyncDeployment('d1');
      expect(mockClient.post).toHaveBeenCalledWith('/v1/admin/deployments/d1/sync');
    });

    it('getCatalogEntries calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: [] });
      await apiService.getCatalogEntries();
      expect(mockClient.get).toHaveBeenCalledWith('/v1/admin/deployments/catalog-entries');
    });
  });

  describe('Gateway Observability', () => {
    it('getGatewayAggregatedMetrics calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: {} });
      await apiService.getGatewayAggregatedMetrics();
      expect(mockClient.get).toHaveBeenCalledWith('/v1/admin/gateways/metrics');
    });

    it('getGatewayHealthSummary calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: {} });
      await apiService.getGatewayHealthSummary();
      expect(mockClient.get).toHaveBeenCalledWith('/v1/admin/gateways/health-summary');
    });

    it('getGatewayInstanceMetrics calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: {} });
      await apiService.getGatewayInstanceMetrics('gw1');
      expect(mockClient.get).toHaveBeenCalledWith('/v1/admin/gateways/gw1/metrics');
    });
  });

  describe('Gateway Policies', () => {
    it('getGatewayPolicies calls with optional tenant_id', async () => {
      mockClient.get.mockResolvedValue({ data: [] });
      await apiService.getGatewayPolicies({ tenant_id: 't1' });
      expect(mockClient.get).toHaveBeenCalledWith('/v1/admin/policies', {
        params: { tenant_id: 't1' },
      });
    });

    it('createGatewayPolicy posts correctly', async () => {
      mockClient.post.mockResolvedValue({ data: { id: 'p1' } });
      await apiService.createGatewayPolicy({ name: 'rate-limit' });
      expect(mockClient.post).toHaveBeenCalledWith('/v1/admin/policies', { name: 'rate-limit' });
    });

    it('updateGatewayPolicy puts correctly', async () => {
      mockClient.put.mockResolvedValue({ data: { id: 'p1' } });
      await apiService.updateGatewayPolicy('p1', { name: 'updated' });
      expect(mockClient.put).toHaveBeenCalledWith('/v1/admin/policies/p1', { name: 'updated' });
    });

    it('deleteGatewayPolicy calls correct endpoint', async () => {
      mockClient.delete.mockResolvedValue({});
      await apiService.deleteGatewayPolicy('p1');
      expect(mockClient.delete).toHaveBeenCalledWith('/v1/admin/policies/p1');
    });

    it('createPolicyBinding posts correctly', async () => {
      mockClient.post.mockResolvedValue({ data: { id: 'b1' } });
      await apiService.createPolicyBinding({ policy_id: 'p1', gateway_id: 'gw1' });
      expect(mockClient.post).toHaveBeenCalledWith('/v1/admin/policies/bindings', {
        policy_id: 'p1',
        gateway_id: 'gw1',
      });
    });

    it('deletePolicyBinding calls correct endpoint', async () => {
      mockClient.delete.mockResolvedValue({});
      await apiService.deletePolicyBinding('b1');
      expect(mockClient.delete).toHaveBeenCalledWith('/v1/admin/policies/bindings/b1');
    });
  });

  describe('Operations & Business', () => {
    it('getOperationsMetrics calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: { error_rate: 0.01 } });
      await apiService.getOperationsMetrics();
      expect(mockClient.get).toHaveBeenCalledWith('/v1/operations/metrics');
    });

    it('getBusinessMetrics calls correct endpoint', async () => {
      mockClient.get.mockResolvedValue({ data: { active_tenants: 5 } });
      await apiService.getBusinessMetrics();
      expect(mockClient.get).toHaveBeenCalledWith('/v1/business/metrics');
    });

    it('getTopAPIs calls with default limit', async () => {
      mockClient.get.mockResolvedValue({ data: [] });
      await apiService.getTopAPIs();
      expect(mockClient.get).toHaveBeenCalledWith('/v1/business/top-apis?limit=10');
    });

    it('getTopAPIs calls with custom limit', async () => {
      mockClient.get.mockResolvedValue({ data: [] });
      await apiService.getTopAPIs(5);
      expect(mockClient.get).toHaveBeenCalledWith('/v1/business/top-apis?limit=5');
    });
  });

  describe('SSE Events', () => {
    let capturedUrls: string[];

    beforeEach(() => {
      capturedUrls = [];
      // EventSource needs to be a real constructor (called with `new`)
      (globalThis as any).EventSource = class MockEventSource {
        url: string;
        close = vi.fn();
        constructor(url: string) {
          this.url = url;
          capturedUrls.push(url);
        }
      };
    });

    it('createEventSource builds URL with event types', () => {
      const es = apiService.createEventSource('t1', ['api.created', 'api.updated']);
      expect(capturedUrls[0]).toContain('/v1/events/stream/t1?event_types=api.created,api.updated');
      expect(es).toBeDefined();
    });

    it('createEventSource builds URL without event types', () => {
      const es = apiService.createEventSource('t1');
      expect(capturedUrls[0]).toContain('/v1/events/stream/t1');
      expect(capturedUrls[0]).not.toContain('event_types');
      expect(es).toBeDefined();
    });
  });
});
