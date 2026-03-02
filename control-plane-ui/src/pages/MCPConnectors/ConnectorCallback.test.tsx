import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const mockHandleCallback = vi.fn();
vi.mock('../../services/mcpConnectorsApi', () => ({
  mcpConnectorsService: {
    handleCallback: (...args: unknown[]) => mockHandleCallback(...args),
  },
}));

const mockToast = { success: vi.fn(), error: vi.fn(), info: vi.fn() };
vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => mockToast,
}));

vi.mock('@stoa/shared/components/StoaLoader', () => ({
  StoaLoader: () => <div data-testid="loader" />,
}));

import { ConnectorCallback } from './ConnectorCallback';

function renderWithParams(search: string) {
  return render(
    <MemoryRouter initialEntries={[`/mcp-connectors/callback${search}`]}>
      <ConnectorCallback />
    </MemoryRouter>
  );
}

describe('ConnectorCallback', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading spinner on mount', () => {
    mockHandleCallback.mockReturnValue(new Promise(() => {}));
    renderWithParams('?code=abc&state=xyz');
    expect(screen.getByTestId('loader')).toBeInTheDocument();
    expect(screen.getByText('Connecting...')).toBeInTheDocument();
  });

  it('calls handleCallback with code and state from URL', async () => {
    mockHandleCallback.mockResolvedValue({
      server_id: 'srv-1',
      server_name: 'linear-mcp',
      display_name: 'Linear',
      slug: 'linear',
      tools_sync_triggered: true,
    });

    renderWithParams('?code=test-code&state=test-state');

    await waitFor(() => {
      expect(mockHandleCallback).toHaveBeenCalledWith({
        code: 'test-code',
        state: 'test-state',
      });
    });
  });

  it('navigates to server detail on success', async () => {
    mockHandleCallback.mockResolvedValue({
      server_id: 'srv-1',
      server_name: 'linear-mcp',
      display_name: 'Linear',
      slug: 'linear',
      tools_sync_triggered: true,
    });

    renderWithParams('?code=abc&state=xyz');

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/external-mcp-servers/srv-1', { replace: true });
    });
    expect(mockToast.success).toHaveBeenCalledWith('Connected', 'Linear has been connected');
  });

  it('uses redirect_url from response when present', async () => {
    mockHandleCallback.mockResolvedValue({
      server_id: 'srv-1',
      server_name: 'linear-mcp',
      display_name: 'Linear',
      slug: 'linear',
      tools_sync_triggered: true,
      redirect_url: '/mcp-connectors',
    });

    renderWithParams('?code=abc&state=xyz');

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/mcp-connectors', { replace: true });
    });
  });

  it('shows error toast and navigates on API error', async () => {
    mockHandleCallback.mockRejectedValue(new Error('Token exchange failed'));

    renderWithParams('?code=abc&state=xyz');

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith('Connection failed', 'Token exchange failed');
      expect(mockNavigate).toHaveBeenCalledWith('/mcp-connectors', { replace: true });
    });
  });

  it('handles OAuth error param', async () => {
    renderWithParams('?error=access_denied&error_description=User+denied+access');

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith('Connection failed', 'User denied access');
      expect(mockNavigate).toHaveBeenCalledWith('/mcp-connectors', { replace: true });
    });
  });

  it('handles missing code/state params', async () => {
    renderWithParams('?code=abc');

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith(
        'Connection failed',
        'Missing authorization parameters'
      );
      expect(mockNavigate).toHaveBeenCalledWith('/mcp-connectors', { replace: true });
    });
  });
});
