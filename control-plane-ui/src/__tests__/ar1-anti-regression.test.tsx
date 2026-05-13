import { describe, expect, it, beforeEach, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { useAuth } from '../contexts/AuthContext';
import { createAuthMock, renderWithProviders } from '../test/helpers';
import type { AggregatedMetrics } from '../types';
import { SecurityPostureDashboard } from '../pages/SecurityPosture/SecurityPostureDashboard';
import { GuardrailsDashboard } from '../pages/GatewayGuardrails/GuardrailsDashboard';

vi.mock('../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

const mockGet = vi.fn();
const mockGetGatewayAggregatedMetrics = vi.fn();
const mockGetGuardrailsConfig = vi.fn();
const mockGetGuardrailsEvents = vi.fn();

vi.mock('../services/api', () => ({
  apiService: {
    get: (...args: unknown[]) => mockGet(...args),
    getGatewayAggregatedMetrics: (...args: unknown[]) => mockGetGatewayAggregatedMetrics(...args),
    getGuardrailsConfig: (...args: unknown[]) => mockGetGuardrailsConfig(...args),
    getGuardrailsEvents: (...args: unknown[]) => mockGetGuardrailsEvents(...args),
    setAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
  },
}));

const guardrailsMetrics = {
  health: {},
  sync: {},
  overall_status: 'healthy',
  guardrails: {
    state: 'metrics_unavailable',
    source_healthy: false,
    by_guardrail: {},
    last_sample_at: null,
    metrics_age_seconds: null,
  },
} as unknown as AggregatedMetrics;

describe('AR-1 anti-regression page copy', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/token-binding')) {
        return Promise.resolve({ data: { label: 'Auto', description: 'Migration mode' } });
      }
      if (url.includes('/governance/drift')) return Promise.resolve({ data: { items: [] } });
      if (url.includes('/scans')) return Promise.resolve({ data: { scans: [] } });
      if (url.includes('/findings')) return Promise.resolve({ data: { findings: [] } });
      return Promise.resolve({ data: { events: [], summary: {} } });
    });
    mockGetGatewayAggregatedMetrics.mockResolvedValue(guardrailsMetrics);
    mockGetGuardrailsConfig.mockResolvedValue({
      pii_enabled: true,
      injection_detection_enabled: true,
      prompt_guard_enabled: true,
      content_filter_enabled: true,
      rate_limit_enabled: true,
      opa_policy_enabled: true,
      source: 'env',
      updated_at: '2026-05-11T00:00:00Z',
    });
    mockGetGuardrailsEvents.mockResolvedValue({ events: [], total: 0 });
  });

  it('locks Security Posture title and subtitle', async () => {
    renderWithProviders(<SecurityPostureDashboard />, { route: '/security-posture' });

    expect(screen.getByRole('heading', { level: 1, name: 'Security Posture' })).toBeInTheDocument();
    expect(
      screen.getByText('Compliance findings, security score, configuration assessment')
    ).toBeInTheDocument();
    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(5));
  });

  it('locks Security & Guardrails title and subtitle', async () => {
    renderWithProviders(<GuardrailsDashboard />, { route: '/observability/security' });

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Security & Guardrails' })
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'Runtime events — guardrail decisions, PII/prompt/content/rate-limit monitoring'
      )
    ).toBeInTheDocument();
  });
});
