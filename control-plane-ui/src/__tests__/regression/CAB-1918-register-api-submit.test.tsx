import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createAuthMock } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import { RegisterApiModal } from '../../pages/BackendApis/RegisterApiModal';

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

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

function getForm(): HTMLFormElement {
  return document.querySelector('form')!;
}

describe('regression/CAB-1918', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mockCreateBackendApi.mockResolvedValue({});
  });

  it('submit button is connected to form via form attribute', () => {
    render(<RegisterApiModal {...defaultProps} />);
    const form = getForm();
    const submitBtn = screen.getByRole('button', { name: /register api/i });

    expect(form).toHaveAttribute('id', 'register-api-form');
    expect(submitBtn).toHaveAttribute('form', 'register-api-form');
    expect(submitBtn).toHaveAttribute('type', 'submit');
  });

  it('clicking submit button triggers form submission and API call', async () => {
    const user = userEvent.setup();
    render(<RegisterApiModal {...defaultProps} />);

    await user.type(screen.getByPlaceholderText('petstore-api'), 'test-api');
    await user.type(
      screen.getByPlaceholderText('https://api.example.com/v1'),
      'https://backend.test.com'
    );

    await user.click(screen.getByRole('button', { name: /register api/i }));

    await waitFor(() => {
      expect(mockCreateBackendApi).toHaveBeenCalledWith(
        'tenant-1',
        expect.objectContaining({
          name: 'test-api',
          backend_url: 'https://backend.test.com',
        })
      );
    });
  });
});
