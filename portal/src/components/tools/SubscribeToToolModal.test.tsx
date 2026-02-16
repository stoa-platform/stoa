import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SubscribeToToolModal } from './SubscribeToToolModal';
import type { MCPTool } from '../../types';

const mockTool: MCPTool = {
  name: 'weather-api',
  displayName: 'Weather API',
  description: 'Get weather data for any location',
  version: '1.0',
  category: 'data',
  tags: ['weather', 'api'],
};

const defaultProps = {
  isOpen: true,
  onClose: vi.fn(),
  onSubmit: vi.fn().mockResolvedValue(undefined),
  tool: mockTool,
};

describe('SubscribeToToolModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should return null when not open', () => {
    const { container } = render(<SubscribeToToolModal {...defaultProps} isOpen={false} />);
    expect(container.firstChild).toBeNull();
  });

  it('should render modal with tool info', () => {
    render(<SubscribeToToolModal {...defaultProps} />);
    expect(screen.getByText('Subscribe to Tool')).toBeInTheDocument();
    expect(screen.getByText('Weather API v1.0')).toBeInTheDocument();
    expect(screen.getByText('Get weather data for any location')).toBeInTheDocument();
  });

  it('should show tool category', () => {
    render(<SubscribeToToolModal {...defaultProps} />);
    expect(screen.getByText('data')).toBeInTheDocument();
  });

  it('should show 3 plan options', () => {
    render(<SubscribeToToolModal {...defaultProps} />);
    expect(screen.getByText('Free')).toBeInTheDocument();
    expect(screen.getByText('Basic')).toBeInTheDocument();
    expect(screen.getByText('Premium')).toBeInTheDocument();
  });

  it('should default to free plan', () => {
    render(<SubscribeToToolModal {...defaultProps} />);
    expect(screen.getByText('For testing and evaluation')).toBeInTheDocument();
  });

  it('should select a different plan', () => {
    render(<SubscribeToToolModal {...defaultProps} />);
    fireEvent.click(screen.getByText('Premium'));
    expect(screen.getByText('For production workloads')).toBeInTheDocument();
  });

  it('should submit with tool id and selected plan', async () => {
    render(<SubscribeToToolModal {...defaultProps} />);
    fireEvent.click(screen.getByText('Basic'));
    fireEvent.click(screen.getByText('Subscribe'));

    await waitFor(() => {
      expect(defaultProps.onSubmit).toHaveBeenCalledWith({
        toolId: 'weather-api',
        plan: 'basic',
      });
    });
  });

  it('should show loading state', () => {
    render(<SubscribeToToolModal {...defaultProps} isLoading={true} />);
    expect(screen.getByText('Subscribing...')).toBeInTheDocument();
  });

  it('should show error message', () => {
    render(<SubscribeToToolModal {...defaultProps} error="Subscription limit reached" />);
    expect(screen.getByText('Subscription limit reached')).toBeInTheDocument();
  });

  it('should disable close when loading', () => {
    render(<SubscribeToToolModal {...defaultProps} isLoading={true} />);
    const cancelBtn = screen.getByText('Cancel');
    expect(cancelBtn).toBeDisabled();
  });

  it('should call onClose on cancel', () => {
    render(<SubscribeToToolModal {...defaultProps} />);
    fireEvent.click(screen.getByText('Cancel'));
    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  it('should reset plan to free when modal reopens', () => {
    const { rerender } = render(<SubscribeToToolModal {...defaultProps} />);
    fireEvent.click(screen.getByText('Premium'));

    rerender(<SubscribeToToolModal {...defaultProps} isOpen={false} />);
    rerender(<SubscribeToToolModal {...defaultProps} isOpen={true} />);

    // Free plan features should be visible after reopening
    expect(screen.getByText('For testing and evaluation')).toBeInTheDocument();
  });

  it('should show plan features', () => {
    render(<SubscribeToToolModal {...defaultProps} />);
    expect(screen.getByText('100 calls/day')).toBeInTheDocument();
  });
});
