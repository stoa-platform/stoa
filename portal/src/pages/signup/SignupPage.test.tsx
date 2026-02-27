/**
 * SignupPage Tests (CAB-1548)
 *
 * Covers: render, form validation, slug generation, API success,
 * API errors (409/429/generic/network), loading state, success state,
 * plan selection, optional fields.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SignupPage } from './SignupPage';

// Mock signup service
const mockSignup = vi.fn();

vi.mock('../../services/signup', () => ({
  signupService: {
    signup: (...args: unknown[]) => mockSignup(...args),
    getStatus: vi.fn(),
  },
}));

// Mock StoaLogo
vi.mock('@stoa/shared/components/StoaLogo', () => ({
  StoaLogo: () => <div data-testid="stoa-logo">STOA</div>,
}));

function renderSignup() {
  return render(
    <MemoryRouter initialEntries={['/signup']}>
      <SignupPage />
    </MemoryRouter>
  );
}

const mockSignupResponse = {
  tenant_id: 'tenant-abc123',
  status: 'provisioning',
  plan: 'trial',
  poll_url: '/v1/self-service/tenants/tenant-abc123/status',
};

// ============ Rendering ============

describe('SignupPage — rendering', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSignup.mockResolvedValue(mockSignupResponse);
  });

  it('renders the signup form with all fields', () => {
    renderSignup();
    expect(screen.getByText('Create your organization')).toBeInTheDocument();
    expect(screen.getByLabelText('Organization name')).toBeInTheDocument();
    expect(screen.getByLabelText('Email')).toBeInTheDocument();
    expect(screen.getByLabelText('Company')).toBeInTheDocument();
    expect(screen.getByLabelText('Invite code')).toBeInTheDocument();
    expect(screen.getByText('Create Organization')).toBeInTheDocument();
  });

  it('renders plan selection with trial and standard options', () => {
    renderSignup();
    expect(screen.getByLabelText('Trial plan')).toBeInTheDocument();
    expect(screen.getByLabelText('Standard plan')).toBeInTheDocument();
  });

  it('renders sign-in link and ToS link', () => {
    renderSignup();
    expect(screen.getByText('Already have an account?')).toBeInTheDocument();
    expect(screen.getByText('Sign in')).toBeInTheDocument();
    expect(screen.getByText('Terms of Service')).toBeInTheDocument();
  });

  it('renders StoaLogo', () => {
    renderSignup();
    expect(screen.getByTestId('stoa-logo')).toBeInTheDocument();
  });
});

// ============ Validation ============

describe('SignupPage — validation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSignup.mockResolvedValue(mockSignupResponse);
  });

  it('disables submit button when form is empty', () => {
    renderSignup();
    expect(screen.getByText('Create Organization')).toBeDisabled();
  });

  it('enables submit button with valid inputs', () => {
    renderSignup();
    fireEvent.change(screen.getByLabelText('Organization name'), {
      target: { value: 'Acme Corp' },
    });
    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'test@acme.com' },
    });
    expect(screen.getByText('Create Organization')).not.toBeDisabled();
  });

  it('keeps submit disabled with invalid email', () => {
    renderSignup();
    fireEvent.change(screen.getByLabelText('Organization name'), {
      target: { value: 'Acme Corp' },
    });
    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'not-an-email' },
    });
    expect(screen.getByText('Create Organization')).toBeDisabled();
  });

  it('keeps submit disabled with name too short', () => {
    renderSignup();
    fireEvent.change(screen.getByLabelText('Organization name'), {
      target: { value: 'A' },
    });
    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'test@acme.com' },
    });
    expect(screen.getByText('Create Organization')).toBeDisabled();
  });
});

// ============ Slug Generation ============

describe('SignupPage — slug generation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows slug preview when name is entered', () => {
    renderSignup();
    fireEvent.change(screen.getByLabelText('Organization name'), {
      target: { value: 'My Cool Org' },
    });
    expect(screen.getByText('my-cool-org')).toBeInTheDocument();
  });

  it('strips special characters from slug', () => {
    renderSignup();
    fireEvent.change(screen.getByLabelText('Organization name'), {
      target: { value: '  Hello World!!!  ' },
    });
    expect(screen.getByText('hello-world')).toBeInTheDocument();
  });

  it('does not show slug when name is empty', () => {
    renderSignup();
    expect(screen.queryByText('Slug:')).not.toBeInTheDocument();
  });
});

// ============ API Integration ============

describe('SignupPage — API integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSignup.mockResolvedValue(mockSignupResponse);
  });

  it('submits form and shows success state', async () => {
    renderSignup();

    fireEvent.change(screen.getByLabelText('Organization name'), {
      target: { value: 'Acme Corp' },
    });
    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'test@acme.com' },
    });
    fireEvent.click(screen.getByText('Create Organization'));

    await waitFor(() => {
      expect(screen.getByText('Welcome to STOA!')).toBeInTheDocument();
    });

    expect(mockSignup).toHaveBeenCalledWith({
      name: 'acme-corp',
      display_name: 'Acme Corp',
      owner_email: 'test@acme.com',
      plan: 'trial',
    });
  });

  it('shows success details after signup', async () => {
    renderSignup();

    fireEvent.change(screen.getByLabelText('Organization name'), {
      target: { value: 'Acme Corp' },
    });
    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'test@acme.com' },
    });
    fireEvent.click(screen.getByText('Create Organization'));

    await waitFor(() => {
      expect(screen.getByText('tenant-abc123')).toBeInTheDocument();
      expect(screen.getByText('trial')).toBeInTheDocument();
      expect(screen.getByText('provisioning')).toBeInTheDocument();
    });
  });

  it('sends optional fields when provided', async () => {
    renderSignup();

    fireEvent.change(screen.getByLabelText('Organization name'), {
      target: { value: 'Acme Corp' },
    });
    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'test@acme.com' },
    });
    fireEvent.change(screen.getByLabelText('Company'), {
      target: { value: 'Acme Industries' },
    });
    fireEvent.change(screen.getByLabelText('Invite code'), {
      target: { value: 'BETA2026' },
    });
    fireEvent.click(screen.getByLabelText('Standard plan'));
    fireEvent.click(screen.getByText('Create Organization'));

    await waitFor(() => {
      expect(mockSignup).toHaveBeenCalledWith({
        name: 'acme-corp',
        display_name: 'Acme Corp',
        owner_email: 'test@acme.com',
        company: 'Acme Industries',
        plan: 'standard',
        invite_code: 'BETA2026',
      });
    });
  });

  it('shows loading state during submission', async () => {
    mockSignup.mockImplementation(() => new Promise(() => {}));

    renderSignup();

    fireEvent.change(screen.getByLabelText('Organization name'), {
      target: { value: 'Acme Corp' },
    });
    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'test@acme.com' },
    });
    fireEvent.click(screen.getByText('Create Organization'));

    expect(screen.getByText('Creating organization...')).toBeInTheDocument();
  });

  it('includes Go to Portal link on success', async () => {
    renderSignup();

    fireEvent.change(screen.getByLabelText('Organization name'), {
      target: { value: 'Acme Corp' },
    });
    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'test@acme.com' },
    });
    fireEvent.click(screen.getByText('Create Organization'));

    await waitFor(() => {
      expect(screen.getByText('Go to Portal')).toBeInTheDocument();
    });
  });
});

// ============ Error Handling ============

describe('SignupPage — error handling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows 409 conflict error', async () => {
    mockSignup.mockRejectedValue({
      response: { status: 409, data: { detail: 'Conflict' } },
    });

    renderSignup();

    fireEvent.change(screen.getByLabelText('Organization name'), {
      target: { value: 'Acme Corp' },
    });
    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'test@acme.com' },
    });
    fireEvent.click(screen.getByText('Create Organization'));

    await waitFor(() => {
      expect(screen.getByText(/already exists/)).toBeInTheDocument();
    });
  });

  it('shows 429 rate limit error', async () => {
    mockSignup.mockRejectedValue({
      response: { status: 429, data: {} },
    });

    renderSignup();

    fireEvent.change(screen.getByLabelText('Organization name'), {
      target: { value: 'Acme Corp' },
    });
    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'test@acme.com' },
    });
    fireEvent.click(screen.getByText('Create Organization'));

    await waitFor(() => {
      expect(screen.getByText(/Too many signup attempts/)).toBeInTheDocument();
    });
  });

  it('shows generic API error with detail message', async () => {
    mockSignup.mockRejectedValue({
      response: { status: 400, data: { detail: 'Invalid invite code' } },
    });

    renderSignup();

    fireEvent.change(screen.getByLabelText('Organization name'), {
      target: { value: 'Acme Corp' },
    });
    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'test@acme.com' },
    });
    fireEvent.click(screen.getByText('Create Organization'));

    await waitFor(() => {
      expect(screen.getByText('Invalid invite code')).toBeInTheDocument();
    });
  });

  it('shows network error', async () => {
    mockSignup.mockRejectedValue(new Error('Network Error'));

    renderSignup();

    fireEvent.change(screen.getByLabelText('Organization name'), {
      target: { value: 'Acme Corp' },
    });
    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'test@acme.com' },
    });
    fireEvent.click(screen.getByText('Create Organization'));

    await waitFor(() => {
      expect(screen.getByText(/Unable to connect/)).toBeInTheDocument();
    });
  });

  it('shows error with role=alert for accessibility', async () => {
    mockSignup.mockRejectedValue({
      response: { status: 500, data: {} },
    });

    renderSignup();

    fireEvent.change(screen.getByLabelText('Organization name'), {
      target: { value: 'Acme Corp' },
    });
    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'test@acme.com' },
    });
    fireEvent.click(screen.getByText('Create Organization'));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
  });
});

// ============ Plan Selection ============

describe('SignupPage — plan selection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSignup.mockResolvedValue(mockSignupResponse);
  });

  it('selects trial plan by default', () => {
    renderSignup();
    const trialBtn = screen.getByLabelText('Trial plan');
    expect(trialBtn.className).toContain('border-primary-500');
  });

  it('allows switching to standard plan', () => {
    renderSignup();
    fireEvent.click(screen.getByLabelText('Standard plan'));
    const standardBtn = screen.getByLabelText('Standard plan');
    expect(standardBtn.className).toContain('border-primary-500');
  });

  it('sends selected plan in API call', async () => {
    renderSignup();

    fireEvent.change(screen.getByLabelText('Organization name'), {
      target: { value: 'Test Org' },
    });
    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'test@example.com' },
    });
    fireEvent.click(screen.getByLabelText('Standard plan'));
    fireEvent.click(screen.getByText('Create Organization'));

    await waitFor(() => {
      expect(mockSignup).toHaveBeenCalledWith(expect.objectContaining({ plan: 'standard' }));
    });
  });
});
