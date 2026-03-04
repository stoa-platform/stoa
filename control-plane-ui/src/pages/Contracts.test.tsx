import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createAuthMock, renderWithProviders } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import type { PersonaRole } from '../test/helpers';

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

const mockContracts = [
  {
    id: 'ctr-1',
    tenant_id: 'oasis-gunters',
    name: 'weather-api',
    display_name: 'Weather API',
    description: 'Weather data contract',
    version: '1.0.0',
    status: 'published' as const,
    openapi_spec_url: 'https://api.example.com/openapi.json',
    bindings: [
      {
        protocol: 'rest' as const,
        enabled: true,
        endpoint: 'https://api.example.com/v1/weather',
        playground_url: null,
        tool_name: null,
        operations: ['GET /forecast'],
        proto_file_url: null,
        topic_name: null,
        traffic_24h: 1250,
      },
      {
        protocol: 'mcp' as const,
        enabled: true,
        endpoint: 'https://mcp.example.com/weather',
        playground_url: null,
        tool_name: 'get_weather',
        operations: [],
        proto_file_url: null,
        topic_name: null,
        traffic_24h: 340,
      },
      {
        protocol: 'graphql' as const,
        enabled: false,
        endpoint: null,
        playground_url: null,
        tool_name: null,
        operations: [],
        proto_file_url: null,
        topic_name: null,
        traffic_24h: null,
      },
    ],
    created_at: '2026-02-15T10:00:00Z',
    updated_at: '2026-02-15T10:00:00Z',
  },
  {
    id: 'ctr-2',
    tenant_id: 'oasis-gunters',
    name: 'payments-api',
    display_name: 'Payments API',
    description: null,
    version: '2.1.0',
    status: 'draft' as const,
    openapi_spec_url: null,
    bindings: [],
    created_at: '2026-02-16T10:00:00Z',
    updated_at: '2026-02-16T10:00:00Z',
  },
];

const mockGetContracts = vi.fn().mockResolvedValue({ items: mockContracts, total: 2 });
const mockCreateContract = vi.fn().mockResolvedValue(mockContracts[0]);
const mockDeleteContract = vi.fn().mockResolvedValue({});
const mockPublishContract = vi.fn().mockResolvedValue({
  contract: mockContracts[0],
  bindings_generated: [
    { protocol: 'rest', endpoint: 'https://api.example.com/v1/weather', tool_name: null },
    { protocol: 'mcp', endpoint: 'https://mcp.example.com/weather', tool_name: 'get_weather' },
  ],
});

vi.mock('../services/api', () => ({
  apiService: {
    getTenants: vi.fn().mockResolvedValue([
      {
        id: 'oasis-gunters',
        name: 'oasis-gunters',
        display_name: 'Oasis Gunters',
        status: 'active',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ]),
    getContracts: (...args: unknown[]) => mockGetContracts(...args),
    createContract: (...args: unknown[]) => mockCreateContract(...args),
    deleteContract: (...args: unknown[]) => mockDeleteContract(...args),
    publishContract: (...args: unknown[]) => mockPublishContract(...args),
  },
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  ToastProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useToast: () => ({ addToast: vi.fn() }),
  useToastActions: () => ({
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  }),
}));

vi.mock('@stoa/shared/components/ConfirmDialog', () => ({
  ConfirmDialog: ({
    open,
    title,
    onConfirm,
    onCancel,
  }: {
    open: boolean;
    title: string;
    onConfirm: () => void;
    onCancel: () => void;
  }) =>
    open ? (
      <div data-testid="confirm-dialog">
        <span>{title}</span>
        <button onClick={onConfirm}>Confirm</button>
        <button onClick={onCancel}>Cancel</button>
      </div>
    ) : null,
}));

// Lazy import the component (after mocks are set up)
const { Contracts } = await import('./Contracts');

describe('Contracts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mockGetContracts.mockResolvedValue({ items: mockContracts, total: 2 });
  });

  it('renders the page title and create button', async () => {
    renderWithProviders(<Contracts />);
    expect(screen.getByText('Contracts')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Create Contract')).toBeInTheDocument();
    });
  });

  it('displays contracts after loading', async () => {
    renderWithProviders(<Contracts />);
    await waitFor(() => {
      expect(screen.getByText('Weather API')).toBeInTheDocument();
      expect(screen.getByText('Payments API')).toBeInTheDocument();
    });
  });

  it('shows empty state when no contracts', async () => {
    mockGetContracts.mockResolvedValue({ items: [], total: 0 });
    renderWithProviders(<Contracts />);
    await waitFor(() => {
      expect(screen.getByText('No contracts configured')).toBeInTheDocument();
    });
  });

  it('shows protocol binding badges on contract cards', async () => {
    renderWithProviders(<Contracts />);
    await waitFor(() => {
      expect(screen.getByText('Weather API')).toBeInTheDocument();
    });
    // Protocol badges are rendered for each contract
    const restBadges = screen.getAllByText('REST');
    expect(restBadges.length).toBeGreaterThan(0);
    const mcpBadges = screen.getAllByText('MCP');
    expect(mcpBadges.length).toBeGreaterThan(0);
  });

  it('shows contract status badge', async () => {
    renderWithProviders(<Contracts />);
    await waitFor(() => {
      expect(screen.getByText('published')).toBeInTheDocument();
      expect(screen.getByText('draft')).toBeInTheDocument();
    });
  });

  it('opens create view when button clicked', async () => {
    const user = userEvent.setup();
    mockGetContracts.mockResolvedValue({ items: [], total: 0 });
    renderWithProviders(<Contracts />);
    await waitFor(() => {
      expect(screen.getByText('No contracts configured')).toBeInTheDocument();
    });
    const createButtons = screen.getAllByText('Create Contract');
    await user.click(createButtons[createButtons.length - 1]);
    await waitFor(() => {
      expect(screen.getByText('Create New Contract')).toBeInTheDocument();
    });
  });

  it('shows confirm dialog when delete clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Contracts />);
    await waitFor(() => {
      expect(screen.getByText('Weather API')).toBeInTheDocument();
    });
    // Click delete button (trash icon)
    const deleteButtons = screen.getAllByTitle('Delete');
    await user.click(deleteButtons[0]);
    await waitFor(() => {
      expect(screen.getByTestId('confirm-dialog')).toBeInTheDocument();
    });
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderWithProviders(<Contracts />);
        expect(screen.getByText('Contracts')).toBeInTheDocument();
      });
    }
  );
});
