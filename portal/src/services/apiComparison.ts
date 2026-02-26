/**
 * API Comparison Service (CAB-1470)
 */

import { apiClient } from './api';
import type { APIComparisonResult } from '../types';

async function compareAPIs(apiIds: string[]): Promise<APIComparisonResult> {
  try {
    const response = await apiClient.post<APIComparisonResult>('/v1/portal/apis/compare', {
      api_ids: apiIds,
    });
    return response.data;
  } catch {
    console.warn('API comparison endpoint not available, using fallback');
    return {
      api_ids: apiIds,
      api_names: {},
      fields: [],
    };
  }
}

export const apiComparisonService = {
  compareAPIs,
};
