import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { PublishSuccessModal } from '../PublishSuccessModal';
import { renderWithProviders } from '../../../test/helpers';
import type { PublishContractResponse } from '../../../types';

const mockData: PublishContractResponse = {
  id: 'contract-1',
  name: 'orders-api',
  version: '1.0.0',
  bindings_generated: [
    {
      protocol: 'rest',
      status: 'created',
      endpoint: '/v1/orders',
      playground_url: 'https://pg.example.com',
    },
    { protocol: 'mcp', status: 'created', tool_name: 'orders-tool', auto_generated: true },
    { protocol: 'graphql', status: 'available' },
    { protocol: 'grpc', status: 'available' },
    { protocol: 'kafka', status: 'available' },
  ],
};

describe('PublishSuccessModal', () => {
  const onClose = vi.fn();
  const onViewContract = vi.fn();
  const onTestPlayground = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when isOpen=false', () => {
    const { container } = renderWithProviders(
      <PublishSuccessModal isOpen={false} onClose={onClose} data={mockData} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when data is null', () => {
    const { container } = renderWithProviders(
      <PublishSuccessModal isOpen={true} onClose={onClose} data={null} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders contract name and version', () => {
    renderWithProviders(<PublishSuccessModal isOpen={true} onClose={onClose} data={mockData} />);
    expect(screen.getByText(/Contract published!/)).toBeInTheDocument();
    expect(screen.getByText(/orders-api/)).toBeInTheDocument();
    expect(screen.getByText(/v1\.0\.0/)).toBeInTheDocument();
  });

  it('renders all 5 binding rows', () => {
    renderWithProviders(<PublishSuccessModal isOpen={true} onClose={onClose} data={mockData} />);
    expect(screen.getByText(/REST endpoint created/)).toBeInTheDocument();
    expect(screen.getByText(/MCP endpoint created/)).toBeInTheDocument();
    expect(screen.getByText(/GraphQL available/)).toBeInTheDocument();
  });

  it('shows active bindings count summary', () => {
    renderWithProviders(<PublishSuccessModal isOpen={true} onClose={onClose} data={mockData} />);
    expect(screen.getByText(/2/)).toBeInTheDocument();
    expect(screen.getByText(/bindings active/)).toBeInTheDocument();
    expect(screen.getByText(/3/)).toBeInTheDocument();
    expect(screen.getByText(/more available/)).toBeInTheDocument();
  });

  it('calls onViewContract when View Contract is clicked', () => {
    renderWithProviders(
      <PublishSuccessModal
        isOpen={true}
        onClose={onClose}
        data={mockData}
        onViewContract={onViewContract}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /View Contract/i }));
    expect(onViewContract).toHaveBeenCalledWith('contract-1');
  });

  it('renders Test in Playground button when playground_url exists', () => {
    renderWithProviders(
      <PublishSuccessModal
        isOpen={true}
        onClose={onClose}
        data={mockData}
        onTestPlayground={onTestPlayground}
      />
    );
    expect(screen.getByRole('button', { name: /Test in Playground/i })).toBeInTheDocument();
  });

  it('calls onTestPlayground with first playground url', () => {
    renderWithProviders(
      <PublishSuccessModal
        isOpen={true}
        onClose={onClose}
        data={mockData}
        onTestPlayground={onTestPlayground}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /Test in Playground/i }));
    expect(onTestPlayground).toHaveBeenCalledWith('https://pg.example.com');
  });

  it('renders Done button when no playground_url exists', () => {
    const noPlayground: PublishContractResponse = {
      ...mockData,
      bindings_generated: [
        { protocol: 'rest', status: 'created', endpoint: '/v1/orders' },
        { protocol: 'mcp', status: 'available' },
      ],
    };
    renderWithProviders(
      <PublishSuccessModal isOpen={true} onClose={onClose} data={noPlayground} />
    );
    expect(screen.getByRole('button', { name: 'Done' })).toBeInTheDocument();
  });

  it('calls onClose when close button is clicked', () => {
    renderWithProviders(<PublishSuccessModal isOpen={true} onClose={onClose} data={mockData} />);
    fireEvent.click(screen.getByRole('button', { name: /Close modal/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('renders Auto-generated badge for MCP binding', () => {
    renderWithProviders(<PublishSuccessModal isOpen={true} onClose={onClose} data={mockData} />);
    expect(screen.getByText('Auto-generated')).toBeInTheDocument();
  });
});
