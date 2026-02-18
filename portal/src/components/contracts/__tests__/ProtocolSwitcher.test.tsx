import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { ProtocolSwitcher } from '../ProtocolSwitcher';
import { renderWithProviders } from '../../../test/helpers';
import type { BindingsListResponse } from '../../../types';

// Mock hooks
const mockUseBindings = vi.fn();
const mockUseEnableBinding = vi.fn();
const mockUseDisableBinding = vi.fn();

vi.mock('../../../hooks/useContracts', () => ({
  useBindings: (...args: unknown[]) => mockUseBindings(...args),
  useEnableBinding: (...args: unknown[]) => mockUseEnableBinding(...args),
  useDisableBinding: (...args: unknown[]) => mockUseDisableBinding(...args),
}));

const defaultBindingsData: BindingsListResponse = {
  contract_id: 'contract-1',
  contract_name: 'Orders API',
  bindings: [
    { protocol: 'rest', enabled: true, endpoint: '/v1/orders', traffic_24h: 100 },
    { protocol: 'mcp', enabled: true, tool_name: 'orders-tool', traffic_24h: 50 },
    { protocol: 'graphql', enabled: false },
    { protocol: 'grpc', enabled: false },
    { protocol: 'kafka', enabled: false },
  ],
};

const makeMutationMock = (overrides = {}) => ({
  mutateAsync: vi.fn().mockResolvedValue({}),
  isPending: false,
  variables: undefined,
  ...overrides,
});

describe('ProtocolSwitcher', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseBindings.mockReturnValue({
      data: defaultBindingsData,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    mockUseEnableBinding.mockReturnValue(makeMutationMock());
    mockUseDisableBinding.mockReturnValue(makeMutationMock());
  });

  it('renders protocol list with enabled count', () => {
    renderWithProviders(<ProtocolSwitcher contractId="contract-1" />);
    expect(screen.getByText('Protocols')).toBeInTheDocument();
    expect(screen.getByText('2 of 5 enabled')).toBeInTheDocument();
  });

  it('renders all 5 protocol rows', () => {
    renderWithProviders(<ProtocolSwitcher contractId="contract-1" />);
    expect(screen.getByText('REST')).toBeInTheDocument();
    expect(screen.getByText('MCP')).toBeInTheDocument();
    expect(screen.getByText('GraphQL')).toBeInTheDocument();
    expect(screen.getByText('gRPC')).toBeInTheDocument();
    expect(screen.getByText('Kafka')).toBeInTheDocument();
  });

  it('renders loading state', () => {
    mockUseBindings.mockReturnValue({ data: null, isLoading: true, error: null, refetch: vi.fn() });
    renderWithProviders(<ProtocolSwitcher contractId="contract-1" />);
    expect(screen.getByText('Loading bindings...')).toBeInTheDocument();
  });

  it('renders error state with retry button', () => {
    mockUseBindings.mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error('Network error'),
      refetch: vi.fn(),
    });
    renderWithProviders(<ProtocolSwitcher contractId="contract-1" />);
    expect(screen.getByText(/Failed to load bindings/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('calls refetch when Retry is clicked', () => {
    const refetch = vi.fn();
    mockUseBindings.mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error('Network error'),
      refetch,
    });
    renderWithProviders(<ProtocolSwitcher contractId="contract-1" />);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it('renders empty state when no bindings', () => {
    mockUseBindings.mockReturnValue({
      data: { contract_id: 'c1', contract_name: 'test', bindings: [] },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    });
    renderWithProviders(<ProtocolSwitcher contractId="contract-1" />);
    expect(screen.getByText('No protocol bindings available')).toBeInTheDocument();
  });

  it('enables a binding when toggle is clicked on disabled protocol', async () => {
    const mutateAsync = vi.fn().mockResolvedValue({});
    mockUseEnableBinding.mockReturnValue(makeMutationMock({ mutateAsync }));

    renderWithProviders(<ProtocolSwitcher contractId="contract-1" />);

    // Click "+ Enable" on GraphQL (disabled, no traffic)
    const enableButtons = screen.getAllByRole('button', { name: '+ Enable' });
    fireEvent.click(enableButtons[0]);

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith('graphql');
    });
  });

  it('shows disable confirmation modal when disabling binding with traffic', async () => {
    const mutateAsync = vi.fn().mockResolvedValue({});
    mockUseDisableBinding.mockReturnValue(makeMutationMock({ mutateAsync }));

    renderWithProviders(<ProtocolSwitcher contractId="contract-1" />);

    // REST binding has traffic_24h: 100, toggle is checked -> click to disable
    const switches = screen.getAllByRole('switch');
    const restSwitch = switches[0];
    fireEvent.click(restSwitch);

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByText(/Disable REST binding\?/)).toBeInTheDocument();
    });
  });

  it('cancels disable modal when Cancel is clicked', async () => {
    renderWithProviders(<ProtocolSwitcher contractId="contract-1" />);

    const switches = screen.getAllByRole('switch');
    fireEvent.click(switches[0]);

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('executes disable when confirmed in modal', async () => {
    const mutateAsync = vi.fn().mockResolvedValue({});
    mockUseDisableBinding.mockReturnValue(makeMutationMock({ mutateAsync }));

    renderWithProviders(<ProtocolSwitcher contractId="contract-1" />);

    const switches = screen.getAllByRole('switch');
    fireEvent.click(switches[0]);

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Disable' }));

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith('rest');
    });
  });

  it('calls refetch when refresh button is clicked', () => {
    const refetch = vi.fn();
    mockUseBindings.mockReturnValue({
      data: defaultBindingsData,
      isLoading: false,
      error: null,
      refetch,
    });
    renderWithProviders(<ProtocolSwitcher contractId="contract-1" />);
    fireEvent.click(screen.getByTitle('Refresh'));
    expect(refetch).toHaveBeenCalledTimes(1);
  });
});
