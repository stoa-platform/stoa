import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Field, FieldInput, FieldLabel } from '@stoa/shared/components/Field';

describe('Field', () => {
  it('associates a label and a constraint error, and clears invalid state after correction', () => {
    render(
      <form>
        <Field>
          <FieldLabel>Email</FieldLabel>
          <FieldInput type="email" required />
        </Field>
      </form>
    );
    const input = screen.getByRole('textbox', { name: 'Email' });
    expect(input).not.toHaveAttribute('aria-invalid');
    fireEvent.invalid(input);
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAccessibleDescription(screen.getByRole('alert').textContent || '');
    fireEvent.input(input, { target: { value: 'person@example.com' } });
    expect(input).not.toHaveAttribute('aria-invalid');
    expect(input).not.toHaveAttribute('aria-describedby');
  });

  it('preserves help text alongside server field errors and generates distinct ids', () => {
    render(
      <>
        <p id="help">Use your work email</p>
        <Field error="Already used">
          <FieldLabel>First email</FieldLabel>
          <FieldInput aria-describedby="help" />
        </Field>
        <Field>
          <FieldLabel>Second email</FieldLabel>
          <FieldInput />
        </Field>
      </>
    );
    const first = screen.getByRole('textbox', { name: 'First email' });
    expect(first).toHaveAccessibleDescription('Use your work email Already used');
    expect(first).toHaveAttribute('aria-invalid', 'true');
    expect(first.id).not.toBe(screen.getByRole('textbox', { name: 'Second email' }).id);
  });
});
