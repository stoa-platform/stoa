/**
 * TokenExchangePanel Tests - CAB-1121 Session 3
 *
 * Tests for the RFC 8693 Token Exchange panel component.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../../test/helpers';
import { TokenExchangePanel } from '../TokenExchangePanel';

// Mock consumers service
const mockExchangeToken = vi.fn();

vi.mock('../../../services/consumers', () => ({
  consumersService: {
    exchangeToken: (...args: unknown[]) => mockExchangeToken(...args),
  },
}));

const defaultProps = {
  tenantId: 'oasis-gunters',
  consumerId: 'consumer-1',
  consumerName: 'My App',
};

describe('TokenExchangePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the exchange form with subject token input', () => {
    renderWithProviders(<TokenExchangePanel {...defaultProps} />);

    expect(screen.getByText('Token Exchange (RFC 8693)')).toBeInTheDocument();
    expect(screen.getByLabelText('Subject Token')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Exchange Token/ })).toBeInTheDocument();
  });

  it('renders audience and scope optional fields', () => {
    renderWithProviders(<TokenExchangePanel {...defaultProps} />);

    expect(screen.getByLabelText(/Audience/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Scope/)).toBeInTheDocument();
  });

  it('disables exchange button when subject token is empty', () => {
    renderWithProviders(<TokenExchangePanel {...defaultProps} />);

    const button = screen.getByRole('button', { name: /Exchange Token/ });
    expect(button).toBeDisabled();
  });

  it('enables exchange button when subject token is entered', async () => {
    const user = userEvent.setup();
    renderWithProviders(<TokenExchangePanel {...defaultProps} />);

    const textarea = screen.getByLabelText('Subject Token');
    await user.type(textarea, 'eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMjM0In0.sig');

    const button = screen.getByRole('button', { name: /Exchange Token/ });
    expect(button).toBeEnabled();
  });

  it('submits exchange request and displays result', async () => {
    const user = userEvent.setup();
    // JWT with base64url-encoded payload {"sub":"1234","aud":"stoa-api"}
    const mockToken = 'eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMjM0IiwiYXVkIjoic3RvYS1hcGkifQ.signature';

    mockExchangeToken.mockResolvedValue({
      access_token: mockToken,
      token_type: 'Bearer',
      expires_in: 300,
    });

    renderWithProviders(<TokenExchangePanel {...defaultProps} />);

    const textarea = screen.getByLabelText('Subject Token');
    await user.type(textarea, 'original-subject-token');

    const button = screen.getByRole('button', { name: /Exchange Token/ });
    await user.click(button);

    await waitFor(() => {
      expect(mockExchangeToken).toHaveBeenCalledWith('oasis-gunters', 'consumer-1', {
        subject_token: 'original-subject-token',
        audience: undefined,
        scope: undefined,
      });
    });

    await waitFor(() => {
      expect(screen.getByText('Exchanged Token')).toBeInTheDocument();
      expect(screen.getByText(/expires in 300s/)).toBeInTheDocument();
      expect(screen.getByText('Token Claims')).toBeInTheDocument();
    });
  });

  it('passes audience and scope to exchange request', async () => {
    const user = userEvent.setup();
    mockExchangeToken.mockResolvedValue({
      access_token: 'eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMjM0In0.sig',
      token_type: 'Bearer',
      expires_in: 300,
    });

    renderWithProviders(<TokenExchangePanel {...defaultProps} />);

    await user.type(screen.getByLabelText('Subject Token'), 'my-token');
    await user.type(screen.getByLabelText(/Audience/), 'stoa-api');
    await user.type(screen.getByLabelText(/Scope/), 'openid profile');

    await user.click(screen.getByRole('button', { name: /Exchange Token/ }));

    await waitFor(() => {
      expect(mockExchangeToken).toHaveBeenCalledWith('oasis-gunters', 'consumer-1', {
        subject_token: 'my-token',
        audience: 'stoa-api',
        scope: 'openid profile',
      });
    });
  });

  it('displays error message on exchange failure', async () => {
    const user = userEvent.setup();
    mockExchangeToken.mockRejectedValue({
      response: { data: { detail: 'Invalid subject token' } },
    });

    renderWithProviders(<TokenExchangePanel {...defaultProps} />);

    await user.type(screen.getByLabelText('Subject Token'), 'bad-token');
    await user.click(screen.getByRole('button', { name: /Exchange Token/ }));

    await waitFor(() => {
      expect(screen.getByText('Invalid subject token')).toBeInTheDocument();
    });
  });

  it('displays fallback error when no detail in response', async () => {
    const user = userEvent.setup();
    mockExchangeToken.mockRejectedValue(new Error('Network error'));

    renderWithProviders(<TokenExchangePanel {...defaultProps} />);

    await user.type(screen.getByLabelText('Subject Token'), 'some-token');
    await user.click(screen.getByRole('button', { name: /Exchange Token/ }));

    await waitFor(() => {
      expect(screen.getByText('Token exchange failed')).toBeInTheDocument();
    });
  });

  it('renders copy button and cURL snippet after exchange', async () => {
    const user = userEvent.setup();
    const mockToken = 'eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMjM0IiwiYXVkIjoic3RvYS1hcGkifQ.signature';

    mockExchangeToken.mockResolvedValue({
      access_token: mockToken,
      token_type: 'Bearer',
      expires_in: 300,
    });

    renderWithProviders(<TokenExchangePanel {...defaultProps} />);

    await user.type(screen.getByLabelText('Subject Token'), 'my-token');
    await user.click(screen.getByRole('button', { name: /Exchange Token/ }));

    await waitFor(() => {
      expect(screen.getByTitle('Copy token')).toBeInTheDocument();
      expect(screen.getByTitle('Copy cURL command')).toBeInTheDocument();
      expect(screen.getByText('Quick Test')).toBeInTheDocument();
    });
  });
});
