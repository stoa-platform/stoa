/**
 * WorkspacePage Tests (CAB-1133)
 *
 * Page-level functional tests for the Workspace page with tabs.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createAuthMock, renderWithProviders } from '../../test/helpers';
import type { PersonaRole } from '../../test/helpers';

// Mock AuthContext
const mockAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth(),
}));

// Mock i18n — return defaultValue when provided, otherwise key
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key,
    i18n: { language: 'en' },
  }),
}));

// Mock lazy-loaded components
vi.mock('../apps', () => ({
  MyApplications: () => <div data-testid="my-applications">My Applications Content</div>,
}));

vi.mock('../subscriptions/MySubscriptions', () => ({
  MySubscriptions: () => <div data-testid="my-subscriptions">My Subscriptions Content</div>,
}));

vi.mock('../usage', () => ({
  UsagePage: () => <div data-testid="usage-page">Usage Content</div>,
}));

vi.mock('../executions', () => ({
  ExecutionHistoryPage: () => <div data-testid="execution-history">Execution History Content</div>,
}));

describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
  'WorkspacePage — %s persona',
  (role) => {
    let WorkspacePage: React.ComponentType;

    beforeEach(async () => {
      vi.clearAllMocks();
      mockAuth.mockReturnValue(createAuthMock(role));

      const pageModule = await import('../workspace/WorkspacePage');
      WorkspacePage = pageModule.WorkspacePage;
    });

    it('renders "My Workspace" heading', () => {
      renderWithProviders(<WorkspacePage />);

      expect(screen.getByText('My Workspace')).toBeInTheDocument();
      expect(screen.getByText('Manage your apps and subscriptions')).toBeInTheDocument();
    });

    it('default tab is "apps"', async () => {
      renderWithProviders(<WorkspacePage />);

      await waitFor(() => {
        expect(screen.getByTestId('my-applications')).toBeInTheDocument();
      });
    });

    it('shows all workspace tabs', () => {
      renderWithProviders(<WorkspacePage />);

      expect(screen.getByRole('button', { name: /Apps/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Subscriptions/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Usage/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Executions/i })).toBeInTheDocument();
    });

    it('clicking Subscriptions tab renders subscriptions content', async () => {
      const user = userEvent.setup();

      renderWithProviders(<WorkspacePage />);

      const subscriptionsTab = screen.getByRole('button', {
        name: /Subscriptions/i,
      });
      await user.click(subscriptionsTab);

      await waitFor(() => {
        expect(screen.getByTestId('my-subscriptions')).toBeInTheDocument();
      });
    });

    it('URL ?tab=subscriptions activates subscriptions tab', async () => {
      renderWithProviders(<WorkspacePage />, { route: '/?tab=subscriptions' });

      await waitFor(() => {
        expect(screen.getByTestId('my-subscriptions')).toBeInTheDocument();
      });
    });

    it('active tab has highlighted styling', () => {
      renderWithProviders(<WorkspacePage />);

      const appsTab = screen.getByRole('button', { name: /Apps/i });
      expect(appsTab).toHaveClass('border-primary-600');
    });

    it('inactive tabs do not have highlighted styling', () => {
      renderWithProviders(<WorkspacePage />);

      const subscriptionsTab = screen.getByRole('button', {
        name: /Subscriptions/i,
      });
      expect(subscriptionsTab).toHaveClass('border-transparent');
    });

    it('clicking Usage tab renders usage content', async () => {
      const user = userEvent.setup();

      renderWithProviders(<WorkspacePage />);

      const usageTab = screen.getByRole('button', { name: /Usage/i });
      await user.click(usageTab);

      await waitFor(() => {
        expect(screen.getByTestId('usage-page')).toBeInTheDocument();
      });
    });

    it('clicking Executions tab renders execution history', async () => {
      const user = userEvent.setup();

      renderWithProviders(<WorkspacePage />);

      const executionsTab = screen.getByRole('button', { name: /Executions/i });
      await user.click(executionsTab);

      await waitFor(() => {
        expect(screen.getByTestId('execution-history')).toBeInTheDocument();
      });
    });

    it('URL ?tab=usage activates usage tab', async () => {
      renderWithProviders(<WorkspacePage />, { route: '/?tab=usage' });

      await waitFor(() => {
        expect(screen.getByTestId('usage-page')).toBeInTheDocument();
      });
    });
  }
);
