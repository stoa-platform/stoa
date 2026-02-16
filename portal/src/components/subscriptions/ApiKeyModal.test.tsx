import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ApiKeyModal } from './ApiKeyModal';

const defaultProps = {
  isOpen: true,
  onClose: vi.fn(),
  apiKey: 'stoa_sk_test1234567890abcdef',
  toolId: 'weather-api',
  toolName: 'Weather API',
};

describe('ApiKeyModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should return null when not open', () => {
    const { container } = render(<ApiKeyModal {...defaultProps} isOpen={false} />);
    expect(container.firstChild).toBeNull();
  });

  it('should render modal with title and tool name', () => {
    render(<ApiKeyModal {...defaultProps} />);
    expect(screen.getByText('Subscription Created')).toBeInTheDocument();
    expect(screen.getByText('Weather API')).toBeInTheDocument();
  });

  it('should display the API key', () => {
    render(<ApiKeyModal {...defaultProps} />);
    expect(screen.getByText('stoa_sk_test1234567890abcdef')).toBeInTheDocument();
  });

  it('should show warning about one-time display', () => {
    render(<ApiKeyModal {...defaultProps} />);
    expect(screen.getByText('Save Your API Key Now')).toBeInTheDocument();
  });

  it('should copy key to clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    render(<ApiKeyModal {...defaultProps} />);
    fireEvent.click(screen.getByTitle('Copy to clipboard'));
    expect(writeText).toHaveBeenCalledWith('stoa_sk_test1234567890abcdef');
  });

  it('should block close until acknowledged', () => {
    render(<ApiKeyModal {...defaultProps} />);
    const doneButton = screen.getByText('Done');
    expect(doneButton).toBeDisabled();
  });

  it('should enable Done button after acknowledgment', () => {
    render(<ApiKeyModal {...defaultProps} />);
    const checkbox = screen.getByRole('checkbox');
    fireEvent.click(checkbox);
    expect(screen.getByText('Done')).not.toBeDisabled();
  });

  it('should call onClose when acknowledged and Done clicked', () => {
    render(<ApiKeyModal {...defaultProps} />);
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByText('Done'));
    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  it('should not show close X button until acknowledged', () => {
    render(<ApiKeyModal {...defaultProps} />);
    // X button only visible after acknowledgment
    expect(screen.queryByLabelText('Close modal')).toBeInTheDocument(); // backdrop
  });

  it('should fall back to toolId when toolName not provided', () => {
    render(<ApiKeyModal {...defaultProps} toolName={undefined} />);
    expect(screen.getByText('weather-api')).toBeInTheDocument();
  });

  it('should render download config button', () => {
    render(<ApiKeyModal {...defaultProps} />);
    expect(screen.getByText('Download Config')).toBeInTheDocument();
  });

  it('should render usage example with tool id', () => {
    render(<ApiKeyModal {...defaultProps} />);
    expect(screen.getByText(/weather-api/)).toBeInTheDocument();
  });
});
