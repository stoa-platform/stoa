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

vi.mock('../../../services/http', async () => {
  const actual =
    await vi.importActual<typeof import('../../../services/http')>('../../../services/http');
  return { ...actual, httpClient: mockHttpClient };
});

import { apisClient } from '../../../services/api/apis';
import { applicationsClient } from '../../../services/api/applications';
import { consumersClient } from '../../../services/api/consumers';

describe('List shape guard (P1-8 — extractList replaces silent fallback)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('apisClient.list', () => {
    it('returns items from a paginated envelope', async () => {
      mockHttpClient.get.mockResolvedValueOnce({
        data: { items: [{ id: 'api-1' }], total: 1 },
      });
      await expect(apisClient.list('tenant-1')).resolves.toEqual([{ id: 'api-1' }]);
    });

    it('returns a bare array as-is', async () => {
      mockHttpClient.get.mockResolvedValueOnce({ data: [{ id: 'api-1' }] });
      await expect(apisClient.list('tenant-1')).resolves.toEqual([{ id: 'api-1' }]);
    });

    it('throws a labeled error on unexpected shape (fail fast, not silent cast)', async () => {
      // Backend drift: envelope without items → previously the `?? data`
      // fallback cast the whole envelope as `API[]`, leaking downstream.
      mockHttpClient.get.mockResolvedValueOnce({ data: { total: 5, page: 1 } });
      await expect(apisClient.list('tenant-1')).rejects.toThrowError(/apis response shape/);
    });
  });

  describe('applicationsClient.list', () => {
    it('throws on unexpected shape', async () => {
      mockHttpClient.get.mockResolvedValueOnce({ data: { page: 1 } });
      await expect(applicationsClient.list('tenant-1')).rejects.toThrowError(
        /applications response shape/
      );
    });
  });

  describe('consumersClient.list', () => {
    it('throws on unexpected shape', async () => {
      mockHttpClient.get.mockResolvedValueOnce({ data: { page: 1 } });
      await expect(consumersClient.list('tenant-1')).rejects.toThrowError(
        /consumers response shape/
      );
    });
  });
});
