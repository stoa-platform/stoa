import { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiClient } from './api';
import { apiCatalogService } from './apiCatalog';

vi.mock('./api', () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

function httpError(status: number): AxiosError {
  return new AxiosError(
    `Request failed with status code ${status}`,
    'ERR_BAD_RESPONSE',
    undefined,
    {},
    {
      status,
      statusText: 'error',
      headers: {},
      config: {} as InternalAxiosRequestConfig,
      data: {},
    }
  );
}

function networkError(): AxiosError {
  const error = new AxiosError('Network Error', 'ERR_NETWORK');
  error.request = {};
  return error;
}

describe('apiCatalogService.listAPIs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns a real empty catalog when the server responds with no APIs', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: { apis: [], total: 0, page: 1, page_size: 20 },
    });

    await expect(apiCatalogService.listAPIs()).resolves.toEqual({
      items: [],
      total: 0,
      page: 1,
      pageSize: 20,
      totalPages: 0,
    });
  });

  it('maps a successful catalog page', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data: {
        apis: [
          {
            id: 'api-weather',
            name: 'weather-api',
            display_name: 'Weather API',
            version: '2.0.0',
            description: 'Real-time weather',
            tenant_id: 'oasis-gunters',
            status: 'published',
            is_promoted: true,
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
      },
    });

    const page = await apiCatalogService.listAPIs({ page: 1, pageSize: 20 });

    expect(page.total).toBe(1);
    expect(page.items).toEqual([
      expect.objectContaining({
        id: 'api-weather',
        name: 'weather-api',
        tenantId: 'oasis-gunters',
      }),
    ]);
  });

  it('rejects a 500 instead of resolving an empty catalog', async () => {
    const error = httpError(500);
    vi.mocked(apiClient.get).mockRejectedValueOnce(error);

    await expect(apiCatalogService.listAPIs()).rejects.toBe(error);
  });

  it('rejects a network failure instead of resolving an empty catalog', async () => {
    const error = networkError();
    vi.mocked(apiClient.get).mockRejectedValueOnce(error);

    await expect(apiCatalogService.listAPIs()).rejects.toBe(error);
  });

  it('rejects 401 and 403 so authorization failures stay observable', async () => {
    vi.mocked(apiClient.get).mockRejectedValueOnce(httpError(401));
    await expect(apiCatalogService.listAPIs()).rejects.toMatchObject({
      response: { status: 401 },
    });

    vi.mocked(apiClient.get).mockRejectedValueOnce(httpError(403));
    await expect(apiCatalogService.listAPIs()).rejects.toMatchObject({
      response: { status: 403 },
    });
  });
});
