import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { UACBadge } from './UACBadge';
import type { ProtocolBinding } from '../../types';

const mockBindings: ProtocolBinding[] = [
  { protocol: 'rest', enabled: true, endpoint: '/api/v1/weather' },
  { protocol: 'mcp', enabled: true, tool_name: 'get_weather' },
  { protocol: 'graphql', enabled: false },
];

const defaultProps = {
  contractName: 'Weather Contract',
  bindings: mockBindings,
};

describe('UACBadge', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render default variant with UAC text', () => {
    render(<UACBadge {...defaultProps} />);
    expect(screen.getByText('UAC')).toBeInTheDocument();
  });

  it('should render compact variant without UAC text', () => {
    render(<UACBadge {...defaultProps} variant="compact" />);
    expect(screen.queryByText('UAC')).not.toBeInTheDocument();
  });

  it('should render with-count variant showing binding count', () => {
    render(<UACBadge {...defaultProps} variant="with-count" />);
    expect(screen.getByText('2 bindings')).toBeInTheDocument();
  });

  it('should toggle tooltip on click', () => {
    render(<UACBadge {...defaultProps} />);
    const button = screen.getByTitle('Universal API Contract - Click to learn more');

    expect(screen.queryByText('Universal API Contract')).not.toBeInTheDocument();
    fireEvent.click(button);
    expect(screen.getByText('Universal API Contract')).toBeInTheDocument();

    fireEvent.click(button);
    expect(screen.queryByText('Universal API Contract')).not.toBeInTheDocument();
  });

  it('should close tooltip on Escape key', () => {
    render(<UACBadge {...defaultProps} />);
    const button = screen.getByTitle('Universal API Contract - Click to learn more');

    fireEvent.click(button);
    expect(screen.getByText('Universal API Contract')).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByText('Universal API Contract')).not.toBeInTheDocument();
  });

  it('should close tooltip on click outside', () => {
    const { container } = render(<UACBadge {...defaultProps} />);
    const button = screen.getByTitle('Universal API Contract - Click to learn more');

    fireEvent.click(button);
    expect(screen.getByText('Universal API Contract')).toBeInTheDocument();

    fireEvent.mouseDown(container);
    expect(screen.queryByText('Universal API Contract')).not.toBeInTheDocument();
  });

  it('should set aria-expanded correctly', () => {
    render(<UACBadge {...defaultProps} />);
    const button = screen.getByTitle('Universal API Contract - Click to learn more');

    expect(button).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(button);
    expect(button).toHaveAttribute('aria-expanded', 'true');
  });

  it('should apply custom className', () => {
    const { container } = render(<UACBadge {...defaultProps} className="custom-class" />);
    expect(container.firstChild).toHaveClass('custom-class');
  });

  it('should pass docsUrl to UACTooltip', () => {
    render(<UACBadge {...defaultProps} docsUrl="/custom-docs" />);
    const button = screen.getByTitle('Universal API Contract - Click to learn more');
    fireEvent.click(button);
    expect(screen.getByText('Learn more')).toHaveAttribute('href', '/custom-docs');
  });
});
