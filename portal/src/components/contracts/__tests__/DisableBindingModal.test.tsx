import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { DisableBindingModal } from '../DisableBindingModal';
import { renderWithProviders } from '../../../test/helpers';
import type { ProtocolBinding } from '../../../types';

const mockBinding: ProtocolBinding = {
  protocol: 'rest',
  enabled: true,
  endpoint: '/v1/orders',
  traffic_24h: 1500,
};

describe('DisableBindingModal', () => {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when binding is null', () => {
    const { container } = renderWithProviders(
      <DisableBindingModal binding={null} onConfirm={onConfirm} onCancel={onCancel} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders modal with protocol label and traffic count', () => {
    renderWithProviders(
      <DisableBindingModal binding={mockBinding} onConfirm={onConfirm} onCancel={onCancel} />
    );
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/Disable REST binding\?/)).toBeInTheDocument();
    expect(screen.getByText(/1,500 requests/)).toBeInTheDocument();
  });

  it('renders endpoint when present', () => {
    renderWithProviders(
      <DisableBindingModal binding={mockBinding} onConfirm={onConfirm} onCancel={onCancel} />
    );
    expect(screen.getByText('/v1/orders')).toBeInTheDocument();
  });

  it('does not render endpoint section when endpoint is absent', () => {
    const bindingNoEndpoint = { ...mockBinding, endpoint: undefined };
    renderWithProviders(
      <DisableBindingModal binding={bindingNoEndpoint} onConfirm={onConfirm} onCancel={onCancel} />
    );
    expect(screen.queryByText('/v1/orders')).not.toBeInTheDocument();
  });

  it('calls onConfirm when Disable button is clicked', () => {
    renderWithProviders(
      <DisableBindingModal binding={mockBinding} onConfirm={onConfirm} onCancel={onCancel} />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Disable' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('calls onCancel when Cancel button is clicked', () => {
    renderWithProviders(
      <DisableBindingModal binding={mockBinding} onConfirm={onConfirm} onCancel={onCancel} />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('calls onCancel when close button is clicked', () => {
    renderWithProviders(
      <DisableBindingModal binding={mockBinding} onConfirm={onConfirm} onCancel={onCancel} />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('calls onCancel when backdrop is clicked', () => {
    renderWithProviders(
      <DisableBindingModal binding={mockBinding} onConfirm={onConfirm} onCancel={onCancel} />
    );
    // The backdrop has aria-hidden and is the first div with onClick
    const backdrop = document.querySelector('[aria-hidden="true"]') as HTMLElement;
    fireEvent.click(backdrop);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('shows loading state when isLoading=true', () => {
    renderWithProviders(
      <DisableBindingModal
        binding={mockBinding}
        onConfirm={onConfirm}
        onCancel={onCancel}
        isLoading={true}
      />
    );
    expect(screen.getByText('Disabling...')).toBeInTheDocument();
  });

  it('disables buttons when isLoading=true', () => {
    renderWithProviders(
      <DisableBindingModal
        binding={mockBinding}
        onConfirm={onConfirm}
        onCancel={onCancel}
        isLoading={true}
      />
    );
    const cancelBtn = screen.getByRole('button', { name: 'Cancel' });
    expect(cancelBtn).toBeDisabled();
  });

  it('uses protocol label from mapping (GraphQL)', () => {
    const graphqlBinding = { ...mockBinding, protocol: 'graphql' as const };
    renderWithProviders(
      <DisableBindingModal binding={graphqlBinding} onConfirm={onConfirm} onCancel={onCancel} />
    );
    expect(screen.getByText(/Disable GraphQL binding\?/)).toBeInTheDocument();
  });

  it('shows 0 requests when traffic_24h is undefined', () => {
    const noTraffic = { ...mockBinding, traffic_24h: undefined };
    renderWithProviders(
      <DisableBindingModal binding={noTraffic} onConfirm={onConfirm} onCancel={onCancel} />
    );
    expect(screen.getByText(/0 requests/)).toBeInTheDocument();
  });
});
