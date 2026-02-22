import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, act } from '@testing-library/react';
import { renderWithProviders } from '../../test/helpers';
import { ApiKeyRevealDialog } from './ApiKeyRevealDialog';

const defaultProps = {
  apiKey: 'sk-test-abc123xyz789',
  name: 'Partner Agent',
  onClose: vi.fn(),
};

function renderDialog(overrides: Partial<typeof defaultProps> = {}) {
  return renderWithProviders(<ApiKeyRevealDialog {...defaultProps} {...overrides} />);
}

describe('ApiKeyRevealDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    defaultProps.onClose = vi.fn();
    vi.mocked(navigator.clipboard.writeText).mockResolvedValue(undefined);
  });

  it('renders the dialog title with account name', () => {
    renderDialog();
    expect(screen.getByText('API Key for Partner Agent')).toBeInTheDocument();
  });

  it('displays the API key value', () => {
    renderDialog();
    expect(screen.getByText('sk-test-abc123xyz789')).toBeInTheDocument();
  });

  it('shows the security warning message', () => {
    renderDialog();
    expect(screen.getByText(/This key will not be shown again/i)).toBeInTheDocument();
  });

  it('copies key to clipboard when copy button clicked', async () => {
    renderDialog();
    const copyBtn = screen.getByTitle('Copy to clipboard');
    await act(async () => {
      fireEvent.click(copyBtn);
    });
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('sk-test-abc123xyz789');
  });

  it('shows check icon after copying', async () => {
    renderDialog();
    const copyBtn = screen.getByTitle('Copy to clipboard');
    // Before copy: Copy icon present (no check)
    expect(document.querySelector('svg.h-4.w-4')).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(copyBtn);
    });
    // After copy: check icon (green)
    expect(document.querySelector('.text-green-600')).toBeInTheDocument();
  });

  it('calls onClose when done button clicked', () => {
    renderDialog();
    fireEvent.click(screen.getByText("I've copied the key"));
    expect(defaultProps.onClose).toHaveBeenCalledOnce();
  });

  it('renders with different account names', () => {
    renderDialog({ name: 'Sub-Account Alpha' });
    expect(screen.getByText('API Key for Sub-Account Alpha')).toBeInTheDocument();
  });
});
