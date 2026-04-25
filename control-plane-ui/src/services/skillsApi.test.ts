import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockApiService } = vi.hoisted(() => ({
  mockApiService: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('./api', () => ({
  apiService: mockApiService,
}));

import { skillsService } from './skillsApi';

describe('skillsApi.deleteSkill (P1-4 — REST path migration)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('uses REST path /v1/gateway/admin/skills/:key (not deprecated ?key=X)', async () => {
    mockApiService.delete.mockResolvedValueOnce({ data: null });

    await skillsService.deleteSkill('my-skill');

    expect(mockApiService.delete).toHaveBeenCalledTimes(1);
    expect(mockApiService.delete).toHaveBeenCalledWith('/v1/gateway/admin/skills/my-skill');
    // Explicit negative assertion: the deprecated query form must be gone.
    const calledUrl = mockApiService.delete.mock.calls[0][0] as string;
    expect(calledUrl).not.toContain('?key=');
  });

  it('URL-encodes keys with special characters (regression against path injection)', async () => {
    mockApiService.delete.mockResolvedValueOnce({ data: null });

    await skillsService.deleteSkill('weird key/with#chars?');

    expect(mockApiService.delete).toHaveBeenCalledWith(
      '/v1/gateway/admin/skills/weird%20key%2Fwith%23chars%3F'
    );
  });
});
