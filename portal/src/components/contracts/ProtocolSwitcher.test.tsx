import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { ProtocolSwitcher } from './ProtocolSwitcher';
import { renderWithProviders } from '../../test/helpers';
import { useBindings, useEnableBinding, useDisableBinding } from '../../hooks/useContracts';

vi.mock('../../hooks/useContracts', () => ({
  useBindings: vi.fn(),
  useEnableBinding: vi.fn(),
  useDisableBinding: vi.fn(),
}));

vi.mock('./ProtocolRow', () => ({
  ProtocolRow: ({
    binding,
    onToggle,
  }: {
    binding: { protocol: string; enabled: boolean };
    onToggle: (enabled: boolean) => void;
  }) => (
    <div data-testid={`protocol-row-${binding.protocol}`}>
      <button onClick={() => onToggle(!binding.enabled)}>Toggle {binding.protocol}</button>
    </div>
  ),
}));

vi.mock('./DisableBindingModal', () => ({
  DisableBindingModal: ({
    binding,
    onConfirm,
    onCancel,
  }: {
    binding: unknown;
    onConfirm: () => void;
    onCancel: () => void;
  }) =>
    binding ? (
      <div data-testid="disable-modal">
        <button onClick={onConfirm}>Confirm</button>
        <button onClick={onCancel}>Cancel</button>
      </div>
    ) : null,
}));

const mockRefetch = vi.fn();
const mockEnableMutateAsync = vi.fn();
const mockDisableMutateAsync = vi.fn();

const mockBindings = [
  { protocol: 'rest', enabled: true, traffic_24h: 0 },
  { protocol: 'mcp', enabled: false, traffic_24h: 1500 },
  { protocol: 'graphql', enabled: false, traffic_24h: 0 },
];

describe('ProtocolSwitcher', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockEnableMutateAsync.mockResolvedValue(undefined);
    mockDisableMutateAsync.mockResolvedValue(undefined);

    vi.mocked(useBindings).mockReturnValue({
      data: { bindings: mockBindings, contract_id: 'contract-1', contract_name: 'orders-api' },
      isLoading: false,
      error: null,
      refetch: mockRefetch,
    } as ReturnType<typeof useBindings>);

    vi.mocked(useEnableBinding).mockReturnValue({
      mutateAsync: mockEnableMutateAsync,
      isPending: false,
      variables: undefined,
    } as unknown as ReturnType<typeof useEnableBinding>);

    vi.mocked(useDisableBinding).mockReturnValue({
      mutateAsync: mockDisableMutateAsync,
      isPending: false,
      variables: undefined,
    } as unknown as ReturnType<typeof useDisableBinding>);
  });

  it('should show loading state when isLoading=true', () => {
    vi.mocked(useBindings).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
      refetch: mockRefetch,
    } as ReturnType<typeof useBindings>);

    renderWithProviders(<ProtocolSwitcher contractId="contract-1" />);
    expect(screen.getByText('Loading bindings...')).toBeInTheDocument();
  });

  it('should show error state when error is set', () => {
    vi.mocked(useBindings).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('Network failure'),
      refetch: mockRefetch,
    } as ReturnType<typeof useBindings>);

    renderWithProviders(<ProtocolSwitcher contractId="contract-1" />);
    expect(screen.getByText(/Failed to load bindings: Network failure/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('should call refetch when Retry button clicked', () => {
    vi.mocked(useBindings).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('Network failure'),
      refetch: mockRefetch,
    } as ReturnType<typeof useBindings>);

    renderWithProviders(<ProtocolSwitcher contractId="contract-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(mockRefetch).toHaveBeenCalledOnce();
  });

  it('should render a protocol row for each binding', () => {
    renderWithProviders(<ProtocolSwitcher contractId="contract-1" />);
    expect(screen.getByTestId('protocol-row-rest')).toBeInTheDocument();
    expect(screen.getByTestId('protocol-row-mcp')).toBeInTheDocument();
    expect(screen.getByTestId('protocol-row-graphql')).toBeInTheDocument();
  });

  it('should show enabled count in header', () => {
    renderWithProviders(<ProtocolSwitcher contractId="contract-1" />);
    // 1 of 3 enabled (only rest is enabled)
    expect(screen.getByText('1 of 3 enabled')).toBeInTheDocument();
  });

  it('should show "No protocol bindings available" when bindings is empty', () => {
    vi.mocked(useBindings).mockReturnValue({
      data: { bindings: [], contract_id: 'contract-1', contract_name: 'orders-api' },
      isLoading: false,
      error: null,
      refetch: mockRefetch,
    } as ReturnType<typeof useBindings>);

    renderWithProviders(<ProtocolSwitcher contractId="contract-1" />);
    expect(screen.getByText('No protocol bindings available')).toBeInTheDocument();
  });

  it('should call enableBinding.mutateAsync when toggling ON', async () => {
    renderWithProviders(<ProtocolSwitcher contractId="contract-1" />);

    // mcp is enabled=false, so Toggle mcp will call onToggle(true)
    fireEvent.click(screen.getByRole('button', { name: 'Toggle mcp' }));

    await waitFor(() => {
      expect(mockEnableMutateAsync).toHaveBeenCalledWith('mcp');
    });
  });

  it('should call disableBinding.mutateAsync directly when toggling OFF a binding with no traffic', async () => {
    renderWithProviders(<ProtocolSwitcher contractId="contract-1" />);

    // rest is enabled=true with traffic_24h=0, so Toggle rest calls onToggle(false) → direct disable
    fireEvent.click(screen.getByRole('button', { name: 'Toggle rest' }));

    await waitFor(() => {
      expect(mockDisableMutateAsync).toHaveBeenCalledWith('rest');
    });
    expect(screen.queryByTestId('disable-modal')).not.toBeInTheDocument();
  });

  it('should show confirm modal when toggling OFF a binding with traffic > 0', async () => {
    // Make rest enabled with traffic so disabling shows modal
    vi.mocked(useBindings).mockReturnValue({
      data: {
        bindings: [{ protocol: 'rest', enabled: true, traffic_24h: 500 }],
        contract_id: 'contract-1',
        contract_name: 'orders-api',
      },
      isLoading: false,
      error: null,
      refetch: mockRefetch,
    } as ReturnType<typeof useBindings>);

    renderWithProviders(<ProtocolSwitcher contractId="contract-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Toggle rest' }));

    await waitFor(() => {
      expect(screen.getByTestId('disable-modal')).toBeInTheDocument();
    });
    expect(mockDisableMutateAsync).not.toHaveBeenCalled();
  });

  it('should call disableBinding.mutateAsync when confirming in modal', async () => {
    vi.mocked(useBindings).mockReturnValue({
      data: {
        bindings: [{ protocol: 'mcp', enabled: true, traffic_24h: 1500 }],
        contract_id: 'contract-1',
        contract_name: 'orders-api',
      },
      isLoading: false,
      error: null,
      refetch: mockRefetch,
    } as ReturnType<typeof useBindings>);

    renderWithProviders(<ProtocolSwitcher contractId="contract-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Toggle mcp' }));

    await waitFor(() => {
      expect(screen.getByTestId('disable-modal')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() => {
      expect(mockDisableMutateAsync).toHaveBeenCalledWith('mcp');
    });
  });

  it('should hide modal when Cancel clicked', async () => {
    vi.mocked(useBindings).mockReturnValue({
      data: {
        bindings: [{ protocol: 'mcp', enabled: true, traffic_24h: 1500 }],
        contract_id: 'contract-1',
        contract_name: 'orders-api',
      },
      isLoading: false,
      error: null,
      refetch: mockRefetch,
    } as ReturnType<typeof useBindings>);

    renderWithProviders(<ProtocolSwitcher contractId="contract-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Toggle mcp' }));

    await waitFor(() => {
      expect(screen.getByTestId('disable-modal')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    await waitFor(() => {
      expect(screen.queryByTestId('disable-modal')).not.toBeInTheDocument();
    });
    expect(mockDisableMutateAsync).not.toHaveBeenCalled();
  });

  it('should call onBindingEnabled callback after successful enable', async () => {
    const onBindingEnabled = vi.fn();
    renderWithProviders(
      <ProtocolSwitcher contractId="contract-1" onBindingEnabled={onBindingEnabled} />
    );

    // mcp is disabled — toggling calls enable
    fireEvent.click(screen.getByRole('button', { name: 'Toggle mcp' }));

    await waitFor(() => {
      expect(onBindingEnabled).toHaveBeenCalledWith('mcp');
    });
  });

  it('should call refetch when refresh button clicked', () => {
    renderWithProviders(<ProtocolSwitcher contractId="contract-1" />);
    const refreshButton = screen.getByTitle('Refresh');
    fireEvent.click(refreshButton);
    expect(mockRefetch).toHaveBeenCalledOnce();
  });
});
