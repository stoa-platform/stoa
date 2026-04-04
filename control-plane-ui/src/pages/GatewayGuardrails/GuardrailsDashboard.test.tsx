import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { createAuthMock, renderWithProviders } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

const mockGetGatewayAggregatedMetrics = vi.fn().mockResolvedValue({
  guardrails: { pii_detections: 5, injection_blocks: 2, content_filters: 0, prompt_guard_flags: 1 },
  rate_limiting: { enforcements: 12 },
});

vi.mock('../../services/api', () => ({
  apiService: {
    getGatewayAggregatedMetrics: (...args: unknown[]) => mockGetGatewayAggregatedMetrics(...args),
    setAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
  },
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

import { GuardrailsDashboard } from './GuardrailsDashboard';

describe('GuardrailsDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetGatewayAggregatedMetrics.mockResolvedValue({
      guardrails: {
        pii_detections: 5,
        injection_blocks: 2,
        content_filters: 0,
        prompt_guard_flags: 1,
      },
      rate_limiting: { enforcements: 12 },
    });
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders the heading', async () => {
    renderWithProviders(<GuardrailsDashboard />);
    expect(await screen.findByRole('heading', { name: /Gateway Guardrails/i })).toBeInTheDocument();
  });

  it('renders guardrail cards', async () => {
    renderWithProviders(<GuardrailsDashboard />);
    // Cards render titles that also appear in config section — use getAllByText
    const piiElements = await screen.findAllByText('PII Detection');
    expect(piiElements.length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Injection/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Prompt Guard/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Rate Limit')).toBeInTheDocument();
  });

  it('renders configuration section', async () => {
    renderWithProviders(<GuardrailsDashboard />);
    expect(await screen.findByText('Guardrail Configuration')).toBeInTheDocument();
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderWithProviders(<GuardrailsDashboard />);
        expect(
          await screen.findByRole('heading', { name: /Gateway Guardrails/i })
        ).toBeInTheDocument();
      });
    }
  );
});
