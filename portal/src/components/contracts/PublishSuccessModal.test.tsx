import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PublishSuccessModal } from './PublishSuccessModal';
import { renderWithProviders } from '../../test/helpers';
import type { PublishContractResponse } from '../../types';

vi.mock('./GeneratedBindingRow', () => ({
  GeneratedBindingRow: ({ binding }: { binding: { protocol: string; status: string } }) => (
    <div data-testid={`binding-${binding.protocol}`}>
      {binding.protocol}: {binding.status}
    </div>
  ),
}));

const mockData: PublishContractResponse = {
  id: 'contract-1',
  name: 'orders-api',
  version: '1.0.0',
  status: 'published',
  bindings_generated: [
    {
      protocol: 'rest',
      status: 'created',
      endpoint: '/v1/orders',
      playground_url: 'https://playground.example.com/rest',
    },
    {
      protocol: 'mcp',
      status: 'created',
      tool_name: 'orders-api',
      auto_generated: true,
      playground_url: undefined,
    },
    { protocol: 'graphql', status: 'available' },
    { protocol: 'grpc', status: 'available' },
    { protocol: 'kafka', status: 'available' },
  ],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-02-01T00:00:00Z',
};

describe('PublishSuccessModal', () => {
  const onClose = vi.fn();
  const onViewContract = vi.fn();
  const onTestPlayground = vi.fn();

  const defaultProps = {
    isOpen: true,
    onClose,
    data: mockData,
    onViewContract,
    onTestPlayground,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should return null when not open', () => {
    const { container } = renderWithProviders(
      <PublishSuccessModal {...defaultProps} isOpen={false} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('should return null when data is null', () => {
    const { container } = renderWithProviders(
      <PublishSuccessModal {...defaultProps} data={null} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('should render success header with contract name', () => {
    renderWithProviders(<PublishSuccessModal {...defaultProps} />);
    expect(screen.getByText('Contract published!')).toBeInTheDocument();
    expect(screen.getByText('orders-api')).toBeInTheDocument();
    expect(screen.getByText(/v1\.0\.0/)).toBeInTheDocument();
  });

  it('should render all binding rows', () => {
    renderWithProviders(<PublishSuccessModal {...defaultProps} />);
    expect(screen.getByTestId('binding-rest')).toBeInTheDocument();
    expect(screen.getByTestId('binding-mcp')).toBeInTheDocument();
    expect(screen.getByTestId('binding-graphql')).toBeInTheDocument();
    expect(screen.getByTestId('binding-grpc')).toBeInTheDocument();
    expect(screen.getByTestId('binding-kafka')).toBeInTheDocument();
  });

  it('should show binding stats summary', () => {
    renderWithProviders(<PublishSuccessModal {...defaultProps} />);
    expect(screen.getByText('2')).toBeInTheDocument(); // created bindings count
    expect(screen.getByText(/active/)).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument(); // available bindings count
    expect(screen.getByText(/more available/)).toBeInTheDocument();
  });

  it('should call onViewContract when View Contract clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<PublishSuccessModal {...defaultProps} />);
    await user.click(screen.getByText('View Contract'));
    expect(onViewContract).toHaveBeenCalledWith('contract-1');
  });

  it('should show Test in Playground button when playground URL exists', async () => {
    const user = userEvent.setup();
    renderWithProviders(<PublishSuccessModal {...defaultProps} />);
    const playgroundButton = screen.getByText('Test in Playground');
    expect(playgroundButton).toBeInTheDocument();
    await user.click(playgroundButton);
    expect(onTestPlayground).toHaveBeenCalledWith('https://playground.example.com/rest');
  });

  it('should show Done button when no playground URL exists', () => {
    const dataWithoutPlayground: PublishContractResponse = {
      ...mockData,
      bindings_generated: [{ protocol: 'rest', status: 'created', endpoint: '/v1/orders' }],
    };
    renderWithProviders(<PublishSuccessModal {...defaultProps} data={dataWithoutPlayground} />);
    expect(screen.getByText('Done')).toBeInTheDocument();
    expect(screen.queryByText('Test in Playground')).not.toBeInTheDocument();
  });

  it('should call onClose when Done clicked', async () => {
    const user = userEvent.setup();
    const dataWithoutPlayground: PublishContractResponse = {
      ...mockData,
      bindings_generated: [{ protocol: 'rest', status: 'created', endpoint: '/v1/orders' }],
    };
    renderWithProviders(<PublishSuccessModal {...defaultProps} data={dataWithoutPlayground} />);
    await user.click(screen.getByText('Done'));
    expect(onClose).toHaveBeenCalled();
  });

  it('should close on close button click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<PublishSuccessModal {...defaultProps} />);
    await user.click(screen.getByLabelText('Close modal'));
    expect(onClose).toHaveBeenCalled();
  });

  it('should render with aria attributes', () => {
    renderWithProviders(<PublishSuccessModal {...defaultProps} />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByLabelText('Close modal')).toBeInTheDocument();
  });
});
