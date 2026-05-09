import { describe, expect, it, beforeEach, vi } from 'vitest';
import { screen } from '@testing-library/react';
import i18n from 'i18next';
import type { ReactElement } from 'react';
import { createAuthMock, renderWithProviders } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import { useBreadcrumbs } from '../../hooks/useBreadcrumbs';
import { AuditLog } from '../../pages/AuditLog';
import { CallFlowDashboard } from '../../pages/CallFlow/CallFlowDashboard';
import { GuardrailsDashboard } from '../../pages/GatewayGuardrails/GuardrailsDashboard';

const mocks = vi.hoisted(() => ({
  getTransactions: vi.fn(),
  getGatewayAggregatedMetrics: vi.fn(),
  getGuardrailsConfig: vi.fn(),
  getGuardrailsEvents: vi.fn(),
  get: vi.fn(),
  refetch: vi.fn(),
}));

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('../../hooks/usePrometheus', () => ({
  usePrometheusQuery: vi.fn(() => ({
    data: null,
    loading: false,
    error: null,
    refetch: mocks.refetch,
  })),
  usePrometheusRange: vi.fn(() => ({
    data: [],
    loading: false,
    error: null,
    refetch: mocks.refetch,
  })),
  scalarValue: vi.fn(() => null),
  groupByLabel: vi.fn(() => ({})),
}));

vi.mock('../../services/api', () => ({
  apiService: {
    getTransactions: mocks.getTransactions,
    getGatewayAggregatedMetrics: mocks.getGatewayAggregatedMetrics,
    getGuardrailsConfig: mocks.getGuardrailsConfig,
    getGuardrailsEvents: mocks.getGuardrailsEvents,
    get: mocks.get,
  },
}));

function BreadcrumbLastLabel() {
  const breadcrumbs = useBreadcrumbs();
  return <span data-testid="breadcrumb-last">{breadcrumbs.at(-1)?.label}</span>;
}

function renderAuditedPage(route: string, page: ReactElement) {
  return renderWithProviders(
    <>
      <BreadcrumbLastLabel />
      {page}
    </>,
    { route }
  );
}

const guardrailsConfig = {
  pii_enabled: true,
  injection_detection_enabled: true,
  prompt_guard_enabled: true,
  content_filter_enabled: true,
  rate_limit_enabled: true,
  opa_policy_enabled: true,
  source: 'env',
  updated_at: '2026-05-09T00:00:00.000Z',
};

const guardrailsMetrics = {
  health: {
    total_gateways: 1,
    online: 1,
    offline: 0,
    degraded: 0,
    maintenance: 0,
    health_percentage: 100,
  },
  sync: {
    total_deployments: 1,
    synced: 1,
    pending: 0,
    syncing: 0,
    drifted: 0,
    error: 0,
    deleting: 0,
    sync_percentage: 100,
  },
  overall_status: 'healthy',
  guardrails: {
    pii_detections: 0,
    injection_blocks: 0,
    prompt_guard_blocks: 0,
    content_filter_blocks: 0,
    rate_limit_blocks: 0,
    last_sample_at: '2026-05-09T00:00:00.000Z',
    metrics_age_seconds: 10,
    source_healthy: true,
  },
};

const auditStatsWindow = {
  window_start: '2026-05-09T00:00:00.000Z',
  window_end: '2026-05-09T01:00:00.000Z',
};

function mockAuditResponse(url: unknown) {
  const path = String(url);

  if (path.endsWith('/stats')) {
    return Promise.resolve({
      data: {
        total_events: 0,
        success_count: 0,
        failed_count: 0,
        unique_actors: 0,
        by_action: {},
        by_status: {},
        ...auditStatsWindow,
      },
    });
  }

  if (path.endsWith('/actions')) {
    return Promise.resolve({ data: { actions: [], ...auditStatsWindow } });
  }

  return Promise.resolve({
    data: {
      entries: [],
      total: 0,
      page: 1,
      page_size: 20,
      has_more: false,
    },
  });
}

describe('regression/observability-titles', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    localStorage.clear();
    await i18n.changeLanguage('en');

    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mocks.getTransactions.mockResolvedValue({ transactions: [] });
    mocks.getGuardrailsConfig.mockResolvedValue(guardrailsConfig);
    mocks.getGatewayAggregatedMetrics.mockResolvedValue(guardrailsMetrics);
    mocks.getGuardrailsEvents.mockResolvedValue({ events: [], total: 0 });
    mocks.get.mockImplementation(mockAuditResponse);
  });

  it.each([
    {
      route: '/observability/live-calls',
      heading: 'Live Calls',
      page: <CallFlowDashboard />,
    },
    {
      route: '/audit-log',
      heading: 'Audit Log',
      page: <AuditLog />,
    },
    {
      route: '/observability/security',
      heading: 'Security & Guardrails',
      page: <GuardrailsDashboard />,
    },
  ])('keeps $route h1 aligned with its breadcrumb label', async ({ route, heading, page }) => {
    renderAuditedPage(route, page);

    const h1 = await screen.findByRole('heading', { level: 1, name: heading });
    expect(screen.getByTestId('breadcrumb-last')).toHaveTextContent(heading);
    expect(h1).toHaveTextContent(screen.getByTestId('breadcrumb-last').textContent ?? '');
  });
});
