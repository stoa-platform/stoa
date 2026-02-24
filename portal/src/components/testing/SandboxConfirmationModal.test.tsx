import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SandboxConfirmationModal } from './SandboxConfirmationModal';
import { renderWithProviders } from '../../test/helpers';

describe('SandboxConfirmationModal', () => {
  const onClose = vi.fn();
  const onConfirm = vi.fn();

  const defaultProps = {
    isOpen: true,
    onClose,
    onConfirm,
    environmentName: 'Production EU',
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should return null when not open', () => {
    const { container } = renderWithProviders(
      <SandboxConfirmationModal {...defaultProps} isOpen={false} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('should render warning header with environment name', () => {
    renderWithProviders(<SandboxConfirmationModal {...defaultProps} />);
    expect(screen.getByText('Production Environment Warning')).toBeInTheDocument();
    expect(screen.getByText(/Production EU/)).toBeInTheDocument();
  });

  it('should show warning notes', () => {
    renderWithProviders(<SandboxConfirmationModal {...defaultProps} />);
    expect(screen.getByText(/real production endpoints/)).toBeInTheDocument();
    expect(screen.getAllByText(/logged for audit purposes/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/modify production data/)).toBeInTheDocument();
    expect(screen.getByText(/shared with production traffic/)).toBeInTheDocument();
  });

  it('should show dev portal suggestion', () => {
    renderWithProviders(<SandboxConfirmationModal {...defaultProps} />);
    expect(screen.getByText(/portal.dev.gostoa.dev/)).toBeInTheDocument();
  });

  it('should disable confirm button by default (checkbox unchecked)', () => {
    renderWithProviders(<SandboxConfirmationModal {...defaultProps} />);
    const confirmButton = screen.getByText(/I Understand, Continue/);
    expect(confirmButton).toBeDisabled();
  });

  it('should enable confirm button after checkbox is checked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<SandboxConfirmationModal {...defaultProps} />);

    const checkbox = screen.getByRole('checkbox');
    await user.click(checkbox);

    const confirmButton = screen.getByText(/I Understand, Continue/);
    expect(confirmButton).not.toBeDisabled();
  });

  it('should call onConfirm when checkbox checked and confirm clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<SandboxConfirmationModal {...defaultProps} />);

    await user.click(screen.getByRole('checkbox'));
    await user.click(screen.getByText(/I Understand, Continue/));

    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('should NOT call onConfirm when checkbox is unchecked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<SandboxConfirmationModal {...defaultProps} />);

    // Try clicking confirm without checking checkbox
    await user.click(screen.getByText(/I Understand, Continue/));
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('should call onClose when Cancel clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<SandboxConfirmationModal {...defaultProps} />);
    await user.click(screen.getByText('Cancel'));
    expect(onClose).toHaveBeenCalled();
  });

  it('should call onClose when close button clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<SandboxConfirmationModal {...defaultProps} />);

    // The X close button
    const closeButtons = screen.getAllByRole('button');
    const xButton = closeButtons.find(
      (btn) => btn.querySelector('.lucide-x') || btn.textContent === ''
    );
    if (xButton) {
      await user.click(xButton);
      expect(onClose).toHaveBeenCalled();
    }
  });

  it('should show checkbox label with confirmation text', () => {
    renderWithProviders(<SandboxConfirmationModal {...defaultProps} />);
    expect(screen.getByText(/I understand I am testing against a/)).toBeInTheDocument();
    expect(screen.getAllByText(/production environment/).length).toBeGreaterThanOrEqual(1);
  });
});
