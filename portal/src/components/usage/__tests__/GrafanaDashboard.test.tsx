import { screen } from '@testing-library/react';
import { renderWithProviders } from '../../../test/helpers';
import { GrafanaDashboard } from '../GrafanaDashboard';

describe('GrafanaDashboard', () => {
  it('renders disabled state when url is empty', () => {
    renderWithProviders(<GrafanaDashboard url="" />);

    expect(screen.getByTestId('grafana-disabled')).toBeInTheDocument();
    expect(screen.getByText(/not configured/)).toBeInTheDocument();
    expect(screen.getByText('VITE_GRAFANA_URL')).toBeInTheDocument();
  });

  it('renders iframe when url is provided', () => {
    renderWithProviders(<GrafanaDashboard url="https://grafana.example.com/d/abc" />);

    const iframe = screen.getByTitle('Analytics Dashboard');
    expect(iframe).toBeInTheDocument();
    expect(iframe).toHaveAttribute('src', 'https://grafana.example.com/d/abc');
    expect(iframe).toHaveAttribute('sandbox', 'allow-scripts allow-same-origin');
  });

  it('uses custom title for iframe accessibility', () => {
    renderWithProviders(
      <GrafanaDashboard url="https://grafana.example.com" title="Custom Title" />
    );

    expect(screen.getByTitle('Custom Title')).toBeInTheDocument();
    expect(screen.getByText('Custom Title')).toBeInTheDocument();
  });

  it('renders heading with title text', () => {
    renderWithProviders(<GrafanaDashboard url="https://grafana.example.com" />);

    expect(screen.getByText('Analytics Dashboard')).toBeInTheDocument();
  });

  it('shows loading skeleton initially', () => {
    renderWithProviders(<GrafanaDashboard url="https://grafana.example.com" />);

    expect(screen.getByTestId('grafana-dashboard')).toBeInTheDocument();
    // iframe is hidden while loading
    const iframe = screen.getByTitle('Analytics Dashboard');
    expect(iframe.className).toContain('hidden');
  });

  it('applies custom className', () => {
    renderWithProviders(<GrafanaDashboard url="https://grafana.example.com" className="my-4" />);

    expect(screen.getByTestId('grafana-dashboard').className).toContain('my-4');
  });
});
