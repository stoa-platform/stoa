import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, fireEvent } from '@testing-library/react';
import { renderWithProviders } from '../../test/helpers';

// Mock federation service
const mockGetToolAllowList = vi.fn();
const mockUpdateToolAllowList = vi.fn();

vi.mock('../../services/federationApi', () => ({
  federationService: {
    getToolAllowList: (...args: unknown[]) => mockGetToolAllowList(...args),
    updateToolAllowList: (...args: unknown[]) => mockUpdateToolAllowList(...args),
  },
}));

// Mock MCP gateway service
const mockGetTools = vi.fn();

vi.mock('../../services/mcpGatewayApi', () => ({
  mcpGatewayService: {
    getTools: (...args: unknown[]) => mockGetTools(...args),
  },
}));

// Mock toast
const mockSuccess = vi.fn();
const mockError = vi.fn();
vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({ success: mockSuccess, error: mockError }),
}));

import { ToolAllowListModal } from './ToolAllowListModal';

const defaultAllowList = {
  sub_account_id: 'sub-1',
  allowed_tools: ['weather-lookup', 'file-search'],
};

const defaultCatalog = {
  tools: [
    {
      name: 'weather-lookup',
      description: 'Look up weather data',
      inputSchema: {},
      method: 'GET',
      tags: [],
      version: '1.0',
    },
    {
      name: 'file-search',
      description: 'Search files',
      inputSchema: {},
      method: 'POST',
      tags: [],
      version: '1.0',
    },
    {
      name: 'code-exec',
      description: 'Execute code snippets',
      inputSchema: {},
      method: 'POST',
      tags: [],
      version: '1.0',
    },
  ],
  totalCount: 3,
};

const defaultProps = {
  tenantId: 'oasis-gunters',
  masterId: 'master-1',
  subAccountId: 'sub-1',
  subAccountName: 'Partner Agent',
  isAdmin: true,
  onClose: vi.fn(),
  onSaved: vi.fn(),
};

function renderModal(overrides: Partial<typeof defaultProps> = {}) {
  return renderWithProviders(<ToolAllowListModal {...defaultProps} {...overrides} />);
}

describe('ToolAllowListModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetToolAllowList.mockResolvedValue(defaultAllowList);
    mockGetTools.mockResolvedValue(defaultCatalog);
    mockUpdateToolAllowList.mockResolvedValue({
      sub_account_id: 'sub-1',
      allowed_tools: ['weather-lookup'],
    });
    defaultProps.onClose = vi.fn();
    defaultProps.onSaved = vi.fn();
  });

  it('renders title and sub-account name', async () => {
    renderModal();
    expect(await screen.findByText('Tool Allow-List')).toBeInTheDocument();
    expect(screen.getByText('Partner Agent')).toBeInTheDocument();
  });

  it('shows loading spinner initially', () => {
    mockGetToolAllowList.mockReturnValue(new Promise(() => {}));
    renderModal();
    expect(document.querySelector('.animate-spin')).toBeInTheDocument();
  });

  it('renders checkbox list from catalog', async () => {
    renderModal();
    await waitFor(() => {
      expect(screen.getByText('weather-lookup')).toBeInTheDocument();
    });
    expect(screen.getByText('file-search')).toBeInTheDocument();
    expect(screen.getByText('code-exec')).toBeInTheDocument();
  });

  it('pre-checks currently allowed tools', async () => {
    renderModal();
    await waitFor(() => {
      expect(screen.getByText('weather-lookup')).toBeInTheDocument();
    });
    const checkboxes = screen.getAllByRole('checkbox');
    // weather-lookup and file-search should be checked
    const weatherCb = checkboxes.find((cb) =>
      cb.closest('label')?.textContent?.includes('weather-lookup')
    ) as HTMLInputElement;
    const codeCb = checkboxes.find((cb) =>
      cb.closest('label')?.textContent?.includes('code-exec')
    ) as HTMLInputElement;
    expect(weatherCb.checked).toBe(true);
    expect(codeCb.checked).toBe(false);
  });

  it('calls updateToolAllowList on save', async () => {
    renderModal();
    await waitFor(() => {
      expect(screen.getByText('weather-lookup')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('Save'));
    await waitFor(() => {
      expect(mockUpdateToolAllowList).toHaveBeenCalledWith(
        'oasis-gunters',
        'master-1',
        'sub-1',
        expect.arrayContaining(['weather-lookup', 'file-search'])
      );
    });
    expect(defaultProps.onSaved).toHaveBeenCalled();
    expect(mockSuccess).toHaveBeenCalled();
  });

  it('closes on cancel', async () => {
    renderModal();
    await waitFor(() => {
      expect(screen.getByText('Cancel')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('Cancel'));
    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  it('shows error toast on save failure', async () => {
    mockUpdateToolAllowList.mockRejectedValue(new Error('Network error'));
    renderModal();
    await waitFor(() => {
      expect(screen.getByText('Save')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('Save'));
    await waitFor(() => {
      expect(mockError).toHaveBeenCalledWith('Update failed', 'Network error');
    });
  });

  it('shows fallback chips when catalog unavailable', async () => {
    mockGetTools.mockRejectedValue(new Error('Catalog down'));
    renderModal();
    await waitFor(() => {
      expect(screen.getByText(/catalog unavailable/i)).toBeInTheDocument();
    });
    expect(screen.getByText('weather-lookup')).toBeInTheDocument();
    expect(screen.getByText('file-search')).toBeInTheDocument();
    expect(screen.queryByText('Save')).not.toBeInTheDocument();
  });

  it('shows selected count', async () => {
    renderModal();
    await waitFor(() => {
      expect(screen.getByText('2 tools selected')).toBeInTheDocument();
    });
  });

  describe('admin vs non-admin', () => {
    it('admin: checkboxes are interactive', async () => {
      renderModal({ isAdmin: true });
      await waitFor(() => {
        expect(screen.getByText('weather-lookup')).toBeInTheDocument();
      });
      const checkboxes = screen.getAllByRole('checkbox');
      expect(checkboxes[0]).not.toBeDisabled();
      expect(screen.getByText('Save')).toBeInTheDocument();
    });

    it('non-admin: checkboxes are disabled, no save button', async () => {
      renderModal({ isAdmin: false });
      await waitFor(() => {
        expect(screen.getByText('weather-lookup')).toBeInTheDocument();
      });
      const checkboxes = screen.getAllByRole('checkbox');
      checkboxes.forEach((cb) => expect(cb).toBeDisabled());
      expect(screen.queryByText('Save')).not.toBeInTheDocument();
    });
  });
});
