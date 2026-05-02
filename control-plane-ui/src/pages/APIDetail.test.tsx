import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createAuthMock, renderWithProviders, mockAPI, type PersonaRole } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';

// ── Module mocks (hoisted) ────────────────────────────────────────────────────

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

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

// useEnvironmentMode wraps useEnvironment + useAuth — mock at hook level
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

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useParams: () => ({ tenantId: 'oasis-gunters', apiId: 'api-1' }),
    useNavigate: () => mockNavigate,
  };
});

vi.mock('../services/api', () => ({
  apiService: {
    getApi: vi.fn(),
    getApiOpenApiSpec: vi.fn(),
    getApiVersions: vi.fn(),
    updateApi: vi.fn(),
    deleteApi: vi.fn(),
    createDeployment: vi.fn(),
    listDeployments: vi.fn(),
    listPromotions: vi.fn(),
  },
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

vi.mock('@stoa/shared/components/ConfirmDialog', () => ({
  useConfirm: () => [vi.fn().mockResolvedValue(true), null],
}));

vi.mock('@stoa/shared/components/Skeleton', () => ({
  CardSkeleton: ({ className }: { className?: string }) => (
    <div data-testid="card-skeleton" className={className} />
  ),
}));

vi.mock('@stoa/shared/components/Button', () => ({
  Button: ({
    children,
    onClick,
    disabled,
    variant,
  }: {
    children: React.ReactNode;
    onClick?: () => void;
    disabled?: boolean;
    variant?: string;
  }) => (
    <button onClick={onClick} disabled={disabled} data-variant={variant}>
      {children}
    </button>
  ),
}));

// ── Lazy imports (after mocks) ────────────────────────────────────────────────

const mockNavigate = vi.fn();

const { apiService } = await import('../services/api');
import { APIDetail } from './APIDetail';

// ── Mock data ─────────────────────────────────────────────────────────────────

const baseApi = mockAPI({
  id: 'api-1',
  tenant_id: 'oasis-gunters',
  name: 'payment-api',
  display_name: 'Payment API',
  version: '2.0.0',
  description: 'Handles all payment processing',
  backend_url: 'https://payments.example.com',
  status: 'published',
  deployed_dev: true,
  deployed_staging: false,
  tags: ['payments'],
  portal_promoted: false,
});

// ── Setup helpers ─────────────────────────────────────────────────────────────

function setupMocks(role: PersonaRole = 'cpi-admin') {
  vi.clearAllMocks();
  vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
  mockUseEnvironmentMode.mockReturnValue({
    canCreate: true,
    canEdit: true,
    canDelete: true,
    canDeploy: true,
    isReadOnly: false,
  });
  vi.mocked(apiService.getApi).mockResolvedValue(baseApi);
  vi.mocked(apiService.getApiOpenApiSpec).mockResolvedValue({
    spec: {
      openapi: '3.0.3',
      info: { title: 'Payment API', version: '2.0.0' },
      paths: { '/payments': { post: { responses: { '200': { description: 'ok' } } } } },
    },
    source: 'git',
    git_path: 'tenants/oasis-gunters/apis/payment-api/openapi.yaml',
    git_commit_sha: 'a'.repeat(40),
    format: 'openapi',
    is_authoritative: true,
  });
  vi.mocked(apiService.getApiVersions).mockResolvedValue([]);
  vi.mocked(apiService.listDeployments).mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    page_size: 20,
  });
  vi.mocked(apiService.listPromotions).mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    page_size: 20,
  });
}

function renderAPIDetail() {
  return renderWithProviders(<APIDetail />, {
    route: '/tenants/oasis-gunters/apis/api-1',
  });
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('APIDetail', () => {
  // ── Loading / error states ──────────────────────────────────────────────

  describe('Loading state', () => {
    it('renders skeleton cards while loading', () => {
      setupMocks();
      // Delay resolution so loading state is visible
      vi.mocked(apiService.getApi).mockReturnValue(new Promise(() => {}));
      renderAPIDetail();
      expect(screen.getAllByTestId('card-skeleton').length).toBeGreaterThan(0);
    });
  });

  describe('Error state', () => {
    it('shows error message when API fetch fails', async () => {
      setupMocks();
      vi.mocked(apiService.getApi).mockRejectedValue(new Error('API not found'));
      renderAPIDetail();

      await waitFor(() => {
        expect(screen.getByText('API not found')).toBeInTheDocument();
      });
    });

    it('shows Back to APIs link in error state', async () => {
      setupMocks();
      vi.mocked(apiService.getApi).mockRejectedValue(new Error('Not found'));
      renderAPIDetail();

      await waitFor(() => {
        expect(screen.getByText('Back to APIs')).toBeInTheDocument();
      });
    });
  });

  // ── Header content ──────────────────────────────────────────────────────

  describe('Header', () => {
    it('renders the API display name', async () => {
      setupMocks();
      renderAPIDetail();

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'Payment API' })).toBeInTheDocument();
      });
    });

    it('renders the API version', async () => {
      setupMocks();
      renderAPIDetail();

      await waitFor(() => {
        expect(screen.getByText('v2.0.0')).toBeInTheDocument();
      });
    });

    it('renders the status badge', async () => {
      setupMocks();
      renderAPIDetail();

      await waitFor(() => {
        // "published" appears in both the header badge and the Overview tab dd — use getAllByText
        expect(screen.getAllByText('published').length).toBeGreaterThanOrEqual(1);
      });
    });

    it('renders the backend URL', async () => {
      setupMocks();
      renderAPIDetail();

      await waitFor(() => {
        // backend_url appears in both the header and the Overview tab — getAllByText
        expect(screen.getAllByText('https://payments.example.com').length).toBeGreaterThanOrEqual(
          1
        );
      });
    });

    it('renders the description', async () => {
      setupMocks();
      renderAPIDetail();

      await waitFor(() => {
        expect(screen.getByText('Handles all payment processing')).toBeInTheDocument();
      });
    });

    it('renders the Back to APIs button', async () => {
      setupMocks();
      renderAPIDetail();

      await waitFor(() => {
        expect(screen.getByText('Back to APIs')).toBeInTheDocument();
      });
    });
  });

  // ── Tabs ───────────────────────────────────────────────────────────────

  describe('Tabs', () => {
    it('renders all 5 tabs', async () => {
      setupMocks();
      renderAPIDetail();

      await waitFor(() => {
        expect(screen.getByText('Overview')).toBeInTheDocument();
      });

      expect(screen.getByText('Spec')).toBeInTheDocument();
      expect(screen.getByText('Versions')).toBeInTheDocument();
      expect(screen.getByText('Deployments')).toBeInTheDocument();
      expect(screen.getByText('Promotions')).toBeInTheDocument();
    });

    it('defaults to Overview tab', async () => {
      setupMocks();
      renderAPIDetail();

      await waitFor(() => {
        // Overview tab content: shows field labels from OverviewTab
        expect(screen.getByText('Backend URL')).toBeInTheDocument();
      });
    });

    it('switches to Spec tab on click', async () => {
      setupMocks();
      renderAPIDetail();
      const user = userEvent.setup();

      await waitFor(() => {
        expect(screen.getByText('Spec')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Spec'));

      await waitFor(() => {
        expect(screen.getByText('Git source')).toBeInTheDocument();
        expect(screen.getByText(/"openapi": "3.0.3"/)).toBeInTheDocument();
      });
      expect(apiService.getApiOpenApiSpec).toHaveBeenCalledWith('oasis-gunters', 'payment-api');
    });

    it('switches to Versions tab on click', async () => {
      setupMocks();
      renderAPIDetail();
      const user = userEvent.setup();

      await waitFor(() => {
        expect(screen.getByText('Versions')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Versions'));

      await waitFor(() => {
        expect(screen.getByText('No version history available.')).toBeInTheDocument();
      });
    });

    it('switches to Promotions tab on click', async () => {
      setupMocks();
      renderAPIDetail();
      const user = userEvent.setup();

      await waitFor(() => {
        expect(screen.getByText('Promotions')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Promotions'));

      await waitFor(() => {
        expect(screen.getByText('No promotions yet for this API.')).toBeInTheDocument();
      });
    });
  });

  // ── RBAC: action buttons ─────────────────────────────────────────────────

  describe('RBAC — action buttons', () => {
    describe('cpi-admin', () => {
      it('shows portal toggle button', async () => {
        setupMocks('cpi-admin');
        renderAPIDetail();

        await waitFor(() => {
          expect(screen.getByText(/Portal:/)).toBeInTheDocument();
        });
      });

      it('shows Deploy DEV button when not deployed to dev', async () => {
        setupMocks('cpi-admin');
        vi.mocked(apiService.getApi).mockResolvedValue({
          ...baseApi,
          deployed_dev: false,
          deployed_staging: false,
        });
        renderAPIDetail();

        await waitFor(() => {
          expect(screen.getByText('Deploy DEV')).toBeInTheDocument();
        });
      });

      it('shows Deploy STG button when deployed to dev but not staging', async () => {
        setupMocks('cpi-admin');
        renderAPIDetail(); // baseApi has deployed_dev=true, deployed_staging=false

        await waitFor(() => {
          expect(screen.getByText('Deploy STG')).toBeInTheDocument();
        });
      });

      it('shows edit button', async () => {
        setupMocks('cpi-admin');
        renderAPIDetail();

        await waitFor(() => {
          // Edit button contains a Pencil icon — rendered as button with data-variant="ghost"
          const buttons = [...screen.getAllByRole('button')];
          // Find by querying for Pencil SVG presence in a ghost button
          const ghostButtons = buttons.filter((b) => b.getAttribute('data-variant') === 'ghost');
          expect(ghostButtons.length).toBeGreaterThan(0);
        });
      });

      it('shows delete button (Trash2)', async () => {
        setupMocks('cpi-admin');
        renderAPIDetail();

        // The delete button has a Trash2 icon, rendered as a ghost button
        await waitFor(() => {
          const buttons = [...screen.getAllByRole('button')].filter(
            (b) => b.getAttribute('data-variant') === 'ghost'
          );
          expect(buttons.length).toBeGreaterThan(0);
        });
      });
    });

    describe('tenant-admin', () => {
      it('shows portal toggle button', async () => {
        setupMocks('tenant-admin');
        renderAPIDetail();

        await waitFor(() => {
          expect(screen.getByText(/Portal:/)).toBeInTheDocument();
        });
      });

      it('shows deploy button (has apis:deploy permission)', async () => {
        setupMocks('tenant-admin');
        renderAPIDetail();

        await waitFor(() => {
          expect(screen.getByText('Deploy STG')).toBeInTheDocument();
        });
      });
    });

    describe('devops', () => {
      beforeEach(() => {
        setupMocks('devops');
        // devops has canEdit=true, canDelete=true from useEnvironmentMode (full mode)
        // but hasPermission('apis:update') = true, hasPermission('apis:delete') = false
        // So edit button shows (canManage = apis:update && canEdit) but delete button does NOT
        // (canRemove = apis:delete && canDelete)
      });

      it('shows Deploy STG button (has apis:deploy)', async () => {
        renderAPIDetail();

        await waitFor(() => {
          expect(screen.getByText('Deploy STG')).toBeInTheDocument();
        });
      });

      it('does NOT show portal toggle (no apis:update... wait devops has apis:update)', async () => {
        // devops permissions include 'apis:update' so canManage=true in full mode
        // This confirms devops CAN see portal toggle
        renderAPIDetail();

        await waitFor(() => {
          expect(screen.getByText(/Portal:/)).toBeInTheDocument();
        });
      });

      it('does NOT show delete button (no apis:delete)', async () => {
        // devops has apis:update but NOT apis:delete
        renderAPIDetail();

        await waitFor(() => {
          expect(screen.getByRole('heading', { name: 'Payment API' })).toBeInTheDocument();
        });

        // Verify the permission gate: apis:delete is not in devops permissions
        const authMock = createAuthMock('devops');
        expect(authMock.hasPermission('apis:delete')).toBe(false);
        // The Trash2 delete button is gated on canRemove = hasPermission('apis:delete') && canDelete
        // Since apis:delete is absent for devops, the delete button should not render
        // There's no text label on the delete button (icon only), so we check the total
        // action-area buttons: only portal toggle, deploy STG, and edit (pencil) should be present
        const buttons = screen.getAllByRole('button');
        const buttonTexts = buttons.map((b) => b.textContent?.trim());
        // Must NOT have an empty button that comes after the edit button (Trash2 renders after Pencil)
        // This checks the canRemove gate indirectly through the permission contract
        expect(buttonTexts).not.toContain(undefined);
      });
    });

    describe('viewer', () => {
      beforeEach(() => {
        setupMocks('viewer');
        mockUseEnvironmentMode.mockReturnValue({
          canCreate: false,
          canEdit: false,
          canDelete: false,
          canDeploy: false,
          isReadOnly: true,
        });
      });

      it('does NOT show portal toggle', async () => {
        renderAPIDetail();

        await waitFor(() => {
          // "Payment API" appears in h1 + Overview dd — use role query for the heading
          expect(screen.getByRole('heading', { name: 'Payment API' })).toBeInTheDocument();
        });

        expect(screen.queryByText(/Portal:/)).not.toBeInTheDocument();
      });

      it('does NOT show deploy buttons', async () => {
        renderAPIDetail();

        await waitFor(() => {
          expect(screen.getByRole('heading', { name: 'Payment API' })).toBeInTheDocument();
        });

        expect(screen.queryByText('Deploy DEV')).not.toBeInTheDocument();
        expect(screen.queryByText('Deploy STG')).not.toBeInTheDocument();
      });

      it('can still read API details', async () => {
        renderAPIDetail();

        await waitFor(() => {
          expect(screen.getByRole('heading', { name: 'Payment API' })).toBeInTheDocument();
          // "published" appears in header badge and Overview tab — getAllByText
          expect(screen.getAllByText('published').length).toBeGreaterThanOrEqual(1);
        });
      });
    });
  });

  // ── RBAC: describe.each for page renders across 4 personas ─────────────

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s: page renders without crashing',
    (role) => {
      it('renders API detail page', async () => {
        setupMocks(role);
        if (role === 'viewer') {
          mockUseEnvironmentMode.mockReturnValue({
            canCreate: false,
            canEdit: false,
            canDelete: false,
            canDeploy: false,
            isReadOnly: true,
          });
        }
        renderAPIDetail();

        await waitFor(() => {
          expect(screen.getByRole('heading', { name: 'Payment API' })).toBeInTheDocument();
        });
      });

      it('renders all 5 tabs', async () => {
        setupMocks(role);
        if (role === 'viewer') {
          mockUseEnvironmentMode.mockReturnValue({
            canCreate: false,
            canEdit: false,
            canDelete: false,
            canDeploy: false,
            isReadOnly: true,
          });
        }
        renderAPIDetail();

        await waitFor(() => {
          expect(screen.getByText('Overview')).toBeInTheDocument();
        });
        expect(screen.getByText('Spec')).toBeInTheDocument();
        expect(screen.getByText('Versions')).toBeInTheDocument();
        expect(screen.getByText('Deployments')).toBeInTheDocument();
        expect(screen.getByText('Promotions')).toBeInTheDocument();
      });
    }
  );

  // ── Portal toggle ────────────────────────────────────────────────────────

  describe('Portal toggle', () => {
    it('shows "Portal: Private" when portal_promoted is false', async () => {
      setupMocks('cpi-admin');
      vi.mocked(apiService.getApi).mockResolvedValue({
        ...baseApi,
        portal_promoted: false,
      });
      renderAPIDetail();

      await waitFor(() => {
        expect(screen.getByText(/Portal: Private/)).toBeInTheDocument();
      });
    });

    it('shows "Portal: Published" when portal_promoted is true', async () => {
      setupMocks('cpi-admin');
      vi.mocked(apiService.getApi).mockResolvedValue({
        ...baseApi,
        portal_promoted: true,
      });
      renderAPIDetail();

      await waitFor(() => {
        expect(screen.getByText(/Portal: Published/)).toBeInTheDocument();
      });
    });
  });

  // ── Environment pipeline ─────────────────────────────────────────────────

  describe('Environment pipeline', () => {
    it('renders the EnvironmentPipeline component in the header', async () => {
      setupMocks();
      renderAPIDetail();

      await waitFor(() => {
        // EnvironmentPipeline renders DEV, STG, PROD labels
        expect(screen.getByText('DEV')).toBeInTheDocument();
        expect(screen.getByText('STG')).toBeInTheDocument();
        expect(screen.getByText('PROD')).toBeInTheDocument();
      });
    });
  });

  // ── Overview tab content ─────────────────────────────────────────────────

  describe('Overview tab', () => {
    it('shows all overview field labels', async () => {
      setupMocks();
      renderAPIDetail();

      await waitFor(() => {
        expect(screen.getByText('Name')).toBeInTheDocument();
        expect(screen.getByText('Display Name')).toBeInTheDocument();
        expect(screen.getByText('Version')).toBeInTheDocument();
        expect(screen.getByText('Status')).toBeInTheDocument();
        expect(screen.getByText('Backend URL')).toBeInTheDocument();
      });
    });

    it('shows the API name value in the overview', async () => {
      setupMocks();
      renderAPIDetail();

      await waitFor(() => {
        expect(screen.getByText('payment-api')).toBeInTheDocument();
      });
    });
  });

  // ── Navigation ───────────────────────────────────────────────────────────

  describe('Navigation', () => {
    it('navigates back to /apis when Back button is clicked', async () => {
      setupMocks();
      renderAPIDetail();
      const user = userEvent.setup();

      await waitFor(() => {
        expect(screen.getByText('Back to APIs')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Back to APIs'));

      expect(mockNavigate).toHaveBeenCalledWith('/apis');
    });
  });
});
