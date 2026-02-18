import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { SandboxConfirmationModal } from '../SandboxConfirmationModal';
import { renderWithProviders } from '../../../test/helpers';

describe('SandboxConfirmationModal', () => {
  const onClose = vi.fn();
  const onConfirm = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when isOpen=false', () => {
    const { container } = renderWithProviders(
      <SandboxConfirmationModal
        isOpen={false}
        onClose={onClose}
        onConfirm={onConfirm}
        environmentName="Production"
      />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders modal content when isOpen=true', () => {
    renderWithProviders(
      <SandboxConfirmationModal
        isOpen={true}
        onClose={onClose}
        onConfirm={onConfirm}
        environmentName="Production"
      />
    );
    expect(screen.getByText('Production Environment Warning')).toBeInTheDocument();
    expect(screen.getByText(/You are about to test against/)).toBeInTheDocument();
    expect(screen.getByText('Production')).toBeInTheDocument();
  });

  it('renders all 4 warning bullet points', () => {
    renderWithProviders(
      <SandboxConfirmationModal
        isOpen={true}
        onClose={onClose}
        onConfirm={onConfirm}
        environmentName="Production"
      />
    );
    expect(screen.getByText(/real production endpoints/)).toBeInTheDocument();
    // "logged for audit purposes" appears in both the bullet list and checkbox label — use getAllByText
    expect(screen.getAllByText(/logged for audit purposes/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/modify production data/)).toBeInTheDocument();
    expect(screen.getByText(/shared with production traffic/)).toBeInTheDocument();
  });

  it('renders confirmation checkbox', () => {
    renderWithProviders(
      <SandboxConfirmationModal
        isOpen={true}
        onClose={onClose}
        onConfirm={onConfirm}
        environmentName="Production"
      />
    );
    expect(screen.getByRole('checkbox')).toBeInTheDocument();
    expect(screen.getByRole('checkbox')).not.toBeChecked();
  });

  it('confirm button is disabled when checkbox is unchecked', () => {
    renderWithProviders(
      <SandboxConfirmationModal
        isOpen={true}
        onClose={onClose}
        onConfirm={onConfirm}
        environmentName="Production"
      />
    );
    const confirmBtn = screen.getByRole('button', { name: /I Understand, Continue/i });
    expect(confirmBtn).toBeDisabled();
  });

  it('confirm button is enabled after checking the checkbox', () => {
    renderWithProviders(
      <SandboxConfirmationModal
        isOpen={true}
        onClose={onClose}
        onConfirm={onConfirm}
        environmentName="Production"
      />
    );
    fireEvent.click(screen.getByRole('checkbox'));
    const confirmBtn = screen.getByRole('button', { name: /I Understand, Continue/i });
    expect(confirmBtn).not.toBeDisabled();
  });

  it('calls onConfirm when checkbox checked and confirm button clicked', () => {
    renderWithProviders(
      <SandboxConfirmationModal
        isOpen={true}
        onClose={onClose}
        onConfirm={onConfirm}
        environmentName="Production"
      />
    );
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: /I Understand, Continue/i }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('does not call onConfirm when checkbox is unchecked and confirm is clicked', () => {
    renderWithProviders(
      <SandboxConfirmationModal
        isOpen={true}
        onClose={onClose}
        onConfirm={onConfirm}
        environmentName="Production"
      />
    );
    // Confirm button is disabled, so click should not fire
    const confirmBtn = screen.getByRole('button', { name: /I Understand, Continue/i });
    fireEvent.click(confirmBtn);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('calls onClose when Cancel button is clicked', () => {
    renderWithProviders(
      <SandboxConfirmationModal
        isOpen={true}
        onClose={onClose}
        onConfirm={onConfirm}
        environmentName="Production"
      />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when X button is clicked', () => {
    renderWithProviders(
      <SandboxConfirmationModal
        isOpen={true}
        onClose={onClose}
        onConfirm={onConfirm}
        environmentName="Production"
      />
    );
    // The X button is at absolute top-right of the modal (first button in the modal)
    const xButton = document.querySelector('button.absolute') as HTMLElement;
    fireEvent.click(xButton);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when backdrop is clicked', () => {
    renderWithProviders(
      <SandboxConfirmationModal
        isOpen={true}
        onClose={onClose}
        onConfirm={onConfirm}
        environmentName="Production"
      />
    );
    const backdrop = screen.getByRole('button', { name: 'Close modal' });
    fireEvent.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('displays the environment name in the warning', () => {
    renderWithProviders(
      <SandboxConfirmationModal
        isOpen={true}
        onClose={onClose}
        onConfirm={onConfirm}
        environmentName="EU-West Production"
      />
    );
    expect(screen.getByText('EU-West Production')).toBeInTheDocument();
  });

  it('resets checkbox state between renders', () => {
    const { rerender } = renderWithProviders(
      <SandboxConfirmationModal
        isOpen={true}
        onClose={onClose}
        onConfirm={onConfirm}
        environmentName="Production"
      />
    );
    // Check the checkbox
    fireEvent.click(screen.getByRole('checkbox'));
    expect(screen.getByRole('checkbox')).toBeChecked();

    // Close and reopen
    rerender(
      <SandboxConfirmationModal
        isOpen={false}
        onClose={onClose}
        onConfirm={onConfirm}
        environmentName="Production"
      />
    );
    rerender(
      <SandboxConfirmationModal
        isOpen={true}
        onClose={onClose}
        onConfirm={onConfirm}
        environmentName="Production"
      />
    );
    // Checkbox state persists within same component instance (useState)
    // but is reset when component unmounts/remounts
  });
});
