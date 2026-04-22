import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockHttpClient } = vi.hoisted(() => ({
  mockHttpClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('../../../services/http', () => ({
  httpClient: mockHttpClient,
}));

import { adminClient } from '../../../services/api/admin';
import { gitClient } from '../../../services/api/git';
import { sessionClient } from '../../../services/api/session';
import { toolPermissionsClient } from '../../../services/api/toolPermissions';
import { workflowsClient } from '../../../services/api/workflows';

describe('UI-2 S2a domain clients', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('covers adminClient request delegation', async () => {
    const users = { items: [] };
    const settings = { items: [] };
    const setting = { key: 'theme', value: 'dark' };
    const roles = { items: [] };
    const accessRequests = { items: [] };
    const prospects = { items: [] };
    const metrics = { total: 1 };
    const prospect = { invite_id: 'inv-1' };
    const csvBlob = new Blob(['id,name']);

    mockHttpClient.get
      .mockResolvedValueOnce({ data: users })
      .mockResolvedValueOnce({ data: settings })
      .mockResolvedValueOnce({ data: roles })
      .mockResolvedValueOnce({ data: accessRequests })
      .mockResolvedValueOnce({ data: prospects })
      .mockResolvedValueOnce({ data: metrics })
      .mockResolvedValueOnce({ data: prospect })
      .mockResolvedValueOnce({ data: csvBlob });
    mockHttpClient.put.mockResolvedValueOnce({ data: setting });

    await expect(
      adminClient.listUsers({ role: 'tenant-admin', status: 'active', page: 2 })
    ).resolves.toBe(users);
    await expect(adminClient.listSettings({ category: 'security' })).resolves.toBe(settings);
    await expect(adminClient.updateSetting('theme', 'dark')).resolves.toBe(setting);
    await expect(adminClient.listRoles()).resolves.toBe(roles);
    await expect(adminClient.listAccessRequests({ status: 'pending', page: 1 })).resolves.toBe(
      accessRequests
    );
    await expect(
      adminClient.listProspects({ company: 'STOA', status: 'new', limit: 10 })
    ).resolves.toBe(prospects);
    await expect(
      adminClient.getProspectsMetrics({ date_from: '2026-04-01', date_to: '2026-04-22' })
    ).resolves.toBe(metrics);
    await expect(adminClient.getProspect('inv-1')).resolves.toBe(prospect);
    await expect(adminClient.exportProspectsCSV({ company: 'STOA' })).resolves.toBe(csvBlob);

    expect(mockHttpClient.get).toHaveBeenNthCalledWith(1, '/v1/admin/users', {
      params: { role: 'tenant-admin', status: 'active', page: 2 },
    });
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(2, '/v1/admin/settings', {
      params: { category: 'security' },
    });
    expect(mockHttpClient.put).toHaveBeenCalledWith('/v1/admin/settings/theme', {
      value: 'dark',
    });
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(3, '/v1/admin/roles');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(4, '/v1/admin/access-requests', {
      params: { status: 'pending', page: 1 },
    });
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(5, '/v1/admin/prospects', {
      params: { company: 'STOA', status: 'new', limit: 10 },
    });
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(6, '/v1/admin/prospects/metrics', {
      params: { date_from: '2026-04-01', date_to: '2026-04-22' },
    });
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(7, '/v1/admin/prospects/inv-1');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(8, '/v1/admin/prospects/export', {
      params: { company: 'STOA' },
      responseType: 'blob',
    });
  });

  it('covers gitClient request delegation', async () => {
    const commits = [{ id: 'c1' }];
    const mergeRequests = [{ id: 'mr-1' }];

    mockHttpClient.get.mockResolvedValueOnce({ data: commits }).mockResolvedValueOnce({
      data: mergeRequests,
    });

    await expect(gitClient.listCommits('tenant-1', 'catalog/uac.yaml')).resolves.toBe(commits);
    await expect(gitClient.listMergeRequests('tenant-1')).resolves.toBe(mergeRequests);

    expect(mockHttpClient.get).toHaveBeenNthCalledWith(1, '/v1/tenants/tenant-1/git/commits', {
      params: { path: 'catalog/uac.yaml' },
    });
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(
      2,
      '/v1/tenants/tenant-1/git/merge-requests'
    );
  });

  it('covers sessionClient request delegation', async () => {
    const me = { roles: ['cpi-admin'], permissions: ['stoa:admin'], tenant_id: 'tenant-1' };
    const environments = [{ name: 'prod' }];

    mockHttpClient.get
      .mockResolvedValueOnce({ data: me })
      .mockResolvedValueOnce({ data: { environments } });

    await expect(sessionClient.getMe()).resolves.toBe(me);
    await expect(sessionClient.listEnvironments()).resolves.toBe(environments);

    expect(mockHttpClient.get).toHaveBeenNthCalledWith(1, '/v1/me');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(2, '/v1/environments');
  });

  it('covers toolPermissionsClient request delegation', async () => {
    const permissionList = { items: [] };
    const permission = { id: 'perm-1' };

    mockHttpClient.get.mockResolvedValueOnce({ data: permissionList });
    mockHttpClient.post.mockResolvedValueOnce({ data: permission });
    mockHttpClient.delete.mockResolvedValueOnce({});

    await expect(
      toolPermissionsClient.list('tenant-1', { mcp_server_id: 'srv-1', page: 2 })
    ).resolves.toBe(permissionList);
    await expect(
      toolPermissionsClient.upsert('tenant-1', {
        mcp_server_id: 'srv-1',
        tool_name: 'list_users',
        allowed: true,
      })
    ).resolves.toBe(permission);
    await expect(toolPermissionsClient.remove('tenant-1', 'perm-1')).resolves.toBeUndefined();

    expect(mockHttpClient.get).toHaveBeenCalledWith('/v1/tenants/tenant-1/tool-permissions', {
      params: { mcp_server_id: 'srv-1', page: 2, page_size: 100 },
    });
    expect(mockHttpClient.post).toHaveBeenCalledWith('/v1/tenants/tenant-1/tool-permissions', {
      mcp_server_id: 'srv-1',
      tool_name: 'list_users',
      allowed: true,
    });
    expect(mockHttpClient.delete).toHaveBeenCalledWith(
      '/v1/tenants/tenant-1/tool-permissions/perm-1'
    );
  });

  it('covers workflowsClient request delegation', async () => {
    const templateList = { items: [] };
    const template = { id: 'tpl-1' };
    const workflowList = { items: [] };
    const workflowInstance = { id: 'wf-1' };
    const seeded = { message: 'seeded' };

    mockHttpClient.get
      .mockResolvedValueOnce({ data: templateList })
      .mockResolvedValueOnce({ data: workflowList });
    mockHttpClient.post
      .mockResolvedValueOnce({ data: template })
      .mockResolvedValueOnce({ data: workflowInstance })
      .mockResolvedValueOnce({ data: workflowInstance })
      .mockResolvedValueOnce({ data: workflowInstance })
      .mockResolvedValueOnce({ data: seeded });
    mockHttpClient.put.mockResolvedValueOnce({ data: template });
    mockHttpClient.delete.mockResolvedValueOnce({});

    await expect(workflowsClient.listTemplates('tenant-1')).resolves.toBe(templateList);
    await expect(
      workflowsClient.createTemplate('tenant-1', {
        name: 'Security Review',
        description: 'Gate',
        steps: [],
      })
    ).resolves.toBe(template);
    await expect(
      workflowsClient.updateTemplate('tenant-1', 'tpl-1', {
        name: 'Security Review v2',
      })
    ).resolves.toBe(template);
    await expect(workflowsClient.deleteTemplate('tenant-1', 'tpl-1')).resolves.toBeUndefined();
    await expect(
      workflowsClient.listInstances('tenant-1', { status: 'pending', limit: 20 })
    ).resolves.toBe(workflowList);
    await expect(
      workflowsClient.start('tenant-1', {
        template_id: 'tpl-1',
        subject_id: 'user-1',
        subject_email: 'user@example.com',
      })
    ).resolves.toBe(workflowInstance);
    await expect(workflowsClient.approveStep('tenant-1', 'wf-1', { comment: 'ok' })).resolves.toBe(
      workflowInstance
    );
    await expect(workflowsClient.rejectStep('tenant-1', 'wf-1', { comment: 'nope' })).resolves.toBe(
      workflowInstance
    );
    await expect(workflowsClient.seedTemplates('tenant-1')).resolves.toBe(seeded);

    expect(mockHttpClient.get).toHaveBeenNthCalledWith(
      1,
      '/v1/tenants/tenant-1/workflows/templates'
    );
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      1,
      '/v1/tenants/tenant-1/workflows/templates',
      {
        name: 'Security Review',
        description: 'Gate',
        steps: [],
      }
    );
    expect(mockHttpClient.put).toHaveBeenCalledWith(
      '/v1/tenants/tenant-1/workflows/templates/tpl-1',
      {
        name: 'Security Review v2',
      }
    );
    expect(mockHttpClient.delete).toHaveBeenCalledWith(
      '/v1/tenants/tenant-1/workflows/templates/tpl-1'
    );
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(
      2,
      '/v1/tenants/tenant-1/workflows/instances',
      {
        params: { status: 'pending', limit: 20 },
      }
    );
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      2,
      '/v1/tenants/tenant-1/workflows/instances',
      {
        template_id: 'tpl-1',
        subject_id: 'user-1',
        subject_email: 'user@example.com',
      }
    );
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      3,
      '/v1/tenants/tenant-1/workflows/instances/wf-1/approve',
      { comment: 'ok' }
    );
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      4,
      '/v1/tenants/tenant-1/workflows/instances/wf-1/reject',
      { comment: 'nope' }
    );
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      5,
      '/v1/tenants/tenant-1/workflows/templates/seed'
    );
  });
});
