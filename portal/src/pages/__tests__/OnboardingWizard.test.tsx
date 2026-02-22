/**
 * OnboardingWizard Tests (CAB-1306)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { renderWithProviders, createAuthMock } from '../../test/helpers';
import { OnboardingWizardPage } from '../onboarding';

// Mock hooks
const mockCreateApp = vi.fn();
const mockAPIsData = {
  items: [
    {
      id: 'api-1',
      name: 'Pet Store API',
      version: '1.0',
      description: 'Manage pet store inventory',
      tenantId: 't1',
      status: 'published' as const,
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
    },
    {
      id: 'api-2',
      name: 'Weather API',
      version: '2.0',
      description: 'Real-time weather data',
      tenantId: 't1',
      status: 'published' as const,
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
    },
  ],
  total: 2,
  page: 1,
  pageSize: 6,
  totalPages: 1,
};

vi.mock('../../hooks/useApplications', () => ({
  useCreateApplication: () => ({
    mutateAsync: mockCreateApp,
    isPending: false,
    error: null,
  }),
}));

vi.mock('../../hooks/useAPIs', () => ({
  useAPIs: () => ({
    data: mockAPIsData,
    isLoading: false,
  }),
}));

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => createAuthMock('cpi-admin'),
}));

vi.mock('../../i18n', () => ({
  loadNamespace: vi.fn(),
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string) => k,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
  Trans: ({ children }: { children: React.ReactNode }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}));

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

describe('OnboardingWizard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCreateApp.mockResolvedValue({
      id: 'app-1',
      name: 'my-app',
      clientId: 'client-123',
      clientSecret: 'secret-xyz',
      callbackUrls: [],
      userId: 'u1',
      status: 'active',
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
    });
  });

  it('renders step 1 — choose use case', () => {
    renderWithProviders(<OnboardingWizardPage />, { route: '/onboarding' });
    expect(screen.getByText('chooseUseCase.title')).toBeInTheDocument();
    expect(screen.getByText('chooseUseCase.mcpAgent')).toBeInTheDocument();
    expect(screen.getByText('chooseUseCase.restApi')).toBeInTheDocument();
    expect(screen.getByText('chooseUseCase.both')).toBeInTheDocument();
  });

  it('navigates to step 2 when use case selected', () => {
    renderWithProviders(<OnboardingWizardPage />, { route: '/onboarding' });
    fireEvent.click(screen.getByText('chooseUseCase.restApi'));
    expect(screen.getByText('createApp.title')).toBeInTheDocument();
  });

  it('creates app and moves to step 3', async () => {
    renderWithProviders(<OnboardingWizardPage />, { route: '/onboarding' });

    // Step 1 -> select use case
    fireEvent.click(screen.getByText('chooseUseCase.mcpAgent'));

    // Step 2 -> fill form
    const nameInput = screen.getByPlaceholderText('createApp.appNamePlaceholder');
    fireEvent.change(nameInput, { target: { value: 'Test App' } });
    fireEvent.click(screen.getByText('createApp.submit'));

    await waitFor(() => {
      expect(mockCreateApp).toHaveBeenCalledWith({
        name: 'test-app',
        description: '',
        callbackUrls: [],
      });
    });

    // Should be on step 3
    await waitFor(() => {
      expect(screen.getByText('subscribeApi.title')).toBeInTheDocument();
    });
  });

  it('shows API catalog in step 3', async () => {
    renderWithProviders(<OnboardingWizardPage />, { route: '/onboarding' });

    // Navigate to step 3
    fireEvent.click(screen.getByText('chooseUseCase.both'));
    const nameInput = screen.getByPlaceholderText('createApp.appNamePlaceholder');
    fireEvent.change(nameInput, { target: { value: 'Test App' } });
    fireEvent.click(screen.getByText('createApp.submit'));

    await waitFor(() => {
      expect(screen.getByText('Pet Store API')).toBeInTheDocument();
      expect(screen.getByText('Weather API')).toBeInTheDocument();
    });
  });

  it('allows skipping subscription step', async () => {
    renderWithProviders(<OnboardingWizardPage />, { route: '/onboarding' });

    fireEvent.click(screen.getByText('chooseUseCase.restApi'));
    const nameInput = screen.getByPlaceholderText('createApp.appNamePlaceholder');
    fireEvent.change(nameInput, { target: { value: 'Test App' } });
    fireEvent.click(screen.getByText('createApp.submit'));

    await waitFor(() => {
      expect(screen.getByText('subscribeApi.skip')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('subscribeApi.skip'));

    await waitFor(() => {
      expect(screen.getByText('firstCall.title')).toBeInTheDocument();
    });
  });

  it('shows credentials on final step', async () => {
    renderWithProviders(<OnboardingWizardPage />, { route: '/onboarding' });

    fireEvent.click(screen.getByText('chooseUseCase.restApi'));
    const nameInput = screen.getByPlaceholderText('createApp.appNamePlaceholder');
    fireEvent.change(nameInput, { target: { value: 'Test App' } });
    fireEvent.click(screen.getByText('createApp.submit'));

    await waitFor(() => screen.getByText('subscribeApi.skip'));
    fireEvent.click(screen.getByText('subscribeApi.skip'));

    await waitFor(() => {
      expect(screen.getByText('firstCall.credentials')).toBeInTheDocument();
      expect(screen.getByText('client-123')).toBeInTheDocument();
      expect(screen.getByText('secret-xyz')).toBeInTheDocument();
    });
  });

  it('navigates to dashboard on finish', async () => {
    renderWithProviders(<OnboardingWizardPage />, { route: '/onboarding' });

    fireEvent.click(screen.getByText('chooseUseCase.restApi'));
    const nameInput = screen.getByPlaceholderText('createApp.appNamePlaceholder');
    fireEvent.change(nameInput, { target: { value: 'Test App' } });
    fireEvent.click(screen.getByText('createApp.submit'));

    await waitFor(() => screen.getByText('subscribeApi.skip'));
    fireEvent.click(screen.getByText('subscribeApi.skip'));

    await waitFor(() => screen.getByText('firstCall.goToDashboard'));
    fireEvent.click(screen.getByText('firstCall.goToDashboard'));

    expect(mockNavigate).toHaveBeenCalledWith('/');
  });

  it('shows back button on step 2', () => {
    renderWithProviders(<OnboardingWizardPage />, { route: '/onboarding' });
    fireEvent.click(screen.getByText('chooseUseCase.mcpAgent'));
    expect(screen.getByText('createApp.back')).toBeInTheDocument();
    fireEvent.click(screen.getByText('createApp.back'));
    expect(screen.getByText('chooseUseCase.title')).toBeInTheDocument();
  });

  it('shows MCP config for mcp-agent use case', async () => {
    renderWithProviders(<OnboardingWizardPage />, { route: '/onboarding' });

    fireEvent.click(screen.getByText('chooseUseCase.mcpAgent'));
    const nameInput = screen.getByPlaceholderText('createApp.appNamePlaceholder');
    fireEvent.change(nameInput, { target: { value: 'Test App' } });
    fireEvent.click(screen.getByText('createApp.submit'));

    await waitFor(() => screen.getByText('subscribeApi.skip'));
    fireEvent.click(screen.getByText('subscribeApi.skip'));

    await waitFor(() => {
      expect(screen.getByText('firstCall.mcpConfig')).toBeInTheDocument();
    });
  });
});
