import { StrictMode } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import {
  Field,
  FieldInput,
  FieldLabel,
  FieldSelect,
  FieldTextarea,
} from '@stoa/shared/components/Field';

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

type ControlProps = { id?: string; 'aria-describedby'?: string; required?: boolean };

const controls = [
  { name: 'input', role: 'textbox', render: (props: ControlProps) => <FieldInput {...props} /> },
  {
    name: 'select',
    role: 'combobox',
    render: (props: ControlProps) => (
      <FieldSelect {...props}>
        <option value="">Choose a value</option>
        <option value="one">One</option>
      </FieldSelect>
    ),
  },
  {
    name: 'textarea',
    role: 'textbox',
    render: (props: ControlProps) => <FieldTextarea {...props} />,
  },
];

function expectResolvedAssociations(container: HTMLElement) {
  const elementsWithIds = [...container.querySelectorAll('[id]')];
  const ids = elementsWithIds.map((element) => element.id);
  expect(new Set(ids).size).toBe(ids.length);
  for (const label of container.querySelectorAll('label')) {
    expect(label.control).not.toBeNull();
    expect(label.control).toHaveAccessibleName(label.textContent || '');
  }
  for (const control of container.querySelectorAll('[aria-describedby]')) {
    for (const id of control.getAttribute('aria-describedby')!.trim().split(/\s+/)) {
      expect(document.getElementById(id)).not.toBeNull();
    }
  }
}

describe.each(controls)('regression/CAB-2298 Field $name associations', (control) => {
  it('uses an explicit Field id for the label, control and error', () => {
    const { container } = render(
      <Field id="explicit-field" error="Invalid value">
        <FieldLabel>Value</FieldLabel>
        {control.render({})}
      </Field>
    );
    const input = screen.getByRole(control.role, { name: 'Value' });
    expect(input).toHaveAttribute('id', 'explicit-field');
    expect(screen.getByText('Value')).toHaveAttribute('for', input.id);
    expect(input).toHaveAccessibleDescription('Invalid value');
    expect(document.getElementById(input.getAttribute('aria-describedby')!)).toBe(
      screen.getByRole('alert')
    );
    expectResolvedAssociations(container);
  });

  it.each([undefined, 'field-fallback'])(
    'tracks an explicit control id and its removal in StrictMode (Field id: %s)',
    (fieldId) => {
      const field = (id?: string) => (
        <StrictMode>
          <Field id={fieldId} error="Invalid value">
            <FieldLabel>Value</FieldLabel>
            {control.render({ id })}
          </Field>
        </StrictMode>
      );
      const { container, rerender } = render(field('explicit-control'));
      const input = screen.getByRole(control.role);
      expect(input).toHaveAttribute('id', 'explicit-control');
      expect(input).toHaveAccessibleName('Value');
      expect(screen.getByLabelText('Value')).toBe(input);
      expectResolvedAssociations(container);

      rerender(field('updated-control'));
      expect(input).toHaveAttribute('id', 'updated-control');
      expect(screen.getByLabelText('Value')).toBe(input);
      expect(input).toHaveAccessibleDescription('Invalid value');
      expectResolvedAssociations(container);

      rerender(field());
      expect(input.id).toBeTruthy();
      expect(input.id).not.toBe('updated-control');
      if (fieldId) expect(input).toHaveAttribute('id', fieldId);
      expect(screen.getByLabelText('Value')).toBe(input);
      expect(input).toHaveAccessibleDescription('Invalid value');
      expectResolvedAssociations(container);
    }
  );

  it('preserves an explicit label target', () => {
    render(
      <Field>
        <FieldLabel htmlFor="chosen-control">Value</FieldLabel>
        {control.render({ id: 'chosen-control' })}
      </Field>
    );
    expect(screen.getByLabelText('Value')).toHaveAttribute('id', 'chosen-control');
  });

  it('removes a native error after correction while preserving existing help', () => {
    const { container } = render(
      <>
        <p id="native-help">Choose a valid value</p>
        <Field>
          <FieldLabel>Required value</FieldLabel>
          {control.render({ required: true, 'aria-describedby': 'native-help' })}
        </Field>
        <Field>
          <FieldLabel>Unaffected value</FieldLabel>
          {control.render({})}
        </Field>
      </>
    );
    const input = screen.getByRole(control.role, { name: 'Required value' });
    const unaffected = screen.getByRole(control.role, { name: 'Unaffected value' });
    fireEvent.invalid(input);
    const error = screen.getByRole('alert');
    const errorId = error.id;
    expect(error).not.toHaveTextContent(/^$/);
    expect(input).toHaveAccessibleDescription(`Choose a valid value ${error.textContent}`);
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(unaffected).not.toHaveAttribute('aria-invalid');
    expect(unaffected).not.toHaveAttribute('aria-describedby');
    expectResolvedAssociations(container);

    fireEvent.input(input, { target: { value: 'one' } });
    expect(input).not.toHaveAttribute('aria-invalid');
    expect(input).toHaveAttribute('aria-describedby', 'native-help');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(document.getElementById(errorId)).toBeNull();
    expectResolvedAssociations(container);
  });

  it('keeps repeated fields independent through error addition, replacement and removal', () => {
    const fields = (firstError?: string, secondError?: string) => (
      <>
        <p id="format-help">Expected format</p>
        <p id="privacy-help">Stored privately</p>
        <Field error={firstError}>
          <FieldLabel>First value</FieldLabel>
          {control.render({ 'aria-describedby': 'format-help privacy-help' })}
        </Field>
        <Field error={secondError}>
          <FieldLabel>Second value</FieldLabel>
          {control.render({})}
        </Field>
        <Field id="third-value" error="Third error">
          <FieldLabel>Third value</FieldLabel>
          {control.render({})}
        </Field>
      </>
    );
    const { container, rerender } = render(fields());
    const first = screen.getByRole(control.role, { name: 'First value' });
    const second = screen.getByRole(control.role, { name: 'Second value' });
    const third = screen.getByRole(control.role, { name: 'Third value' });
    const ids = [first.id, second.id, third.id];
    expect(ids.every(Boolean)).toBe(true);
    expect(new Set(ids).size).toBe(3);
    expect(first).toHaveAccessibleDescription('Expected format Stored privately');
    expect(second).not.toHaveAttribute('aria-describedby');
    expectResolvedAssociations(container);

    rerender(fields('First error', 'Second error'));
    const firstErrorId = first.getAttribute('aria-describedby')!.split(/\s+/).slice(-1)[0];
    const secondErrorId = second.getAttribute('aria-describedby')!;
    expect(first).toHaveAccessibleDescription('Expected format Stored privately First error');
    expect(second).toHaveAccessibleDescription('Second error');
    expect(third).toHaveAccessibleDescription('Third error');
    expect(first).toHaveAttribute('aria-invalid', 'true');
    expect(second).toHaveAttribute('aria-invalid', 'true');
    expectResolvedAssociations(container);

    rerender(fields('Replacement error'));
    expect(first).toHaveAccessibleDescription('Expected format Stored privately Replacement error');
    expect(second).not.toHaveAttribute('aria-invalid');
    expect(second).not.toHaveAttribute('aria-describedby');
    expect(document.getElementById(secondErrorId)).toBeNull();
    expectResolvedAssociations(container);

    rerender(fields());
    expect(first).toHaveAttribute('aria-describedby', 'format-help privacy-help');
    expect(first).not.toHaveAttribute('aria-invalid');
    expect(document.getElementById(firstErrorId)).toBeNull();
    expect(third).toHaveAttribute('aria-invalid', 'true');
    expect([first.id, second.id, third.id]).toEqual(ids);
    expectResolvedAssociations(container);
  });
});
