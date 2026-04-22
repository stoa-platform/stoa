import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockHttpClient } = vi.hoisted(() => ({
  mockHttpClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('../../../services/http', () => ({
  httpClient: mockHttpClient,
}));

import { deploymentsClient } from '../../../services/api/deployments';
import { tracesClient } from '../../../services/api/traces';
import { gatewaysClient } from '../../../services/api/gateways';
import { gatewayDeploymentsClient } from '../../../services/api/gatewayDeployments';

describe('UI-2 S2d domain clients', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('covers deploymentsClient request delegation', async () => {
    const deploymentList = { items: [{ id: 'dep-1' }], total: 1 };
    const deployment = { id: 'dep-1', status: 'running' };
    const logs = { items: [{ seq: 1, message: 'ok' }] };
    const envStatus = { environment: 'prod', status: 'healthy' };
    const deployable = { environments: [{ environment: 'prod', deployable: true }] };
    const deployResult = {
      deployed: 1,
      environment: 'prod',
      deployment_ids: ['dep-1'],
    };
    const assignments = { items: [{ id: 'assign-1' }], total: 1 };
    const assignment = { id: 'assign-1', gateway_id: 'gw-1' };

    mockHttpClient.get
      .mockResolvedValueOnce({ data: deploymentList })
      .mockResolvedValueOnce({ data: deployment })
      .mockResolvedValueOnce({ data: logs })
      .mockResolvedValueOnce({ data: envStatus })
      .mockResolvedValueOnce({ data: deployable })
      .mockResolvedValueOnce({ data: assignments });
    mockHttpClient.post
      .mockResolvedValueOnce({ data: deployment })
      .mockResolvedValueOnce({ data: deployment })
      .mockResolvedValueOnce({ data: deployResult })
      .mockResolvedValueOnce({ data: assignment });
    mockHttpClient.delete.mockResolvedValueOnce({});

    await expect(
      deploymentsClient.list('tenant-1', {
        api_id: 'api-1',
        environment: 'prod',
        status: 'running',
        page: 2,
        page_size: 20,
      })
    ).resolves.toBe(deploymentList);
    await expect(deploymentsClient.get('tenant-1', 'dep-1')).resolves.toBe(deployment);
    await expect(
      deploymentsClient.create('tenant-1', {
        api_id: 'api-1',
        environment: 'prod',
      } as never)
    ).resolves.toBe(deployment);
    await expect(deploymentsClient.rollback('tenant-1', 'dep-1', '1.2.3')).resolves.toBe(
      deployment
    );
    await expect(deploymentsClient.getLogs('tenant-1', 'dep-1', 10, 50)).resolves.toBe(logs);
    await expect(deploymentsClient.getEnvironmentStatus('tenant-1', 'prod')).resolves.toBe(
      envStatus
    );
    await expect(deploymentsClient.getDeployableEnvironments('tenant-1', 'api-1')).resolves.toBe(
      deployable
    );
    await expect(
      deploymentsClient.deployApiToEnv('tenant-1', 'api-1', {
        environment: 'prod',
        gateway_ids: ['gw-1'],
      })
    ).resolves.toBe(deployResult);
    await expect(
      deploymentsClient.getApiGatewayAssignments('tenant-1', 'api-1', 'prod')
    ).resolves.toBe(assignments);
    await expect(
      deploymentsClient.createApiGatewayAssignment('tenant-1', 'api-1', {
        gateway_id: 'gw-1',
        environment: 'prod',
        auto_deploy: true,
      })
    ).resolves.toBe(assignment);
    await expect(
      deploymentsClient.deleteApiGatewayAssignment('tenant-1', 'api-1', 'assign-1')
    ).resolves.toBeUndefined();

    expect(mockHttpClient.get).toHaveBeenNthCalledWith(1, '/v1/tenants/tenant-1/deployments', {
      params: {
        api_id: 'api-1',
        environment: 'prod',
        status: 'running',
        page: 2,
        page_size: 20,
      },
    });
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(2, '/v1/tenants/tenant-1/deployments/dep-1');
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(1, '/v1/tenants/tenant-1/deployments', {
      api_id: 'api-1',
      environment: 'prod',
    });
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      2,
      '/v1/tenants/tenant-1/deployments/dep-1/rollback',
      {
        target_version: '1.2.3',
      }
    );
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(
      3,
      '/v1/tenants/tenant-1/deployments/dep-1/logs',
      {
        params: { after_seq: 10, limit: 50 },
      }
    );
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(
      4,
      '/v1/tenants/tenant-1/deployments/environments/prod/status'
    );
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(
      5,
      '/v1/tenants/tenant-1/apis/api-1/deployable-environments'
    );
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      3,
      '/v1/tenants/tenant-1/apis/api-1/deploy',
      {
        environment: 'prod',
        gateway_ids: ['gw-1'],
      }
    );
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(
      6,
      '/v1/tenants/tenant-1/apis/api-1/gateway-assignments',
      {
        params: { environment: 'prod' },
      }
    );
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      4,
      '/v1/tenants/tenant-1/apis/api-1/gateway-assignments',
      {
        gateway_id: 'gw-1',
        environment: 'prod',
        auto_deploy: true,
      }
    );
    expect(mockHttpClient.delete).toHaveBeenCalledWith(
      '/v1/tenants/tenant-1/apis/api-1/gateway-assignments/assign-1'
    );
  });

  it('covers tracesClient request delegation', async () => {
    const traceList = { traces: [{ id: 'trace-1' }], total: 1 };
    const trace = { id: 'trace-1' };
    const timeline = { events: [{ id: 'evt-1' }] };
    const stats = { total: 10 };
    const live = { traces: [{ id: 'trace-live' }], count: 1 };
    const aiStats = { total_sessions: 5 };
    const csvBlob = new Blob(['trace,data'], { type: 'text/csv' });

    mockHttpClient.get
      .mockResolvedValueOnce({ data: traceList })
      .mockResolvedValueOnce({ data: trace })
      .mockResolvedValueOnce({ data: timeline })
      .mockResolvedValueOnce({ data: stats })
      .mockResolvedValueOnce({ data: live })
      .mockResolvedValueOnce({ data: aiStats })
      .mockResolvedValueOnce({ data: csvBlob });

    await expect(tracesClient.list(25, 'tenant-1', 'failed', 'prod')).resolves.toBe(traceList);
    await expect(tracesClient.get('trace-1')).resolves.toBe(trace);
    await expect(tracesClient.getTimeline('trace-1')).resolves.toBe(timeline);
    await expect(tracesClient.getStats()).resolves.toBe(stats);
    await expect(tracesClient.listLive()).resolves.toBe(live);
    await expect(tracesClient.getAiSessionStats(7, 'worker-a')).resolves.toBe(aiStats);
    await expect(tracesClient.exportAiSessionsCsv(7, 'worker-a')).resolves.toBe(csvBlob);

    expect(mockHttpClient.get).toHaveBeenNthCalledWith(1, '/v1/traces', {
      params: {
        limit: 25,
        tenant_id: 'tenant-1',
        status: 'failed',
        environment: 'prod',
      },
    });
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(2, '/v1/traces/trace-1');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(3, '/v1/traces/trace-1/timeline');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(4, '/v1/traces/stats');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(5, '/v1/traces/live');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(6, '/v1/traces/stats/ai-sessions', {
      params: { days: 7, worker: 'worker-a' },
    });
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(7, '/v1/traces/export/ai-sessions', {
      params: { days: 7, worker: 'worker-a' },
      responseType: 'blob',
    });
  });

  it('covers gatewaysClient request delegation', async () => {
    const gatewayList = { items: [{ id: 'gw-1' }], total: 1, page: 1, page_size: 20 };
    const gateway = { id: 'gw-1', mode: 'edge-mcp' };
    const tools = [{ id: 'tool-1' }];
    const modeStats = { modes: [{ mode: 'edge-mcp', total: 1 }], total_gateways: 1 };
    const metrics = { requests_total: 42 };
    const guardrails = { items: [{ id: 'evt-1' }] };
    const healthSummary = { healthy: 1 };
    const policies = [{ id: 'policy-1' }];
    const policy = { id: 'policy-1' };
    const binding = { id: 'binding-1' };

    mockHttpClient.get
      .mockResolvedValueOnce({ data: gatewayList })
      .mockResolvedValueOnce({ data: gateway })
      .mockResolvedValueOnce({ data: tools })
      .mockResolvedValueOnce({ data: modeStats })
      .mockResolvedValueOnce({ data: metrics })
      .mockResolvedValueOnce({ data: guardrails })
      .mockResolvedValueOnce({ data: healthSummary })
      .mockResolvedValueOnce({ data: metrics })
      .mockResolvedValueOnce({ data: policies });
    mockHttpClient.post
      .mockResolvedValueOnce({ data: gateway })
      .mockResolvedValueOnce({ data: gateway })
      .mockResolvedValueOnce({ data: gateway })
      .mockResolvedValueOnce({ data: policy })
      .mockResolvedValueOnce({ data: binding });
    mockHttpClient.put
      .mockResolvedValueOnce({ data: gateway })
      .mockResolvedValueOnce({ data: policy });
    mockHttpClient.delete
      .mockResolvedValueOnce({})
      .mockResolvedValueOnce({})
      .mockResolvedValueOnce({});

    await expect(
      gatewaysClient.listInstances({
        gateway_type: 'mcp',
        environment: 'prod',
        tenant_id: 'tenant-1',
        include_deleted: false,
        page: 1,
        page_size: 20,
      })
    ).resolves.toBe(gatewayList);
    await expect(gatewaysClient.getInstance('gw-1')).resolves.toBe(gateway);
    await expect(gatewaysClient.listTools('gw-1')).resolves.toBe(tools);
    await expect(
      gatewaysClient.createInstance({
        name: 'Gateway 1',
      })
    ).resolves.toBe(gateway);
    await expect(
      gatewaysClient.updateInstance('gw-1', {
        name: 'Gateway 1B',
      })
    ).resolves.toBe(gateway);
    await expect(gatewaysClient.removeInstance('gw-1')).resolves.toBeUndefined();
    await expect(gatewaysClient.restoreInstance('gw-1')).resolves.toBe(gateway);
    await expect(gatewaysClient.checkHealth('gw-1')).resolves.toBe(gateway);
    await expect(gatewaysClient.getModeStats()).resolves.toBe(modeStats);
    await expect(gatewaysClient.getAggregatedMetrics()).resolves.toBe(metrics);
    await expect(gatewaysClient.getGuardrailsEvents(15)).resolves.toBe(guardrails);
    await expect(gatewaysClient.getHealthSummary()).resolves.toBe(healthSummary);
    await expect(gatewaysClient.getInstanceMetrics('gw-1')).resolves.toBe(metrics);
    await expect(
      gatewaysClient.listPolicies({
        tenant_id: 'tenant-1',
        environment: 'prod',
      })
    ).resolves.toBe(policies);
    await expect(
      gatewaysClient.createPolicy({
        name: 'Policy A',
      })
    ).resolves.toBe(policy);
    await expect(
      gatewaysClient.updatePolicy('policy-1', {
        name: 'Policy B',
      })
    ).resolves.toBe(policy);
    await expect(gatewaysClient.removePolicy('policy-1')).resolves.toBeUndefined();
    await expect(
      gatewaysClient.createPolicyBinding({
        policy_id: 'policy-1',
        gateway_id: 'gw-1',
      })
    ).resolves.toBe(binding);
    await expect(gatewaysClient.removePolicyBinding('binding-1')).resolves.toBeUndefined();

    expect(mockHttpClient.get).toHaveBeenNthCalledWith(1, '/v1/admin/gateways', {
      params: {
        gateway_type: 'mcp',
        environment: 'prod',
        tenant_id: 'tenant-1',
        include_deleted: false,
        page: 1,
        page_size: 20,
      },
    });
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(2, '/v1/admin/gateways/gw-1');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(3, '/v1/admin/gateways/gw-1/tools');
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(1, '/v1/admin/gateways', {
      name: 'Gateway 1',
    });
    expect(mockHttpClient.put).toHaveBeenNthCalledWith(1, '/v1/admin/gateways/gw-1', {
      name: 'Gateway 1B',
    });
    expect(mockHttpClient.delete).toHaveBeenNthCalledWith(1, '/v1/admin/gateways/gw-1');
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(2, '/v1/admin/gateways/gw-1/restore');
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(3, '/v1/admin/gateways/gw-1/health');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(4, '/v1/admin/gateways/modes/stats');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(5, '/v1/admin/gateways/metrics');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(
      6,
      '/v1/admin/gateways/metrics/guardrails/events?limit=15'
    );
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(7, '/v1/admin/gateways/health-summary');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(8, '/v1/admin/gateways/gw-1/metrics');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(9, '/v1/admin/policies', {
      params: { tenant_id: 'tenant-1', environment: 'prod' },
    });
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(4, '/v1/admin/policies', {
      name: 'Policy A',
    });
    expect(mockHttpClient.put).toHaveBeenNthCalledWith(2, '/v1/admin/policies/policy-1', {
      name: 'Policy B',
    });
    expect(mockHttpClient.delete).toHaveBeenNthCalledWith(2, '/v1/admin/policies/policy-1');
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(5, '/v1/admin/policies/bindings', {
      policy_id: 'policy-1',
      gateway_id: 'gw-1',
    });
    expect(mockHttpClient.delete).toHaveBeenNthCalledWith(
      3,
      '/v1/admin/policies/bindings/binding-1'
    );
  });

  it('covers gatewayDeploymentsClient request delegation', async () => {
    const statusSummary = { synced: 1 };
    const deploymentList = { items: [{ id: 'dep-1' }], total: 1, page: 1, page_size: 20 };
    const deployment = { id: 'dep-1', sync_status: 'ok' };
    const created = [{ id: 'dep-1' }];
    const syncResult = { synced: true };
    const testResult = { reachable: true, status_code: 200 };
    const catalogEntries = [
      { id: 'cat-1', api_name: 'Payments', tenant_id: 'tenant-1', version: '1.0.0' },
    ];

    mockHttpClient.get
      .mockResolvedValueOnce({ data: statusSummary })
      .mockResolvedValueOnce({ data: deploymentList })
      .mockResolvedValueOnce({ data: deployment })
      .mockResolvedValueOnce({ data: catalogEntries });
    mockHttpClient.post
      .mockResolvedValueOnce({ data: created })
      .mockResolvedValueOnce({ data: syncResult })
      .mockResolvedValueOnce({ data: testResult });
    mockHttpClient.delete.mockResolvedValueOnce({});

    await expect(gatewayDeploymentsClient.getStatusSummary()).resolves.toBe(statusSummary);
    await expect(
      gatewayDeploymentsClient.list({
        sync_status: 'ok',
        gateway_instance_id: 'gw-1',
        environment: 'prod',
        gateway_type: 'mcp',
        page: 2,
        page_size: 50,
      })
    ).resolves.toBe(deploymentList);
    await expect(gatewayDeploymentsClient.get('dep-1')).resolves.toBe(deployment);
    await expect(
      gatewayDeploymentsClient.deployApiToGateways({
        api_catalog_id: 'cat-1',
        gateway_instance_ids: ['gw-1'],
      })
    ).resolves.toBe(created);
    await expect(gatewayDeploymentsClient.undeploy('dep-1')).resolves.toBeUndefined();
    await expect(gatewayDeploymentsClient.forceSync('dep-1')).resolves.toBe(syncResult);
    await expect(gatewayDeploymentsClient.test('dep-1')).resolves.toBe(testResult);
    await expect(gatewayDeploymentsClient.listCatalogEntries()).resolves.toBe(catalogEntries);

    expect(mockHttpClient.get).toHaveBeenNthCalledWith(1, '/v1/admin/deployments/status');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(2, '/v1/admin/deployments', {
      params: {
        sync_status: 'ok',
        gateway_instance_id: 'gw-1',
        environment: 'prod',
        gateway_type: 'mcp',
        page: 2,
        page_size: 50,
      },
    });
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(3, '/v1/admin/deployments/dep-1');
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(1, '/v1/admin/deployments', {
      api_catalog_id: 'cat-1',
      gateway_instance_ids: ['gw-1'],
    });
    expect(mockHttpClient.delete).toHaveBeenCalledWith('/v1/admin/deployments/dep-1');
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(2, '/v1/admin/deployments/dep-1/sync');
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(3, '/v1/admin/deployments/dep-1/test');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(4, '/v1/admin/deployments/catalog-entries');
  });
});
