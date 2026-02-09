/**
 * Tests for CreateConsumerModal component (CAB-1121)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CreateConsumerModal } from './CreateConsumerModal';

describe('CreateConsumerModal', () => {
  const mockOnClose = vi.fn();
  const mockOnSubmit = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockOnSubmit.mockResolvedValue(undefined);
  });

  it('should not render when isOpen is false', () => {
    render(<CreateConsumerModal isOpen={false} onClose={mockOnClose} onSubmit={mockOnSubmit} />);

    expect(screen.queryByText('Register New Consumer')).not.toBeInTheDocument();
  });

  it('should render when isOpen is true', () => {
    render(<CreateConsumerModal isOpen={true} onClose={mockOnClose} onSubmit={mockOnSubmit} />);

    expect(screen.getByText('Register New Consumer')).toBeInTheDocument();
  });

  it('should render all form fields', () => {
    render(<CreateConsumerModal isOpen={true} onClose={mockOnClose} onSubmit={mockOnSubmit} />);

    expect(screen.getByLabelText(/Consumer Name/)).toBeInTheDocument();
    expect(screen.getByLabelText(/External ID/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Contact Email/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Company/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Description/)).toBeInTheDocument();
  });

  it('should disable submit when name is empty', () => {
    render(<CreateConsumerModal isOpen={true} onClose={mockOnClose} onSubmit={mockOnSubmit} />);

    const submitButton = screen.getByText('Register Consumer');
    expect(submitButton).toBeDisabled();
  });

  it('should call onSubmit with form data', async () => {
    render(<CreateConsumerModal isOpen={true} onClose={mockOnClose} onSubmit={mockOnSubmit} />);

    fireEvent.change(screen.getByLabelText(/Consumer Name/), {
      target: { value: 'ACME Corp' },
    });
    fireEvent.change(screen.getByLabelText(/External ID/), {
      target: { value: 'acme-001' },
    });
    fireEvent.change(screen.getByLabelText(/Contact Email/), {
      target: { value: 'api@acme.com' },
    });
    fireEvent.change(screen.getByLabelText(/Company/), {
      target: { value: 'ACME Corporation' },
    });

    const submitButton = screen.getByText('Register Consumer');
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(mockOnSubmit).toHaveBeenCalledWith({
        name: 'ACME Corp',
        external_id: 'acme-001',
        email: 'api@acme.com',
        company: 'ACME Corporation',
        description: undefined,
      });
    });
  });

  it('should show email validation error for invalid email', () => {
    render(<CreateConsumerModal isOpen={true} onClose={mockOnClose} onSubmit={mockOnSubmit} />);

    const emailInput = screen.getByLabelText(/Contact Email/);
    fireEvent.change(emailInput, { target: { value: 'not-an-email' } });
    fireEvent.blur(emailInput);

    expect(screen.getByText('Please enter a valid email address')).toBeInTheDocument();
  });

  it('should display error message when error prop is provided', () => {
    render(
      <CreateConsumerModal
        isOpen={true}
        onClose={mockOnClose}
        onSubmit={mockOnSubmit}
        error="Something went wrong"
      />
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });

  it('should show loading state when isLoading is true', () => {
    render(
      <CreateConsumerModal
        isOpen={true}
        onClose={mockOnClose}
        onSubmit={mockOnSubmit}
        isLoading={true}
      />
    );

    expect(screen.getByText('Creating...')).toBeInTheDocument();
  });

  it('should call onClose when Cancel is clicked', () => {
    render(<CreateConsumerModal isOpen={true} onClose={mockOnClose} onSubmit={mockOnSubmit} />);

    fireEvent.click(screen.getByText('Cancel'));
    expect(mockOnClose).toHaveBeenCalled();
  });
});
