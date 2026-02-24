/**
 * Tests for DisableBindingModal component
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { DisableBindingModal } from './DisableBindingModal';
import { renderWithProviders } from '../../test/helpers';
import type { ProtocolBinding } from '../../types';

describe('DisableBindingModal', () => {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();

  const mockBinding: ProtocolBinding = {
    protocol: 'rest',
    enabled: true,
    traffic_24h: 1250,
    endpoint: 'https://api.example.com/v1',
  };

  const defaultProps = { onConfirm, onCancel, binding: mockBinding };

  beforeEach(() => {
    vi.clearAllMocks();
    onConfirm.mockReset();
    onCancel.mockReset();
  });

  it('returns null (renders nothing) when binding is null', () => {
    const { container } = renderWithProviders(
      <DisableBindingModal binding={null} onConfirm={onConfirm} onCancel={onCancel} />
    );

    expect(container.firstChild).toBeNull();
  });

  it('renders modal title with protocol name "REST"', () => {
    renderWithProviders(<DisableBindingModal {...defaultProps} />);

    expect(screen.getByText('Disable REST binding?')).toBeInTheDocument();
  });

  it('shows traffic count formatted with locale separator', () => {
    renderWithProviders(<DisableBindingModal {...defaultProps} />);

    // 1250 formatted with toLocaleString → "1,250" (en-US), "1 250" (fr-FR)
    expect(screen.getByText(/1[\s\u202f,.]?250/)).toBeInTheDocument();
  });

  it('shows the endpoint URL', () => {
    renderWithProviders(<DisableBindingModal {...defaultProps} />);

    expect(screen.getByText('https://api.example.com/v1')).toBeInTheDocument();
  });

  it('clicking Cancel calls onCancel', () => {
    renderWithProviders(<DisableBindingModal {...defaultProps} />);

    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));

    expect(onCancel).toHaveBeenCalledOnce();
  });

  it('clicking Confirm calls onConfirm', () => {
    renderWithProviders(<DisableBindingModal {...defaultProps} />);

    fireEvent.click(screen.getByText('Disable'));

    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it('Cancel and Disable buttons are disabled when isLoading is true', () => {
    renderWithProviders(<DisableBindingModal {...defaultProps} isLoading={true} />);

    const cancelButton = screen.getByRole('button', { name: /cancel/i });
    expect(cancelButton).toBeDisabled();

    // Disable button is replaced by "Disabling..." text, still disabled
    const disablingButton = screen.getByRole('button', { name: /disabling/i });
    expect(disablingButton).toBeDisabled();
  });

  it('clicking the backdrop calls onCancel', () => {
    const { container } = renderWithProviders(<DisableBindingModal {...defaultProps} />);

    // The backdrop is the div with aria-hidden="true" and fixed inset-0 bg-black/50
    const backdrop = container.querySelector('[aria-hidden="true"]') as HTMLElement;
    expect(backdrop).toBeInTheDocument();

    fireEvent.click(backdrop);

    expect(onCancel).toHaveBeenCalledOnce();
  });

  it('renders the dialog with role="dialog"', () => {
    renderWithProviders(<DisableBindingModal {...defaultProps} />);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('shows loading spinner text when isLoading is true', () => {
    renderWithProviders(<DisableBindingModal {...defaultProps} isLoading={true} />);

    expect(screen.getByText(/Disabling\.\.\./)).toBeInTheDocument();
  });

  it('renders "Disable REST binding?" for REST protocol', () => {
    renderWithProviders(<DisableBindingModal {...defaultProps} />);

    expect(screen.getByText(/Disable REST binding\?/)).toBeInTheDocument();
  });

  it('renders the correct label for MCP protocol', () => {
    const mcpBinding: ProtocolBinding = {
      protocol: 'mcp',
      enabled: true,
      traffic_24h: 100,
    };

    renderWithProviders(
      <DisableBindingModal binding={mcpBinding} onConfirm={onConfirm} onCancel={onCancel} />
    );

    expect(screen.getByText('Disable MCP binding?')).toBeInTheDocument();
  });

  it('does not show endpoint section when endpoint is absent', () => {
    const bindingNoEndpoint: ProtocolBinding = {
      protocol: 'rest',
      enabled: true,
      traffic_24h: 10,
    };

    renderWithProviders(
      <DisableBindingModal binding={bindingNoEndpoint} onConfirm={onConfirm} onCancel={onCancel} />
    );

    expect(screen.queryByText('https://api.example.com/v1')).not.toBeInTheDocument();
  });
});
