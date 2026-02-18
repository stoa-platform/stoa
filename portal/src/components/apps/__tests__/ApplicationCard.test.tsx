import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { ApplicationCard } from '../ApplicationCard';
import { renderWithProviders, mockApplication } from '../../../test/helpers';

vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: null, isAuthenticated: false }),
}));

describe('ApplicationCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders application name and clientId', () => {
    const app = mockApplication({ name: 'My Test App', clientId: 'client-xyz' });
    renderWithProviders(<ApplicationCard application={app as never} />);

    expect(screen.getByText('My Test App')).toBeInTheDocument();
    expect(screen.getByText('client-xyz')).toBeInTheDocument();
  });

  it('renders description when provided', () => {
    const app = mockApplication({ description: 'A great application' });
    renderWithProviders(<ApplicationCard application={app as never} />);

    expect(screen.getByText('A great application')).toBeInTheDocument();
  });

  it('renders fallback description when none provided', () => {
    const app = mockApplication({ description: undefined });
    renderWithProviders(<ApplicationCard application={app as never} />);

    expect(screen.getByText('No description provided')).toBeInTheDocument();
  });

  it('renders active status badge', () => {
    const app = mockApplication({ status: 'active' });
    renderWithProviders(<ApplicationCard application={app as never} />);

    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('renders suspended status badge', () => {
    const app = mockApplication({ status: 'suspended' });
    renderWithProviders(<ApplicationCard application={app as never} />);

    expect(screen.getByText('Suspended')).toBeInTheDocument();
  });

  it('renders deleted status badge', () => {
    const app = mockApplication({ status: 'deleted' });
    renderWithProviders(<ApplicationCard application={app as never} />);

    expect(screen.getByText('Deleted')).toBeInTheDocument();
  });

  it('renders subscription count', () => {
    const app = mockApplication({
      subscriptions: [{ id: 'sub-1' }, { id: 'sub-2' }],
    });
    renderWithProviders(<ApplicationCard application={app as never} />);

    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('renders zero subscriptions when none', () => {
    const app = mockApplication({ subscriptions: [] });
    renderWithProviders(<ApplicationCard application={app as never} />);

    expect(screen.getByText('0')).toBeInTheDocument();
  });

  it('renders callback URL count when present', () => {
    const app = mockApplication({
      callbackUrls: ['https://app.com/cb1', 'https://app.com/cb2'],
    });
    renderWithProviders(<ApplicationCard application={app as never} />);

    expect(screen.getByText('Callbacks:')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('does not show callbacks section when empty', () => {
    const app = mockApplication({ callbackUrls: [] });
    renderWithProviders(<ApplicationCard application={app as never} />);

    expect(screen.queryByText('Callbacks:')).not.toBeInTheDocument();
  });

  it('renders link to app detail page', () => {
    const app = mockApplication({ id: 'app-123' });
    renderWithProviders(<ApplicationCard application={app as never} />);

    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', '/apps/app-123');
  });

  it('renders Manage link text', () => {
    const app = mockApplication();
    renderWithProviders(<ApplicationCard application={app as never} />);

    expect(screen.getByText('Manage')).toBeInTheDocument();
  });

  it('renders creation date', () => {
    const app = mockApplication({ createdAt: '2026-01-15T00:00:00Z' });
    renderWithProviders(<ApplicationCard application={app as never} />);

    expect(screen.getByText(/Created/)).toBeInTheDocument();
  });
});
