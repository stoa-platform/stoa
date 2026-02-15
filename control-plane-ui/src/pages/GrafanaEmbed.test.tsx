import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { createAuthMock } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import type { PersonaRole } from '../test/helpers';
import { GrafanaEmbed } from './GrafanaEmbed';

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('../config', () => ({
  config: {
    services: {
      grafana: {
        url: '/grafana/',
      },
    },
  },
}));

const mockSearchParams = new URLSearchParams();
vi.mock('react-router-dom', () => ({
  useSearchParams: () => [mockSearchParams],
}));

vi.mock('../utils/navigation', () => ({
  isAllowedEmbedUrl: vi.fn().mockReturnValue(true),
}));

vi.mock('../hooks/useServiceHealth', () => ({
  useServiceHealth: () => ({ status: 'available', retry: vi.fn() }),
}));

describe('GrafanaEmbed', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    vi.spyOn(window, 'open').mockImplementation(() => null);
    mockSearchParams.delete('url');
  });

  it('renders title heading', () => {
    render(<GrafanaEmbed />);
    expect(screen.getByRole('heading', { name: 'STOA Observability' })).toBeInTheDocument();
  });

  it('renders iframe with correct src', () => {
    render(<GrafanaEmbed />);
    const iframe = screen.getByTitle('STOA Observability - Grafana');
    expect(iframe).toBeInTheDocument();
    expect(iframe).toHaveAttribute('src', '/grafana/');
  });

  it('shows loading state initially', () => {
    render(<GrafanaEmbed />);
    expect(screen.getByText('Loading Grafana...')).toBeInTheDocument();
  });

  it('refresh button increments key and renders a new iframe', () => {
    render(<GrafanaEmbed />);
    const iframe1 = screen.getByTitle('STOA Observability - Grafana');
    const refreshButton = screen.getByTitle('Refresh');
    fireEvent.click(refreshButton);
    const iframe2 = screen.getByTitle('STOA Observability - Grafana');
    expect(iframe2).toBeInTheDocument();
    expect(iframe2).not.toBe(iframe1);
  });

  it('fullscreen toggle changes layout', () => {
    const { container } = render(<GrafanaEmbed />);
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
    render(<GrafanaEmbed />);
    const openButton = screen.getByTitle('Open in new tab');
    fireEvent.click(openButton);
    expect(window.open).toHaveBeenCalledWith('/grafana/', '_blank', 'noopener,noreferrer');
  });

  it('handles iframe load event and hides loading', () => {
    render(<GrafanaEmbed />);
    expect(screen.getByText('Loading Grafana...')).toBeInTheDocument();
    const iframe = screen.getByTitle('STOA Observability - Grafana');
    fireEvent.load(iframe);
    expect(screen.queryByText('Loading Grafana...')).not.toBeInTheDocument();
  });

  it('iframe has sandbox and referrerPolicy attributes for security', () => {
    render(<GrafanaEmbed />);
    const iframe = screen.getByTitle('STOA Observability - Grafana');
    expect(iframe).toHaveAttribute(
      'sandbox',
      'allow-same-origin allow-scripts allow-popups allow-forms allow-downloads'
    );
    expect(iframe).toHaveAttribute('referrerPolicy', 'no-referrer-when-downgrade');
  });

  it('uses deep-link URL from search params when provided', () => {
    mockSearchParams.set('url', 'https://grafana.gostoa.dev/d/custom-dashboard');
    render(<GrafanaEmbed />);
    const iframe = screen.getByTitle('STOA Observability - Grafana');
    expect(iframe).toHaveAttribute('src', 'https://grafana.gostoa.dev/d/custom-dashboard');
  });

  // 4-persona coverage
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        render(<GrafanaEmbed />);
        expect(screen.getByRole('heading', { name: 'STOA Observability' })).toBeInTheDocument();
      });
    }
  );
});
