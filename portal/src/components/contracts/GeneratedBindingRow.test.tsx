import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { GeneratedBindingRow } from './GeneratedBindingRow';
import type { GeneratedBinding } from '../../types';

const makeBinding = (overrides: Partial<GeneratedBinding> = {}): GeneratedBinding => ({
  protocol: 'rest',
  status: 'created',
  endpoint: '/v1/orders',
  ...overrides,
});

describe('GeneratedBindingRow', () => {
  it('should render REST binding with correct label', () => {
    render(<GeneratedBindingRow binding={makeBinding()} />);
    expect(screen.getByText(/REST/)).toBeInTheDocument();
    expect(screen.getByText(/endpoint created/)).toBeInTheDocument();
  });

  it('should render MCP binding with tool name', () => {
    render(
      <GeneratedBindingRow
        binding={makeBinding({
          protocol: 'mcp',
          status: 'created',
          tool_name: 'orders-api',
        })}
      />
    );
    expect(screen.getByText(/MCP/)).toBeInTheDocument();
    expect(screen.getByText(/tool: orders-api/)).toBeInTheDocument();
  });

  it('should show Auto-generated badge for auto-generated MCP bindings', () => {
    render(
      <GeneratedBindingRow
        binding={makeBinding({
          protocol: 'mcp',
          status: 'created',
          auto_generated: true,
        })}
      />
    );
    expect(screen.getByText('Auto-generated')).toBeInTheDocument();
  });

  it('should not show Auto-generated badge for non-auto-generated', () => {
    render(
      <GeneratedBindingRow
        binding={makeBinding({
          protocol: 'mcp',
          status: 'created',
          auto_generated: false,
        })}
      />
    );
    expect(screen.queryByText('Auto-generated')).not.toBeInTheDocument();
  });

  it('should show "available" text for non-created bindings', () => {
    render(
      <GeneratedBindingRow binding={makeBinding({ protocol: 'graphql', status: 'available' })} />
    );
    expect(screen.getByText(/GraphQL/)).toBeInTheDocument();
    expect(screen.getByText(/available/)).toBeInTheDocument();
  });

  it('should show "Enable in Protocol Settings" for non-created bindings', () => {
    render(<GeneratedBindingRow binding={makeBinding({ status: 'available' })} />);
    expect(screen.getByText('Enable in Protocol Settings')).toBeInTheDocument();
  });

  it('should show endpoint for REST bindings', () => {
    render(<GeneratedBindingRow binding={makeBinding({ endpoint: '/v1/payments' })} />);
    expect(screen.getByText('/v1/payments')).toBeInTheDocument();
  });

  it('should show operations for GraphQL bindings', () => {
    render(
      <GeneratedBindingRow
        binding={makeBinding({
          protocol: 'graphql',
          status: 'created',
          operations: ['getOrder', 'createOrder'],
        })}
      />
    );
    expect(screen.getByText('getOrder, createOrder')).toBeInTheDocument();
  });

  it('should render Test link when playground URL exists', () => {
    render(
      <GeneratedBindingRow
        binding={makeBinding({
          playground_url: 'https://playground.example.com',
        })}
      />
    );
    const link = screen.getByText('Test');
    expect(link).toBeInTheDocument();
    expect(link.closest('a')).toHaveAttribute('href', 'https://playground.example.com');
  });

  it('should not render Test link when no playground URL', () => {
    render(<GeneratedBindingRow binding={makeBinding({ playground_url: undefined })} />);
    expect(screen.queryByText('Test')).not.toBeInTheDocument();
  });

  it('should render all protocol types', () => {
    const protocols = ['rest', 'graphql', 'grpc', 'mcp', 'kafka'] as const;
    const labels = ['REST', 'GraphQL', 'gRPC', 'MCP', 'Kafka'];

    protocols.forEach((protocol, i) => {
      const { unmount } = render(
        <GeneratedBindingRow binding={makeBinding({ protocol, status: 'created' })} />
      );
      expect(screen.getByText(new RegExp(labels[i]))).toBeInTheDocument();
      unmount();
    });
  });

  it('should use green check icon for created status', () => {
    const { container } = render(
      <GeneratedBindingRow binding={makeBinding({ status: 'created' })} />
    );
    const greenCheck = container.querySelector('.text-green-500');
    expect(greenCheck).toBeInTheDocument();
  });

  it('should use clock icon for available status', () => {
    const { container } = render(
      <GeneratedBindingRow binding={makeBinding({ status: 'available' })} />
    );
    const clockIcon = container.querySelector('.text-neutral-400');
    expect(clockIcon).toBeInTheDocument();
  });
});
