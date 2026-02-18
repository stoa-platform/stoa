import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { ProtocolRow } from '../ProtocolRow';
import { renderWithProviders } from '../../../test/helpers';
import type { ProtocolBinding } from '../../../types';

const makeBinding = (overrides: Partial<ProtocolBinding> = {}): ProtocolBinding => ({
  protocol: 'rest',
  enabled: true,
  endpoint: '/v1/orders',
  ...overrides,
});

describe('ProtocolRow', () => {
  const onToggle = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('enabled binding', () => {
    it('renders protocol badge for REST', () => {
      renderWithProviders(<ProtocolRow binding={makeBinding()} onToggle={onToggle} />);
      expect(screen.getByText('REST')).toBeInTheDocument();
    });

    it('renders endpoint URL', () => {
      renderWithProviders(<ProtocolRow binding={makeBinding()} onToggle={onToggle} />);
      expect(screen.getByText('/v1/orders')).toBeInTheDocument();
    });

    it('renders toggle switch as checked', () => {
      renderWithProviders(<ProtocolRow binding={makeBinding()} onToggle={onToggle} />);
      const toggle = screen.getByRole('switch');
      expect(toggle).toHaveAttribute('aria-checked', 'true');
    });

    it('calls onToggle with false when toggle is clicked', () => {
      renderWithProviders(<ProtocolRow binding={makeBinding()} onToggle={onToggle} />);
      fireEvent.click(screen.getByRole('switch'));
      expect(onToggle).toHaveBeenCalledWith(false);
    });

    it('renders traffic stats when traffic_24h is present', () => {
      renderWithProviders(
        <ProtocolRow binding={makeBinding({ traffic_24h: 2500 })} onToggle={onToggle} />
      );
      expect(screen.getByText('2,500 req/24h')).toBeInTheDocument();
    });

    it('does not render traffic stats when traffic_24h is absent', () => {
      renderWithProviders(<ProtocolRow binding={makeBinding()} onToggle={onToggle} />);
      expect(screen.queryByText(/req\/24h/)).not.toBeInTheDocument();
    });

    it('renders action link with playground_url', () => {
      renderWithProviders(
        <ProtocolRow
          binding={makeBinding({ playground_url: 'https://pg.example.com' })}
          onToggle={onToggle}
        />
      );
      expect(screen.getByRole('link', { name: /Endpoint/i })).toBeInTheDocument();
    });
  });

  describe('disabled binding', () => {
    it('renders toggle switch as unchecked', () => {
      renderWithProviders(
        <ProtocolRow binding={makeBinding({ enabled: false })} onToggle={onToggle} />
      );
      const toggle = screen.getByRole('switch');
      expect(toggle).toHaveAttribute('aria-checked', 'false');
    });

    it('renders "Enable to generate" text', () => {
      renderWithProviders(
        <ProtocolRow binding={makeBinding({ enabled: false })} onToggle={onToggle} />
      );
      expect(screen.getByText('─ Enable to generate')).toBeInTheDocument();
    });

    it('renders + Enable button', () => {
      renderWithProviders(
        <ProtocolRow binding={makeBinding({ enabled: false })} onToggle={onToggle} />
      );
      expect(screen.getByRole('button', { name: '+ Enable' })).toBeInTheDocument();
    });

    it('calls onToggle with true when + Enable is clicked', () => {
      renderWithProviders(
        <ProtocolRow binding={makeBinding({ enabled: false })} onToggle={onToggle} />
      );
      fireEvent.click(screen.getByRole('button', { name: '+ Enable' }));
      expect(onToggle).toHaveBeenCalledWith(true);
    });
  });

  describe('loading state', () => {
    it('renders spinner instead of toggle when isLoading=true', () => {
      renderWithProviders(
        <ProtocolRow binding={makeBinding()} onToggle={onToggle} isLoading={true} />
      );
      expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    });
  });

  describe('protocol-specific endpoint display', () => {
    it('renders MCP tool name', () => {
      renderWithProviders(
        <ProtocolRow
          binding={makeBinding({ protocol: 'mcp', tool_name: 'orders-tool' })}
          onToggle={onToggle}
        />
      );
      expect(screen.getByText('tool: orders-tool')).toBeInTheDocument();
    });

    it('renders GraphQL operations', () => {
      renderWithProviders(
        <ProtocolRow
          binding={makeBinding({
            protocol: 'graphql',
            operations: ['getOrder', 'listOrders'],
          })}
          onToggle={onToggle}
        />
      );
      expect(screen.getByText('getOrder, listOrders')).toBeInTheDocument();
    });

    it('renders Kafka topic name', () => {
      renderWithProviders(
        <ProtocolRow
          binding={makeBinding({ protocol: 'kafka', topic_name: 'orders-topic' })}
          onToggle={onToggle}
        />
      );
      expect(screen.getByText('orders-topic')).toBeInTheDocument();
    });
  });
});
