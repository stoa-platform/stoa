import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { createAuthMock } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

const mockToolData = {
  name: 'stoa_list_apis',
  description: 'List all APIs in the STOA platform',
  method: 'GET',
  version: '1.0.0',
  tags: ['platform', 'apis'],
  endpoint: 'https://api.gostoa.dev/v1/apis',
  inputSchema: { type: 'object', properties: {} },
};

const mockGetTool = vi.fn().mockResolvedValue(mockToolData);
const mockGetToolUsage = vi.fn().mockResolvedValue(null);

vi.mock('../../services/mcpGatewayApi', () => ({
  mcpGatewayService: {
    getTool: (...args: unknown[]) => mockGetTool(...args),
    getToolUsage: (...args: unknown[]) => mockGetToolUsage(...args),
    setAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
  },
}));

vi.mock('../../components/tools', () => ({
  ToolSchemaViewer: () => <div data-testid="schema-viewer">Schema</div>,
  SchemaJsonViewer: () => <div data-testid="json-viewer">JSON</div>,
  QuickStartGuide: () => <div data-testid="quickstart">QuickStart</div>,
}));

vi.mock('@stoa/shared/components/Skeleton', () => ({
  CardSkeleton: () => <div data-testid="card-skeleton" />,
}));

import { ToolDetail } from './ToolDetail';

function renderToolDetail() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/tools/stoa_list_apis']}>
        <Routes>
          <Route path="/tools/:toolName" element={<ToolDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('ToolDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetTool.mockResolvedValue(mockToolData);
    mockGetToolUsage.mockResolvedValue(null);
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders the tool name heading', async () => {
    renderToolDetail();
    expect(await screen.findByRole('heading', { name: 'stoa_list_apis' })).toBeInTheDocument();
  });

  it('renders the tool description', async () => {
    renderToolDetail();
    const descriptions = await screen.findAllByText('List all APIs in the STOA platform');
    expect(descriptions.length).toBeGreaterThanOrEqual(1);
  });

  it('renders the HTTP method badge', async () => {
    renderToolDetail();
    expect(await screen.findByText('GET')).toBeInTheDocument();
  });

  it('renders tab navigation', async () => {
    renderToolDetail();
    await screen.findByRole('heading', { name: 'stoa_list_apis' });
    expect(screen.getByRole('button', { name: /Overview/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Schema/ })).toBeInTheDocument();
  });

  it('shows error state when tool not found', async () => {
    mockGetTool.mockRejectedValue(new Error('Not found'));
    renderToolDetail();
    await waitFor(() => {
      expect(screen.getByText(/not found|error/i)).toBeInTheDocument();
    });
  });

  it('renders back link to AI Tools', async () => {
    renderToolDetail();
    await screen.findByRole('heading', { name: 'stoa_list_apis' });
    expect(screen.getByText('AI Tools')).toBeInTheDocument();
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderToolDetail();
        expect(await screen.findByRole('heading', { name: 'stoa_list_apis' })).toBeInTheDocument();
      });
    }
  );
});
