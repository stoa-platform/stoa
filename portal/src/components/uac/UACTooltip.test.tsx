import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { UACTooltip } from './UACTooltip';
import type { ProtocolBinding } from '../../types';

const mockBindings: ProtocolBinding[] = [
  { protocol: 'rest', enabled: true, endpoint: '/api/v1/weather' },
  { protocol: 'mcp', enabled: true, tool_name: 'get_weather' },
  { protocol: 'graphql', enabled: false },
  { protocol: 'grpc', enabled: true, operations: ['GetWeather', 'ListCities'] },
  { protocol: 'kafka', enabled: true },
];

const defaultProps = {
  contractName: 'Weather Contract',
  bindings: mockBindings,
};

describe('UACTooltip', () => {
  it('should render header', () => {
    render(<UACTooltip {...defaultProps} />);
    expect(screen.getByText('Universal API Contract')).toBeInTheDocument();
  });

  it('should render description', () => {
    render(<UACTooltip {...defaultProps} />);
    expect(
      screen.getByText(/This API is defined once and automatically available/)
    ).toBeInTheDocument();
  });

  it('should only show enabled bindings', () => {
    render(<UACTooltip {...defaultProps} />);
    expect(screen.getByText('REST')).toBeInTheDocument();
    expect(screen.getByText('MCP')).toBeInTheDocument();
    expect(screen.getByText('gRPC')).toBeInTheDocument();
    expect(screen.getByText('Kafka')).toBeInTheDocument();
    expect(screen.queryByText('GraphQL')).not.toBeInTheDocument();
  });

  it('should show endpoint for REST binding', () => {
    render(<UACTooltip {...defaultProps} />);
    expect(screen.getByText('/api/v1/weather')).toBeInTheDocument();
  });

  it('should show tool_name for MCP binding', () => {
    render(<UACTooltip {...defaultProps} />);
    expect(screen.getByText('tool: get_weather')).toBeInTheDocument();
  });

  it('should show operations for gRPC binding', () => {
    render(<UACTooltip {...defaultProps} />);
    expect(screen.getByText('GetWeather, ListCities')).toBeInTheDocument();
  });

  it('should show "Enabled" fallback for binding without details', () => {
    render(<UACTooltip {...defaultProps} />);
    expect(screen.getByText('Enabled')).toBeInTheDocument();
  });

  it('should show tagline', () => {
    render(<UACTooltip {...defaultProps} />);
    expect(screen.getByText('One contract, zero duplication.')).toBeInTheDocument();
  });

  it('should render learn more link with default docs URL', () => {
    render(<UACTooltip {...defaultProps} />);
    const link = screen.getByText('Learn more');
    expect(link).toHaveAttribute('href', '/docs/uac');
  });

  it('should render learn more link with custom docs URL', () => {
    render(<UACTooltip {...defaultProps} docsUrl="/custom/path" />);
    const link = screen.getByText('Learn more');
    expect(link).toHaveAttribute('href', '/custom/path');
  });
});
