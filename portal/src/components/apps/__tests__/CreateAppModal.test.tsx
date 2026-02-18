import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { CreateAppModal } from '../CreateAppModal';
import { renderWithProviders } from '../../../test/helpers';

describe('CreateAppModal', () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    onSubmit: vi.fn().mockResolvedValue(undefined),
    isLoading: false,
    error: null,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    defaultProps.onClose = vi.fn();
    defaultProps.onSubmit = vi.fn().mockResolvedValue(undefined);
  });

  it('renders nothing when closed', () => {
    renderWithProviders(<CreateAppModal {...defaultProps} isOpen={false} />);

    expect(screen.queryByText('Create New Application')).not.toBeInTheDocument();
  });

  it('renders modal when open', () => {
    renderWithProviders(<CreateAppModal {...defaultProps} />);

    expect(screen.getByText('Create New Application')).toBeInTheDocument();
  });

  it('renders name input', () => {
    renderWithProviders(<CreateAppModal {...defaultProps} />);

    expect(screen.getByLabelText(/Application Name/)).toBeInTheDocument();
  });

  it('renders description textarea', () => {
    renderWithProviders(<CreateAppModal {...defaultProps} />);

    expect(screen.getByLabelText('Description')).toBeInTheDocument();
  });

  it('renders callback URL input', () => {
    renderWithProviders(<CreateAppModal {...defaultProps} />);

    expect(screen.getByLabelText(/Callback URLs/)).toBeInTheDocument();
  });

  it('renders error message when error prop is set', () => {
    renderWithProviders(<CreateAppModal {...defaultProps} error="Something went wrong" />);

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });

  it('calls onClose when Cancel button clicked', () => {
    renderWithProviders(<CreateAppModal {...defaultProps} />);

    fireEvent.click(screen.getByText('Cancel'));
    expect(defaultProps.onClose).toHaveBeenCalledOnce();
  });

  it('calls onClose when X button clicked', () => {
    renderWithProviders(<CreateAppModal {...defaultProps} />);

    const closeButtons = screen.getAllByRole('button');
    const xButton = closeButtons.find((btn) => btn.querySelector('svg'));
    if (xButton) fireEvent.click(xButton);

    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  it('submit button is disabled when name is empty', () => {
    renderWithProviders(<CreateAppModal {...defaultProps} />);

    const submitButton = screen.getByText('Create Application');
    expect(submitButton).toBeDisabled();
  });

  it('enables submit button when name is entered', () => {
    renderWithProviders(<CreateAppModal {...defaultProps} />);

    fireEvent.change(screen.getByLabelText(/Application Name/), {
      target: { value: 'My New App' },
    });

    expect(screen.getByText('Create Application')).not.toBeDisabled();
  });

  it('calls onSubmit with correct data on form submit', async () => {
    renderWithProviders(<CreateAppModal {...defaultProps} />);

    fireEvent.change(screen.getByLabelText(/Application Name/), {
      target: { value: 'Test App' },
    });
    fireEvent.change(screen.getByLabelText('Description'), {
      target: { value: 'A test app' },
    });

    fireEvent.click(screen.getByText('Create Application'));

    await waitFor(() => {
      expect(defaultProps.onSubmit).toHaveBeenCalledWith({
        name: 'Test App',
        description: 'A test app',
        callbackUrls: [],
      });
    });
  });

  it('adds another callback URL field when clicking Add another URL', () => {
    renderWithProviders(<CreateAppModal {...defaultProps} />);

    fireEvent.click(screen.getByText('Add another URL'));

    const urlInputs = screen.getAllByPlaceholderText('https://your-app.com/callback');
    expect(urlInputs).toHaveLength(2);
  });

  it('shows loading state when isLoading is true', () => {
    renderWithProviders(<CreateAppModal {...defaultProps} isLoading={true} />);

    expect(screen.getByText('Creating...')).toBeInTheDocument();
  });

  it('disables buttons when isLoading is true', () => {
    renderWithProviders(<CreateAppModal {...defaultProps} isLoading={true} />);

    expect(screen.getByText('Cancel')).toBeDisabled();
    expect(screen.getByText('Creating...')).toBeDisabled();
  });

  it('renders info box about client secret', () => {
    renderWithProviders(<CreateAppModal {...defaultProps} />);

    expect(screen.getByText(/Client Secret/)).toBeInTheDocument();
    expect(screen.getByText(/only be shown once/)).toBeInTheDocument();
  });
});
