import { describe, it, expect, vi, beforeEach } from 'vitest';
import { errorSnapshotsService } from './errorSnapshotsApi';
import { apiService } from './api';

vi.mock('./api', () => ({
  apiService: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockGet = vi.mocked(apiService.get);
const mockPost = vi.mocked(apiService.post);
const mockPatch = vi.mocked(apiService.patch);
const mockDelete = vi.mocked(apiService.delete);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ErrorSnapshotsService', () => {
  describe('getSnapshots', () => {
    it('calls with default pagination', async () => {
      mockGet.mockResolvedValue({ data: { items: [], total: 0 } } as any);
      await errorSnapshotsService.getSnapshots();
      expect(mockGet).toHaveBeenCalledWith('/v1/snapshots?page=1&page_size=20');
    });

    it('passes all filter params', async () => {
      mockGet.mockResolvedValue({ data: { items: [] } } as any);
      await errorSnapshotsService.getSnapshots(
        {
          trigger: 'rate_limit',
          status_code: 429,
          source: 'gateway',
          resolution_status: 'open',
          start_date: '2026-01-01',
          end_date: '2026-02-01',
          path_contains: '/api/v1',
        },
        2,
        10
      );
      const url = mockGet.mock.calls[0][0] as string;
      expect(url).toContain('page=2');
      expect(url).toContain('page_size=10');
      expect(url).toContain('trigger=rate_limit');
      expect(url).toContain('status_code=429');
      expect(url).toContain('source=gateway');
      expect(url).toContain('resolution_status=open');
      expect(url).toContain('start_date=2026-01-01');
      expect(url).toContain('end_date=2026-02-01');
      expect(url).toContain('path_contains=%2Fapi%2Fv1');
    });

    it('skips undefined filter values', async () => {
      mockGet.mockResolvedValue({ data: { items: [] } } as any);
      await errorSnapshotsService.getSnapshots({ trigger: 'timeout' });
      const url = mockGet.mock.calls[0][0] as string;
      expect(url).toContain('trigger=timeout');
      expect(url).not.toContain('status_code');
      expect(url).not.toContain('source');
    });
  });

  describe('getSnapshot', () => {
    it('calls correct endpoint', async () => {
      mockGet.mockResolvedValue({ data: { id: 'snap1' } } as any);
      const result = await errorSnapshotsService.getSnapshot('snap1');
      expect(mockGet).toHaveBeenCalledWith('/v1/snapshots/snap1');
      expect(result).toEqual({ id: 'snap1' });
    });
  });

  describe('getStats', () => {
    it('calls without date params', async () => {
      mockGet.mockResolvedValue({ data: { total: 100 } } as any);
      await errorSnapshotsService.getStats();
      expect(mockGet).toHaveBeenCalledWith('/v1/snapshots/stats');
    });

    it('calls with date params', async () => {
      mockGet.mockResolvedValue({ data: { total: 50 } } as any);
      await errorSnapshotsService.getStats('2026-01-01', '2026-02-01');
      const url = mockGet.mock.calls[0][0] as string;
      expect(url).toContain('start_date=2026-01-01');
      expect(url).toContain('end_date=2026-02-01');
    });
  });

  describe('getFilters', () => {
    it('calls correct endpoint', async () => {
      const filters = { triggers: ['rate_limit'], sources: ['gateway'] };
      mockGet.mockResolvedValue({ data: filters } as any);
      const result = await errorSnapshotsService.getFilters();
      expect(mockGet).toHaveBeenCalledWith('/v1/snapshots/filters');
      expect(result).toEqual(filters);
    });
  });

  describe('updateResolution', () => {
    it('patches with status and notes', async () => {
      mockPatch.mockResolvedValue({ data: { id: 'snap1', resolution_status: 'resolved' } } as any);
      const result = await errorSnapshotsService.updateResolution(
        'snap1',
        'resolved' as any,
        'Fixed in PR #123'
      );
      expect(mockPatch).toHaveBeenCalledWith('/v1/snapshots/snap1', {
        resolution_status: 'resolved',
        resolution_notes: 'Fixed in PR #123',
      });
      expect(result).toEqual({ id: 'snap1', resolution_status: 'resolved' });
    });

    it('patches without notes', async () => {
      mockPatch.mockResolvedValue({ data: { id: 'snap1' } } as any);
      await errorSnapshotsService.updateResolution('snap1', 'acknowledged' as any);
      expect(mockPatch).toHaveBeenCalledWith('/v1/snapshots/snap1', {
        resolution_status: 'acknowledged',
        resolution_notes: undefined,
      });
    });
  });

  describe('deleteSnapshot', () => {
    it('deletes correct endpoint', async () => {
      mockDelete.mockResolvedValue({ data: null } as any);
      await errorSnapshotsService.deleteSnapshot('snap1');
      expect(mockDelete).toHaveBeenCalledWith('/v1/snapshots/snap1');
    });
  });

  describe('generateReplay', () => {
    it('posts to correct endpoint', async () => {
      mockPost.mockResolvedValue({
        data: { curl_command: 'curl -X GET http://...', warning: 'uses prod' },
      } as any);
      const result = await errorSnapshotsService.generateReplay('snap1');
      expect(mockPost).toHaveBeenCalledWith('/v1/snapshots/snap1/replay');
      expect(result).toEqual({ curl_command: 'curl -X GET http://...', warning: 'uses prod' });
    });
  });
});
