import { describe, it, expect, vi, beforeEach } from 'vitest';
import { skillsService } from './skillsApi';

vi.mock('./api', () => ({
  apiService: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

import { apiService } from './api';

const mockSkill = {
  key: 'test-skill',
  name: 'Test Skill',
  description: 'A test skill',
  tenant_id: 'tenant-1',
  scope: 'tenant',
  priority: 100,
  instructions: 'Do something',
  tool_ref: null,
  user_ref: null,
  enabled: true,
};

describe('skillsService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('listSkills calls GET /v1/gateway/admin/skills', async () => {
    vi.mocked(apiService.get).mockResolvedValue({ data: [mockSkill] });
    const result = await skillsService.listSkills();
    expect(apiService.get).toHaveBeenCalledWith('/v1/gateway/admin/skills');
    expect(result).toEqual([mockSkill]);
  });

  it('upsertSkill calls POST /v1/gateway/admin/skills', async () => {
    const payload = { key: 'new-skill', name: 'New', tenant_id: 't1', scope: 'global' };
    vi.mocked(apiService.post).mockResolvedValue({ data: { key: 'new-skill' } });
    const result = await skillsService.upsertSkill(payload);
    expect(apiService.post).toHaveBeenCalledWith('/v1/gateway/admin/skills', payload);
    expect(result).toEqual({ key: 'new-skill' });
  });

  it('deleteSkill calls DELETE with encoded key', async () => {
    vi.mocked(apiService.delete).mockResolvedValue({});
    await skillsService.deleteSkill('my-skill');
    expect(apiService.delete).toHaveBeenCalledWith('/v1/gateway/admin/skills?key=my-skill');
  });

  it('deleteSkill encodes special characters', async () => {
    vi.mocked(apiService.delete).mockResolvedValue({});
    await skillsService.deleteSkill('my skill/test');
    expect(apiService.delete).toHaveBeenCalledWith(
      '/v1/gateway/admin/skills?key=my%20skill%2Ftest'
    );
  });

  it('resolveSkills calls GET with tenant_id only', async () => {
    vi.mocked(apiService.get).mockResolvedValue({ data: [] });
    const result = await skillsService.resolveSkills('tenant-1');
    expect(apiService.get).toHaveBeenCalledWith(
      '/v1/gateway/admin/skills/resolve?tenant_id=tenant-1'
    );
    expect(result).toEqual([]);
  });

  it('resolveSkills includes tool_ref and user_ref', async () => {
    const resolved = [
      { name: 'S1', scope: 'tool', priority: 100, instructions: 'X', specificity: 2 },
    ];
    vi.mocked(apiService.get).mockResolvedValue({ data: resolved });
    const result = await skillsService.resolveSkills('t1', 'tool-ref', 'user-ref');
    expect(apiService.get).toHaveBeenCalledWith(
      '/v1/gateway/admin/skills/resolve?tenant_id=t1&tool_ref=tool-ref&user_ref=user-ref'
    );
    expect(result).toEqual(resolved);
  });

  it('resolveSkills with only tool_ref', async () => {
    vi.mocked(apiService.get).mockResolvedValue({ data: [] });
    await skillsService.resolveSkills('t1', 'tool-ref');
    expect(apiService.get).toHaveBeenCalledWith(
      '/v1/gateway/admin/skills/resolve?tenant_id=t1&tool_ref=tool-ref'
    );
  });
});
