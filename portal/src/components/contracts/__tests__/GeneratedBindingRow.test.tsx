import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { GeneratedBindingRow } from '../GeneratedBindingRow';
import { renderWithProviders } from '../../../test/helpers';
import type { GeneratedBinding } from '../../../types';

const makeBinding = (overrides: Partial<GeneratedBinding> = {}): GeneratedBinding => ({
  protocol: 'rest',
  status: 'created',
  endpoint: '/v1/orders',
  ...overrides,
});

describe('GeneratedBindingRow', () => {
  describe('status=created', () => {
    it('renders REST endpoint created label', () => {
      renderWithProviders(<GeneratedBindingRow binding={makeBinding()} />);
      expect(screen.getByText(/REST endpoint created/)).toBeInTheDocument();
    });

    it('renders endpoint URL for REST binding', () => {
      renderWithProviders(
        <GeneratedBindingRow binding={makeBinding({ endpoint: '/v1/orders' })} />
      );
      expect(screen.getByText('/v1/orders')).toBeInTheDocument();
    });

    it('renders MCP tool name when present', () => {
      renderWithProviders(
        <GeneratedBindingRow binding={makeBinding({ protocol: 'mcp', tool_name: 'orders-tool' })} />
      );
      expect(screen.getByText('tool: orders-tool')).toBeInTheDocument();
    });

    it('renders GraphQL operations when present', () => {
      renderWithProviders(
        <GeneratedBindingRow
          binding={makeBinding({
            protocol: 'graphql',
            operations: ['getOrder', 'listOrders'],
          })}
        />
      );
      expect(screen.getByText('getOrder, listOrders')).toBeInTheDocument();
    });

    it('renders Auto-generated badge for MCP with auto_generated=true', () => {
      renderWithProviders(
        <GeneratedBindingRow
          binding={makeBinding({ protocol: 'mcp', tool_name: 'orders', auto_generated: true })}
        />
      );
      expect(screen.getByText('Auto-generated')).toBeInTheDocument();
    });

    it('does not render Auto-generated badge when auto_generated=false', () => {
      renderWithProviders(
        <GeneratedBindingRow
          binding={makeBinding({ protocol: 'mcp', tool_name: 'orders', auto_generated: false })}
        />
      );
      expect(screen.queryByText('Auto-generated')).not.toBeInTheDocument();
    });

    it('renders Test link when playground_url is present', () => {
      renderWithProviders(
        <GeneratedBindingRow
          binding={makeBinding({ playground_url: 'https://playground.example.com' })}
        />
      );
      const link = screen.getByRole('link', { name: /Test/i });
      expect(link).toHaveAttribute('href', 'https://playground.example.com');
      expect(link).toHaveAttribute('target', '_blank');
    });

    it('does not render Test link when playground_url is absent', () => {
      renderWithProviders(<GeneratedBindingRow binding={makeBinding()} />);
      expect(screen.queryByRole('link')).not.toBeInTheDocument();
    });
  });

  describe('status=available', () => {
    it('renders available label instead of endpoint created', () => {
      renderWithProviders(<GeneratedBindingRow binding={makeBinding({ status: 'available' })} />);
      expect(screen.getByText(/REST available/)).toBeInTheDocument();
    });

    it('renders "Enable in Protocol Settings" when not created', () => {
      renderWithProviders(<GeneratedBindingRow binding={makeBinding({ status: 'available' })} />);
      expect(screen.getByText('Enable in Protocol Settings')).toBeInTheDocument();
    });

    it('does not render Test link for available bindings', () => {
      renderWithProviders(
        <GeneratedBindingRow
          binding={makeBinding({ status: 'available', playground_url: 'https://pg.example.com' })}
        />
      );
      expect(screen.queryByRole('link')).not.toBeInTheDocument();
    });
  });

  describe('protocol labels', () => {
    it.each([
      ['rest', 'REST'],
      ['graphql', 'GraphQL'],
      ['grpc', 'gRPC'],
      ['mcp', 'MCP'],
      ['kafka', 'Kafka'],
    ] as const)('renders %s protocol label', (protocol, label) => {
      renderWithProviders(<GeneratedBindingRow binding={makeBinding({ protocol })} />);
      expect(screen.getByText(new RegExp(label))).toBeInTheDocument();
    });
  });
});
