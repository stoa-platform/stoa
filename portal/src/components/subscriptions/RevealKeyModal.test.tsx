import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { RevealKeyModal } from './RevealKeyModal';
import type { MCPSubscription } from '../../types';

const mockMutateAsync = vi.fn();

vi.mock('../../hooks/useSubscriptions', () => ({
  useRevealApiKey: () => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
  }),
}));

const mockSubscription: MCPSubscription = {
  id: 'sub-1',
  tenant_id: 'tenant-1',
  user_id: 'user-1',
  tool_id: 'weather-tool',
  status: 'active',
  plan: 'basic',
  created_at: '2026-01-15T10:00:00Z',
  expires_at: null,
};

const defaultProps = {
  subscription: mockSubscription,
  isOpen: true,
  onClose: vi.fn(),
};

describe('RevealKeyModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should return null when not open', () => {
    const { container } = render(<RevealKeyModal {...defaultProps} isOpen={false} />);
    expect(container.firstChild).toBeNull();
  });

  it('should show modal title and tool_id', () => {
    render(<RevealKeyModal {...defaultProps} />);
    expect(screen.getByText('Reveal API Key')).toBeInTheDocument();
    expect(screen.getByText('weather-tool')).toBeInTheDocument();
  });

  it('should show security notice before reveal', () => {
    render(<RevealKeyModal {...defaultProps} />);
    expect(screen.getByText('Security Notice')).toBeInTheDocument();
    expect(screen.getByText(/visible for 30 seconds/)).toBeInTheDocument();
  });

  it('should show Reveal Key button', () => {
    render(<RevealKeyModal {...defaultProps} />);
    expect(screen.getByText('Reveal Key')).toBeInTheDocument();
  });

  it('should call mutateAsync on Reveal Key click', async () => {
    mockMutateAsync.mockResolvedValue({ api_key: 'stoa_sk_test123', expires_in: 30 });
    render(<RevealKeyModal {...defaultProps} />);
    fireEvent.click(screen.getByText('Reveal Key'));

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith({
        id: 'sub-1',
        totpCode: undefined,
      });
    });
  });

  it('should display revealed key', async () => {
    mockMutateAsync.mockResolvedValue({ api_key: 'stoa_sk_test_key_value', expires_in: 30 });
    render(<RevealKeyModal {...defaultProps} />);
    fireEvent.click(screen.getByText('Reveal Key'));

    await waitFor(() => {
      expect(screen.getByText(/stoa_sk_test/)).toBeInTheDocument();
    });
  });

  it('should show countdown timer after reveal', async () => {
    mockMutateAsync.mockResolvedValue({ api_key: 'stoa_sk_abc', expires_in: 30 });
    render(<RevealKeyModal {...defaultProps} />);
    fireEvent.click(screen.getByText('Reveal Key'));

    await waitFor(() => {
      expect(screen.getByText(/Hiding in 30 second/)).toBeInTheDocument();
    });
  });

  it('should show Cancel before reveal and Close after', async () => {
    mockMutateAsync.mockResolvedValue({ api_key: 'stoa_sk_abc', expires_in: 30 });
    render(<RevealKeyModal {...defaultProps} />);
    expect(screen.getByText('Cancel')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Reveal Key'));
    await waitFor(() => {
      expect(screen.getByText('Close')).toBeInTheDocument();
    });
  });

  it('should show error message on failure', async () => {
    mockMutateAsync.mockRejectedValue({
      response: { status: 500, data: { detail: 'Key retrieval failed' } },
    });
    render(<RevealKeyModal {...defaultProps} />);
    fireEvent.click(screen.getByText('Reveal Key'));

    await waitFor(() => {
      expect(screen.getByText('Key retrieval failed')).toBeInTheDocument();
    });
  });

  it('should show TOTP input when 403 with TOTP detail', async () => {
    mockMutateAsync.mockRejectedValue({
      response: {
        status: 403,
        data: { detail: 'TOTP required' },
        headers: { get: () => null },
      },
    });
    render(<RevealKeyModal {...defaultProps} />);
    fireEvent.click(screen.getByText('Reveal Key'));

    await waitFor(() => {
      expect(screen.getByText('2FA Verification Required')).toBeInTheDocument();
    });
  });

  it('should show TOTP input when subscription has totp_required', () => {
    const sub = { ...mockSubscription, totp_required: true };
    render(<RevealKeyModal {...defaultProps} subscription={sub} />);
    expect(screen.getByText('2FA Verification Required')).toBeInTheDocument();
  });

  it('should call onClose on Cancel click', () => {
    render(<RevealKeyModal {...defaultProps} />);
    fireEvent.click(screen.getByText('Cancel'));
    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  it('should copy key to clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    mockMutateAsync.mockResolvedValue({ api_key: 'stoa_sk_copy_me', expires_in: 30 });
    render(<RevealKeyModal {...defaultProps} />);
    fireEvent.click(screen.getByText('Reveal Key'));

    await waitFor(() => {
      expect(screen.getByTitle('Copy to clipboard')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTitle('Copy to clipboard'));
    expect(writeText).toHaveBeenCalledWith('stoa_sk_copy_me');
  });
});
