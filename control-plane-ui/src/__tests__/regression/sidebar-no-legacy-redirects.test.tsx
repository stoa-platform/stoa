import { describe, expect, it, beforeEach, vi } from 'vitest';
import { within } from '@testing-library/react';
import { createAuthMock, renderWithProviders } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import { Layout } from '../../components/Layout';

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('../../contexts/EnvironmentContext', () => ({
  useEnvironment: () => ({
    activeEnvironment: 'dev',
    activeConfig: { name: 'dev', label: 'Development', mode: 'full', color: 'green' },
    environments: [{ name: 'dev', label: 'Development', mode: 'full', color: 'green' }],
    switchEnvironment: vi.fn(),
  }),
}));

vi.mock('../../services/api', () => ({
  apiService: {
    getTenants: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock('../../hooks/useApiConnectivity', () => ({
  useApiConnectivity: () => ({ isConnected: true, isChecking: false }),
}));

vi.mock('@stoa/shared/components/Breadcrumb', () => ({
  Breadcrumb: () => <nav data-testid="breadcrumb" />,
}));

vi.mock('@stoa/shared/components/CommandPalette', () => ({
  useCommandPalette: () => ({ setOpen: vi.fn(), setItems: vi.fn() }),
}));

vi.mock('@stoa/shared/components/EnvironmentChrome', () => ({
  EnvironmentChrome: () => null,
}));

vi.mock('@stoa/shared/components/ThemeToggle', () => ({
  ThemeToggle: () => <button type="button" data-testid="theme-toggle" />,
}));

vi.mock('@stoa/shared/contexts', () => ({
  useTheme: () => ({ resolvedTheme: 'light', toggleTheme: vi.fn() }),
}));

vi.mock('@stoa/shared/hooks', () => ({
  useSequenceShortcuts: vi.fn(),
}));

describe('regression/sidebar-no-legacy-redirects', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('does not advertise legacy gateway redirect routes in the active sidebar', () => {
    const { container } = renderWithProviders(
      <Layout>
        <div>Console content</div>
      </Layout>,
      { route: '/observability/security' }
    );

    const sidebar = container.querySelector('nav');
    expect(sidebar).not.toBeNull();

    const hrefs = within(sidebar as HTMLElement)
      .getAllByRole('link')
      .map((link) => link.getAttribute('href') ?? link.getAttribute('to') ?? '');

    expect(
      hrefs.filter(
        (href) => href.startsWith('/gateway-security') || href.startsWith('/gateway-guardrails')
      )
    ).toEqual([]);
  });
});
