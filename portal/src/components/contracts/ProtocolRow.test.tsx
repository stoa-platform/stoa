import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProtocolRow } from './ProtocolRow';
import type { ProtocolBinding, ProtocolType } from '../../types';

const makeBinding = (overrides: Partial<ProtocolBinding> = {}): ProtocolBinding => ({
  protocol: 'rest',
  enabled: true,
  endpoint: '/v1/orders',
  ...overrides,
});

describe('ProtocolRow', () => {
  const defaultProps = {
    binding: makeBinding(),
    onToggle: vi.fn(),
  };

  it('should render with REST protocol badge', () => {
    render(<ProtocolRow {...defaultProps} />);
    expect(screen.getByText('REST')).toBeInTheDocument();
  });

  it('should render all protocol types with correct labels', () => {
    const protocols: Array<{ type: ProtocolType; label: string }> = [
      { type: 'rest', label: 'REST' },
      { type: 'graphql', label: 'GraphQL' },
      { type: 'grpc', label: 'gRPC' },
      { type: 'mcp', label: 'MCP' },
      { type: 'kafka', label: 'Kafka' },
    ];

    protocols.forEach(({ type, label }) => {
      const { unmount } = render(
        <ProtocolRow binding={makeBinding({ protocol: type })} onToggle={vi.fn()} />
      );
      expect(screen.getByText(label)).toBeInTheDocument();
      unmount();
    });
  });

  it('should render toggle switch with correct aria-checked state', () => {
    render(<ProtocolRow {...defaultProps} binding={makeBinding({ enabled: true })} />);
    const toggle = screen.getByRole('switch');
    expect(toggle).toHaveAttribute('aria-checked', 'true');
  });

  it('should render toggle as unchecked when disabled', () => {
    render(<ProtocolRow {...defaultProps} binding={makeBinding({ enabled: false })} />);
    const toggle = screen.getByRole('switch');
    expect(toggle).toHaveAttribute('aria-checked', 'false');
  });

  it('should call onToggle when toggle is clicked', async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    render(<ProtocolRow binding={makeBinding({ enabled: true })} onToggle={onToggle} />);
    await user.click(screen.getByRole('switch'));
    expect(onToggle).toHaveBeenCalledWith(false);
  });

  it('should call onToggle with true when enabling', async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    render(<ProtocolRow binding={makeBinding({ enabled: false })} onToggle={onToggle} />);
    await user.click(screen.getByRole('switch'));
    expect(onToggle).toHaveBeenCalledWith(true);
  });

  it('should show loading spinner when isLoading', () => {
    const { container } = render(<ProtocolRow {...defaultProps} isLoading={true} />);
    const spinner = container.querySelector('.animate-spin');
    expect(spinner).toBeInTheDocument();
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
  });

  it('should show "Enable to generate" text when not enabled', () => {
    render(<ProtocolRow {...defaultProps} binding={makeBinding({ enabled: false })} />);
    expect(screen.getByText('─ Enable to generate')).toBeInTheDocument();
  });

  it('should show endpoint for REST binding', () => {
    render(<ProtocolRow {...defaultProps} binding={makeBinding({ endpoint: '/v1/payments' })} />);
    expect(screen.getByText('/v1/payments')).toBeInTheDocument();
  });

  it('should show tool name for MCP binding', () => {
    render(
      <ProtocolRow
        {...defaultProps}
        binding={makeBinding({
          protocol: 'mcp',
          tool_name: 'orders-api',
        })}
      />
    );
    expect(screen.getByText('tool: orders-api')).toBeInTheDocument();
  });

  it('should show operations for GraphQL binding', () => {
    render(
      <ProtocolRow
        {...defaultProps}
        binding={makeBinding({
          protocol: 'graphql',
          operations: ['getOrder', 'createOrder'],
        })}
      />
    );
    expect(screen.getByText('getOrder, createOrder')).toBeInTheDocument();
  });

  it('should show topic name for Kafka binding', () => {
    render(
      <ProtocolRow
        {...defaultProps}
        binding={makeBinding({
          protocol: 'kafka',
          topic_name: 'orders.events',
        })}
      />
    );
    expect(screen.getByText('orders.events')).toBeInTheDocument();
  });

  it('should show proto file for gRPC binding', () => {
    render(
      <ProtocolRow
        {...defaultProps}
        binding={makeBinding({
          protocol: 'grpc',
          proto_file_url: 'https://example.com/protos/orders.proto',
        })}
      />
    );
    expect(screen.getByText('proto: orders.proto')).toBeInTheDocument();
  });

  it('should show traffic stats when enabled and available', () => {
    render(<ProtocolRow {...defaultProps} binding={makeBinding({ traffic_24h: 12345 })} />);
    expect(screen.getByText(/12[\s\u202f,.]?345 req\/24h/)).toBeInTheDocument();
  });

  it('should not show traffic stats when not enabled', () => {
    render(
      <ProtocolRow {...defaultProps} binding={makeBinding({ enabled: false, traffic_24h: 100 })} />
    );
    expect(screen.queryByText(/req\/24h/)).not.toBeInTheDocument();
  });

  it('should render action link with correct label for REST', () => {
    render(
      <ProtocolRow
        {...defaultProps}
        binding={makeBinding({
          endpoint: '/v1/orders',
          playground_url: 'https://playground.example.com',
        })}
      />
    );
    const link = screen.getByText('Endpoint');
    expect(link.closest('a')).toHaveAttribute('href', 'https://playground.example.com');
  });

  it('should render action link with correct label for GraphQL', () => {
    render(
      <ProtocolRow
        {...defaultProps}
        binding={makeBinding({
          protocol: 'graphql',
          playground_url: 'https://graphql.example.com',
        })}
      />
    );
    expect(screen.getByText('Playground')).toBeInTheDocument();
  });

  it('should render "+ Enable" button when not enabled', async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    render(<ProtocolRow binding={makeBinding({ enabled: false })} onToggle={onToggle} />);
    const enableBtn = screen.getByText('+ Enable');
    expect(enableBtn).toBeInTheDocument();
    await user.click(enableBtn);
    expect(onToggle).toHaveBeenCalledWith(true);
  });

  it('should not render action link when disabled and no url', () => {
    render(
      <ProtocolRow
        {...defaultProps}
        binding={makeBinding({
          enabled: true,
          endpoint: undefined,
          playground_url: undefined,
        })}
      />
    );
    expect(screen.queryByText('Endpoint')).not.toBeInTheDocument();
    expect(screen.queryByText('+ Enable')).not.toBeInTheDocument();
  });

  it('should open action link in new tab', () => {
    render(
      <ProtocolRow
        {...defaultProps}
        binding={makeBinding({
          playground_url: 'https://test.example.com',
        })}
      />
    );
    const link = screen.getByText('Endpoint').closest('a');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });
});
