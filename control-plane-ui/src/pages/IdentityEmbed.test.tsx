import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { IdentityEmbed } from './IdentityEmbed';

vi.mock('../config', () => ({
  config: {
    keycloak: {
      url: 'https://auth.gostoa.dev',
      realm: 'stoa',
    },
  },
}));

describe('IdentityEmbed', () => {
  beforeEach(() => {
    vi.spyOn(window, 'open').mockImplementation(() => null);
  });

  it('renders title heading', () => {
    render(<IdentityEmbed />);
    expect(screen.getByRole('heading', { name: 'Identity Management' })).toBeInTheDocument();
  });

  it('renders iframe with correct src', () => {
    render(<IdentityEmbed />);
    const iframe = screen.getByTitle('STOA Identity Management - Keycloak');
    expect(iframe).toBeInTheDocument();
    expect(iframe).toHaveAttribute('src', 'https://auth.gostoa.dev/realms/stoa/account');
  });

  it('shows loading state initially', () => {
    render(<IdentityEmbed />);
    expect(screen.getByText('Loading Identity Management...')).toBeInTheDocument();
  });

  it('refresh button increments key and renders a new iframe', () => {
    render(<IdentityEmbed />);
    const iframe1 = screen.getByTitle('STOA Identity Management - Keycloak');
    const refreshButton = screen.getByTitle('Refresh');
    fireEvent.click(refreshButton);
    const iframe2 = screen.getByTitle('STOA Identity Management - Keycloak');
    expect(iframe2).toBeInTheDocument();
    expect(iframe2).not.toBe(iframe1);
  });

  it('fullscreen toggle changes layout', () => {
    const { container } = render(<IdentityEmbed />);
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
    render(<IdentityEmbed />);
    const openButton = screen.getByTitle('Open in new tab');
    fireEvent.click(openButton);
    expect(window.open).toHaveBeenCalledWith(
      'https://auth.gostoa.dev/realms/stoa/account',
      '_blank',
      'noopener,noreferrer'
    );
  });

  it('handles iframe load event and hides loading', () => {
    render(<IdentityEmbed />);
    expect(screen.getByText('Loading Identity Management...')).toBeInTheDocument();
    const iframe = screen.getByTitle('STOA Identity Management - Keycloak');
    fireEvent.load(iframe);
    expect(screen.queryByText('Loading Identity Management...')).not.toBeInTheDocument();
  });

  it('iframe has sandbox and referrerPolicy attributes for security', () => {
    render(<IdentityEmbed />);
    const iframe = screen.getByTitle('STOA Identity Management - Keycloak');
    expect(iframe).toHaveAttribute(
      'sandbox',
      'allow-same-origin allow-scripts allow-popups allow-forms'
    );
    expect(iframe).toHaveAttribute('referrerPolicy', 'no-referrer-when-downgrade');
  });
});
