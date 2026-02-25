import { describe, it, expect, vi } from 'vitest';
import { runDiagnostic, checkConnectivity, getDiagnosticHistory } from './diagnosticService';
import { apiService } from './api';

vi.mock('./api', () => ({
  apiService: {
    get: vi.fn(),
  },
}));

const mockReport = {
  id: 'diag-1',
  timestamp: '2026-02-15T10:00:00Z',
  tenant_id: 'tenant-1',
  gateway_id: 'gw-1',
  root_causes: [],
  timing: null,
  network_path: null,
  redacted: false,
};

const mockConnectivity = {
  overall_status: 'healthy',
  stages: [{ name: 'dns', status: 'ok', latency_ms: 5, detail: null }],
  network_path: null,
  checked_at: '2026-02-15T10:00:00Z',
};

describe('diagnosticService', () => {
  it('runDiagnostic calls the correct endpoint', async () => {
    vi.mocked(apiService.get).mockResolvedValue({ data: mockReport });
    const result = await runDiagnostic('gw-1');
    expect(apiService.get).toHaveBeenCalledWith('/v1/admin/diagnostics/gw-1');
    expect(result).toEqual(mockReport);
  });

  it('checkConnectivity calls the correct endpoint', async () => {
    vi.mocked(apiService.get).mockResolvedValue({ data: mockConnectivity });
    const result = await checkConnectivity('gw-1');
    expect(apiService.get).toHaveBeenCalledWith('/v1/admin/diagnostics/gw-1/connectivity');
    expect(result).toEqual(mockConnectivity);
  });

  it('getDiagnosticHistory calls the correct endpoint with default limit', async () => {
    vi.mocked(apiService.get).mockResolvedValue({ data: [mockReport] });
    const result = await getDiagnosticHistory('gw-1');
    expect(apiService.get).toHaveBeenCalledWith('/v1/admin/diagnostics/gw-1/history', {
      params: { limit: 20 },
    });
    expect(result).toEqual([mockReport]);
  });

  it('getDiagnosticHistory accepts custom limit', async () => {
    vi.mocked(apiService.get).mockResolvedValue({ data: [] });
    await getDiagnosticHistory('gw-1', 5);
    expect(apiService.get).toHaveBeenCalledWith('/v1/admin/diagnostics/gw-1/history', {
      params: { limit: 5 },
    });
  });
});
