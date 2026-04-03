/**
 * EU API Catalog Discovery Service (CAB-1639)
 *
 * Client for the Control Plane API discovery endpoints.
 * GET /v1/discovery/catalog — curated EU public API catalog
 */

import { apiService } from './api';
import type { CatalogResponse } from '../types';

interface CatalogParams {
  category?: string;
  country?: string;
  protocol?: string;
  status?: string;
}

class DiscoveryService {
  async getCatalog(params?: CatalogParams): Promise<CatalogResponse> {
    const { data } = await apiService.get('/v1/discovery/catalog', { params });
    return data;
  }
}

export const discoveryService = new DiscoveryService();
