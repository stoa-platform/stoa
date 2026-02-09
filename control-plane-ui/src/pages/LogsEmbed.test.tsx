import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { LogsEmbed } from './LogsEmbed';

vi.mock('../config', () => ({
  config: {
    services: {
      logs: {
        url: '/logs/',
      },
    },
  },
}));

vi.mock('../hooks/useServiceHealth', () => ({
  useServiceHealth: () => ({ status: 'available', retry: vi.fn() }),
}));

describe('LogsEmbed', () => {
  beforeEach(() => {
    vi.spyOn(window, 'open').mockImplementation(() => null);
  });

  it('renders title heading', () => {
    render(<LogsEmbed />);
    expect(screen.getByRole('heading', { name: 'STOA Logs' })).toBeInTheDocument();
  });

  it('renders iframe with correct src', () => {
    render(<LogsEmbed />);
    const iframe = screen.getByTitle('STOA Logs - OpenSearch Dashboards');
    expect(iframe).toBeInTheDocument();
    expect(iframe).toHaveAttribute('src', '/logs/');
  });

  it('shows loading state initially', () => {
    render(<LogsEmbed />);
    expect(screen.getByText('Loading STOA Logs...')).toBeInTheDocument();
  });

  it('refresh button increments key and renders a new iframe', () => {
    render(<LogsEmbed />);
    const iframe1 = screen.getByTitle('STOA Logs - OpenSearch Dashboards');
    const refreshButton = screen.getByTitle('Refresh');
    fireEvent.click(refreshButton);
    const iframe2 = screen.getByTitle('STOA Logs - OpenSearch Dashboards');
    expect(iframe2).toBeInTheDocument();
    expect(iframe2).not.toBe(iframe1);
  });

  it('fullscreen toggle changes layout', () => {
    const { container } = render(<LogsEmbed />);
    const rootDiv = container.firstChild as HTMLElement;
    expect(rootDiv.className).toContain('space-y-4');
    expect(rootDiv.className).not.toContain('fixed');
    const fullscreenButton = screen.getByTitle('Fullscreen');
    fireEvent.click(fullscreenButton);
    expect(rootDiv.className).toContain('fixed');
    expect(rootDiv.className).toContain('inset-0');
    expect(rootDiv.className).not.toContain('space-y-4');
    const exitButton = screen.getByTitle('Exit fullscreen');
    fireEvent.click(exitButton);
    expect(rootDiv.className).toContain('space-y-4');
    expect(rootDiv.className).not.toContain('fixed');
  });

  it('open in new tab calls window.open', () => {
    render(<LogsEmbed />);
    const openButton = screen.getByTitle('Open in new tab');
    fireEvent.click(openButton);
    expect(window.open).toHaveBeenCalledWith('/logs/', '_blank', 'noopener,noreferrer');
  });

  it('handles iframe load event and hides loading', () => {
    render(<LogsEmbed />);
    expect(screen.getByText('Loading STOA Logs...')).toBeInTheDocument();
    const iframe = screen.getByTitle('STOA Logs - OpenSearch Dashboards');
    fireEvent.load(iframe);
    expect(screen.queryByText('Loading STOA Logs...')).not.toBeInTheDocument();
  });

  it('iframe has sandbox and referrerPolicy attributes for security', () => {
    render(<LogsEmbed />);
    const iframe = screen.getByTitle('STOA Logs - OpenSearch Dashboards');
    expect(iframe).toHaveAttribute(
      'sandbox',
      'allow-same-origin allow-scripts allow-popups allow-forms'
    );
    expect(iframe).toHaveAttribute('referrerPolicy', 'no-referrer-when-downgrade');
  });
});
