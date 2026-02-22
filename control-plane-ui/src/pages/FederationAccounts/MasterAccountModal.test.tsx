import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, fireEvent } from '@testing-library/react';
import { renderWithProviders } from '../../test/helpers';

// Mock federation service
const mockCreateMasterAccount = vi.fn();

vi.mock('../../services/federationApi', () => ({
  federationService: {
    createMasterAccount: (...args: unknown[]) => mockCreateMasterAccount(...args),
  },
}));

// Mock toast
const mockSuccess = vi.fn();
const mockError = vi.fn();
vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({ success: mockSuccess, error: mockError }),
}));

import { MasterAccountModal } from './MasterAccountModal';

const defaultProps = {
  tenantId: 'oasis-gunters',
  onClose: vi.fn(),
  onCreated: vi.fn(),
};

function renderModal(overrides: Partial<typeof defaultProps> = {}) {
  return renderWithProviders(<MasterAccountModal {...defaultProps} {...overrides} />);
}

describe('MasterAccountModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    defaultProps.onClose = vi.fn();
    defaultProps.onCreated = vi.fn();
    mockCreateMasterAccount.mockResolvedValue({ id: 'master-new', name: 'OASIS Federation' });
  });

  it('renders modal title', () => {
    renderModal();
    expect(screen.getByText('Create Master Account')).toBeInTheDocument();
  });

  it('submit button disabled when name is empty', () => {
    renderModal();
    const submitBtn = screen.getByRole('button', { name: /create/i });
    expect(submitBtn).toBeDisabled();
  });

  it('submit button enabled when name is filled', () => {
    renderModal();
    fireEvent.change(screen.getByPlaceholderText(/Partner Federation/i), {
      target: { value: 'OASIS Federation' },
    });
    expect(screen.getByRole('button', { name: /^create$/i })).not.toBeDisabled();
  });

  it('calls createMasterAccount with correct args on submit', async () => {
    renderModal();
    fireEvent.change(screen.getByPlaceholderText(/Partner Federation/i), {
      target: { value: 'OASIS Federation' },
    });
    fireEvent.change(screen.getByPlaceholderText(/Optional description/i), {
      target: { value: 'Main federation' },
    });
    fireEvent.submit(screen.getByRole('button', { name: /^create$/i }).closest('form')!);
    await waitFor(() => {
      expect(mockCreateMasterAccount).toHaveBeenCalledWith('oasis-gunters', {
        name: 'OASIS Federation',
        description: 'Main federation',
        max_sub_accounts: 10,
      });
    });
  });

  it('shows success toast and calls onCreated on success', async () => {
    renderModal();
    fireEvent.change(screen.getByPlaceholderText(/Partner Federation/i), {
      target: { value: 'OASIS Federation' },
    });
    fireEvent.submit(screen.getByRole('button', { name: /^create$/i }).closest('form')!);
    await waitFor(() => {
      expect(mockSuccess).toHaveBeenCalledWith(
        'Account created',
        'OASIS Federation has been created'
      );
      expect(defaultProps.onCreated).toHaveBeenCalledOnce();
    });
  });

  it('shows error toast on failure', async () => {
    mockCreateMasterAccount.mockRejectedValue(new Error('Server error'));
    renderModal();
    fireEvent.change(screen.getByPlaceholderText(/Partner Federation/i), {
      target: { value: 'OASIS Federation' },
    });
    fireEvent.submit(screen.getByRole('button', { name: /^create$/i }).closest('form')!);
    await waitFor(() => {
      expect(mockError).toHaveBeenCalledWith('Creation failed', 'Server error');
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
    // X button is the first button in the header
    const xBtn = screen
      .getAllByRole('button')
      .find((btn) => btn.querySelector('svg') && !btn.textContent?.trim());
    fireEvent.click(xBtn!);
    expect(defaultProps.onClose).toHaveBeenCalledOnce();
  });

  it('omits description when empty', async () => {
    renderModal();
    fireEvent.change(screen.getByPlaceholderText(/Partner Federation/i), {
      target: { value: 'OASIS Federation' },
    });
    fireEvent.submit(screen.getByRole('button', { name: /^create$/i }).closest('form')!);
    await waitFor(() => {
      expect(mockCreateMasterAccount).toHaveBeenCalledWith('oasis-gunters', {
        name: 'OASIS Federation',
        description: undefined,
        max_sub_accounts: 10,
      });
    });
  });

  it('respects custom max sub-accounts value', async () => {
    renderModal();
    fireEvent.change(screen.getByPlaceholderText(/Partner Federation/i), {
      target: { value: 'OASIS Federation' },
    });
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '25' } });
    fireEvent.submit(screen.getByRole('button', { name: /^create$/i }).closest('form')!);
    await waitFor(() => {
      expect(mockCreateMasterAccount).toHaveBeenCalledWith('oasis-gunters', {
        name: 'OASIS Federation',
        description: undefined,
        max_sub_accounts: 25,
      });
    });
  });
});
