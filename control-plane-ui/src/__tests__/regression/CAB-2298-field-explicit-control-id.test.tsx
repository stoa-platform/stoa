import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Field, FieldInput, FieldLabel } from '@stoa/shared/components/Field';

// Regression for CAB-2298: a control rendered with its own id inside a Field
// left the label pointing at the Field's generated id, so the label no longer
// named the control.
describe('regression/CAB-2298', () => {
  it('labels a control that carries an explicit id', () => {
    render(
      <Field>
        <FieldLabel>Common name</FieldLabel>
        <FieldInput id="cert-common-name" />
      </Field>
    );
    const input = screen.getByLabelText('Common name');
    expect(input).toHaveAttribute('id', 'cert-common-name');
    expect(screen.getByText('Common name')).toHaveAttribute('for', 'cert-common-name');
  });

  it('keeps the error description on the explicit control id', () => {
    render(
      <Field error="Required">
        <FieldLabel>Common name</FieldLabel>
        <FieldInput id="cert-common-name" />
      </Field>
    );
    const input = screen.getByRole('textbox', { name: 'Common name' });
    expect(input).toHaveAccessibleDescription('Required');
    expect(input.getAttribute('aria-describedby')).toContain('cert-common-name-error');
  });
});
