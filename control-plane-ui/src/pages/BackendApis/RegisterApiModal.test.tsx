import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RegisterApiModal } from './RegisterApiModal';

const mockCreateBackendApi = vi.fn();

vi.mock('../../services/backendApisApi', () => ({
  backendApisService: {
    createBackendApi: (...args: unknown[]) => mockCreateBackendApi(...args),
  },
}));

const mockToast = { success: vi.fn(), error: vi.fn(), info: vi.fn() };
vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => mockToast,
}));

const defaultProps = {
  tenantId: 'tenant-1',
  onClose: vi.fn(),
  onCreated: vi.fn(),
};

beforeEach(() => {
  vi.clearAllMocks();
  mockCreateBackendApi.mockResolvedValue({});
});

function getForm(): HTMLFormElement {
  return document.querySelector('form')!;
}

describe('RegisterApiModal', () => {
  it('renders form with required fields', () => {
    render(<RegisterApiModal {...defaultProps} />);
    expect(screen.getByText('Register Backend API')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('petstore-api')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('https://api.example.com/v1')).toBeInTheDocument();
  });

  it('renders auth type selector with all options', () => {
    render(<RegisterApiModal {...defaultProps} />);
    const select = screen.getByDisplayValue('None');
    expect(select).toBeInTheDocument();
    // Check options exist
    const options = select.querySelectorAll('option');
    expect(options.length).toBe(5);
  });

  it('shows API Key config fields when selected', async () => {
    const user = userEvent.setup();
    render(<RegisterApiModal {...defaultProps} />);

    await user.selectOptions(screen.getByDisplayValue('None'), 'api_key');
    expect(screen.getByText('API Key Configuration')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('X-API-Key')).toBeInTheDocument();
  });

  it('shows Bearer Token field when selected', async () => {
    const user = userEvent.setup();
    render(<RegisterApiModal {...defaultProps} />);

    await user.selectOptions(screen.getByDisplayValue('None'), 'bearer');
    expect(screen.getByPlaceholderText('Enter bearer token')).toBeInTheDocument();
  });

  it('shows Basic Auth fields when selected', async () => {
    const user = userEvent.setup();
    render(<RegisterApiModal {...defaultProps} />);

    await user.selectOptions(screen.getByDisplayValue('None'), 'basic');
    expect(screen.getByText('Basic Auth Credentials')).toBeInTheDocument();
  });

  it('shows OAuth2 fields when selected', async () => {
    const user = userEvent.setup();
    render(<RegisterApiModal {...defaultProps} />);

    await user.selectOptions(screen.getByDisplayValue('None'), 'oauth2_cc');
    // The heading appears alongside the option text — use getByRole heading
    expect(screen.getByPlaceholderText('https://auth.example.com/oauth/token')).toBeInTheDocument();
  });

  it('calls onClose when cancel clicked', async () => {
    const user = userEvent.setup();
    render(<RegisterApiModal {...defaultProps} />);

    await user.click(screen.getByText('Cancel'));
    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  it('submits form with correct payload', async () => {
    const user = userEvent.setup();
    render(<RegisterApiModal {...defaultProps} />);

    await user.type(screen.getByPlaceholderText('petstore-api'), 'my-api');
    await user.type(
      screen.getByPlaceholderText('https://api.example.com/v1'),
      'https://api.test.com'
    );

    // Submit the form directly (button is outside form in the DOM)
    fireEvent.submit(getForm());

    await waitFor(() => {
      expect(mockCreateBackendApi).toHaveBeenCalledWith(
        'tenant-1',
        expect.objectContaining({
          name: 'my-api',
          backend_url: 'https://api.test.com',
          auth_type: 'none',
        })
      );
    });
  });

  it('shows error on submit failure', async () => {
    mockCreateBackendApi.mockRejectedValue(new Error('Network error'));
    const user = userEvent.setup();
    render(<RegisterApiModal {...defaultProps} />);

    await user.type(screen.getByPlaceholderText('petstore-api'), 'my-api');
    await user.type(
      screen.getByPlaceholderText('https://api.example.com/v1'),
      'https://api.test.com'
    );

    fireEvent.submit(getForm());

    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });
  });

  it('calls onCreated after successful submit', async () => {
    const user = userEvent.setup();
    render(<RegisterApiModal {...defaultProps} />);

    await user.type(screen.getByPlaceholderText('petstore-api'), 'my-api');
    await user.type(
      screen.getByPlaceholderText('https://api.example.com/v1'),
      'https://api.test.com'
    );

    fireEvent.submit(getForm());

    await waitFor(() => {
      expect(defaultProps.onCreated).toHaveBeenCalled();
    });
  });

  it('shows loading state during submit', async () => {
    mockCreateBackendApi.mockImplementation(() => new Promise(() => {}));
    const user = userEvent.setup();
    render(<RegisterApiModal {...defaultProps} />);

    await user.type(screen.getByPlaceholderText('petstore-api'), 'my-api');
    await user.type(
      screen.getByPlaceholderText('https://api.example.com/v1'),
      'https://api.test.com'
    );

    fireEvent.submit(getForm());

    await waitFor(() => {
      expect(screen.getByText('Registering...')).toBeInTheDocument();
    });
  });
});
