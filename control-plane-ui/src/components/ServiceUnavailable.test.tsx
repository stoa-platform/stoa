import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ServiceUnavailable } from './ServiceUnavailable';
import { Activity } from 'lucide-react';

describe('ServiceUnavailable', () => {
  const defaultProps = {
    serviceName: 'Grafana',
    description: 'The monitoring service is currently unreachable.',
    icon: Activity,
  };

  it('renders service name and description', () => {
    render(<ServiceUnavailable {...defaultProps} />);
    expect(screen.getByText('Grafana is not available')).toBeInTheDocument();
    expect(
      screen.getByText('The monitoring service is currently unreachable.')
    ).toBeInTheDocument();
  });

  it('renders retry button when onRetry provided', () => {
    const onRetry = vi.fn();
    render(<ServiceUnavailable {...defaultProps} onRetry={onRetry} />);

    const retryButton = screen.getByText('Retry');
    expect(retryButton).toBeInTheDocument();

    fireEvent.click(retryButton);
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('does not render retry button when onRetry not provided', () => {
    render(<ServiceUnavailable {...defaultProps} />);
    expect(screen.queryByText('Retry')).not.toBeInTheDocument();
  });

  it('renders external link when externalUrl provided', () => {
    render(<ServiceUnavailable {...defaultProps} externalUrl="https://grafana.gostoa.dev" />);

    const link = screen.getByText('Open Directly');
    expect(link).toBeInTheDocument();
    expect(link.closest('a')).toHaveAttribute('href', 'https://grafana.gostoa.dev');
    expect(link.closest('a')).toHaveAttribute('target', '_blank');
    expect(link.closest('a')).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('does not render external link when externalUrl not provided', () => {
    render(<ServiceUnavailable {...defaultProps} />);
    expect(screen.queryByText('Open Directly')).not.toBeInTheDocument();
  });

  it('renders config hint when provided', () => {
    render(<ServiceUnavailable {...defaultProps} configHint="Set VITE_GRAFANA_URL in .env" />);
    expect(screen.getByText(/Configuration hint:/)).toBeInTheDocument();
    expect(screen.getByText(/Set VITE_GRAFANA_URL in .env/)).toBeInTheDocument();
  });

  it('does not render config hint when not provided', () => {
    render(<ServiceUnavailable {...defaultProps} />);
    expect(screen.queryByText(/Configuration hint:/)).not.toBeInTheDocument();
  });

  it('renders both retry and external link together', () => {
    render(
      <ServiceUnavailable
        {...defaultProps}
        onRetry={vi.fn()}
        externalUrl="https://grafana.gostoa.dev"
      />
    );
    expect(screen.getByText('Retry')).toBeInTheDocument();
    expect(screen.getByText('Open Directly')).toBeInTheDocument();
  });
});
