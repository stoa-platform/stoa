import { StrictMode, useState } from 'react';
import { render, screen, within, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { Modal, ModalTitle } from '@stoa/shared/components/Modal';

function Example() {
  const [open, setOpen] = useState(false);
  const [child, setChild] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>Open</button>
      {open && (
        <Modal onClose={() => setOpen(false)}>
          <ModalTitle>Parent</ModalTitle>
          <button onClick={() => setChild(true)}>Open child</button>
          <button onClick={() => setOpen(false)}>Close</button>
          {child && (
            <Modal onClose={() => setChild(false)}>
              <ModalTitle>Child</ModalTitle>
              <button onClick={() => setChild(false)}>Close child</button>
              <button onClick={() => setOpen(false)}>Close all</button>
            </Modal>
          )}
        </Modal>
      )}
    </>
  );
}

describe('accessible Modal', () => {
  it('names the dialog, moves focus, cycles Tab both ways and restores the opener in StrictMode', async () => {
    const user = userEvent.setup();
    render(
      <StrictMode>
        <Example />
      </StrictMode>
    );
    const opener = screen.getByRole('button', { name: 'Open' });
    await user.click(opener);
    const dialog = screen.getByRole('dialog', { name: 'Parent' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(within(dialog).getByRole('heading')).toHaveFocus();
    await user.tab();
    expect(within(dialog).getByRole('button', { name: 'Open child' })).toHaveFocus();
    await user.tab({ shift: true });
    expect(within(dialog).getByRole('button', { name: 'Close' })).toHaveFocus();
    await user.tab();
    expect(within(dialog).getByRole('button', { name: 'Open child' })).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it('closes only the top dialog and restores focus through a nested dialog', async () => {
    const user = userEvent.setup();
    document.body.style.overflow = 'auto';
    render(<Example />);
    await user.click(screen.getByRole('button', { name: 'Open' }));
    const trigger = screen.getByRole('button', { name: 'Open child' });
    await user.click(trigger);
    expect(screen.getByRole('dialog', { name: 'Child' })).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog', { name: 'Child' })).not.toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: 'Parent' })).toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(document.body.style.overflow).toBe('hidden');
    await user.keyboard('{Escape}');
    expect(document.body.style.overflow).toBe('auto');
    document.body.style.overflow = '';
  });

  it('keeps focus with no interactive children and rejects cancellation while busy', async () => {
    const onClose = vi.fn();
    const { rerender } = render(
      <Modal closeDisabled onClose={onClose}>
        <ModalTitle>Busy</ModalTitle>
      </Modal>
    );
    const user = userEvent.setup();
    await user.tab();
    expect(screen.getByRole('dialog')).toHaveFocus();
    await user.keyboard('{Escape}');
    fireEvent(screen.getByRole('dialog'), new Event('cancel', { cancelable: true }));
    expect(onClose).not.toHaveBeenCalled();
    rerender(
      <Modal onClose={onClose}>
        <ModalTitle>Ready</ModalTitle>
      </Modal>
    );
    await user.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('keeps unique names for simultaneous instances', () => {
    render(
      <>
        <Modal onClose={() => {}}>
          <ModalTitle>First</ModalTitle>
        </Modal>
        <Modal onClose={() => {}}>
          <ModalTitle>Second</ModalTitle>
        </Modal>
      </>
    );
    const dialogs = screen.getAllByRole('dialog');
    expect(dialogs[0].getAttribute('aria-labelledby')).not.toBe(
      dialogs[1].getAttribute('aria-labelledby')
    );
  });

  it('restores the original opener if parent and child are removed together', async () => {
    const user = userEvent.setup();
    render(<Example />);
    const opener = screen.getByRole('button', { name: 'Open' });
    await user.click(opener);
    await user.click(screen.getByRole('button', { name: 'Open child' }));
    await user.click(screen.getByRole('button', { name: 'Close all' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });
});
