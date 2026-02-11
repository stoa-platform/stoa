/**
 * CreateContractPage Tests - CAB-1133
 *
 * Tests for the create contract form page.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders, createAuthMock } from '../../test/helpers';
import { CreateContractPage } from '../contracts/CreateContractPage';

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

// Mock usePublishContract hook
const mockUsePublishContract = vi.fn();

vi.mock('../../hooks/useContracts', () => ({
  usePublishContract: (options: { onSuccess?: () => void; onError?: () => void }) =>
    mockUsePublishContract(options),
}));

// Mock PublishSuccessModal
vi.mock('../../components/contracts/PublishSuccessModal', () => ({
  PublishSuccessModal: ({
    isOpen,
    data,
  }: {
    isOpen: boolean;
    data: { contract: { id: string } } | null;
  }) =>
    isOpen && data ? (
      <div data-testid="publish-success-modal">Success: {data.contract.id}</div>
    ) : null,
}));

describe('CreateContractPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
  });

  it('renders form with required fields', async () => {
    mockUsePublishContract.mockReturnValue({ mutate: vi.fn(), isPending: false });

    renderWithProviders(<CreateContractPage />);

    await waitFor(() => {
      expect(screen.getByLabelText(/Contract Name/)).toBeInTheDocument();
      expect(screen.getByLabelText(/Display Name/)).toBeInTheDocument();
      expect(screen.getByLabelText(/Description/)).toBeInTheDocument();
      expect(screen.getByLabelText(/Version/)).toBeInTheDocument();
      expect(screen.getByLabelText(/OpenAPI Spec URL/)).toBeInTheDocument();
    });
  });

  it('renders Cancel button that navigates back', async () => {
    const user = userEvent.setup();
    mockUsePublishContract.mockReturnValue({ mutate: vi.fn(), isPending: false });

    renderWithProviders(<CreateContractPage />);

    const cancelButton = screen.getByRole('button', { name: /Cancel/ });
    await user.click(cancelButton);

    expect(mockNavigate).toHaveBeenCalledWith('/contracts');
  });

  it('renders submit button', async () => {
    mockUsePublishContract.mockReturnValue({ mutate: vi.fn(), isPending: false });

    renderWithProviders(<CreateContractPage />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Publish Contract/ })).toBeInTheDocument();
    });
  });

  it('disables submit button when name is empty', async () => {
    mockUsePublishContract.mockReturnValue({ mutate: vi.fn(), isPending: false });

    renderWithProviders(<CreateContractPage />);

    await waitFor(() => {
      const submitButton = screen.getByRole('button', { name: /Publish Contract/ });
      expect(submitButton).toBeDisabled();
    });
  });

  it('enables submit button when name is filled', async () => {
    const user = userEvent.setup();
    mockUsePublishContract.mockReturnValue({ mutate: vi.fn(), isPending: false });

    renderWithProviders(<CreateContractPage />);

    const nameInput = screen.getByLabelText(/Contract Name/);
    await user.type(nameInput, 'test-api');

    await waitFor(() => {
      const submitButton = screen.getByRole('button', { name: /Publish Contract/ });
      expect(submitButton).not.toBeDisabled();
    });
  });

  it('shows "Publishing..." when submitting', async () => {
    mockUsePublishContract.mockReturnValue({ mutate: vi.fn(), isPending: true });

    renderWithProviders(<CreateContractPage />);

    await waitFor(() => {
      expect(screen.getByText('Publishing...')).toBeInTheDocument();
    });
  });

  it('calls mutate with form data on submit', async () => {
    const user = userEvent.setup();
    const mutateMock = vi.fn();
    mockUsePublishContract.mockReturnValue({ mutate: mutateMock, isPending: false });

    renderWithProviders(<CreateContractPage />);

    const nameInput = screen.getByLabelText(/Contract Name/);
    await user.type(nameInput, 'orders-api');

    const displayNameInput = screen.getByLabelText(/Display Name/);
    await user.type(displayNameInput, 'Orders API');

    const submitButton = screen.getByRole('button', { name: /Publish Contract/ });
    await user.click(submitButton);

    await waitFor(() => {
      expect(mutateMock).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'orders-api',
          display_name: 'Orders API',
        })
      );
    });
  });
});
