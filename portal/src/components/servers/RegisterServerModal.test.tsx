import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RegisterServerModal } from './RegisterServerModal';
import { renderWithProviders } from '../../test/helpers';

describe('RegisterServerModal', () => {
  const onClose = vi.fn();
  const onSubmit = vi.fn().mockResolvedValue(undefined);

  const defaultProps = {
    isOpen: true,
    onClose,
    onSubmit,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    onSubmit.mockResolvedValue(undefined);
  });

  it('should return null when not open', () => {
    const { container } = renderWithProviders(
      <RegisterServerModal {...defaultProps} isOpen={false} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('should render modal title', () => {
    renderWithProviders(<RegisterServerModal {...defaultProps} />);
    expect(screen.getByText('Register MCP Server')).toBeInTheDocument();
  });

  it('should render required form fields', () => {
    renderWithProviders(<RegisterServerModal {...defaultProps} />);
    expect(screen.getByLabelText(/Display Name/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Base URL/)).toBeInTheDocument();
    expect(screen.getByLabelText('Transport Protocol')).toBeInTheDocument();
    expect(screen.getByLabelText('Authentication')).toBeInTheDocument();
    expect(screen.getByLabelText('Tool Prefix')).toBeInTheDocument();
    expect(screen.getByLabelText('Description')).toBeInTheDocument();
  });

  it('should show transport options', () => {
    renderWithProviders(<RegisterServerModal {...defaultProps} />);
    const transport = screen.getByLabelText('Transport Protocol');
    expect(transport).toHaveValue('sse');
    expect(screen.getByText('SSE (Server-Sent Events)')).toBeInTheDocument();
    expect(screen.getByText('HTTP (Streamable HTTP)')).toBeInTheDocument();
    expect(screen.getByText('WebSocket')).toBeInTheDocument();
  });

  it('should show auth type options', () => {
    renderWithProviders(<RegisterServerModal {...defaultProps} />);
    const authSelect = screen.getByLabelText('Authentication');
    expect(authSelect).toHaveValue('none');
  });

  it('should show API Key field when api_key auth selected', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterServerModal {...defaultProps} />);
    await user.selectOptions(screen.getByLabelText('Authentication'), 'api_key');
    expect(screen.getByLabelText(/API Key/)).toBeInTheDocument();
  });

  it('should show Bearer Token field when bearer_token auth selected', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterServerModal {...defaultProps} />);
    await user.selectOptions(screen.getByLabelText('Authentication'), 'bearer_token');
    expect(screen.getByLabelText(/Bearer Token/)).toBeInTheDocument();
  });

  it('should show OAuth2 fields when oauth2 auth selected', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterServerModal {...defaultProps} />);
    await user.selectOptions(screen.getByLabelText('Authentication'), 'oauth2');
    expect(screen.getByText('OAuth2 Configuration')).toBeInTheDocument();
    expect(screen.getByLabelText(/Client ID/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Client Secret/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Token URL/)).toBeInTheDocument();
    expect(screen.getByLabelText('Scope')).toBeInTheDocument();
  });

  it('should disable Register button when form is incomplete', () => {
    renderWithProviders(<RegisterServerModal {...defaultProps} />);
    expect(screen.getByText('Register Server')).toBeDisabled();
  });

  it('should enable Register button when required fields filled (none auth)', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterServerModal {...defaultProps} />);

    await user.type(screen.getByLabelText(/Display Name/), 'My Server');
    await user.type(screen.getByLabelText(/Base URL/), 'https://mcp.example.com/sse');

    expect(screen.getByText('Register Server')).not.toBeDisabled();
  });

  it('should submit form with correct payload for none auth', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterServerModal {...defaultProps} />);

    await user.type(screen.getByLabelText(/Display Name/), 'My Server');
    await user.type(screen.getByLabelText(/Base URL/), 'https://mcp.example.com/sse');
    await user.type(screen.getByLabelText('Description'), 'Test server');

    await user.click(screen.getByText('Register Server'));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          display_name: 'My Server',
          base_url: 'https://mcp.example.com/sse',
          description: 'Test server',
          transport: 'sse',
          auth_type: 'none',
        })
      );
    });
  });

  it('should submit form with api_key credentials', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterServerModal {...defaultProps} />);

    await user.type(screen.getByLabelText(/Display Name/), 'My Server');
    await user.type(screen.getByLabelText(/Base URL/), 'https://mcp.example.com/sse');
    await user.selectOptions(screen.getByLabelText('Authentication'), 'api_key');
    await user.type(screen.getByLabelText(/API Key/), 'sk-test-123');

    await user.click(screen.getByText('Register Server'));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          auth_type: 'api_key',
          credentials: { api_key: 'sk-test-123' },
        })
      );
    });
  });

  it('should show error message when error prop passed', () => {
    renderWithProviders(<RegisterServerModal {...defaultProps} error="Server already exists" />);
    expect(screen.getByText('Server already exists')).toBeInTheDocument();
  });

  it('should show loading state when isLoading', () => {
    renderWithProviders(<RegisterServerModal {...defaultProps} isLoading={true} />);
    expect(screen.getByText('Registering...')).toBeInTheDocument();
  });

  it('should not close when loading', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterServerModal {...defaultProps} isLoading={true} />);
    await user.click(screen.getByText('Cancel'));
    expect(onClose).not.toHaveBeenCalled();
  });

  it('should call onClose when cancel clicked and not loading', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterServerModal {...defaultProps} />);
    await user.click(screen.getByText('Cancel'));
    expect(onClose).toHaveBeenCalled();
  });

  it('should show tool prefix hint text', () => {
    renderWithProviders(<RegisterServerModal {...defaultProps} />);
    expect(screen.getByText(/Prefix for namespaced tool names/)).toBeInTheDocument();
  });
});
