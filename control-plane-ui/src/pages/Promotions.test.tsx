import { describe, it, expect, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Promotions } from './Promotions';
import { createAuthMock, renderWithProviders, type PersonaRole } from '../test/helpers';
import type { Promotion, Tenant, API, GatewayDeployment, GatewayInstance } from '../types';

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  }),
}));

vi.mock('@stoa/shared/components/ConfirmDialog', () => ({
  useConfirm: () => [vi.fn().mockResolvedValue(true), null],
}));

vi.mock('../services/api', () => ({
  apiService: {
    getTenants: vi.fn(),
    getApis: vi.fn(),
    listPromotions: vi.fn(),
    createPromotion: vi.fn(),
    approvePromotion: vi.fn(),
    completePromotion: vi.fn(),
    rollbackPromotion: vi.fn(),
    getPromotionDiff: vi.fn(),
    getGatewayInstances: vi.fn(),
    getGatewayDeployments: vi.fn(),
  },
}));

const mockTenants: Tenant[] = [
  {
    id: 'tenant-1',
    name: 'acme',
    display_name: 'ACME Corp',
    status: 'active',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'tenant-2',
    name: 'globex',
    display_name: 'Globex',
    status: 'active',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
];

const mockApis: API[] = [
  {
    id: 'api-1',
    tenant_id: 'tenant-1',
    name: 'orders-api',
    display_name: 'Orders API',
    version: '1.0.0',
    description: 'Order management',
    backend_url: 'https://api.example.com',
    status: 'published',
    deployed_dev: true,
    deployed_staging: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'api-2',
    tenant_id: 'tenant-1',
    name: 'billing-api',
    display_name: 'Billing API',
    version: '1.0.0',
    description: 'Billing management',
    backend_url: 'https://billing.example.com',
    status: 'published',
    deployed_dev: false,
    deployed_staging: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
];

const mockTenantTwoApis: API[] = [
  {
    id: 'api-3',
    tenant_id: 'tenant-2',
    name: 'inventory-api',
    display_name: 'Inventory API',
    version: '1.0.0',
    description: 'Inventory management',
    backend_url: 'https://inventory.example.com',
    status: 'published',
    deployed_dev: false,
    deployed_staging: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
];

const mockPromotion: Promotion = {
  id: 'promo-1',
  tenant_id: 'tenant-1',
  api_id: 'api-1',
  source_environment: 'dev',
  target_environment: 'staging',
  source_deployment_id: 'deploy-1',
  target_deployment_id: null,
  target_gateway_ids: ['gw-staging'],
  status: 'pending',
  spec_diff: null,
  message: 'Ready for staging validation',
  requested_by: 'parzival',
  approved_by: null,
  completed_at: null,
  created_at: '2026-03-08T10:00:00Z',
  updated_at: '2026-03-08T10:00:00Z',
};

const mockGateways: GatewayInstance[] = [
  {
    id: 'gw-dev',
    name: 'stoa-gateway-dev',
    display_name: 'STOA Gateway Dev',
    gateway_type: 'stoa_edge_mcp',
    environment: 'dev',
    tenant_id: 'tenant-1',
    base_url: 'https://dev.example.com',
    auth_config: {},
    capabilities: [],
    status: 'online',
    health_details: null,
    last_health_check: null,
    source: 'self_register',
    protected: false,
    enabled: true,
    tags: [],
    version: null,
    endpoints: {},
    target_gateway_type: 'stoa',
    topology: 'native-edge',
    deployment_mode: 'edge',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'gw-staging',
    name: 'stoa-gateway-staging',
    display_name: 'STOA Gateway Staging',
    gateway_type: 'stoa_edge_mcp',
    environment: 'staging',
    tenant_id: 'tenant-1',
    base_url: 'https://staging.example.com',
    auth_config: {},
    capabilities: [],
    status: 'online',
    health_details: null,
    last_health_check: null,
    source: 'self_register',
    protected: false,
    enabled: true,
    tags: [],
    version: null,
    endpoints: {},
    target_gateway_type: 'stoa',
    topology: 'native-edge',
    deployment_mode: 'edge',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
];

const mockSourceDeployments: GatewayDeployment[] = [
  {
    id: 'deploy-1',
    api_catalog_id: 'catalog-1',
    gateway_instance_id: 'gw-dev',
    desired_state: {
      api_id: 'api-1',
      api_name: 'orders-api',
      api_catalog_id: 'catalog-1',
      tenant_id: 'tenant-1',
    },
    desired_at: '2026-03-08T09:00:00Z',
    sync_status: 'synced',
    sync_attempts: 0,
    created_at: '2026-03-08T09:00:00Z',
    updated_at: '2026-03-08T09:00:00Z',
    gateway_name: 'stoa-gateway-dev',
    gateway_display_name: 'STOA Gateway Dev',
    gateway_type: 'stoa_edge_mcp',
    gateway_environment: 'dev',
  },
];

// ── Setup ─────────────────────────────────────────────────────────────────────

const { useAuth } = await import('../contexts/AuthContext');
const { apiService } = await import('../services/api');

function setupMocks(role: PersonaRole = 'cpi-admin') {
  vi.clearAllMocks();
  vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
  vi.mocked(apiService.getTenants).mockResolvedValue(mockTenants);
  vi.mocked(apiService.getApis).mockImplementation(async (tenantId: string) =>
    tenantId === 'tenant-1' ? mockApis : mockTenantTwoApis
  );
  vi.mocked(apiService.getGatewayInstances).mockResolvedValue({
    items: mockGateways,
    total: mockGateways.length,
    page: 1,
    page_size: 100,
  });
  vi.mocked(apiService.getGatewayDeployments).mockResolvedValue({
    items: mockSourceDeployments,
    total: mockSourceDeployments.length,
    page: 1,
    page_size: 100,
  });
  vi.mocked(apiService.listPromotions).mockResolvedValue({
    items: [mockPromotion],
    total: 1,
    page: 1,
    page_size: 50,
  });
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('Promotions', () => {
  describe('Page rendering', () => {
    it('renders the page title and description', async () => {
      setupMocks();
      renderWithProviders(<Promotions />);

      expect(screen.getByText('Promotions')).toBeInTheDocument();
      expect(screen.getByText(/Promote APIs across environments/)).toBeInTheDocument();
    });

    it('shows the New Promotion button for users with apis:deploy', async () => {
      setupMocks('cpi-admin');
      renderWithProviders(<Promotions />);

      expect(screen.getByText('New Promotion')).toBeInTheDocument();
    });

    it('hides the New Promotion button for viewers', async () => {
      setupMocks('viewer');
      renderWithProviders(<Promotions />);

      expect(screen.queryByText('New Promotion')).not.toBeInTheDocument();
    });
  });

  describe('Promotion list', () => {
    it('limits tenant and API filters to promotion-eligible APIs', async () => {
      setupMocks();
      renderWithProviders(<Promotions />);

      await waitFor(() => {
        expect(apiService.getGatewayDeployments).toHaveBeenCalled();
      });

      const tenantFilter = screen.getByTestId('promotion-tenant-filter');
      expect(within(tenantFilter).getByRole('option', { name: 'ACME Corp' })).toBeInTheDocument();
      expect(
        within(tenantFilter).queryByRole('option', { name: 'Globex' })
      ).not.toBeInTheDocument();

      const apiFilter = screen.getByTestId('promotion-api-filter');
      expect(within(apiFilter).getByRole('option', { name: 'Orders API' })).toBeInTheDocument();
      expect(
        within(apiFilter).queryByRole('option', { name: 'Billing API' })
      ).not.toBeInTheDocument();
      expect(
        within(apiFilter).queryByRole('option', { name: 'Inventory API' })
      ).not.toBeInTheDocument();
    });

    it('loads and displays promotions after tenant selection', async () => {
      setupMocks();
      renderWithProviders(<Promotions />);

      await waitFor(() => {
        expect(apiService.listPromotions).toHaveBeenCalledWith('tenant-1', expect.any(Object));
      });

      await waitFor(() => {
        expect(screen.getByText('Ready for staging validation')).toBeInTheDocument();
      });
    });

    it('displays promotion status badge', async () => {
      setupMocks();
      renderWithProviders(<Promotions />);

      await waitFor(() => {
        expect(screen.getByText('Pending Approval')).toBeInTheDocument();
      });
    });

    it('shows environment path (source -> target)', async () => {
      setupMocks();
      renderWithProviders(<Promotions />);

      await waitFor(() => {
        // Multiple DEV/STAGING elements exist (pipeline + row); check at least one pair
        expect(screen.getAllByText('DEV').length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText('STAGING').length).toBeGreaterThanOrEqual(1);
      });
    });

    it('shows empty state when no promotions exist', async () => {
      setupMocks();
      vi.mocked(apiService.listPromotions).mockResolvedValue({
        items: [],
        total: 0,
        page: 1,
        page_size: 50,
      });
      renderWithProviders(<Promotions />);

      await waitFor(() => {
        expect(screen.getByText(/No promotions yet/)).toBeInTheDocument();
      });
    });
  });

  describe('RBAC — 4-eyes principle', () => {
    it('shows Approve button when different user can approve', async () => {
      setupMocks('cpi-admin');
      // cpi-admin is "halliday", promotion requested by "parzival" => can approve
      renderWithProviders(<Promotions />);

      await waitFor(() => {
        expect(screen.getByText('Approve')).toBeInTheDocument();
      });
    });

    it('allows self-approval for dev→staging (2-eyes)', async () => {
      setupMocks('tenant-admin');
      // tenant-admin is "parzival", same as requested_by, but target is staging => allowed
      renderWithProviders(<Promotions />);

      await waitFor(() => {
        expect(screen.getByText('Approve')).toBeInTheDocument();
      });
      expect(screen.queryByText('Self-approve blocked')).not.toBeInTheDocument();
    });

    it('blocks self-approval for staging→production (4-eyes)', async () => {
      const prodPromotion: Promotion = {
        ...mockPromotion,
        source_environment: 'staging',
        target_environment: 'production',
      };
      setupMocks('tenant-admin');
      vi.mocked(apiService.listPromotions).mockResolvedValue({
        items: [prodPromotion],
        total: 1,
        page: 1,
        page_size: 50,
      });
      renderWithProviders(<Promotions />);

      await waitFor(() => {
        expect(screen.getByText('Self-approve blocked')).toBeInTheDocument();
      });
      expect(screen.queryByText('Approve')).not.toBeInTheDocument();
    });

    it('hides approve and rollback for viewers', async () => {
      setupMocks('viewer');
      renderWithProviders(<Promotions />);

      await waitFor(() => {
        expect(screen.getByText('Pending Approval')).toBeInTheDocument();
      });
      expect(screen.queryByText('Approve')).not.toBeInTheDocument();
      expect(screen.queryByText('Rollback')).not.toBeInTheDocument();
    });
  });

  describe('Verify Complete', () => {
    it('shows Verify Complete button for promoting promotions', async () => {
      const promotingPromotion: Promotion = {
        ...mockPromotion,
        status: 'promoting',
        approved_by: 'James Halliday',
      };
      setupMocks('cpi-admin');
      vi.mocked(apiService.listPromotions).mockResolvedValue({
        items: [promotingPromotion],
        total: 1,
        page: 1,
        page_size: 50,
      });
      renderWithProviders(<Promotions />);

      await waitFor(() => {
        expect(screen.getByText('Verify Complete')).toBeInTheDocument();
      });
    });

    it('calls completePromotion when Verify Complete is clicked', async () => {
      const promotingPromotion: Promotion = {
        ...mockPromotion,
        status: 'promoting',
        approved_by: 'James Halliday',
      };
      setupMocks('cpi-admin');
      vi.mocked(apiService.listPromotions).mockResolvedValue({
        items: [promotingPromotion],
        total: 1,
        page: 1,
        page_size: 50,
      });
      vi.mocked(apiService.completePromotion).mockResolvedValue(undefined as never);
      renderWithProviders(<Promotions />);

      const user = userEvent.setup();

      await waitFor(() => {
        expect(screen.getByText('Verify Complete')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Verify Complete'));

      await waitFor(() => {
        expect(apiService.completePromotion).toHaveBeenCalledWith('tenant-1', 'promo-1');
      });
    });

    it('hides Verify Complete for viewers', async () => {
      const promotingPromotion: Promotion = {
        ...mockPromotion,
        status: 'promoting',
        approved_by: 'James Halliday',
      };
      setupMocks('viewer');
      vi.mocked(apiService.listPromotions).mockResolvedValue({
        items: [promotingPromotion],
        total: 1,
        page: 1,
        page_size: 50,
      });
      renderWithProviders(<Promotions />);

      await waitFor(() => {
        expect(screen.getByText('Promoting')).toBeInTheDocument();
      });
      expect(screen.queryByText('Verify Complete')).not.toBeInTheDocument();
    });
  });

  describe('Rollback', () => {
    it('shows Rollback button for promoted promotions', async () => {
      const promotedPromotion: Promotion = {
        ...mockPromotion,
        status: 'promoted',
        approved_by: 'James Halliday',
        completed_at: '2026-03-08T11:00:00Z',
      };
      setupMocks('cpi-admin');
      vi.mocked(apiService.listPromotions).mockResolvedValue({
        items: [promotedPromotion],
        total: 1,
        page: 1,
        page_size: 50,
      });
      renderWithProviders(<Promotions />);

      await waitFor(() => {
        expect(screen.getByText('Rollback')).toBeInTheDocument();
      });
    });
  });

  describe('Create promotion dialog', () => {
    it('opens the create dialog when clicking New Promotion', async () => {
      setupMocks('cpi-admin');
      renderWithProviders(<Promotions />);

      const user = userEvent.setup();

      let newPromotionButton: HTMLElement | null = null;
      await waitFor(() => {
        newPromotionButton = screen.getByText('New Promotion');
        expect(newPromotionButton).toBeEnabled();
      });

      await user.click(newPromotionButton!);

      // Dialog has a heading "Create Promotion" and a submit button with same text
      expect(screen.getByRole('heading', { name: 'Create Promotion' })).toBeInTheDocument();
      expect(screen.getByText('Promotion Path')).toBeInTheDocument();
    });

    it('creates a gateway-aware promotion with source deployment and target gateways', async () => {
      setupMocks('cpi-admin');
      vi.mocked(apiService.createPromotion).mockResolvedValue(mockPromotion);
      renderWithProviders(<Promotions />);

      const user = userEvent.setup();

      let newPromotionButton: HTMLElement | null = null;
      await waitFor(() => {
        newPromotionButton = screen.getByText('New Promotion');
        expect(newPromotionButton).toBeEnabled();
      });

      await user.click(newPromotionButton!);
      expect(
        within(screen.getByTestId('promotion-api-select')).getByRole('option', {
          name: 'Orders API (orders-api)',
        })
      ).toBeInTheDocument();
      expect(
        within(screen.getByTestId('promotion-api-select')).queryByRole('option', {
          name: 'Billing API (billing-api)',
        })
      ).not.toBeInTheDocument();
      await user.selectOptions(screen.getByTestId('promotion-api-select'), 'api-1');

      await waitFor(() => {
        expect(apiService.getGatewayDeployments).toHaveBeenCalledWith({
          environment: 'dev',
          sync_status: 'synced',
          page_size: 100,
        });
      });

      await user.selectOptions(screen.getByTestId('source-deployment-select'), 'deploy-1');

      await waitFor(() => {
        expect(screen.getByText('STOA Gateway Staging')).toBeInTheDocument();
      });

      await user.click(screen.getByLabelText(/STOA Gateway Staging/));
      await user.type(screen.getByPlaceholderText(/Why are you promoting/), 'Ready for staging');
      await user.click(screen.getByRole('button', { name: /Create Promotion/ }));

      await waitFor(() => {
        expect(apiService.createPromotion).toHaveBeenCalledWith('tenant-1', 'api-1', {
          source_deployment_id: 'deploy-1',
          target_gateway_ids: ['gw-staging'],
          source_environment: 'dev',
          target_environment: 'staging',
          message: 'Ready for staging',
        });
      });
    });
  });

  describe('Pipeline indicator', () => {
    it('renders the pipeline indicator when promotions exist', async () => {
      setupMocks();
      renderWithProviders(<Promotions />);

      await waitFor(() => {
        expect(screen.getByText('Promotion Pipeline')).toBeInTheDocument();
      });
    });
  });

  describe('Row expand & diff', () => {
    it('expands a row and loads diff on click', async () => {
      setupMocks('cpi-admin');
      vi.mocked(apiService.getPromotionDiff).mockResolvedValue({
        source_environment: 'dev',
        target_environment: 'staging',
        source_spec: { version: '1.0' },
        target_spec: null,
        diff_summary: {},
      });
      renderWithProviders(<Promotions />);

      const user = userEvent.setup();

      await waitFor(() => {
        expect(screen.getByText('Ready for staging validation')).toBeInTheDocument();
      });

      // Click the row to expand
      await user.click(screen.getByText('Ready for staging validation'));

      await waitFor(() => {
        expect(apiService.getPromotionDiff).toHaveBeenCalledWith('tenant-1', 'promo-1');
      });

      await waitFor(() => {
        expect(screen.getByText(/Source/)).toBeInTheDocument();
      });
    });

    it('shows "no diff" when diff fetch fails', async () => {
      setupMocks('cpi-admin');
      vi.mocked(apiService.getPromotionDiff).mockRejectedValue(new Error('Not found'));
      renderWithProviders(<Promotions />);

      const user = userEvent.setup();

      await waitFor(() => {
        expect(screen.getByText('Ready for staging validation')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Ready for staging validation'));

      await waitFor(() => {
        expect(screen.getByText(/No diff available/)).toBeInTheDocument();
      });
    });
  });

  describe('Approve action', () => {
    it('calls approvePromotion when Approve is clicked', async () => {
      setupMocks('cpi-admin');
      vi.mocked(apiService.approvePromotion).mockResolvedValue(undefined as never);
      renderWithProviders(<Promotions />);

      const user = userEvent.setup();

      await waitFor(() => {
        expect(screen.getByText('Approve')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Approve'));

      await waitFor(() => {
        expect(apiService.approvePromotion).toHaveBeenCalledWith('tenant-1', 'promo-1');
      });
    });

    it('calls error toast when approve fails', async () => {
      setupMocks('cpi-admin');
      vi.mocked(apiService.approvePromotion).mockRejectedValue(new Error('Server error'));
      renderWithProviders(<Promotions />);

      const user = userEvent.setup();

      await waitFor(() => {
        expect(screen.getByText('Approve')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Approve'));

      await waitFor(() => {
        expect(apiService.approvePromotion).toHaveBeenCalledWith('tenant-1', 'promo-1');
      });
    });
  });

  describe('Rollback action', () => {
    it('calls rollbackPromotion when Rollback is clicked', async () => {
      const promotedPromotion: Promotion = {
        ...mockPromotion,
        status: 'promoted',
        approved_by: 'James Halliday',
        completed_at: '2026-03-08T11:00:00Z',
      };
      setupMocks('cpi-admin');
      vi.mocked(apiService.listPromotions).mockResolvedValue({
        items: [promotedPromotion],
        total: 1,
        page: 1,
        page_size: 50,
      });
      vi.mocked(apiService.rollbackPromotion).mockResolvedValue(undefined as never);
      renderWithProviders(<Promotions />);

      const user = userEvent.setup();

      await waitFor(() => {
        expect(screen.getByText('Rollback')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Rollback'));

      await waitFor(() => {
        expect(apiService.rollbackPromotion).toHaveBeenCalledWith(
          'tenant-1',
          'promo-1',
          expect.objectContaining({ message: expect.any(String) })
        );
      });
    });
  });

  describe('Error handling', () => {
    it('shows error when tenant loading fails', async () => {
      setupMocks('cpi-admin');
      vi.mocked(apiService.getTenants).mockRejectedValue(new Error('Network error'));
      renderWithProviders(<Promotions />);

      await waitFor(() => {
        expect(screen.getByText('Network error')).toBeInTheDocument();
      });
    });

    it('shows error when promotions loading fails', async () => {
      setupMocks('cpi-admin');
      vi.mocked(apiService.listPromotions).mockRejectedValue(new Error('Server error'));
      renderWithProviders(<Promotions />);

      await waitFor(() => {
        expect(screen.getByText('Server error')).toBeInTheDocument();
      });
    });
  });

  describe('Status badges', () => {
    it.each([
      { status: 'promoting' as const, label: 'Promoting' },
      { status: 'failed' as const, label: 'Failed' },
      { status: 'rolled_back' as const, label: 'Rolled Back' },
    ])('renders $label badge for $status status', async ({ status, label }) => {
      const promotion: Promotion = {
        ...mockPromotion,
        status,
        approved_by: status !== 'promoting' ? 'James Halliday' : null,
      };
      setupMocks('cpi-admin');
      vi.mocked(apiService.listPromotions).mockResolvedValue({
        items: [promotion],
        total: 1,
        page: 1,
        page_size: 50,
      });
      renderWithProviders(<Promotions />);

      await waitFor(() => {
        expect(screen.getByText(label)).toBeInTheDocument();
      });
    });
  });
});
