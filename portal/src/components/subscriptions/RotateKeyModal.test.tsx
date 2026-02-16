import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { RotateKeyModal } from './RotateKeyModal';
import type { MCPSubscription, KeyRotationResponse } from '../../types';

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

const mockRotationResult: KeyRotationResponse = {
  subscription_id: 'sub-1',
  new_api_key: 'stoa_sk_new_key_abc123',
  new_api_key_prefix: 'stoa_sk_new_',
  old_key_expires_at: '2026-02-17T10:00:00Z',
  grace_period_hours: 24,
  rotation_count: 2,
};

const defaultProps = {
  isOpen: true,
  onClose: vi.fn(),
  subscription: mockSubscription,
  onRotate: vi.fn().mockResolvedValue(mockRotationResult),
  isRotating: false,
};

describe('RotateKeyModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should return null when not open', () => {
    const { container } = render(<RotateKeyModal {...defaultProps} isOpen={false} />);
    expect(container.firstChild).toBeNull();
  });

  it('should show confirm step by default', () => {
    render(<RotateKeyModal {...defaultProps} />);
    expect(screen.getByText('Rotate API Key')).toBeInTheDocument();
    expect(screen.getByText('weather-tool')).toBeInTheDocument();
  });

  it('should show grace period selector', () => {
    render(<RotateKeyModal {...defaultProps} />);
    expect(screen.getByText('Grace Period Duration')).toBeInTheDocument();
    const select = screen.getByRole('combobox');
    expect(select).toHaveValue('24');
  });

  it('should change grace period', () => {
    render(<RotateKeyModal {...defaultProps} />);
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '48' } });
    expect(screen.getByRole('combobox')).toHaveValue('48');
  });

  it('should show loading state when rotating', () => {
    render(<RotateKeyModal {...defaultProps} isRotating={true} />);
    expect(screen.getByText('Rotating...')).toBeInTheDocument();
  });

  it('should call onRotate with grace period', async () => {
    render(<RotateKeyModal {...defaultProps} />);
    fireEvent.click(screen.getByText('Rotate Key'));
    await waitFor(() => {
      expect(defaultProps.onRotate).toHaveBeenCalledWith(24);
    });
  });

  it('should transition to success step after rotation', async () => {
    render(<RotateKeyModal {...defaultProps} />);
    fireEvent.click(screen.getByText('Rotate Key'));
    await waitFor(() => {
      expect(screen.getByText('Key Rotated Successfully')).toBeInTheDocument();
    });
  });

  it('should display new key on success step', async () => {
    render(<RotateKeyModal {...defaultProps} />);
    fireEvent.click(screen.getByText('Rotate Key'));
    await waitFor(() => {
      expect(screen.getByText('stoa_sk_new_key_abc123')).toBeInTheDocument();
    });
  });

  it('should show grace period info on success', async () => {
    render(<RotateKeyModal {...defaultProps} />);
    fireEvent.click(screen.getByText('Rotate Key'));
    await waitFor(() => {
      expect(screen.getByText(/24 hours/)).toBeInTheDocument();
      expect(screen.getByText(/rotation #2/)).toBeInTheDocument();
    });
  });

  it('should require acknowledgment before closing on success', async () => {
    render(<RotateKeyModal {...defaultProps} />);
    fireEvent.click(screen.getByText('Rotate Key'));
    await waitFor(() => {
      expect(screen.getByText('Done')).toBeDisabled();
    });
  });

  it('should enable Done after acknowledgment', async () => {
    render(<RotateKeyModal {...defaultProps} />);
    fireEvent.click(screen.getByText('Rotate Key'));
    await waitFor(() => {
      expect(screen.getByText('Done')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('checkbox'));
    expect(screen.getByText('Done')).not.toBeDisabled();
  });

  it('should show error message on rotation failure', async () => {
    const onRotate = vi.fn().mockRejectedValue(new Error('Server error'));
    render(<RotateKeyModal {...defaultProps} onRotate={onRotate} />);
    fireEvent.click(screen.getByText('Rotate Key'));
    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeInTheDocument();
    });
  });

  it('should copy new key to clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    render(<RotateKeyModal {...defaultProps} />);
    fireEvent.click(screen.getByText('Rotate Key'));
    await waitFor(() => {
      expect(screen.getByText('stoa_sk_new_key_abc123')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTitle('Copy to clipboard'));
    expect(writeText).toHaveBeenCalledWith('stoa_sk_new_key_abc123');
  });

  it('should call onClose on cancel in confirm step', () => {
    render(<RotateKeyModal {...defaultProps} />);
    fireEvent.click(screen.getByText('Cancel'));
    expect(defaultProps.onClose).toHaveBeenCalled();
  });
});
