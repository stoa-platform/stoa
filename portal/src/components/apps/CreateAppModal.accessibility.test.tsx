import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { CreateAppModal } from './CreateAppModal';

describe('CreateAppModal accessibility', () => {
  it('names every URL and never submits on Add URL or Cancel', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined),
      onClose = vi.fn();
    const user = userEvent.setup();
    render(<CreateAppModal isOpen onClose={onClose} onSubmit={onSubmit} />);
    expect(screen.getByRole('dialog', { name: 'Create New Application' })).toBeInTheDocument();
    await user.type(screen.getByRole('textbox', { name: /Application Name/ }), 'Example');
    await user.click(screen.getByRole('button', { name: /Add another URL/ }));
    expect(screen.getByRole('textbox', { name: 'Callback URL 1' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Callback URL 2' })).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onClose).toHaveBeenCalledOnce();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('describes the form error and connects a native validation error to its field', () => {
    const { container } = render(
      <CreateAppModal isOpen onClose={() => {}} onSubmit={vi.fn()} error="Creation failed" />
    );
    // Modal renders in a portal; locate the actual form in the document.
    expect(document.querySelector('form')).toHaveAccessibleDescription('Creation failed');
    expect(container).toBeEmptyDOMElement();
    const input = screen.getByRole('textbox', { name: /Application Name/ });
    fireEvent.invalid(input);
    expect(input).toHaveAttribute('aria-invalid', 'true');
    const id = input.getAttribute('aria-describedby');
    expect(id).toBeTruthy();
    expect(document.getElementById(id!)).toHaveAttribute('role', 'alert');
    fireEvent.input(input, { target: { value: 'Example' } });
    expect(input).not.toHaveAttribute('aria-invalid');
  });
});
