import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, fireEvent, within } from '@testing-library/react';
import { renderWithProviders } from '../../test/helpers';
import { ToastProvider } from '@stoa/shared/components/Toast';
import { MasterAccountModal } from './MasterAccountModal';
import { SubAccountModal } from './SubAccountModal';

const mockCreateMasterAccount = vi.fn();
const mockCreateSubAccount = vi.fn();

vi.mock('../../services/federationApi', () => ({
  federationService: {
    createMasterAccount: (...args: unknown[]) => mockCreateMasterAccount(...args),
    createSubAccount: (...args: unknown[]) => mockCreateSubAccount(...args),
  },
}));

function submit(name: RegExp | string) {
  fireEvent.submit(screen.getByRole('button', { name }).closest('form')!);
}

describe('account modals keep submission errors inside the open dialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows a master-account API error in the dialog and the live region', async () => {
    mockCreateMasterAccount.mockRejectedValue(new Error('Server error'));
    renderWithProviders(
      <ToastProvider>
        <MasterAccountModal tenantId="oasis-gunters" onClose={vi.fn()} onCreated={vi.fn()} />
      </ToastProvider>
    );
    fireEvent.change(screen.getByPlaceholderText(/Partner Federation/i), {
      target: { value: 'OASIS Federation' },
    });
    submit(/^create$/i);

    const dialog = screen.getByRole('dialog', { name: 'Create Master Account' });
    await waitFor(() => {
      expect(
        within(dialog)
          .getAllByRole('alert')
          .some((alert) => alert.textContent?.includes('Server error'))
      ).toBe(true);
    });
    const notifications = within(dialog).getByLabelText('Notifications');
    expect(notifications).toHaveAttribute('aria-live', 'polite');
    expect(
      within(notifications).getByRole('button', { name: 'Dismiss notification' })
    ).toBeInTheDocument();
    expect(dialog.contains(notifications)).toBe(true);
  });

  it('shows a sub-account API error in the dialog and the live region', async () => {
    mockCreateSubAccount.mockRejectedValue(new Error('Quota exceeded'));
    renderWithProviders(
      <ToastProvider>
        <SubAccountModal
          tenantId="oasis-gunters"
          masterId="master-1"
          onClose={vi.fn()}
          onCreated={vi.fn()}
        />
      </ToastProvider>
    );
    fireEvent.change(screen.getByPlaceholderText(/Partner Agent/i), {
      target: { value: 'New Agent' },
    });
    submit(/^create$/i);

    const dialog = screen.getByRole('dialog', { name: 'Create Sub-Account' });
    await waitFor(() => {
      expect(
        within(dialog)
          .getAllByRole('alert')
          .some((alert) => alert.textContent?.includes('Quota exceeded'))
      ).toBe(true);
    });
    expect(
      within(dialog).getByRole('button', { name: 'Dismiss notification' })
    ).toBeInTheDocument();
  });
});
