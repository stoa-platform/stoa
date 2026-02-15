/**
 * ToolDetail Tests - CAB-1167
 *
 * Tests for the tool detail page with schema viewer, usage stats, and try-it form.
 */

import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders, createAuthMock, type PersonaRole } from '../../test/helpers';
import { ToolDetail } from '../tools/ToolDetail';

// Mock AuthContext at module level
const mockAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth(),
}));

// Mock react-router-dom
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useParams: () => ({ id: 'test-tool' }),
    useNavigate: () => mockNavigate,
  };
});

// Mock hooks
const mockToolData = vi.fn();
const mockSchemaData = vi.fn();
const mockSubscribeMutation = vi.fn();
const mockRefetch = vi.fn();

vi.mock('../../hooks/useTools', () => ({
  useTool: () => ({
    data: mockToolData(),
    isLoading: false,
    isError: false,
    error: null,
    refetch: mockRefetch,
  }),
  useToolSchema: () => ({
    data: mockSchemaData(),
    isLoading: false,
  }),
  useSubscribeToTool: () => ({
    mutateAsync: mockSubscribeMutation,
    isPending: false,
  }),
}));

// Mock services
vi.mock('../../services/tools', () => ({
  toolsService: {
    invokeTool: vi.fn().mockResolvedValue({ result: 'success' }),
  },
}));

// Mock tool components
vi.mock('../../components/tools', () => ({
  SubscribeToToolModal: ({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) =>
    isOpen ? <div data-testid="subscribe-modal"><button onClick={onClose}>Close</button></div> : null,
  SchemaViewer: ({ schema }: { schema: unknown }) => (
    <div data-testid="schema-viewer">{JSON.stringify(schema)}</div>
  ),
  UsageStats: () => <div data-testid="usage-stats">Usage Statistics</div>,
  TryItForm: ({ toolName }: { toolName: string }) => (
    <div data-testid="try-it-form">Try {toolName}</div>
  ),
}));

// Mock subscriptions components
vi.mock('../../components/subscriptions/ApiKeyModal', () => ({
  ApiKeyModal: ({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) =>
    isOpen ? <div data-testid="api-key-modal"><button onClick={onClose}>Close</button></div> : null,
}));

// Mock config
vi.mock('../../config', () => ({
  config: {
    features: {
      enableSubscriptions: true,
    },
  },
}));

describe('ToolDetail', () => {
  const mockTool = {
    id: 'test-tool',
    name: 'test-tool',
    displayName: 'Test Tool',
    description: 'A test tool for testing',
    status: 'active',
    category: 'testing',
    version: '1.0.0',
    endpoint: 'https://api.example.com/tool',
    method: 'POST',
    tags: ['test', 'demo'],
    pricing: { model: 'free' },
    rateLimit: { requests: 100, period: 'hour' },
    inputSchema: {
      type: 'object',
      properties: {
        input: { type: 'string', description: 'Input parameter' },
      },
      required: ['input'],
    },
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    mockToolData.mockReturnValue(mockTool);
    mockSchemaData.mockReturnValue(null);
  });

  it('renders the tool name and description', async () => {
    renderWithProviders(<ToolDetail />);
    await waitFor(() => {
      expect(screen.getByText('Test Tool')).toBeInTheDocument();
      expect(screen.getByText('A test tool for testing')).toBeInTheDocument();
    });
  });

  it('renders the back button', async () => {
    renderWithProviders(<ToolDetail />);
    await waitFor(() => {
      expect(screen.getByText('Back to Tools Catalog')).toBeInTheDocument();
    });
  });

  it('renders status badge', async () => {
    renderWithProviders(<ToolDetail />);
    await waitFor(() => {
      expect(screen.getByText('Active')).toBeInTheDocument();
    });
  });

  it('renders subscribe button', async () => {
    renderWithProviders(<ToolDetail />);
    await waitFor(() => {
      expect(screen.getByText('Subscribe')).toBeInTheDocument();
    });
  });

  it('renders tabs navigation', async () => {
    renderWithProviders(<ToolDetail />);
    await waitFor(() => {
      expect(screen.getByText('Overview')).toBeInTheDocument();
      expect(screen.getByText('Schema')).toBeInTheDocument();
      expect(screen.getByText('Try It')).toBeInTheDocument();
    });
  });

  it('shows error state when tool not found', async () => {
    mockToolData.mockReturnValue(null);
    renderWithProviders(<ToolDetail />);
    await waitFor(() => {
      expect(screen.getByText('Failed to load tool')).toBeInTheDocument();
    });
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      beforeEach(() => {
        vi.clearAllMocks();
        mockAuth.mockReturnValue(createAuthMock(role));
        mockToolData.mockReturnValue(mockTool);
        mockSchemaData.mockReturnValue(null);
      });

      it('renders the page without error', async () => {
        renderWithProviders(<ToolDetail />);
        await waitFor(() => {
          expect(screen.getByText('Test Tool')).toBeInTheDocument();
        });
      });

      it('renders tabs', async () => {
        renderWithProviders(<ToolDetail />);
        await waitFor(() => {
          expect(screen.getByText('Overview')).toBeInTheDocument();
          expect(screen.getByText('Schema')).toBeInTheDocument();
        });
      });
    }
  );
});
