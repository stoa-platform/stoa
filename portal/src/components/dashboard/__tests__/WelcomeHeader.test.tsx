import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { WelcomeHeader } from '../WelcomeHeader';
import { renderWithProviders, createMockUser } from '../../../test/helpers';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (key === 'welcome.greeting' && opts?.name) return `Hello, ${opts.name}!`;
      if (key === 'welcome.subtitle') return 'Discover AI-powered tools.';
      return key;
    },
    i18n: { language: 'en' },
  }),
}));

vi.mock('../../../config', () => ({
  config: {
    features: {
      enableI18n: false,
    },
  },
}));

describe('WelcomeHeader', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders greeting with user first name', () => {
    const user = createMockUser('tenant-admin'); // name: 'Wade Watts'
    renderWithProviders(<WelcomeHeader user={user} />);

    expect(screen.getByText(/Wade/)).toBeInTheDocument();
  });

  it('renders fallback name when user is null', () => {
    renderWithProviders(<WelcomeHeader user={null} />);

    // Heading contains "Developer" as the fallback name
    const heading = screen.getByRole('heading', { level: 1 });
    expect(heading.textContent).toContain('Developer');
  });

  it('renders the STOA Developer Portal label', () => {
    renderWithProviders(<WelcomeHeader user={null} />);

    expect(screen.getByText('STOA Developer Portal')).toBeInTheDocument();
  });

  it('renders subtitle text', () => {
    renderWithProviders(<WelcomeHeader user={null} />);

    expect(screen.getByText(/Discover AI-powered tools/)).toBeInTheDocument();
  });

  it('renders only first name from full name', () => {
    const user = createMockUser('cpi-admin'); // name: 'James Halliday'
    renderWithProviders(<WelcomeHeader user={user} />);

    expect(screen.getByText(/James/)).toBeInTheDocument();
    // "Halliday" should not appear in the greeting heading
    const heading = screen.getByRole('heading', { level: 1 });
    expect(heading.textContent).not.toContain('Halliday');
  });
});
