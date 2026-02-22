import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, fireEvent } from '@testing-library/react';
import { renderWithProviders } from '../../test/helpers';

// Mock federation service
const mockCreateSubAccount = vi.fn();

vi.mock('../../services/federationApi', () => ({
  federationService: {
    createSubAccount: (...args: unknown[]) => mockCreateSubAccount(...args),
  },
}));

// Mock toast
const mockSuccess = vi.fn();
const mockError = vi.fn();
vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({ success: mockSuccess, error: mockError }),
}));

import { SubAccountModal } from './SubAccountModal';

const mockResult = {
  id: 'sub-new',
  master_id: 'master-1',
  name: 'Partner Agent',
  api_key: 'sk-test-new-key',
};

const defaultProps = {
  tenantId: 'oasis-gunters',
  masterId: 'master-1',
  onClose: vi.fn(),
  onCreated: vi.fn(),
};

function renderModal(overrides: Partial<typeof defaultProps> = {}) {
  return renderWithProviders(<SubAccountModal {...defaultProps} {...overrides} />);
}

describe('SubAccountModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    defaultProps.onClose = vi.fn();
    defaultProps.onCreated = vi.fn();
    mockCreateSubAccount.mockResolvedValue(mockResult);
  });

  it('renders modal title', () => {
    renderModal();
    expect(screen.getByText('Create Sub-Account')).toBeInTheDocument();
  });

  it('submit button disabled when name is empty', () => {
    renderModal();
    const submitBtn = screen.getByRole('button', { name: /^create$/i });
    expect(submitBtn).toBeDisabled();
  });

  it('submit button enabled when name is filled', () => {
    renderModal();
    fireEvent.change(screen.getByPlaceholderText(/Partner Agent/i), {
      target: { value: 'New Agent' },
    });
    expect(screen.getByRole('button', { name: /^create$/i })).not.toBeDisabled();
  });

  it('calls createSubAccount with correct args on submit', async () => {
    renderModal();
    fireEvent.change(screen.getByPlaceholderText(/Partner Agent/i), {
      target: { value: 'New Agent' },
    });
    fireEvent.change(screen.getByPlaceholderText(/Optional description/i), {
      target: { value: 'Agent for partner' },
    });
    fireEvent.submit(screen.getByRole('button', { name: /^create$/i }).closest('form')!);
    await waitFor(() => {
      expect(mockCreateSubAccount).toHaveBeenCalledWith('oasis-gunters', 'master-1', {
        name: 'New Agent',
        description: 'Agent for partner',
      });
    });
  });

  it('shows success toast and calls onCreated with result on success', async () => {
    renderModal();
    fireEvent.change(screen.getByPlaceholderText(/Partner Agent/i), {
      target: { value: 'New Agent' },
    });
    fireEvent.submit(screen.getByRole('button', { name: /^create$/i }).closest('form')!);
    await waitFor(() => {
      expect(mockSuccess).toHaveBeenCalledWith('Sub-account created', 'New Agent has been created');
      expect(defaultProps.onCreated).toHaveBeenCalledWith(mockResult);
    });
  });

  it('shows error toast on failure', async () => {
    mockCreateSubAccount.mockRejectedValue(new Error('Quota exceeded'));
    renderModal();
    fireEvent.change(screen.getByPlaceholderText(/Partner Agent/i), {
      target: { value: 'New Agent' },
    });
    fireEvent.submit(screen.getByRole('button', { name: /^create$/i }).closest('form')!);
    await waitFor(() => {
      expect(mockError).toHaveBeenCalledWith('Creation failed', 'Quota exceeded');
    });
    expect(defaultProps.onCreated).not.toHaveBeenCalled();
  });

  it('calls onClose when cancel button clicked', () => {
    renderModal();
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(defaultProps.onClose).toHaveBeenCalledOnce();
  });

  it('calls onClose when X button clicked', () => {
    renderModal();
    const xBtn = screen
      .getAllByRole('button')
      .find((btn) => btn.querySelector('svg') && !btn.textContent?.trim());
    fireEvent.click(xBtn!);
    expect(defaultProps.onClose).toHaveBeenCalledOnce();
  });

  it('omits description when blank', async () => {
    renderModal();
    fireEvent.change(screen.getByPlaceholderText(/Partner Agent/i), {
      target: { value: 'New Agent' },
    });
    fireEvent.submit(screen.getByRole('button', { name: /^create$/i }).closest('form')!);
    await waitFor(() => {
      expect(mockCreateSubAccount).toHaveBeenCalledWith('oasis-gunters', 'master-1', {
        name: 'New Agent',
        description: undefined,
      });
    });
  });

  it('trims whitespace from name before submitting', async () => {
    renderModal();
    fireEvent.change(screen.getByPlaceholderText(/Partner Agent/i), {
      target: { value: '  Trimmed Agent  ' },
    });
    fireEvent.submit(screen.getByRole('button', { name: /^create$/i }).closest('form')!);
    await waitFor(() => {
      expect(mockCreateSubAccount).toHaveBeenCalledWith('oasis-gunters', 'master-1', {
        name: 'Trimmed Agent',
        description: undefined,
      });
    });
  });
});
