/**
 * Register Server Modal Tests (CAB-1319)
 *
 * Tests for form validation, conditional credential fields, and submit flow.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RegisterServerModal } from '../../components/servers/RegisterServerModal';
import type { TenantMCPServerCreatePayload } from '../../services/tenantMcpServers';

// ============ Setup ============

const defaultProps = {
  isOpen: true,
  onClose: vi.fn(),
  onSubmit: vi
    .fn<(data: TenantMCPServerCreatePayload) => Promise<void>>()
    .mockResolvedValue(undefined),
  isLoading: false,
  error: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  defaultProps.onSubmit.mockResolvedValue(undefined);
});

// ============ Rendering ============

describe('RegisterServerModal — rendering', () => {
  it('renders modal when isOpen is true', () => {
    render(<RegisterServerModal {...defaultProps} />);
    expect(screen.getByText('Register MCP Server')).toBeInTheDocument();
  });

  it('does not render when isOpen is false', () => {
    render(<RegisterServerModal {...defaultProps} isOpen={false} />);
    expect(screen.queryByText('Register MCP Server')).not.toBeInTheDocument();
  });

  it('renders all required form fields', () => {
    render(<RegisterServerModal {...defaultProps} />);
    expect(screen.getByLabelText(/Display Name/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Base URL/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Transport Protocol/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Authentication/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Tool Prefix/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Description/)).toBeInTheDocument();
  });

  it('shows error message when error prop is set', () => {
    render(<RegisterServerModal {...defaultProps} error="Something went wrong" />);
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });

  it('shows loading state on submit button', () => {
    render(<RegisterServerModal {...defaultProps} isLoading={true} />);
    expect(screen.getByText('Registering...')).toBeInTheDocument();
  });
});

// ============ Form Validation ============

describe('RegisterServerModal — validation', () => {
  it('disables submit button when required fields are empty', () => {
    render(<RegisterServerModal {...defaultProps} />);
    const submitBtn = screen.getByRole('button', { name: /Register Server/i });
    expect(submitBtn).toBeDisabled();
  });

  it('enables submit button when display name and base URL are filled (auth=none)', async () => {
    const user = userEvent.setup();
    render(<RegisterServerModal {...defaultProps} />);

    await user.type(screen.getByLabelText(/Display Name/), 'My Server');
    await user.type(screen.getByLabelText(/Base URL/), 'https://example.com/sse');

    const submitBtn = screen.getByRole('button', { name: /Register Server/i });
    expect(submitBtn).not.toBeDisabled();
  });

  it('requires API key when auth type is api_key', async () => {
    const user = userEvent.setup();
    render(<RegisterServerModal {...defaultProps} />);

    await user.type(screen.getByLabelText(/Display Name/), 'My Server');
    await user.type(screen.getByLabelText(/Base URL/), 'https://example.com/sse');
    await user.selectOptions(screen.getByLabelText(/Authentication/), 'api_key');

    // Submit should be disabled without API key
    const submitBtn = screen.getByRole('button', { name: /Register Server/i });
    expect(submitBtn).toBeDisabled();

    // Fill API key
    await user.type(screen.getByLabelText(/API Key/), 'my-secret-key');
    expect(submitBtn).not.toBeDisabled();
  });

  it('requires bearer token when auth type is bearer_token', async () => {
    const user = userEvent.setup();
    render(<RegisterServerModal {...defaultProps} />);

    await user.type(screen.getByLabelText(/Display Name/), 'My Server');
    await user.type(screen.getByLabelText(/Base URL/), 'https://example.com/sse');
    await user.selectOptions(screen.getByLabelText(/Authentication/), 'bearer_token');

    const submitBtn = screen.getByRole('button', { name: /Register Server/i });
    expect(submitBtn).toBeDisabled();

    await user.type(screen.getByLabelText(/Bearer Token/), 'my-token');
    expect(submitBtn).not.toBeDisabled();
  });

  it('requires OAuth2 fields when auth type is oauth2', async () => {
    const user = userEvent.setup();
    render(<RegisterServerModal {...defaultProps} />);

    await user.type(screen.getByLabelText(/Display Name/), 'My Server');
    await user.type(screen.getByLabelText(/Base URL/), 'https://example.com/sse');
    await user.selectOptions(screen.getByLabelText(/Authentication/), 'oauth2');

    const submitBtn = screen.getByRole('button', { name: /Register Server/i });
    expect(submitBtn).toBeDisabled();

    await user.type(screen.getByLabelText(/Client ID/), 'client-id');
    expect(submitBtn).toBeDisabled();

    await user.type(screen.getByLabelText(/Client Secret/), 'client-secret');
    expect(submitBtn).toBeDisabled();

    await user.type(screen.getByLabelText(/Token URL/), 'https://auth.example.com/token');
    expect(submitBtn).not.toBeDisabled();
  });
});

// ============ Conditional Fields ============

describe('RegisterServerModal — conditional auth fields', () => {
  it('shows no credential fields when auth is none', () => {
    render(<RegisterServerModal {...defaultProps} />);
    expect(screen.queryByLabelText(/API Key/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Bearer Token/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Client ID/)).not.toBeInTheDocument();
  });

  it('shows API key field when auth is api_key', async () => {
    const user = userEvent.setup();
    render(<RegisterServerModal {...defaultProps} />);

    await user.selectOptions(screen.getByLabelText(/Authentication/), 'api_key');
    expect(screen.getByLabelText(/API Key/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Bearer Token/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Client ID/)).not.toBeInTheDocument();
  });

  it('shows bearer token field when auth is bearer_token', async () => {
    const user = userEvent.setup();
    render(<RegisterServerModal {...defaultProps} />);

    await user.selectOptions(screen.getByLabelText(/Authentication/), 'bearer_token');
    expect(screen.getByLabelText(/Bearer Token/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/API Key/)).not.toBeInTheDocument();
  });

  it('shows OAuth2 fields when auth is oauth2', async () => {
    const user = userEvent.setup();
    render(<RegisterServerModal {...defaultProps} />);

    await user.selectOptions(screen.getByLabelText(/Authentication/), 'oauth2');
    expect(screen.getByLabelText(/Client ID/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Client Secret/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Token URL/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Scope/)).toBeInTheDocument();
  });
});

// ============ Submit ============

describe('RegisterServerModal — submit', () => {
  it('submits form with basic fields (auth=none)', async () => {
    const user = userEvent.setup();
    render(<RegisterServerModal {...defaultProps} />);

    await user.type(screen.getByLabelText(/Display Name/), 'Linear');
    await user.type(screen.getByLabelText(/Base URL/), 'https://mcp.linear.app/sse');
    await user.type(screen.getByLabelText(/Tool Prefix/), 'linear');
    await user.type(screen.getByLabelText(/Description/), 'Linear integration');

    await user.click(screen.getByRole('button', { name: /Register Server/i }));

    await waitFor(() => {
      expect(defaultProps.onSubmit).toHaveBeenCalledWith({
        display_name: 'Linear',
        base_url: 'https://mcp.linear.app/sse',
        description: 'Linear integration',
        transport: 'sse',
        auth_type: 'none',
        tool_prefix: 'linear',
      });
    });
  });

  it('submits form with API key credentials', async () => {
    const user = userEvent.setup();
    render(<RegisterServerModal {...defaultProps} />);

    await user.type(screen.getByLabelText(/Display Name/), 'My API');
    await user.type(screen.getByLabelText(/Base URL/), 'https://api.example.com/sse');
    await user.selectOptions(screen.getByLabelText(/Authentication/), 'api_key');
    await user.type(screen.getByLabelText(/API Key/), 'secret-key-123');

    await user.click(screen.getByRole('button', { name: /Register Server/i }));

    await waitFor(() => {
      expect(defaultProps.onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          auth_type: 'api_key',
          credentials: { api_key: 'secret-key-123' },
        })
      );
    });
  });

  it('submits form with OAuth2 credentials', async () => {
    const user = userEvent.setup();
    render(<RegisterServerModal {...defaultProps} />);

    await user.type(screen.getByLabelText(/Display Name/), 'OAuth Server');
    await user.type(screen.getByLabelText(/Base URL/), 'https://oauth.example.com/sse');
    await user.selectOptions(screen.getByLabelText(/Authentication/), 'oauth2');
    await user.type(screen.getByLabelText(/Client ID/), 'my-client-id');
    await user.type(screen.getByLabelText(/Client Secret/), 'my-client-secret');
    await user.type(screen.getByLabelText(/Token URL/), 'https://auth.example.com/token');
    await user.type(screen.getByLabelText(/Scope/), 'read write');

    await user.click(screen.getByRole('button', { name: /Register Server/i }));

    await waitFor(() => {
      expect(defaultProps.onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          auth_type: 'oauth2',
          credentials: {
            oauth2: {
              client_id: 'my-client-id',
              client_secret: 'my-client-secret',
              token_url: 'https://auth.example.com/token',
              scope: 'read write',
            },
          },
        })
      );
    });
  });

  it('calls onClose when Cancel is clicked', async () => {
    const user = userEvent.setup();
    render(<RegisterServerModal {...defaultProps} />);

    await user.click(screen.getByRole('button', { name: /Cancel/i }));
    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  it('calls onClose when backdrop is clicked', async () => {
    const user = userEvent.setup();
    render(<RegisterServerModal {...defaultProps} />);

    await user.click(screen.getByRole('button', { name: /Close modal/i }));
    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  it('does not close when loading', async () => {
    const user = userEvent.setup();
    render(<RegisterServerModal {...defaultProps} isLoading={true} />);

    await user.click(screen.getByRole('button', { name: /Cancel/i }));
    expect(defaultProps.onClose).not.toHaveBeenCalled();
  });
});
