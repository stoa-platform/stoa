import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { TenantChatSettings } from './TenantChatSettings';
import { createAuthMock } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import { apiService } from '../services/api';
import type { PersonaRole } from '../test/helpers';

vi.mock('../contexts/AuthContext', () => ({ useAuth: vi.fn() }));
vi.mock('../services/api', () => ({
  apiService: {
    getChatSettings: vi.fn(),
    updateChatSettings: vi.fn(),
  },
}));

const defaultSettings = {
  chat_console_enabled: true,
  chat_portal_enabled: true,
  chat_daily_budget: 100_000,
};

describe('TenantChatSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem('stoa-active-tenant', 'test-tenant');
    vi.mocked(apiService.getChatSettings).mockResolvedValue(defaultSettings);
    vi.mocked(apiService.updateChatSettings).mockResolvedValue(defaultSettings);
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin'])('%s', (role) => {
    beforeEach(() => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
    });

    it('renders the page title', async () => {
      render(<TenantChatSettings />);
      await waitFor(() => expect(apiService.getChatSettings).toHaveBeenCalledWith('test-tenant'));
      expect(screen.getByText('Chat Agent Settings')).toBeInTheDocument();
    });

    it('shows tenant ID', async () => {
      render(<TenantChatSettings />);
      await waitFor(() => expect(apiService.getChatSettings).toHaveBeenCalled());
      expect(screen.getByText('test-tenant')).toBeInTheDocument();
    });

    it('renders console and portal toggles', async () => {
      render(<TenantChatSettings />);
      await waitFor(() => expect(apiService.getChatSettings).toHaveBeenCalled());
      expect(screen.getByText('Enable Chat in Console')).toBeInTheDocument();
      expect(screen.getByText('Enable Chat in Developer Portal')).toBeInTheDocument();
    });

    it('renders daily budget input with loaded value', async () => {
      render(<TenantChatSettings />);
      await waitFor(() => expect(apiService.getChatSettings).toHaveBeenCalled());
      const input = screen.getByRole('spinbutton');
      expect(input).toHaveValue(100_000);
    });

    it('calls updateChatSettings on save', async () => {
      render(<TenantChatSettings />);
      await waitFor(() => expect(apiService.getChatSettings).toHaveBeenCalled());
      fireEvent.click(screen.getByRole('button', { name: /Save Settings/i }));
      await waitFor(() =>
        expect(apiService.updateChatSettings).toHaveBeenCalledWith('test-tenant', defaultSettings)
      );
    });
  });

  it('shows no-tenant fallback when no tenantId available', () => {
    localStorage.removeItem('stoa-active-tenant');
    const mock = createAuthMock('cpi-admin');
    vi.mocked(useAuth).mockReturnValue({ ...mock, user: { ...mock.user, tenant_id: undefined } });
    render(<TenantChatSettings />);
    expect(screen.getByText(/No tenant selected/i)).toBeInTheDocument();
  });

  it('shows error message when getChatSettings fails', async () => {
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    vi.mocked(apiService.getChatSettings).mockRejectedValue(new Error('Network error'));
    render(<TenantChatSettings />);
    await waitFor(() => expect(screen.getByText(/Failed to load settings/i)).toBeInTheDocument());
  });
});
