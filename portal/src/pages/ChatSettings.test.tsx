import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders, createAuthMock, type PersonaRole } from '../test/helpers';

const mockGetChatSettings = vi.fn();
const mockUpdateChatSettings = vi.fn();

vi.mock('../services/api', () => ({
  getChatSettings: (...args: unknown[]) => mockGetChatSettings(...args),
  updateChatSettings: (...args: unknown[]) => mockUpdateChatSettings(...args),
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

import { useAuth } from '../contexts/AuthContext';
import { ChatSettings } from './ChatSettings';

const defaultSettings = {
  chat_console_enabled: true,
  chat_portal_enabled: true,
  chat_daily_budget: 100_000,
};

describe('ChatSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('tenant-admin'));
    mockGetChatSettings.mockResolvedValue({ ...defaultSettings });
    mockUpdateChatSettings.mockResolvedValue({ ...defaultSettings });
  });

  it('renders the heading and description', async () => {
    renderWithProviders(<ChatSettings />);
    expect(screen.getByRole('heading', { name: /chat agent settings/i })).toBeInTheDocument();
    expect(screen.getByText(/configure the ai chat agent/i)).toBeInTheDocument();
  });

  it('loads settings on mount', async () => {
    renderWithProviders(<ChatSettings />);
    await waitFor(() => {
      expect(mockGetChatSettings).toHaveBeenCalledWith('oasis-gunters');
    });
  });

  it('renders portal and console toggles', async () => {
    renderWithProviders(<ChatSettings />);
    await waitFor(() => {
      expect(mockGetChatSettings).toHaveBeenCalled();
    });
    const switches = screen.getAllByRole('switch');
    expect(switches).toHaveLength(2);
  });

  it('renders daily budget input', async () => {
    renderWithProviders(<ChatSettings />);
    await waitFor(() => {
      expect(mockGetChatSettings).toHaveBeenCalled();
    });
    const input = screen.getByLabelText(/daily token budget/i);
    expect(input).toBeInTheDocument();
    expect(input).toHaveValue(100_000);
  });

  it('toggles portal switch on click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ChatSettings />);
    await waitFor(() => {
      expect(mockGetChatSettings).toHaveBeenCalled();
    });

    const portalSwitch = screen.getAllByRole('switch')[0];
    expect(portalSwitch).toHaveAttribute('aria-checked', 'true');

    await user.click(portalSwitch);
    expect(portalSwitch).toHaveAttribute('aria-checked', 'false');
  });

  it('toggles console switch on click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ChatSettings />);
    await waitFor(() => {
      expect(mockGetChatSettings).toHaveBeenCalled();
    });

    const consoleSwitch = screen.getAllByRole('switch')[1];
    expect(consoleSwitch).toHaveAttribute('aria-checked', 'true');

    await user.click(consoleSwitch);
    expect(consoleSwitch).toHaveAttribute('aria-checked', 'false');
  });

  it('saves settings on button click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ChatSettings />);
    await waitFor(() => {
      expect(mockGetChatSettings).toHaveBeenCalled();
    });

    await user.click(screen.getByRole('button', { name: /save settings/i }));

    await waitFor(() => {
      expect(mockUpdateChatSettings).toHaveBeenCalledWith('oasis-gunters', defaultSettings);
    });
    expect(screen.getByText(/settings saved successfully/i)).toBeInTheDocument();
  });

  it('shows error when loading fails', async () => {
    mockGetChatSettings.mockRejectedValue(new Error('Network error'));
    renderWithProviders(<ChatSettings />);

    await waitFor(() => {
      expect(screen.getByText(/failed to load settings: network error/i)).toBeInTheDocument();
    });
  });

  it('shows error when saving fails', async () => {
    const user = userEvent.setup();
    mockUpdateChatSettings.mockRejectedValue(new Error('Forbidden'));
    renderWithProviders(<ChatSettings />);
    await waitFor(() => {
      expect(mockGetChatSettings).toHaveBeenCalled();
    });

    await user.click(screen.getByRole('button', { name: /save settings/i }));

    await waitFor(() => {
      expect(screen.getByText(/failed to save settings: forbidden/i)).toBeInTheDocument();
    });
  });

  it('shows "No tenant available" when user has no tenant', () => {
    vi.mocked(useAuth).mockReturnValue({
      ...createAuthMock('viewer'),
      user: { ...createAuthMock('viewer').user, tenant_id: '' },
    });
    renderWithProviders(<ChatSettings />);
    expect(screen.getByText(/no tenant available/i)).toBeInTheDocument();
  });

  it('disables save button while saving', async () => {
    const user = userEvent.setup();
    // Make updateChatSettings hang
    mockUpdateChatSettings.mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(defaultSettings), 500))
    );
    renderWithProviders(<ChatSettings />);
    await waitFor(() => {
      expect(mockGetChatSettings).toHaveBeenCalled();
    });

    await user.click(screen.getByRole('button', { name: /save settings/i }));
    expect(screen.getByText(/saving/i)).toBeInTheDocument();
  });

  it('updates budget when input changes', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ChatSettings />);
    await waitFor(() => {
      expect(mockGetChatSettings).toHaveBeenCalled();
    });

    const input = screen.getByLabelText(/daily token budget/i);
    await user.clear(input);
    await user.type(input, '50000');
    expect(input).toHaveValue(50000);
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    'persona: %s',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderWithProviders(<ChatSettings />);
        await waitFor(() => {
          expect(mockGetChatSettings).toHaveBeenCalled();
        });
        expect(screen.getByRole('heading', { name: /chat agent settings/i })).toBeInTheDocument();
      });
    }
  );
});
