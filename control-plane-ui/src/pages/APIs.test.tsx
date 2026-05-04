import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createAuthMock } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import type { PersonaRole } from '../test/helpers';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../contexts/EnvironmentContext', () => ({
  useEnvironment: vi.fn(() => ({
    activeEnvironment: 'dev',
    activeConfig: { name: 'dev', label: 'Development', mode: 'full', color: 'green' },
    environments: [
      { name: 'dev', label: 'Development', mode: 'full', color: 'green' },
      { name: 'staging', label: 'Staging', mode: 'full', color: 'amber' },
      { name: 'prod', label: 'Production', mode: 'read-only', color: 'red' },
    ],
    switchEnvironment: vi.fn(),
  })),
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('../services/api', () => ({
  apiService: {
    getTenants: vi.fn().mockResolvedValue([
      {
        id: 'oasis-gunters',
        name: 'oasis-gunters',
        display_name: 'Oasis Gunters',
        status: 'active',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      },
    ]),
    getApis: vi.fn().mockResolvedValue([
      {
        id: 'api-1',
        tenant_id: 'oasis-gunters',
        name: 'payment-api',
        display_name: 'Payment API',
        version: '1.0.0',
        description: 'Handles all payment processing',
        backend_url: 'https://payments.example.com',
        status: 'published',
        deployed_dev: true,
        deployed_staging: false,
        runtime_deployments: [
          {
            environment: 'dev',
            status: 'synced',
            gateway_count: 1,
            synced_count: 1,
            error_count: 0,
            pending_count: 0,
            drifted_count: 0,
            latest_error: null,
            gateway_names: ['stoa-dev'],
          },
          {
            environment: 'staging',
            status: 'error',
            gateway_count: 1,
            synced_count: 0,
            error_count: 1,
            pending_count: 0,
            drifted_count: 0,
            latest_error: 'activation failed',
            gateway_names: ['webmethods-staging'],
          },
        ],
        tags: ['payments'],
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-15T00:00:00Z',
      },
      {
        id: 'api-2',
        tenant_id: 'oasis-gunters',
        name: 'user-api',
        display_name: 'User API',
        version: '2.0.0',
        description: 'User management service',
        backend_url: 'https://users.example.com',
        status: 'draft',
        deployed_dev: false,
        deployed_staging: false,
        tags: ['users'],
        created_at: '2024-01-05T00:00:00Z',
        updated_at: '2024-01-10T00:00:00Z',
      },
    ]),
    getAdminApis: vi.fn().mockResolvedValue([
      {
        id: 'api-1',
        tenant_id: 'oasis-gunters',
        name: 'payment-api',
        display_name: 'Payment API',
        version: '1.0.0',
        description: 'Handles all payment processing',
        backend_url: 'https://payments.example.com',
        status: 'published',
        deployed_dev: true,
        deployed_staging: false,
        runtime_deployments: [
          {
            environment: 'dev',
            status: 'synced',
            gateway_count: 1,
            synced_count: 1,
            error_count: 0,
            pending_count: 0,
            drifted_count: 0,
            latest_error: null,
            gateway_names: ['stoa-dev'],
          },
          {
            environment: 'staging',
            status: 'error',
            gateway_count: 1,
            synced_count: 0,
            error_count: 1,
            pending_count: 0,
            drifted_count: 0,
            latest_error: 'activation failed',
            gateway_names: ['webmethods-staging'],
          },
        ],
        tags: ['payments'],
      },
      {
        id: 'api-2',
        tenant_id: 'oasis-gunters',
        name: 'user-api',
        display_name: 'User API',
        version: '2.0.0',
        description: 'User management service',
        backend_url: 'https://users.example.com',
        status: 'draft',
        deployed_dev: false,
        deployed_staging: false,
        tags: ['users'],
      },
    ]),
    createApi: vi.fn(),
    createLifecycleDraft: vi.fn(),
    updateApi: vi.fn(),
    deleteApi: vi.fn(),
    deployApi: vi.fn(),
  },
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  ToastProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useToast: () => ({ addToast: vi.fn() }),
  useToastActions: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

vi.mock('@stoa/shared/components/CommandPalette', () => ({
  CommandPaletteProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useCommandPalette: () => ({ setOpen: vi.fn(), setItems: vi.fn() }),
}));

vi.mock('@stoa/shared/contexts', () => ({
  ThemeProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useTheme: () => ({ resolvedTheme: 'light', toggleTheme: vi.fn() }),
}));

vi.mock('@stoa/shared/hooks', () => ({
  useSequenceShortcuts: vi.fn(),
}));

vi.mock('@stoa/shared/components/ConfirmDialog', () => ({
  useConfirm: () => [vi.fn().mockResolvedValue(true), () => null],
}));

vi.mock('@stoa/shared/components/EmptyState', () => ({
  EmptyState: ({ title }: { title: string }) => <div>{title}</div>,
}));

vi.mock('@stoa/shared/components/Skeleton', () => ({
  TableSkeleton: () => <div data-testid="table-skeleton" />,
}));

vi.mock('@stoa/shared/components/Celebration', () => ({
  useCelebration: () => ({ celebrate: vi.fn() }),
}));

vi.mock('@stoa/shared/components/Collapsible', () => ({
  Collapsible: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const mockUseEnvironmentMode = vi.fn(() => ({
  canCreate: true,
  canEdit: true,
  canDelete: true,
  canDeploy: true,
  isReadOnly: false,
}));

vi.mock('../hooks/useEnvironmentMode', () => ({
  useEnvironmentMode: () => mockUseEnvironmentMode(),
}));

import { APIs } from './APIs';

const { apiService } = await import('../services/api');

const READ_ONLY_MODE = {
  canCreate: false,
  canEdit: false,
  canDelete: false,
  canDeploy: false,
  isReadOnly: true,
};

function renderAPIs() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <APIs />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('APIs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  afterEach(() => {
    mockUseEnvironmentMode.mockReturnValue({
      canCreate: true,
      canEdit: true,
      canDelete: true,
      canDeploy: true,
      isReadOnly: false,
    });
  });

  it('renders the tenant selector with All tenants for admin', async () => {
    renderAPIs();
    await waitFor(() => {
      expect(screen.getByDisplayValue('All tenants')).toBeInTheDocument();
    });
  });

  it('renders the Create API button', async () => {
    renderAPIs();
    expect(await screen.findByText('Create API')).toBeInTheDocument();
  });

  it('renders the search input label', async () => {
    renderAPIs();
    expect(await screen.findByText('Search')).toBeInTheDocument();
  });

  it('renders API display names from data', async () => {
    renderAPIs();
    expect(await screen.findByText('Payment API')).toBeInTheDocument();
    expect(screen.getByText('User API')).toBeInTheDocument();
  });

  it('renders the tenant selector with first tenant for non-admin', async () => {
    vi.mocked(useAuth).mockReturnValue(createAuthMock('viewer'));
    renderAPIs();
    await waitFor(() => {
      expect(screen.getByDisplayValue('Oasis Gunters')).toBeInTheDocument();
    });
  });

  it('renders status filter dropdown', async () => {
    renderAPIs();
    expect(await screen.findByText('All Status')).toBeInTheDocument();
  });

  it('renders API status badges', async () => {
    renderAPIs();
    expect(await screen.findByText('published')).toBeInTheDocument();
    expect(screen.getByText('draft')).toBeInTheDocument();
  });

  it('renders runtime deployment statuses from GatewayDeployment summaries', async () => {
    renderAPIs();
    expect(await screen.findByText('DEV synced')).toBeInTheDocument();
    expect(screen.getByText('STAGING error')).toBeInTheDocument();
    expect(screen.getByTitle(/activation failed/)).toBeInTheDocument();
  });

  it('renders API backend URLs', async () => {
    renderAPIs();
    expect(await screen.findByText('https://payments.example.com')).toBeInTheDocument();
    expect(screen.getByText('https://users.example.com')).toBeInTheDocument();
  });

  it('hides Create API button in read-only mode', async () => {
    mockUseEnvironmentMode.mockReturnValue(READ_ONLY_MODE);
    renderAPIs();
    await screen.findByText('Payment API');
    expect(screen.queryByText('Create API')).not.toBeInTheDocument();
  });

  it('shows read-only banner in read-only mode', async () => {
    mockUseEnvironmentMode.mockReturnValue(READ_ONLY_MODE);
    renderAPIs();
    expect(await screen.findByText(/Production environment — read-only/)).toBeInTheDocument();
  });

  it('hides Edit and Delete buttons in read-only mode', async () => {
    mockUseEnvironmentMode.mockReturnValue(READ_ONLY_MODE);
    renderAPIs();
    await screen.findByText('Payment API');
    expect(screen.queryByText('Edit')).not.toBeInTheDocument();
    expect(screen.queryByText('Delete')).not.toBeInTheDocument();
  });

  it('links writable users to the lifecycle detail', async () => {
    renderAPIs();
    await screen.findByText('Payment API');
    const lifecycleLinks = screen.getAllByRole('link', { name: 'Open Lifecycle' });
    expect(lifecycleLinks[0]).toHaveAttribute('href', '/apis/oasis-gunters/payment-api');
  });

  it('creates lifecycle drafts through the canonical endpoint', async () => {
    vi.mocked(useAuth).mockReturnValue(createAuthMock('tenant-admin'));
    vi.mocked(apiService.createLifecycleDraft).mockResolvedValue({
      catalog_id: 'api-new',
      tenant_id: 'oasis-gunters',
      api_id: 'payments-api',
      api_name: 'payments-api',
      display_name: 'Payments API',
      version: '1.0.0',
      description: 'Payments',
      backend_url: 'https://payments.internal',
      catalog_status: 'draft',
      lifecycle_phase: 'draft',
      portal_published: false,
      tags: [],
      spec: { source: 'inline', has_openapi_spec: true },
      deployments: [],
      promotions: [],
      last_error: null,
      portal: {
        published: false,
        status: 'not_published',
        publications: [],
        last_result: null,
        last_environment: null,
        last_gateway_instance_id: null,
        last_deployment_id: null,
        last_published_at: null,
      },
    });

    renderAPIs();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Create API' }));
    await user.type(screen.getByTestId('api-form-name'), 'payments-api');
    await user.type(screen.getByTestId('api-form-display-name'), 'Payments API');
    await user.type(screen.getByTestId('api-form-description'), 'Payments');
    await user.type(screen.getByTestId('api-form-backend-url'), 'https://payments.internal');
    fireEvent.change(screen.getByTestId('api-form-openapi-spec'), {
      target: {
        value: JSON.stringify({
          openapi: '3.0.3',
          info: { title: 'Payments API', version: '1.0.0' },
          paths: { '/payments': { get: { responses: { '200': { description: 'ok' } } } } },
        }),
      },
    });
    await user.click(screen.getByRole('button', { name: 'Create lifecycle draft' }));

    await waitFor(() => {
      expect(apiService.createLifecycleDraft).toHaveBeenCalledWith(
        'oasis-gunters',
        expect.objectContaining({
          name: 'payments-api',
          display_name: 'Payments API',
          backend_url: 'https://payments.internal',
          tags: [],
          spec_reference: null,
        })
      );
    });
  });

  it('does not expose legacy deployment workflow links in read-only mode', async () => {
    mockUseEnvironmentMode.mockReturnValue(READ_ONLY_MODE);
    renderAPIs();
    await screen.findByText('Payment API');
    expect(screen.queryByText('Deploy DEV')).not.toBeInTheDocument();
    expect(screen.queryByText('Deploy STG')).not.toBeInTheDocument();
    expect(screen.queryByText('Open Deployments')).not.toBeInTheDocument();
  });

  it('removes legacy portal tags before legacy create/update submits', async () => {
    vi.mocked(useAuth).mockReturnValue(createAuthMock('tenant-admin'));
    renderAPIs();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Create API' }));
    await user.click(screen.getByRole('button', { name: 'Manual Entry' }));
    await user.type(screen.getByTestId('api-form-name'), 'manual-api');
    await user.type(screen.getByTestId('api-form-display-name'), 'Manual API');
    await user.type(screen.getByTestId('api-form-backend-url'), 'https://manual.internal');
    const submitButtons = screen.getAllByRole('button', { name: 'Create API' });
    await user.click(submitButtons[submitButtons.length - 1]);

    await waitFor(() => {
      expect(apiService.createApi).toHaveBeenCalledWith(
        'oasis-gunters',
        expect.objectContaining({
          tags: [],
          portal_promoted: false,
        })
      );
    });
  });

  it('keeps existing deployment route href out of the API list', async () => {
    renderAPIs();
    await screen.findByText('Payment API');
    const links = screen.getAllByRole('link', { name: 'Open Lifecycle' });
    expect(links[0]).not.toHaveAttribute(
      'href',
      '/api-deployments?api_id=api-1&api_name=payment-api&environment=dev&open_deploy=true&tenant_id=oasis-gunters'
    );
  });

  // 4-persona coverage
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderAPIs();
        const expectedValue = role === 'cpi-admin' ? 'All tenants' : 'Oasis Gunters';
        await waitFor(() => {
          expect(screen.getByDisplayValue(expectedValue)).toBeInTheDocument();
        });
      });
    }
  );

  // CAB-1673: Structural snapshot guards
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    'snapshot: %s persona',
    (role) => {
      it('matches structural snapshot', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        const { container } = renderAPIs();
        await screen.findByText('Payment API');
        const buttons = [...container.querySelectorAll('button')].map(
          (b) => b.textContent?.trim() || ''
        );
        const headings = [...container.querySelectorAll('h1, h2, h3')].map(
          (h) => h.textContent?.trim() || ''
        );
        const links = [...container.querySelectorAll('a[href]')].map((a) => ({
          text: a.textContent?.trim() || '',
          href: a.getAttribute('href'),
        }));
        expect({ buttons, headings, links }).toMatchSnapshot();
      });
    }
  );
});
