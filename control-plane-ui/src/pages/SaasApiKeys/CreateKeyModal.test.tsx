import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { CreateKeyModal } from './CreateKeyModal';

const mockListBackendApis = vi.fn();
const mockCreateSaasKey = vi.fn();

vi.mock('../../services/backendApisApi', () => ({
  backendApisService: {
    listBackendApis: (...args: unknown[]) => mockListBackendApis(...args),
    createSaasKey: (...args: unknown[]) => mockCreateSaasKey(...args),
  },
}));

const defaultProps = {
  tenantId: 'tenant-1',
  onClose: vi.fn(),
  onCreated: vi.fn(),
};

function renderModal(props = defaultProps) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    React.createElement(
      QueryClientProvider,
      { client: queryClient },
      React.createElement(CreateKeyModal, props)
    )
  );
}

function getForm(): HTMLFormElement {
  return document.querySelector('form')!;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockListBackendApis.mockResolvedValue({
    items: [
      { id: 'api-1', name: 'petstore', display_name: 'Petstore API', status: 'active' },
      { id: 'api-2', name: 'weather', display_name: 'Weather API', status: 'active' },
      { id: 'api-3', name: 'draft-api', display_name: 'Draft API', status: 'draft' },
    ],
    total: 3,
  });
  mockCreateSaasKey.mockResolvedValue({
    id: 'key-1',
    name: 'test-key',
    key: 'sk_test_abc123',
  });
});

describe('CreateKeyModal', () => {
  it('renders form with required fields', () => {
    renderModal();
    expect(screen.getByText('Create API Key')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('my-api-key')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Key for production use')).toBeInTheDocument();
  });

  it('loads and shows active backend APIs as checkboxes', async () => {
    renderModal();

    await waitFor(() => {
      expect(screen.getByText('Petstore API')).toBeInTheDocument();
      expect(screen.getByText('Weather API')).toBeInTheDocument();
    });
    // Draft API should NOT appear (only active APIs shown)
    expect(screen.queryByText('Draft API')).not.toBeInTheDocument();
  });

  it('shows empty message when no active APIs', async () => {
    mockListBackendApis.mockResolvedValue({ items: [], total: 0 });
    renderModal();

    await waitFor(() => {
      expect(screen.getByText(/No active backend APIs available/)).toBeInTheDocument();
    });
  });

  it('toggles API checkbox selection', async () => {
    const user = userEvent.setup();
    renderModal();

    await waitFor(() => {
      expect(screen.getByText('Petstore API')).toBeInTheDocument();
    });

    const checkboxes = screen.getAllByRole('checkbox');
    await user.click(checkboxes[0]);
    expect(checkboxes[0]).toBeChecked();

    await user.click(checkboxes[0]);
    expect(checkboxes[0]).not.toBeChecked();
  });

  it('calls onClose when cancel clicked', async () => {
    const user = userEvent.setup();
    renderModal();

    await user.click(screen.getByText('Cancel'));
    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  it('submits form with name and selected APIs', async () => {
    const user = userEvent.setup();
    renderModal();

    await user.type(screen.getByPlaceholderText('my-api-key'), 'production-key');

    await waitFor(() => {
      expect(screen.getByText('Petstore API')).toBeInTheDocument();
    });

    const checkboxes = screen.getAllByRole('checkbox');
    await user.click(checkboxes[0]);

    // Submit form directly (button is outside form element)
    fireEvent.submit(getForm());

    await waitFor(() => {
      expect(mockCreateSaasKey).toHaveBeenCalledWith(
        'tenant-1',
        expect.objectContaining({
          name: 'production-key',
          allowed_backend_api_ids: ['api-1'],
        })
      );
    });
  });

  it('calls onCreated with result after successful submit', async () => {
    const user = userEvent.setup();
    renderModal();

    await user.type(screen.getByPlaceholderText('my-api-key'), 'test-key');

    fireEvent.submit(getForm());

    await waitFor(() => {
      expect(defaultProps.onCreated).toHaveBeenCalledWith(
        expect.objectContaining({ key: 'sk_test_abc123' })
      );
    });
  });

  it('shows error on submit failure', async () => {
    mockCreateSaasKey.mockRejectedValue(new Error('Rate limit exceeded'));
    const user = userEvent.setup();
    renderModal();

    await user.type(screen.getByPlaceholderText('my-api-key'), 'test-key');

    fireEvent.submit(getForm());

    await waitFor(() => {
      expect(screen.getByText('Rate limit exceeded')).toBeInTheDocument();
    });
  });

  it('shows loading state during submit', async () => {
    mockCreateSaasKey.mockImplementation(() => new Promise(() => {}));
    const user = userEvent.setup();
    renderModal();

    await user.type(screen.getByPlaceholderText('my-api-key'), 'test-key');

    fireEvent.submit(getForm());

    await waitFor(() => {
      expect(screen.getByText('Creating...')).toBeInTheDocument();
    });
  });

  it('passes rate limit when set', async () => {
    const user = userEvent.setup();
    renderModal();

    await user.type(screen.getByPlaceholderText('my-api-key'), 'test-key');
    await user.type(screen.getByPlaceholderText('No limit'), '100');

    fireEvent.submit(getForm());

    await waitFor(() => {
      expect(mockCreateSaasKey).toHaveBeenCalledWith(
        'tenant-1',
        expect.objectContaining({
          rate_limit_rpm: 100,
        })
      );
    });
  });
});
