import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { ApplicationCard } from './ApplicationCard';
import { renderWithProviders, mockApplication } from '../../test/helpers';

describe('ApplicationCard', () => {
  it('should render the application name', () => {
    const app = mockApplication({ name: 'My Test App' });
    renderWithProviders(<ApplicationCard application={app as never} />);
    expect(screen.getByText('My Test App')).toBeInTheDocument();
  });

  it('should show the clientId in monospace font', () => {
    const app = mockApplication({ clientId: 'client-xyz789' });
    renderWithProviders(<ApplicationCard application={app as never} />);
    const clientIdEl = screen.getByText('client-xyz789');
    expect(clientIdEl).toBeInTheDocument();
    expect(clientIdEl.className).toMatch(/font-mono/);
  });

  it('should link to /apps/{id}', () => {
    const app = mockApplication({ id: 'app-42' });
    renderWithProviders(<ApplicationCard application={app as never} />);
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', '/apps/app-42');
  });

  it('should show "Active" badge for status: active', () => {
    const app = mockApplication({ status: 'active' });
    renderWithProviders(<ApplicationCard application={app as never} />);
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('should show "Suspended" badge for status: suspended', () => {
    const app = mockApplication({ status: 'suspended' });
    renderWithProviders(<ApplicationCard application={app as never} />);
    expect(screen.getByText('Suspended')).toBeInTheDocument();
  });

  it('should show "Deleted" badge for status: deleted', () => {
    const app = mockApplication({ status: 'deleted' });
    renderWithProviders(<ApplicationCard application={app as never} />);
    expect(screen.getByText('Deleted')).toBeInTheDocument();
  });

  it('should show description when provided', () => {
    const app = mockApplication({ description: 'This app processes payments' });
    renderWithProviders(<ApplicationCard application={app as never} />);
    expect(screen.getByText('This app processes payments')).toBeInTheDocument();
  });

  it('should show "No description provided" when description is empty', () => {
    const app = mockApplication({ description: '' });
    renderWithProviders(<ApplicationCard application={app as never} />);
    expect(screen.getByText('No description provided')).toBeInTheDocument();
  });

  it('should show "No description provided" when description is undefined', () => {
    const app = mockApplication({ description: undefined });
    renderWithProviders(<ApplicationCard application={app as never} />);
    expect(screen.getByText('No description provided')).toBeInTheDocument();
  });

  it('should show subscription count', () => {
    const app = mockApplication({
      subscriptions: [{ id: 's1' }, { id: 's2' }, { id: 's3' }],
    });
    renderWithProviders(<ApplicationCard application={app as never} />);
    expect(screen.getByText('Subscriptions:')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('should show subscription count of 0 when subscriptions is empty', () => {
    const app = mockApplication({ subscriptions: [] });
    renderWithProviders(<ApplicationCard application={app as never} />);
    expect(screen.getByText('0')).toBeInTheDocument();
  });

  it('should show callback URL count when callbackUrls is non-empty', () => {
    const app = mockApplication({
      callbackUrls: ['https://app.example.com/cb1', 'https://app.example.com/cb2'],
    });
    renderWithProviders(<ApplicationCard application={app as never} />);
    expect(screen.getByText('Callbacks:')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('should not show callback section when callbackUrls is empty', () => {
    const app = mockApplication({ callbackUrls: [] });
    renderWithProviders(<ApplicationCard application={app as never} />);
    expect(screen.queryByText('Callbacks:')).not.toBeInTheDocument();
  });

  it('should show formatted creation date', () => {
    const app = mockApplication({ createdAt: '2026-01-15T00:00:00Z' });
    renderWithProviders(<ApplicationCard application={app as never} />);
    // toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    // → "Jan 15, 2026"
    expect(screen.getByText(/created/i)).toBeInTheDocument();
    expect(screen.getByText(/jan 15, 2026/i)).toBeInTheDocument();
  });
});
