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

vi.mock('../../i18n', () => ({}));
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
    expect(screen.getByText('How will you use STOA?')).toBeInTheDocument();
    expect(screen.getByText('MCP Agent')).toBeInTheDocument();
    expect(screen.getByText('REST API')).toBeInTheDocument();
    expect(screen.getByText('Both')).toBeInTheDocument();
  });

  it('navigates to step 2 when use case selected', () => {
    renderWithProviders(<OnboardingWizardPage />, { route: '/onboarding' });
    fireEvent.click(screen.getByText('REST API'));
    expect(screen.getByText('Create your application')).toBeInTheDocument();
  });

  it('creates app and moves to step 3', async () => {
    renderWithProviders(<OnboardingWizardPage />, { route: '/onboarding' });

    // Step 1 -> select use case
    fireEvent.click(screen.getByText('MCP Agent'));

    // Step 2 -> fill form
    const nameInput = screen.getByPlaceholderText('My Integration');
    fireEvent.change(nameInput, { target: { value: 'Test App' } });
    fireEvent.click(screen.getByText('Create Application'));

    await waitFor(() => {
      expect(mockCreateApp).toHaveBeenCalledWith({
        name: 'test-app',
        description: '',
        callbackUrls: [],
      });
    });

    // Should be on step 3
    await waitFor(() => {
      expect(screen.getByText('Subscribe to an API')).toBeInTheDocument();
    });
  });

  it('shows API catalog in step 3', async () => {
    renderWithProviders(<OnboardingWizardPage />, { route: '/onboarding' });

    // Navigate to step 3
    fireEvent.click(screen.getByText('Both'));
    const nameInput = screen.getByPlaceholderText('My Integration');
    fireEvent.change(nameInput, { target: { value: 'Test App' } });
    fireEvent.click(screen.getByText('Create Application'));

    await waitFor(() => {
      expect(screen.getByText('Pet Store API')).toBeInTheDocument();
      expect(screen.getByText('Weather API')).toBeInTheDocument();
    });
  });

  it('allows skipping subscription step', async () => {
    renderWithProviders(<OnboardingWizardPage />, { route: '/onboarding' });

    fireEvent.click(screen.getByText('REST API'));
    const nameInput = screen.getByPlaceholderText('My Integration');
    fireEvent.change(nameInput, { target: { value: 'Test App' } });
    fireEvent.click(screen.getByText('Create Application'));

    await waitFor(() => {
      expect(screen.getByText('Skip for now')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Skip for now'));

    await waitFor(() => {
      expect(screen.getByText("You're all set!")).toBeInTheDocument();
    });
  });

  it('shows credentials on final step', async () => {
    renderWithProviders(<OnboardingWizardPage />, { route: '/onboarding' });

    fireEvent.click(screen.getByText('REST API'));
    const nameInput = screen.getByPlaceholderText('My Integration');
    fireEvent.change(nameInput, { target: { value: 'Test App' } });
    fireEvent.click(screen.getByText('Create Application'));

    await waitFor(() => screen.getByText('Skip for now'));
    fireEvent.click(screen.getByText('Skip for now'));

    await waitFor(() => {
      expect(screen.getByText('Application Credentials')).toBeInTheDocument();
      expect(screen.getByText('client-123')).toBeInTheDocument();
      expect(screen.getByText('secret-xyz')).toBeInTheDocument();
    });
  });

  it('navigates to dashboard on finish', async () => {
    renderWithProviders(<OnboardingWizardPage />, { route: '/onboarding' });

    fireEvent.click(screen.getByText('REST API'));
    const nameInput = screen.getByPlaceholderText('My Integration');
    fireEvent.change(nameInput, { target: { value: 'Test App' } });
    fireEvent.click(screen.getByText('Create Application'));

    await waitFor(() => screen.getByText('Skip for now'));
    fireEvent.click(screen.getByText('Skip for now'));

    await waitFor(() => screen.getByText('Go to Dashboard'));
    fireEvent.click(screen.getByText('Go to Dashboard'));

    expect(mockNavigate).toHaveBeenCalledWith('/');
  });

  it('shows back button on step 2', () => {
    renderWithProviders(<OnboardingWizardPage />, { route: '/onboarding' });
    fireEvent.click(screen.getByText('MCP Agent'));
    expect(screen.getByText('Back')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Back'));
    expect(screen.getByText('How will you use STOA?')).toBeInTheDocument();
  });

  it('shows MCP config for mcp-agent use case', async () => {
    renderWithProviders(<OnboardingWizardPage />, { route: '/onboarding' });

    fireEvent.click(screen.getByText('MCP Agent'));
    const nameInput = screen.getByPlaceholderText('My Integration');
    fireEvent.change(nameInput, { target: { value: 'Test App' } });
    fireEvent.click(screen.getByText('Create Application'));

    await waitFor(() => screen.getByText('Skip for now'));
    fireEvent.click(screen.getByText('Skip for now'));

    await waitFor(() => {
      expect(screen.getByText('MCP Configuration')).toBeInTheDocument();
    });
  });
});
