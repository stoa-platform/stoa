import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { createAuthMock, renderWithProviders } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

const mockGetGatewayAggregatedMetrics = vi.fn().mockResolvedValue({
  guardrails: { pii_detections: 5, injection_blocks: 2, content_filters: 0, prompt_guard_flags: 1 },
  rate_limiting: { enforcements: 12 },
});

const mockGetGuardrailsEvents = vi.fn().mockResolvedValue({ events: [] });

vi.mock('../../services/api', () => ({
  apiService: {
    getGatewayAggregatedMetrics: (...args: unknown[]) => mockGetGatewayAggregatedMetrics(...args),
    getGuardrailsEvents: (...args: unknown[]) => mockGetGuardrailsEvents(...args),
    setAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
  },
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

import { GuardrailsDashboard } from './GuardrailsDashboard';

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

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
    mockGetGuardrailsEvents.mockResolvedValue({ events: [] });
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders the heading', async () => {
    renderWithProviders(<GuardrailsDashboard />);
    expect(
      await screen.findByRole('heading', { name: /Security & Guardrails/i })
    ).toBeInTheDocument();
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

  it('does not render Rate Limit as a misleading all-filter button', async () => {
    renderWithProviders(<GuardrailsDashboard />);
    const rateLimit = await screen.findByText('Rate Limit');
    expect(rateLimit.closest('button')).toBeNull();
  });

  it('routes guardrail event traces through the canonical Live Calls detail path', async () => {
    mockGetGuardrailsEvents.mockResolvedValue({
      events: [
        {
          timestamp: '2026-05-07T10:00:00Z',
          trace_id: 'trace-123',
          span_id: 'span-123',
          tool: 'payment-api',
          action: 'pii-redacted',
          reason: 'Sensitive payload redacted',
        },
      ],
    });

    render(
      <MemoryRouter initialEntries={['/observability/security']}>
        <Routes>
          <Route path="/observability/security" element={<GuardrailsDashboard />} />
          <Route path="/observability/live-calls/trace/:traceId" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    );

    const toolCell = await screen.findByText('payment-api');
    const eventRow = toolCell.closest('button');
    expect(eventRow).not.toBeNull();
    fireEvent.click(eventRow as HTMLButtonElement);

    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent(
        '/observability/live-calls/trace/trace-123'
      );
    });
  });

  it('renders configuration section', async () => {
    renderWithProviders(<GuardrailsDashboard />);
    expect(await screen.findByText('Guardrail Configuration')).toBeInTheDocument();
  });

  it('P1-1: metrics render when events endpoint fails (allSettled)', async () => {
    // Regression: Promise.all would have discarded the fulfilled metrics
    // slice the moment the auxiliary events endpoint threw. allSettled
    // preserves metrics + error is not set for a partial failure.
    mockGetGuardrailsEvents.mockRejectedValue(new Error('Events endpoint 500'));
    renderWithProviders(<GuardrailsDashboard />);
    expect(
      await screen.findByRole('heading', { name: /Security & Guardrails/i })
    ).toBeInTheDocument();
    // Metric cards still render with non-zero PII detection value from the
    // fulfilled metrics slice.
    const pii = await screen.findAllByText('PII Detection');
    expect(pii.length).toBeGreaterThanOrEqual(1);
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderWithProviders(<GuardrailsDashboard />);
        expect(
          await screen.findByRole('heading', { name: /Security & Guardrails/i })
        ).toBeInTheDocument();
      });
    }
  );
});
