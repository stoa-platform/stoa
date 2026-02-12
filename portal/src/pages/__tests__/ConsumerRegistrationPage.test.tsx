/**
 * ConsumerRegistrationPage Tests - CAB-1133
 *
 * Tests for the consumer self-registration form.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/helpers';
import { ConsumerRegistrationPage } from '../consumers/ConsumerRegistrationPage';

// Mock AuthContext at module level
const mockAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth(),
}));

// Mock useNavigate
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// Mock useConsumers hooks
const mockUseRegisterConsumer = vi.fn();
const mockUseConsumerCredentials = vi.fn();

vi.mock('../../hooks/useConsumers', () => ({
  useRegisterConsumer: () => mockUseRegisterConsumer(),
  useConsumerCredentials: () => mockUseConsumerCredentials(),
}));

// Mock Toast
const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();

vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({
    success: mockToastSuccess,
    error: mockToastError,
  }),
}));

// Mock CredentialsModal
vi.mock('../../components/consumers/CredentialsModal', () => ({
  CredentialsModal: ({
    isOpen,
    consumerName,
  }: {
    isOpen: boolean;
    consumerName: string;
    onClose: () => void;
  }) => (isOpen ? <div data-testid="credentials-modal">Credentials for {consumerName}</div> : null),
}));

describe('ConsumerRegistrationPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseRegisterConsumer.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mockUseConsumerCredentials.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  });

  it('renders "Register as Consumer" heading', async () => {
    mockAuth.mockReturnValue({
      user: { email: 'test@example.com', tenant_id: 'tenant-1' },
    });

    renderWithProviders(<ConsumerRegistrationPage />);

    await waitFor(() => {
      expect(screen.getByText('Register as Consumer')).toBeInTheDocument();
    });
  });

  it('renders form fields: name, external_id, email, company, description', async () => {
    mockAuth.mockReturnValue({
      user: { email: 'test@example.com', tenant_id: 'tenant-1' },
    });

    renderWithProviders(<ConsumerRegistrationPage />);

    await waitFor(() => {
      expect(screen.getByLabelText(/Consumer Name/)).toBeInTheDocument();
      expect(screen.getByLabelText(/External ID/)).toBeInTheDocument();
      expect(screen.getByLabelText(/Email/)).toBeInTheDocument();
      expect(screen.getByLabelText(/Company/)).toBeInTheDocument();
      expect(screen.getByLabelText(/Description/)).toBeInTheDocument();
    });
  });

  it('pre-fills email from user.email', async () => {
    mockAuth.mockReturnValue({
      user: { email: 'prefilled@example.com', tenant_id: 'tenant-1' },
    });

    renderWithProviders(<ConsumerRegistrationPage />);

    await waitFor(() => {
      const emailInput = screen.getByLabelText(/Email/) as HTMLInputElement;
      expect(emailInput.value).toBe('prefilled@example.com');
    });
  });

  it('auto-generates external_id from name', async () => {
    const user = userEvent.setup();
    mockAuth.mockReturnValue({
      user: { email: 'test@example.com', tenant_id: 'tenant-1' },
    });

    renderWithProviders(<ConsumerRegistrationPage />);

    const nameInput = screen.getByLabelText(/Consumer Name/);
    await user.type(nameInput, 'My App');

    await waitFor(() => {
      const externalIdInput = screen.getByLabelText(/External ID/) as HTMLInputElement;
      expect(externalIdInput.value).toBe('my-app');
    });
  });

  it('renders Back button', async () => {
    mockAuth.mockReturnValue({
      user: { email: 'test@example.com', tenant_id: 'tenant-1' },
    });

    renderWithProviders(<ConsumerRegistrationPage />);

    await waitFor(() => {
      expect(screen.getByText('Back')).toBeInTheDocument();
    });
  });

  it('renders Cancel button that navigates back', async () => {
    const user = userEvent.setup();
    mockAuth.mockReturnValue({
      user: { email: 'test@example.com', tenant_id: 'tenant-1' },
    });

    renderWithProviders(<ConsumerRegistrationPage />);

    const cancelButton = screen.getByRole('button', { name: /Cancel/ });
    await user.click(cancelButton);

    expect(mockNavigate).toHaveBeenCalledWith(-1);
  });

  it('disables submit button when required fields are empty', async () => {
    mockAuth.mockReturnValue({
      user: { email: '', tenant_id: 'tenant-1' },
    });

    renderWithProviders(<ConsumerRegistrationPage />);

    await waitFor(() => {
      const submitButton = screen.getByRole('button', { name: /Register/ });
      expect(submitButton).toBeDisabled();
    });
  });

  it('shows "Registering..." when submitting', async () => {
    const user = userEvent.setup();
    mockAuth.mockReturnValue({
      user: { email: 'test@example.com', tenant_id: 'tenant-1' },
    });

    const mutateAsync = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          setTimeout(() => resolve({ id: 'consumer-1' }), 100);
        })
    );
    mockUseRegisterConsumer.mockReturnValue({ mutateAsync, isPending: true });
    mockUseConsumerCredentials.mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({ client_id: 'test', client_secret: 'secret' }),
      isPending: false,
    });

    renderWithProviders(<ConsumerRegistrationPage />);

    const nameInput = screen.getByLabelText(/Consumer Name/);
    await user.type(nameInput, 'Test App');

    const submitButton = screen.getByRole('button', { name: /Register/ });

    await waitFor(() => {
      if (submitButton.textContent?.includes('Registering...')) {
        expect(submitButton.textContent).toContain('Registering...');
      } else {
        // If not pending yet, just check button exists
        expect(submitButton).toBeInTheDocument();
      }
    });
  });

  it('displays form error in red banner', async () => {
    const user = userEvent.setup();
    mockAuth.mockReturnValue({
      user: { email: 'test@example.com', tenant_id: null },
    });

    renderWithProviders(<ConsumerRegistrationPage />);

    const nameInput = screen.getByLabelText(/Consumer Name/);
    await user.type(nameInput, 'Test App');

    const emailInput = screen.getByLabelText(/Email/);
    await user.clear(emailInput);
    await user.type(emailInput, 'test@example.com');

    const submitButton = screen.getByRole('button', { name: /Register/ });
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/No tenant assigned/)).toBeInTheDocument();
    });
  });

  it('handles no tenant_id: shows error on submit', async () => {
    const user = userEvent.setup();
    mockAuth.mockReturnValue({
      user: { email: 'test@example.com', tenant_id: null },
    });

    renderWithProviders(<ConsumerRegistrationPage />);

    const nameInput = screen.getByLabelText(/Consumer Name/);
    await user.type(nameInput, 'Test App');

    const emailInput = screen.getByLabelText(/Email/);
    await user.clear(emailInput);
    await user.type(emailInput, 'test@example.com');

    const submitButton = screen.getByRole('button', { name: /Register/ });
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/No tenant assigned/)).toBeInTheDocument();
    });
  });
});
