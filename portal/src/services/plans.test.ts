import { describe, expect, it, vi, beforeEach } from 'vitest';
import { plansService } from './plans';
import { apiClient } from './api';

vi.mock('./api', () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

describe('plansService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('lists plans through the read-only Portal provider endpoint', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        items: [],
        total: 0,
        page: 1,
        page_size: 50,
        total_pages: 1,
      },
    });

    await plansService.list('acme', { status: 'active' });

    expect(apiClient.get).toHaveBeenCalledWith('/v1/portal/plans/acme', {
      params: {
        page: 1,
        page_size: 50,
        status: 'active',
      },
    });
  });
});
