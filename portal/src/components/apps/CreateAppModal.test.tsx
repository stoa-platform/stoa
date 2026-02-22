import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { CreateAppModal } from './CreateAppModal';
import { renderWithProviders } from '../../test/helpers';

const defaultProps = {
  isOpen: true,
  onClose: vi.fn(),
  onSubmit: vi.fn().mockResolvedValue(undefined),
};

describe('CreateAppModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    defaultProps.onClose = vi.fn();
    defaultProps.onSubmit = vi.fn().mockResolvedValue(undefined);
  });

  it('should return null when isOpen is false', () => {
    const { container } = renderWithProviders(<CreateAppModal {...defaultProps} isOpen={false} />);
    expect(container.firstChild).toBeNull();
  });

  it('should render the modal title when isOpen is true', () => {
    renderWithProviders(<CreateAppModal {...defaultProps} />);
    expect(screen.getByText('Create New Application')).toBeInTheDocument();
  });

  it('should disable submit button when name field is empty', () => {
    renderWithProviders(<CreateAppModal {...defaultProps} />);
    const submitBtn = screen.getByRole('button', { name: /create application/i });
    expect(submitBtn).toBeDisabled();
  });

  it('should enable submit button after typing a name', () => {
    renderWithProviders(<CreateAppModal {...defaultProps} />);
    const nameInput = screen.getByLabelText(/application name/i);
    fireEvent.change(nameInput, { target: { value: 'My New App' } });
    const submitBtn = screen.getByRole('button', { name: /create application/i });
    expect(submitBtn).not.toBeDisabled();
  });

  it('should call onSubmit with correct data when form is submitted', async () => {
    renderWithProviders(<CreateAppModal {...defaultProps} />);
    const nameInput = screen.getByLabelText(/application name/i);
    fireEvent.change(nameInput, { target: { value: 'My New App' } });
    const submitBtn = screen.getByRole('button', { name: /create application/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(defaultProps.onSubmit).toHaveBeenCalledWith({
        name: 'My New App',
        description: undefined,
        callbackUrls: [],
      });
    });
  });

  it('should filter out empty callback URLs before submit', async () => {
    renderWithProviders(<CreateAppModal {...defaultProps} />);
    const nameInput = screen.getByLabelText(/application name/i);
    fireEvent.change(nameInput, { target: { value: 'App With URLs' } });

    // The first callback URL input starts empty — add a real URL to it
    const callbackInput = screen.getByPlaceholderText('https://your-app.com/callback');
    fireEvent.change(callbackInput, {
      target: { value: 'https://example.com/callback' },
    });

    // Add another URL via button
    fireEvent.click(screen.getByText(/add another url/i));

    // Second input stays empty (default value)
    const submitBtn = screen.getByRole('button', { name: /create application/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(defaultProps.onSubmit).toHaveBeenCalledWith({
        name: 'App With URLs',
        description: undefined,
        callbackUrls: ['https://example.com/callback'],
      });
    });
  });

  it('should show error message when error prop is set', () => {
    renderWithProviders(
      <CreateAppModal {...defaultProps} error="Application name already exists" />
    );
    expect(screen.getByText('Application name already exists')).toBeInTheDocument();
  });

  it('should show loading state with spinner and "Creating..." text', () => {
    renderWithProviders(<CreateAppModal {...defaultProps} isLoading={true} />);
    expect(screen.getByText('Creating...')).toBeInTheDocument();
  });

  it('should call onClose when Cancel button is clicked and not loading', () => {
    renderWithProviders(<CreateAppModal {...defaultProps} />);
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  it('should not call onClose when isLoading is true and Cancel is clicked', () => {
    renderWithProviders(<CreateAppModal {...defaultProps} isLoading={true} />);
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(defaultProps.onClose).not.toHaveBeenCalled();
  });

  it('should add a new callback URL input when "Add another URL" is clicked', () => {
    renderWithProviders(<CreateAppModal {...defaultProps} />);
    // Initially one placeholder
    expect(screen.getAllByPlaceholderText('https://your-app.com/callback')).toHaveLength(1);

    fireEvent.click(screen.getByText(/add another url/i));

    expect(screen.getAllByPlaceholderText('https://your-app.com/callback')).toHaveLength(2);
  });

  it('should remove a callback URL when the trash button is clicked', () => {
    renderWithProviders(<CreateAppModal {...defaultProps} />);

    // Add a second URL so the remove (trash) buttons appear (requires length > 1)
    fireEvent.click(screen.getByText(/add another url/i));
    expect(screen.getAllByPlaceholderText('https://your-app.com/callback')).toHaveLength(2);

    // The trash button is inside the same row div as the first callback input
    const callbackInputs = screen.getAllByPlaceholderText('https://your-app.com/callback');
    const firstRow = callbackInputs[0].closest('div');
    const trashBtn = firstRow?.querySelector('button') as HTMLButtonElement;
    fireEvent.click(trashBtn);

    expect(screen.getAllByPlaceholderText('https://your-app.com/callback')).toHaveLength(1);
  });
});
