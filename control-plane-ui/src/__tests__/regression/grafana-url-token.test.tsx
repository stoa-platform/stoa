import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useAuth } from '../../contexts/AuthContext';
import { GrafanaEmbed } from '../../pages/GrafanaEmbed';
import { createAuthMock } from '../../test/helpers';

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('../../config', () => ({
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

vi.mock('../../utils/navigation', () => ({
  isAllowedEmbedUrl: vi.fn().mockReturnValue(true),
}));

vi.mock('../../hooks/useServiceHealth', () => ({
  useServiceHealth: () => ({ status: 'available', retry: vi.fn() }),
}));

describe('regression/observability-grafana-token-url', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    vi.spyOn(window, 'open').mockImplementation(() => null);
    mockSearchParams.delete('url');
  });

  it('does not expose the Keycloak JWT in Grafana iframe or external URLs', () => {
    mockSearchParams.set('url', 'https://grafana.gostoa.dev/d/stoa-gateway-overview');

    render(<GrafanaEmbed />);

    const iframe = screen.getByTitle('STOA Observability - Grafana');
    const iframeSrc = iframe.getAttribute('src') ?? '';

    expect(iframeSrc).toContain('https://grafana.gostoa.dev/d/stoa-gateway-overview');
    expect(iframeSrc).not.toContain('mock-jwt-token-for-grafana');
    expect(iframeSrc).not.toContain('auth_token=');
    expect(iframeSrc).not.toContain('var-tenant_id=');

    fireEvent.click(screen.getByTitle('Open in new tab'));

    const openedUrl = vi.mocked(window.open).mock.calls.at(-1)?.[0] as string;
    expect(openedUrl).not.toContain('mock-jwt-token-for-grafana');
    expect(openedUrl).not.toContain('auth_token=');
    expect(openedUrl).not.toContain('var-tenant_id=');
  });
});
