import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../../test/helpers';
import { TryItForm } from '../TryItForm';
import type { MCPInputSchema } from '../../../types';

const baseSchema: MCPInputSchema = {
  type: 'object',
  properties: {
    name: { type: 'string', minLength: 2, maxLength: 50 },
    email: { type: 'string', format: 'email' },
    age: { type: 'integer', minimum: 0, maximum: 150 },
    code: { type: 'string', pattern: '^[A-Z]{3}-\\d{3}$' },
    role: { type: 'string', enum: ['admin', 'user', 'viewer'] },
  },
  required: ['name', 'email'],
};

describe('TryItForm', () => {
  const mockOnInvoke = vi.fn().mockResolvedValue({ ok: true });
  const user = userEvent.setup();

  beforeEach(() => {
    vi.clearAllMocks();
    mockOnInvoke.mockResolvedValue({ ok: true });
  });

  it('submits valid data without errors', async () => {
    renderWithProviders(
      <TryItForm schema={baseSchema} toolName="test-tool" onInvoke={mockOnInvoke} />
    );

    await user.type(screen.getByPlaceholderText('Enter name...'), 'Alice');
    await user.type(screen.getByPlaceholderText('Enter email...'), 'alice@example.com');
    await user.click(screen.getByRole('button', { name: /Invoke Tool/ }));

    await waitFor(() => {
      expect(mockOnInvoke).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'Alice', email: 'alice@example.com' })
      );
    });
    expect(screen.queryByText(/Validation failed/)).not.toBeInTheDocument();
  });

  it('shows error for missing required field', async () => {
    renderWithProviders(
      <TryItForm schema={baseSchema} toolName="test-tool" onInvoke={mockOnInvoke} />
    );

    // Only fill name, skip email
    await user.type(screen.getByPlaceholderText('Enter name...'), 'Alice');
    await user.click(screen.getByRole('button', { name: /Invoke Tool/ }));

    await waitFor(() => {
      expect(screen.getByText(/Validation failed/)).toBeInTheDocument();
    });
    expect(mockOnInvoke).not.toHaveBeenCalled();
  });

  it('shows error for invalid pattern', async () => {
    renderWithProviders(
      <TryItForm schema={baseSchema} toolName="test-tool" onInvoke={mockOnInvoke} />
    );

    await user.type(screen.getByPlaceholderText('Enter name...'), 'Alice');
    await user.type(screen.getByPlaceholderText('Enter email...'), 'alice@example.com');
    await user.type(screen.getByPlaceholderText('Enter code...'), 'bad-code');
    await user.click(screen.getByRole('button', { name: /Invoke Tool/ }));

    await waitFor(() => {
      expect(screen.getByText(/Validation failed/)).toBeInTheDocument();
    });
    expect(mockOnInvoke).not.toHaveBeenCalled();
  });

  it('shows error for string shorter than minLength', async () => {
    renderWithProviders(
      <TryItForm schema={baseSchema} toolName="test-tool" onInvoke={mockOnInvoke} />
    );

    await user.type(screen.getByPlaceholderText('Enter name...'), 'A');
    await user.type(screen.getByPlaceholderText('Enter email...'), 'a@b.co');
    await user.click(screen.getByRole('button', { name: /Invoke Tool/ }));

    await waitFor(() => {
      expect(screen.getByText(/Validation failed/)).toBeInTheDocument();
    });
    expect(mockOnInvoke).not.toHaveBeenCalled();
  });

  it('shows error for string exceeding maxLength', async () => {
    renderWithProviders(
      <TryItForm schema={baseSchema} toolName="test-tool" onInvoke={mockOnInvoke} />
    );

    // name has maxLength: 50 — type a string longer than 50 chars
    const longName = 'A'.repeat(51);
    await user.type(screen.getByPlaceholderText('Enter name...'), longName);
    await user.type(screen.getByPlaceholderText('Enter email...'), 'alice@example.com');
    await user.click(screen.getByRole('button', { name: /Invoke Tool/ }));

    await waitFor(() => {
      expect(screen.getByText(/Validation failed/)).toBeInTheDocument();
    });
    expect(mockOnInvoke).not.toHaveBeenCalled();
  });

  it('clears field error when user fixes the value', async () => {
    renderWithProviders(
      <TryItForm schema={baseSchema} toolName="test-tool" onInvoke={mockOnInvoke} />
    );

    // Submit empty to get required error
    await user.click(screen.getByRole('button', { name: /Invoke Tool/ }));
    await waitFor(() => {
      expect(screen.getByText(/Validation failed/)).toBeInTheDocument();
    });

    // Fix the fields
    await user.type(screen.getByPlaceholderText('Enter name...'), 'Alice');
    await user.type(screen.getByPlaceholderText('Enter email...'), 'alice@example.com');

    // Per-field errors should be cleared on change
    const fieldErrors = screen.queryAllByText(/is a required property/i);
    expect(fieldErrors).toHaveLength(0);
  });

  it('renders "No input schema" when schema is empty', () => {
    renderWithProviders(<TryItForm schema={null} toolName="test-tool" onInvoke={mockOnInvoke} />);

    expect(screen.getByText('No input schema available')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Invoke Tool/ })).not.toBeInTheDocument();
  });
});
