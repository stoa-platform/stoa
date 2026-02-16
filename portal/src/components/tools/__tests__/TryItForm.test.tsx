import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../../test/helpers';
import { TryItForm, validateField } from '../TryItForm';
import type { MCPInputSchema, MCPPropertySchema } from '../../../types';

// --- Unit tests for validateField ---

describe('validateField', () => {
  describe('required fields', () => {
    it('returns error when required field is empty', () => {
      const prop: MCPPropertySchema = { type: 'string' };
      expect(validateField('', prop, true)).toBe('This field is required');
      expect(validateField(undefined, prop, true)).toBe('This field is required');
      expect(validateField(null, prop, true)).toBe('This field is required');
    });

    it('passes when required field has value', () => {
      const prop: MCPPropertySchema = { type: 'string' };
      expect(validateField('hello', prop, true)).toBeUndefined();
    });

    it('skips validation for optional empty fields', () => {
      const prop: MCPPropertySchema = { type: 'string', minLength: 5 };
      expect(validateField('', prop, false)).toBeUndefined();
    });
  });

  describe('string minLength / maxLength', () => {
    it('rejects string shorter than minLength', () => {
      const prop: MCPPropertySchema = { type: 'string', minLength: 3 };
      expect(validateField('ab', prop, false)).toBe('Minimum length is 3');
    });

    it('accepts string at minLength', () => {
      const prop: MCPPropertySchema = { type: 'string', minLength: 3 };
      expect(validateField('abc', prop, false)).toBeUndefined();
    });

    it('rejects string longer than maxLength', () => {
      const prop: MCPPropertySchema = { type: 'string', maxLength: 5 };
      expect(validateField('abcdef', prop, false)).toBe('Maximum length is 5');
    });

    it('accepts string at maxLength', () => {
      const prop: MCPPropertySchema = { type: 'string', maxLength: 5 };
      expect(validateField('abcde', prop, false)).toBeUndefined();
    });
  });

  describe('string pattern', () => {
    it('rejects string not matching pattern', () => {
      const prop: MCPPropertySchema = { type: 'string', pattern: '^[a-z]+$' };
      expect(validateField('ABC123', prop, false)).toBe('Must match pattern: ^[a-z]+$');
    });

    it('accepts string matching pattern', () => {
      const prop: MCPPropertySchema = { type: 'string', pattern: '^[a-z]+$' };
      expect(validateField('abc', prop, false)).toBeUndefined();
    });

    it('skips validation for invalid regex', () => {
      const prop: MCPPropertySchema = { type: 'string', pattern: '[invalid(' };
      expect(validateField('anything', prop, false)).toBeUndefined();
    });
  });

  describe('string enum', () => {
    it('rejects value not in enum', () => {
      const prop: MCPPropertySchema = { type: 'string', enum: ['a', 'b', 'c'] };
      expect(validateField('d', prop, false)).toBe('Must be one of: a, b, c');
    });

    it('accepts value in enum', () => {
      const prop: MCPPropertySchema = { type: 'string', enum: ['a', 'b', 'c'] };
      expect(validateField('b', prop, false)).toBeUndefined();
    });
  });

  describe('number minimum / maximum', () => {
    it('rejects number below minimum', () => {
      const prop: MCPPropertySchema = { type: 'number', minimum: 10 };
      expect(validateField(5, prop, false)).toBe('Minimum value is 10');
    });

    it('accepts number at minimum', () => {
      const prop: MCPPropertySchema = { type: 'number', minimum: 10 };
      expect(validateField(10, prop, false)).toBeUndefined();
    });

    it('rejects number above maximum', () => {
      const prop: MCPPropertySchema = { type: 'number', maximum: 100 };
      expect(validateField(101, prop, false)).toBe('Maximum value is 100');
    });

    it('accepts number at maximum', () => {
      const prop: MCPPropertySchema = { type: 'number', maximum: 100 };
      expect(validateField(100, prop, false)).toBeUndefined();
    });

    it('works for integer type', () => {
      const prop: MCPPropertySchema = { type: 'integer', minimum: 1, maximum: 10 };
      expect(validateField(0, prop, false)).toBe('Minimum value is 1');
      expect(validateField(11, prop, false)).toBe('Maximum value is 10');
      expect(validateField(5, prop, false)).toBeUndefined();
    });
  });
});

// --- Integration tests for TryItForm component ---

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
