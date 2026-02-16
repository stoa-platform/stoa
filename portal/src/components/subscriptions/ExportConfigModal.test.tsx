import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ExportConfigModal } from './ExportConfigModal';
import type { MCPSubscription } from '../../types';

const mockSubscription: MCPSubscription = {
  id: 'sub-1',
  tenant_id: 'tenant-1',
  user_id: 'user-1',
  tool_id: 'Weather Tool',
  status: 'active',
  plan: 'basic',
  created_at: '2026-01-15T10:00:00Z',
  expires_at: null,
  api_key_prefix: 'stoa_sk_1234',
};

const defaultProps = {
  subscription: mockSubscription,
  isOpen: true,
  onClose: vi.fn(),
};

function renderModal(props: Partial<typeof defaultProps> = {}) {
  return render(
    <MemoryRouter>
      <ExportConfigModal {...defaultProps} {...props} />
    </MemoryRouter>
  );
}

describe('ExportConfigModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should return null when not open', () => {
    const { container } = renderModal({ isOpen: false });
    expect(container.firstChild).toBeNull();
  });

  it('should render modal title', () => {
    renderModal();
    expect(screen.getByText('Export MCP Config')).toBeInTheDocument();
  });

  it('should show tool info', () => {
    renderModal();
    expect(screen.getByText('Weather Tool')).toBeInTheDocument();
    expect(screen.getByText(/stoa_sk_1234/)).toBeInTheDocument();
  });

  it('should default to OAuth2 auth method', () => {
    renderModal();
    expect(screen.getByText('Client ID')).toBeInTheDocument();
    expect(screen.getByText('Client Secret')).toBeInTheDocument();
  });

  it('should switch to API Key auth method', () => {
    renderModal();
    fireEvent.click(screen.getByText('API Key'));
    expect(screen.getByPlaceholderText('stoa_sk_...')).toBeInTheDocument();
  });

  it('should show validation warning when fields empty', () => {
    renderModal();
    expect(screen.getByText(/Don't have credentials/)).toBeInTheDocument();
  });

  it('should generate config preview when API key entered', () => {
    renderModal();
    fireEvent.click(screen.getByText('API Key'));
    fireEvent.change(screen.getByPlaceholderText('stoa_sk_...'), {
      target: { value: 'stoa_sk_test123' },
    });
    expect(screen.getByText('Config ready to download!')).toBeInTheDocument();
    expect(screen.getByText('Configuration Preview')).toBeInTheDocument();
  });

  it('should generate config for OAuth2 when both fields filled', () => {
    renderModal();
    fireEvent.change(screen.getByPlaceholderText('stoa-mcp-client'), {
      target: { value: 'my-client' },
    });
    fireEvent.change(screen.getByPlaceholderText('your-client-secret'), {
      target: { value: 'secret-123' },
    });
    expect(screen.getByText('Config ready to download!')).toBeInTheDocument();
  });

  it('should copy config to clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    renderModal();
    fireEvent.click(screen.getByText('API Key'));
    fireEvent.change(screen.getByPlaceholderText('stoa_sk_...'), {
      target: { value: 'test-key' },
    });
    fireEvent.click(screen.getByText('Copy'));
    expect(writeText).toHaveBeenCalled();
  });

  it('should disable Copy/Download when no valid config', () => {
    renderModal();
    const copyBtn = screen.getByText('Copy').closest('button');
    const downloadBtn = screen.getByText('Download').closest('button');
    expect(copyBtn).toBeDisabled();
    expect(downloadBtn).toBeDisabled();
  });

  it('should call onClose and clear fields on close', () => {
    renderModal();
    fireEvent.click(screen.getByText('Close'));
    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  it('should show instructions', () => {
    renderModal();
    expect(screen.getByText('How to use')).toBeInTheDocument();
  });
});
